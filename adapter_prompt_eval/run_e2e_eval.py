"""독립 테스트셋(test_set/eval_final) TTS end-to-end 평가 — EM / EX / Syntactic Validity / 응답시간.

run_final_eval.py(모델 단독)와 다른 점
  - 테스트셋의 input(직접 만든 재료)은 쓰지 않는다. 자연어 질의(text)만 TTS POST /nl2sql 에 보내
    질의 분석 → Schema RAG → Concept RAG → SQL 생성 → 검증·실행 → Self-Repair 전체를 거친 SQL을 받는다.
  - 채점은 정답 SQL(query)과 샌드박스 DB로 한다(문법·EXPLAIN·EM·EX 함수는 scripts/eval_api_model.py 그대로).
  - rag 단계(선택): 같은 질의로 POST /rag 를 불러 개념 후보를 남긴다. 정답 앵커가 RAG 후보에 있었는지로
    "RAG가 못 찾음 / 찾았는데 다른 개념을 고름"을 나눈다. /nl2sql 내부 RAG와 따로 부르는 것이라
    (trans=true 번역 단계 등) 후보가 드물게 다를 수 있다.

요청 본문: {"query": text, "top_k": 5, "trans": true}  (+ ?page_size=1, 결과 행은 채점에 쓰지 않음)
API 키는 환경변수 TTS_API_KEY 로만 받는다(파일에 남기지 않음). 서버 주소는 TTS_URL (기본 http://10.1.1.106:8080).

정답 SQL의 CURRENT_DATE 와 TTS 기준일(요청한 날)이 같아야 EX가 성립하므로, 생성한 날과 채점하는 날
(DB current_date)이 다르면 채점을 시작하지 않는다(--allow-date-mismatch 로 무시).

    TTS_API_KEY=... python3 run_e2e_eval.py generate [--limit 5] [--delay 1]
    TTS_API_KEY=... python3 run_e2e_eval.py rag      [--limit 5]       # 선택
    python3 run_e2e_eval.py score [--limit 5]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import statistics
import sys
import time
from collections import Counter

import requests

import run_final_eval as fe
from run_final_eval import base, sql_concept_ids, subset_summary, SLOW_GOLD_IDS

OUT_DIR = fe.ROOT / "results/adapter_eval/e2e"
TTS_URL = os.environ.get("TTS_URL", "http://10.1.1.106:8080").rstrip("/")
KEEP = ("sql", "success", "status", "error", "error_kind", "retry_count", "repair_history", "warnings", "concepts")


def _headers() -> dict:
    key = os.environ.get("TTS_API_KEY")
    if not key:
        raise SystemExit("TTS_API_KEY 환경변수가 필요합니다.")
    return {"Content-Type": "application/json", "X-API-Key": key}


def _done(path) -> set:
    return {json.loads(l)["id"] for l in open(path, encoding="utf-8")} if path.exists() else set()


def _call(endpoint: str, args, path, keep) -> None:
    """질의마다 TTS를 순차 호출해 path(jsonl)에 이어 쓴다. 이미 받은 id는 건너뛴다(재실행 안전).

    200·422(개념 못 찾음 등)·504(요청 시간 초과)는 '질의 자체'의 결과라 저장하고,
    네트워크 오류·그 밖의 5xx는 3번까지 다시 시도한 뒤 저장하지 않는다(다시 실행하면 이어서 시도)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    headers = _headers()
    done = _done(path)
    cases = [c for c in fe.load_cases(args.limit) if c["id"] not in done]
    print(f"{TTS_URL}{endpoint} / top_k {args.top_k} / trans {not args.no_trans} / 남은 {len(cases)}건 (완료 {len(done)}건)")
    body_base = {"top_k": args.top_k, "trans": not args.no_trans}
    with open(path, "a", encoding="utf-8") as out:
        for i, c in enumerate(cases, 1):
            body = {"query": c["text"], **body_base}
            rec, error = None, None
            for attempt in range(1, 4):
                start = time.perf_counter()
                try:
                    r = requests.post(f"{TTS_URL}{endpoint}", params={"page_size": 1} if endpoint == "/nl2sql" else None,
                                      json=body, headers=headers, timeout=args.timeout)
                    elapsed = time.perf_counter() - start
                    if r.status_code in (401, 403):
                        raise SystemExit(f"인증 실패 {r.status_code}: {r.text[:200]} — TTS_API_KEY·TTS_URL({TTS_URL}) 확인")
                    if r.status_code in (200, 422, 504):
                        d = r.json()
                        d = d.get("detail", d) if isinstance(d.get("detail"), dict) else d
                        rec = {"id": c["id"], "http_status": r.status_code, "elapsed": round(elapsed, 3),
                               "attempts": attempt, "requested_at": dt.datetime.now().isoformat(timespec="seconds"),
                               "request": body, **{k: d.get(k) for k in keep}}
                        break
                    error = f"{r.status_code}: {r.text[:300]}"
                except requests.RequestException as exc:
                    error = str(exc)
                time.sleep(5)
            if rec is None:
                print(f"[{i}/{len(cases)}] {c['id']} 실패(저장 안 함): {error}")
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i}/{len(cases)}] {c['id']} {rec['http_status']} {rec['elapsed']:.1f}s "
                  f"status={rec.get('status')} retry={rec.get('retry_count')} {rec.get('error_kind') or ''}")
            time.sleep(args.delay)


