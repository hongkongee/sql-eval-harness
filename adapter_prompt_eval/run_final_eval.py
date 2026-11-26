"""독립 테스트셋(test_set/eval_final) 최종 평가 — EM / EX / Syntactic Validity / 응답시간
+ 재료의 concept_id 후보 중 모델이 무엇을 골랐는지 기록.

run_eval.py와 다른 점
  - 재료가 "개념 후보"(표면어마다 여러 concept_id) 형식이라 adherence.parse_anchors
    ("용어" → table.column IN (...))로는 읽히지 않는다. 후보를 직접 파싱해 표면어별로
    모델 선택과 정답을 대조한다.
  - 생성(generate)과 채점(score)을 나눈다. 응답 원문을 responses.jsonl에 남기고 채점만
    다시 돌릴 수 있다. 생성은 순차(동시 요청 1)라 응답시간에 DB 부하가 섞이지 않는다.
  - max_tokens 4096 (정답 SQL이 최대 1,866토큰이라 기존 512로는 잘린다). finish_reason도 남긴다.

채점 함수(문법 / EXPLAIN / EM / EX, 정답 결과 캐시)는 scripts/eval_api_model.py 것을 그대로 쓴다.

정답 SQL의 CURRENT_DATE와 재료의 기준일(DATE '2026-11-25')이 같은 날이어야 EX가 성립하므로
재료의 기준일과 DB의 current_date가 다르면 채점을 시작하지 않는다(--allow-date-mismatch로 무시).

    python3 run_final_eval.py generate [--limit 5]
    python3 run_final_eval.py score
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import requests
import sqlglot
from sqlglot import exp

import adherence as ad

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import eval_api_model as base  # noqa: E402

TESTSET = ROOT / "test_set/eval_final/repaired.jsonl"
SYSTEM_PROMPT_FILE = ROOT / "results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt"
OUT_DIR = ROOT / "results/adapter_eval/final"
# 정답 SQL이 30초를 넘기는 문항(34~65초). 이 문항만 정답·모델 SQL 모두 120초까지 기다린다.
SLOW_GOLD_IDS = {"24", "68", "126", "130", "216", "224", "300", "313", "385", "513", "530"}
_ENUM_LINE = re.compile(r"허용값:\s*(.+)$")
_SURFACE_LINE = re.compile(r'^  - "(.*)":')
_CAND_LINE = re.compile(r"^\s+·\s+(\d+)\s+(.*)\[([^\[\]]+?) → (\w+)\.(\w+)\](.*)$")
_INT = re.compile(r"(?<![\w.])\d{3,}(?![\w.])")


# ── 재료 파싱 ──────────────────────────────────────────────

def parse_material(material: str) -> dict:
    """{surfaces: [{surface, cands: [{id, name, table, column, parent}]}], enums: {id}}"""
    surfaces, enums, section = [], set(), None
    for line in material.splitlines():
        if line and not line.startswith(" "):
            section = line.split(" (")[0].rstrip(":")
            continue
        if section == "개념 후보":
            m = _SURFACE_LINE.match(line)
            if m:
                surfaces.append({"surface": m.group(1), "cands": []})
                continue
            m = _CAND_LINE.match(line)
            if m and surfaces:
                surfaces[-1]["cands"].append({
                    "id": int(m.group(1)), "name": m.group(2).strip(),
                    "table": m.group(4), "column": m.group(5), "parent": "상위개념" in m.group(6),
                })
        else:
            m = _ENUM_LINE.search(line)
            if m:
                enums.update(int(x) for x in re.findall(r"(\d+)=", m.group(1)))
    return {"surfaces": surfaces, "enums": enums}


# ── SQL이 쓴 concept_id ────────────────────────────────────

def _int_literals(node: exp.Expression) -> list[int]:
    return [int(l.this) for l in node.find_all(exp.Literal) if not l.is_string and str(l.this).isdigit()]


def sql_concept_ids(sql: str, known: set[int]) -> dict:
    """SQL이 쓴 concept_id와, 그중 concept_ancestor 전개 형태로 쓴 것.

    *_concept_id 컬럼과 비교(=, IN)되는 정수를 모으고, VALUES·CASE 등 다른 자리에 쓴 경우를
    놓치지 않게 재료에 있는 id가 SQL에 나타나면 함께 넣는다."""
    used, expanded = set(), set()
    text_ids = {int(x) for x in _INT.findall(sql)} & known
    try:
        tree = sqlglot.parse_one(base.PLACEHOLDER_RE.sub("0", sql), read="postgres")
        for node in tree.find_all(exp.EQ, exp.In, exp.NEQ):
            sides = [node.this] + ([node.expression] if not isinstance(node, exp.In) else [])
            col = next((s for s in sides if isinstance(s, exp.Column) and s.name.lower().endswith("concept_id")), None)
            if col is None:
                continue
            vals = [v for e in node.expressions for v in _int_literals(e)] if isinstance(node, exp.In) else [
                v for s in sides if s is not col and isinstance(s, exp.Literal) for v in _int_literals(s)]
            vals = [v for v in vals if v != 0]
            used.update(vals)
            if col.name.lower() == "ancestor_concept_id":
                expanded.update(vals)
    except Exception:  # noqa: BLE001 - 파싱 실패 SQL은 본문에 나온 재료 id만 센다
        pass
    return {"used": used | text_ids, "expanded": expanded}


def concept_record(sql: str, gold_sql: str, anchors: list[int], material: dict) -> tuple[dict, list[dict]]:
    cand_ids = {c["id"] for s in material["surfaces"] for c in s["cands"]}
    known = cand_ids | material["enums"]
    pred = sql_concept_ids(sql, known)
    gold = sql_concept_ids(gold_sql, known)["used"] | set(anchors)
    used = pred["used"]
    surf_rows = []
    for s in material["surfaces"]:
        ids = {c["id"] for c in s["cands"]}
        g, p = ids & gold, ids & used
        if g:
            verdict = ("정답 선택" if p == g else "정답+다른 후보" if p > g else
                       "일부만 선택" if p and p < g else "다른 후보 선택" if p and not (p & g) else
                       "일부+다른 후보" if p else "선택 안 함")
        else:
            verdict = "정답도 미사용·모델도 미사용" if not p else "정답은 미사용인데 선택"
        if not p and f"{{{{{s['surface']}}}}}" in sql:
            verdict = "미해결({{}})로 남김" + ("" if g else " (정답도 미사용)")
        surf_rows.append({
            "표면어": s["surface"], "후보 수": len(s["cands"]),
            "모델 선택": sorted(p), "정답": sorted(g), "판정": verdict,
            "모델 선택 이름": [c["name"] for c in s["cands"] if c["id"] in p],
            "정답 이름": [c["name"] for c in s["cands"] if c["id"] in g],
        })
    row = {
        "정답 concept_id": sorted(gold), "모델 concept_id": sorted(used),
        "놓친 concept_id": sorted(gold - used), "정답 밖 concept_id": sorted(used - gold),
        "재료에 없는 concept_id": sorted(used - known - gold),
        "하위전개 concept_id": sorted(pred["expanded"] & cand_ids),
        "concept 판정": "N/A" if not gold and not used else "pass" if used == gold else "fail",
    }
    return row, surf_rows


# ── 생성 ───────────────────────────────────────────────────

def load_cases(limit: int | None) -> list[dict]:
    cases = base.load_jsonl(str(TESTSET))
    return cases[:limit] if limit else cases


def generate(args) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    url, model = os.environ["LLM_API_URL"], os.environ["LLM_MODEL_NAME"]
    system = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()
    path = OUT_DIR / "responses.jsonl"
    done = {json.loads(l)["id"] for l in open(path, encoding="utf-8")} if path.exists() else set()
    cases = [c for c in load_cases(args.limit) if c["id"] not in done]
    print(f"{url} / {model} / max_tokens {args.max_tokens} / 남은 {len(cases)}건 (완료 {len(done)}건)")
    with open(path, "a", encoding="utf-8") as out:
        for i, c in enumerate(cases, 1):
            body = {
                "model": model, "temperature": 0, "max_tokens": args.max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": ad.build_prompt(c)}],
            }
            rec, error = {"id": c["id"]}, None
            for attempt in range(1, 4):
                start = time.perf_counter()
                try:
                    r = requests.post(url, json=body, timeout=args.timeout)
                    elapsed = time.perf_counter() - start
                    if r.ok:
                        d = r.json()
                        rec.update(content=d["choices"][0]["message"]["content"], elapsed=elapsed,
                                   finish_reason=d["choices"][0]["finish_reason"],
                                   prompt_tokens=d["usage"]["prompt_tokens"],
                                   completion_tokens=d["usage"]["completion_tokens"], attempts=attempt)
                        error = None
                        break
                    error = f"{r.status_code}: {r.text[:300]}"
                except requests.RequestException as exc:
                    error = str(exc)
                time.sleep(5)
            if error:  # 실패는 저장하지 않아 다시 실행하면 이어서 시도된다
                print(f"[{i}/{len(cases)}] {c['id']} API 실패: {error}")
                continue
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            print(f"[{i}/{len(cases)}] {c['id']} {rec['elapsed']:.2f}s {rec['completion_tokens']}tok {rec['finish_reason']}")


# ── 채점 ───────────────────────────────────────────────────

def _pct(n: int, d: int) -> dict:
    return {"n": n, "total": d, "rate": round(n / d, 4) if d else None}


def subset_summary(rows: list[dict]) -> dict:
    n = len(rows)
    c = lambda k: sum(r[k] == "pass" for r in rows)  # noqa: E731
    ex_ok = [r for r in rows if r["EX 결과"] != "ERROR"]
    return {
        "n": n, "syntax(sqlglot)": _pct(c("문법 결과"), n), "syntax(EXPLAIN)": _pct(c("실행검증 결과"), n),
        "EM": _pct(c("EM 결과"), n), "EX": _pct(c("EX 결과"), n),
        "EX(정답 실행 실패 제외)": _pct(c("EX 결과"), len(ex_ok)),
        "concept": _pct(sum(r["concept 판정"] == "pass" for r in rows),
                        sum(r["concept 판정"] != "N/A" for r in rows)),
    }


def score(args) -> None:
    cases = load_cases(args.limit)
    resp = {r["id"]: r for r in base.load_jsonl(str(OUT_DIR / "responses.jsonl"))}
    missing = [c["id"] for c in cases if c["id"] not in resp]
    if missing:
        print(f"[경고] 응답 없는 문항 {len(missing)}건: {missing[:10]}")
    pool = base.SandboxConnectionPool()
    conn = pool.get()
    if conn is None:
        raise SystemExit("[오류] 샌드박스 DB에 연결할 수 없습니다 (../.env의 SANDBOX_DB_* 확인).")
    db_date = str(conn.execute("select current_date").fetchone()[0])
    as_of = Counter(m.group(1) for c in cases if (m := re.search(r"기준일: DATE '([\d-]+)'", c["input"])))
    if set(as_of) != {db_date} and not args.allow_date_mismatch:
        raise SystemExit(f"[오류] 재료 기준일 {dict(as_of)} ≠ DB current_date {db_date}: CURRENT_DATE 정답의 EX가 어긋납니다.")

    rows, surface_rows = [], []
    for i, c in enumerate(cases, 1):
        if c["id"] not in resp:
            continue
        r, gold = resp[c["id"]], c["query"]
        sql, is_sql = base.extract_sql(r["content"])
        syn_ok, syn_err = base.check_syntax(sql) if is_sql else (False, "SQL이 아닌 응답")
        sb, sb_err = base.check_sandbox_validity(pool.get(), sql) if is_sql else ("fail", "SQL이 아닌 응답")
        limit_ms = 120000 if c["id"] in SLOW_GOLD_IDS else int(os.environ.get("SANDBOX_DB_TIMEOUT", "30000"))
        pool.get().execute(f"SET statement_timeout = {limit_ms}")
        ex, ex_note = base.check_ex(pool.get(), sql, gold) if is_sql else ("fail", "SQL이 아닌 응답")
        material = parse_material(c["input"])
        crow, srows = concept_record(sql, gold, c["anchor_concept_ids"], material)
        rows.append({
            "id": c["id"], "시나리오": c["scenario_name"], "섹션": c["section"], "항목": c["item"],
            "질의유형": c["query_type"], "난이도": c["difficulty"], "플래그": "|".join(c["eval_flags"]),
            "재료 수정": "|".join(sorted({x["type"] for x in c["input_repairs"]})),
            "자연어 질의": c["text"], "모델 SQL": sql, "정답 SQL": gold,
            "문법 결과": "pass" if syn_ok else "fail", "문법 에러": "" if syn_ok else syn_err,
            "실행검증 결과": sb, "실행검증 에러": sb_err,
            "EM 결과": base.check_em(sql, gold), "EX 결과": ex, "EX 참고": ex_note,
            "응답시간(초)": round(r["elapsed"], 3), "출력 토큰": r["completion_tokens"],
            "입력 토큰": r["prompt_tokens"], "종료": r["finish_reason"],
            "플레이스홀더": "|".join(base.PLACEHOLDER_RE.findall(sql)), **crow,
        })
        surface_rows += [{"id": c["id"], **s} for s in srows]
        print(f"[{i}/{len(cases)}] {c['id']} 문법={rows[-1]['문법 결과']} 실행={sb} EM={rows[-1]['EM 결과']} EX={ex} concept={crow['concept 판정']}")
    pool.close_all()

    suffix = f"_limit{args.limit}" if args.limit else ""
    for name, data in (("items", rows), ("concept_choices", surface_rows)):
        with open(OUT_DIR / f"final_{name}{suffix}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)

    flag = lambda r, f: f in r["플래그"].split("|")  # noqa: E731
    lat = sorted(r["응답시간(초)"] for r in rows)
    summary = {
        "model": os.environ["LLM_MODEL_NAME"], "db_current_date": db_date, "응답 없음": len(missing),
        "전체": subset_summary(rows),
        "EX 판단용(나이 조건·빈 결과 제외)": subset_summary(
            [r for r in rows if not flag(r, "age_condition") and not flag(r, "empty_result")]),
        "나이 조건 제외": subset_summary([r for r in rows if not flag(r, "age_condition")]),
        "플래그 없음": subset_summary([r for r in rows if not r["플래그"]]),
        **{f"플래그:{f}": subset_summary([r for r in rows if flag(r, f)])
           for f in ("age_condition", "current_date", "empty_result", "parent_tag")},
        **{f"난이도:{d}": subset_summary([r for r in rows if r["난이도"] == d]) for d in ("EASY", "MEDIUM", "HARD")},
        **{f"질의유형:{q}": subset_summary([r for r in rows if r["질의유형"] == q])
           for q in sorted({r["질의유형"] for r in rows})},
        **{f"섹션:{s}": subset_summary([r for r in rows if r["섹션"] == s]) for s in sorted({r["섹션"] for r in rows})},
        "응답시간(초)": {"평균": round(statistics.mean(lat), 2), "중앙값": round(statistics.median(lat), 2),
                     "p95": lat[int(len(lat) * 0.95)], "최대": lat[-1],
                     "평균(첫 요청 제외)": round(statistics.mean([r["응답시간(초)"] for r in rows][1:]), 2)},
        "종료 사유": Counter(r["종료"] for r in rows),
        "출력 512토큰 초과": sum(r["출력 토큰"] > 512 for r in rows),
        "플레이스홀더 남긴 문항": sum(bool(r["플레이스홀더"]) for r in rows),
        "재료에 없는 concept_id 쓴 문항": sum(bool(r["재료에 없는 concept_id"]) for r in rows),
        "표면어 판정": Counter(s["판정"] for s in surface_rows),
        "모델 SQL 시간 초과": [r["id"] for r in rows if "statement timeout" in r["EX 참고"]],
        "EX ERROR(정답 실행 실패)": [r["id"] for r in rows if r["EX 결과"] == "ERROR"],
    }
    (OUT_DIR / f"final_summary{suffix}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["generate", "score"])
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--allow-date-mismatch", action="store_true")
    args = p.parse_args()
    (generate if args.cmd == "generate" else score)(args)


if __name__ == "__main__":
    main()