def generate(args) -> None:
    _call("/nl2sql", args, OUT_DIR / "responses.jsonl", KEEP)


def rag(args) -> None:
    _call("/rag", args, OUT_DIR / "rag.jsonl", ("success", "status", "error", "error_kind", "concepts", "warnings"))


# ── 채점 ───────────────────────────────────────────────────

def _rag_ids(rec: dict | None) -> tuple[set[int], dict[int, str]]:
    """RAG 개념 후보 id 전체와 id→표면어."""
    ids, surf = set(), {}
    for s in (rec or {}).get("concepts") or []:
        for cand in s.get("candidates") or []:
            if cand.get("concept_id") is not None:
                ids.add(cand["concept_id"])
                surf.setdefault(cand["concept_id"], s.get("surface"))
    return ids, surf


def concept_cause(gold: set[int], used: set[int], rag_ids: set[int] | None) -> str:
    if not gold and not used:
        return "N/A"
    if used == gold:
        return "일치"
    missed = gold - used
    if rag_ids is None:
        return "불일치"
    if missed and not (missed & rag_ids):
        return "RAG 후보에 정답 없음"
    if missed and not missed <= rag_ids:
        return "일부 정답이 RAG 후보에 없음"
    if missed:
        return "RAG 후보에 있는데 다른 개념/누락"
    return "정답 외 개념 추가"


def score(args) -> None:
    cases = fe.load_cases(args.limit)
    resp = {r["id"]: r for r in base.load_jsonl(str(OUT_DIR / "responses.jsonl"))}
    rag_path = OUT_DIR / "rag.jsonl"
    rags = {r["id"]: r for r in base.load_jsonl(str(rag_path))} if rag_path.exists() else {}
    missing = [c["id"] for c in cases if c["id"] not in resp]
    if missing:
        print(f"[경고] 응답 없는 문항 {len(missing)}건: {missing[:10]}")
    pool = base.SandboxConnectionPool()
    conn = pool.get()
    if conn is None:
        raise SystemExit("[오류] 샌드박스 DB에 연결할 수 없습니다 (.env의 SANDBOX_DB_* 확인).")
    db_date = str(conn.execute("select current_date").fetchone()[0])
    gen_dates = Counter(r["requested_at"][:10] for r in resp.values())
    if set(gen_dates) != {db_date} and not args.allow_date_mismatch:
        raise SystemExit(f"[오류] 생성일 {dict(gen_dates)} ≠ DB current_date {db_date}: CURRENT_DATE 정답의 EX가 어긋납니다.")

    rows = []
    for i, c in enumerate(cases, 1):
        if c["id"] not in resp:
            continue
        r, gold = resp[c["id"]], c["query"]
        sql = (r.get("sql") or "").strip()
        is_sql = bool(sql)
        fail_note = f"TTS 실패: {r.get('error_kind') or ''} {(r.get('error') or '')[:200]}".strip()
        syn_ok, syn_err = base.check_syntax(sql) if is_sql else (False, fail_note)
        sb, sb_err = base.check_sandbox_validity(pool.get(), sql) if is_sql else ("fail", fail_note)
        limit_ms = 120000 if c["id"] in SLOW_GOLD_IDS else int(os.environ.get("SANDBOX_DB_TIMEOUT", "30000"))
        pool.get().execute(f"SET statement_timeout = {limit_ms}")
        ex, ex_note = base.check_ex(pool.get(), sql, gold) if is_sql else ("fail", fail_note)

        rag_ids, rag_surf = _rag_ids(rags.get(c["id"])) if c["id"] in rags else (None, {})
        chosen = {x["concept_id"] for x in r.get("concepts") or [] if x.get("concept_id") is not None}
        known = chosen | set(c["anchor_concept_ids"]) | (rag_ids or set())
        used = sql_concept_ids(sql, known)["used"] if is_sql else set()
        gold_ids = sql_concept_ids(gold, known)["used"] | set(c["anchor_concept_ids"])
        anchors = set(c["anchor_concept_ids"])
        rows.append({
            "id": c["id"], "시나리오": c["scenario_name"], "섹션": c["section"], "항목": c["item"],
            "질의유형": c["query_type"], "난이도": c["difficulty"], "플래그": "|".join(c["eval_flags"]),
            "자연어 질의": c["text"], "TTS SQL": sql, "정답 SQL": gold,
            "TTS 상태": r.get("status"), "TTS 실패 유형": r.get("error_kind") or "",
            "self-repair 횟수": r.get("retry_count") or 0, "HTTP": r["http_status"],
            "경고": "|".join(w.get("code", "") for w in r.get("warnings") or []),
            "문법 결과": "pass" if syn_ok else "fail", "문법 에러": "" if syn_ok else syn_err,
            "실행검증 결과": sb, "실행검증 에러": sb_err,
            "EM 결과": base.check_em(sql, gold) if is_sql else "fail", "EX 결과": ex, "EX 참고": ex_note,
            "응답시간(초)": r["elapsed"],
            "정답 concept_id": sorted(gold_ids), "TTS concept_id": sorted(used),
            "놓친 concept_id": sorted(gold_ids - used), "정답 밖 concept_id": sorted(used - gold_ids),
            "RAG 후보에 있는 앵커": "" if rag_ids is None else f"{len(anchors & rag_ids)}/{len(anchors)}",
            "RAG 후보에 없는 앵커": "" if rag_ids is None else sorted(anchors - rag_ids),
            "concept 판정": "N/A" if not gold_ids and not used else "pass" if used == gold_ids else "fail",
            "concept 원인": concept_cause(gold_ids, used, rag_ids),
        })
        print(f"[{i}/{len(cases)}] {c['id']} 문법={rows[-1]['문법 결과']} 실행={sb} EM={rows[-1]['EM 결과']} "
              f"EX={ex} concept={rows[-1]['concept 원인']}")
    pool.close_all()

    suffix = f"_limit{args.limit}" if args.limit else ""
    with open(OUT_DIR / f"e2e_items{suffix}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    flag = lambda r, f: f in r["플래그"].split("|")  # noqa: E731
    lat = sorted(r["응답시간(초)"] for r in rows)
    anchor_total = sum(len(c["anchor_concept_ids"]) for c in cases if c["id"] in rags)
    anchor_hit = sum(len(set(c["anchor_concept_ids"]) & _rag_ids(rags[c["id"]])[0]) for c in cases if c["id"] in rags)
    summary = {
        "tts_url": TTS_URL, "db_current_date": db_date, "생성일": gen_dates, "응답 없음": len(missing),
        "전체": subset_summary(rows),
        "EX 판단용(나이 조건·빈 결과 제외)": subset_summary(
            [r for r in rows if not flag(r, "age_condition") and not flag(r, "empty_result")]),
        "나이 조건 제외": subset_summary([r for r in rows if not flag(r, "age_condition")]),
        **{f"플래그:{f}": subset_summary([r for r in rows if flag(r, f)])
           for f in ("age_condition", "current_date", "empty_result", "parent_tag")},
        **{f"난이도:{d}": subset_summary([r for r in rows if r["난이도"] == d]) for d in ("EASY", "MEDIUM", "HARD")},
        **{f"질의유형:{q}": subset_summary([r for r in rows if r["질의유형"] == q])
           for q in sorted({r["질의유형"] for r in rows})},
        **{f"섹션:{s}": subset_summary([r for r in rows if r["섹션"] == s]) for s in sorted({r["섹션"] for r in rows})},
        "응답시간(초)": {"평균": round(statistics.mean(lat), 2), "중앙값": round(statistics.median(lat), 2),
                     "p95": lat[int(len(lat) * 0.95)], "최대": lat[-1]},
        "TTS 상태": Counter(r["TTS 상태"] for r in rows),
        "TTS 실패 유형": Counter(r["TTS 실패 유형"] for r in rows if r["TTS 실패 유형"]),
        "self-repair 횟수": Counter(r["self-repair 횟수"] for r in rows),
        "concept 원인": Counter(r["concept 원인"] for r in rows),
        "RAG 앵커 포함률": fe._pct(anchor_hit, anchor_total) if rags else None,
        "모델 SQL 시간 초과": [r["id"] for r in rows if "statement timeout" in r["EX 참고"]],
        "EX ERROR(정답 실행 실패)": [r["id"] for r in rows if r["EX 결과"] == "ERROR"],
    }
    (OUT_DIR / f"e2e_summary{suffix}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["generate", "rag", "score"])
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--no-trans", action="store_true", help="trans=false 로 요청 (기본 true)")
    p.add_argument("--delay", type=float, default=1.0, help="요청 사이 쉬는 초")
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--allow-date-mismatch", action="store_true")
    args = p.parse_args()
    {"generate": generate, "rag": rag, "score": score}[args.cmd](args)


if __name__ == "__main__":
    main()
