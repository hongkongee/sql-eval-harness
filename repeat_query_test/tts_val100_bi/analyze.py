"""3단계: responses.jsonl → summary.json + report.md

- 질의마다 서로 다른 SQL(답) 개수. 기준 답 A = 1회차 답.
- alone(서버에서 혼자 처리된 요청)만 놓고 본 서로 다른 답 개수도 따로 센다.
- 갈린 질의는 답마다 샌드박스 DB 에서 실행해 행 수·결과 해시를 비교하고(결과가 같은지),
  정답 SQL 이 있으면(testset) 정답과 결과가 같은지(EX)도 본다.
실행: python3 analyze.py [--no-exec]
"""
import argparse, collections, difflib, hashlib, json, re, sys
from common import ROOT, HARNESS, REQUESTS, RESPONSES, read_jsonl

TOK = re.compile(r"\w+|'[^']*'|[^\w\s]")


def first_diff(a, b, ctx=4):
    x, y = TOK.findall(a), TOK.findall(b)
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
        if op != "equal":
            return f"…{' '.join(x[max(0, i1 - ctx):i2 + ctx])}…  →  …{' '.join(y[max(0, j1 - ctx):j2 + ctx])}…"
    return "(토큰 동일, 공백만 다름)"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-exec", action="store_true"); a = ap.parse_args()
    reqs = json.load(open(REQUESTS, encoding="utf-8"))
    rows = [r for r in read_jsonl(RESPONSES) if r.get("sql_restored") is not None]
    errs = [r for r in read_jsonl(RESPONSES) if r.get("sql") is None]
    run = None
    if not a.no_exec:
        sys.path.insert(0, str(HARNESS / "adapter_prompt_eval"))
        from run_eval import base                               # noqa: E402
        conn = base.SandboxConnectionPool().get()

        def run(sql):
            try:
                res = base._run_rows(conn, sql)
                return {"rows": len(res), "hash": hashlib.md5(json.dumps(sorted(map(repr, res))).encode()).hexdigest()[:8]}
            except Exception as e:                              # noqa: BLE001
                try: conn.rollback()
                except Exception: pass                          # noqa: E701
                return {"error": str(e).splitlines()[0][:200]}

    summary = []
    for q, meta in reqs.items():
        rs = sorted([r for r in rows if r["qid"] == q], key=lambda r: r["rep"])
        if not rs:
            continue
        order = list(dict.fromkeys(r["sql_restored"] for r in rs))
        lab = {s: chr(65 + i) for i, s in enumerate(order)}
        seq = "".join(lab[r["sql_restored"]] for r in rs)
        alone = [r for r in rs if r["alone"]]
        item = {"qid": q, "text": meta["text"], "seq": seq, "n": len(rs), "distinct": len(order),
                "n_alone": len(alone), "distinct_alone": len({r["sql_restored"] for r in alone}),
                "alone_flags": "".join("o" if r["alone"] else "x" for r in rs), "variants": []}
        for s in order:
            v = {"label": lab[s], "count": sum(r["sql_restored"] == s for r in rs), "sql": s,
                 "diff_vs_A": None if lab[s] == "A" else first_diff(order[0], s)}
            if run and len(order) > 1:
                v["exec"] = run(s)
                if meta.get("gold"):
                    try: v["ex_vs_gold"] = str(base.check_ex(conn, s, meta["gold"])[0])
                    except Exception as e: v["ex_vs_gold"] = f"ERR {e}"   # noqa: E701
            item["variants"].append(v)
        if run and len(order) > 1:
            item["same_result"] = len({json.dumps(v["exec"], sort_keys=True) for v in item["variants"]}) == 1
        summary.append(item)
    json.dump(summary, open(ROOT / "summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    flaky = [s for s in summary if s["distinct"] > 1]
    flaky_alone = [s for s in summary if s["distinct_alone"] > 1]
    n_alone = sum(s["n_alone"] for s in summary); n_all = sum(s["n"] for s in summary)
    L = ["# 순차 반복 결과 (자동 생성: analyze.py)", "",
         f"- 질의 {len(summary)}개, 응답 {n_all}건 (오류 {len(errs)}건), 서버에서 혼자 처리된 요청 {n_alone}건",
         f"- **답이 갈린 질의: {len(flaky)}/{len(summary)}개**",
         f"- 혼자 처리된 요청만 봐도 갈린 질의: {len(flaky_alone)}개", ""]
    if flaky:
        L += ["## 갈린 질의", "", "| 질의 | 회차별 답 | 혼자 처리(o/x) | 답별 횟수 | 실행 결과 같음 | 첫 차이 (A → 다른 답) |", "|---|---|---|---|---|---|"]
        for s in flaky:
            cnt = ", ".join(f"{v['label']}×{v['count']}" for v in s["variants"])
            diff = "<br>".join(f"{v['label']}: `{v['diff_vs_A']}`" for v in s["variants"] if v["diff_vs_A"])
            L.append(f"| {s['qid']} {s['text'][:40]} | {s['seq']} | {s['alone_flags']} | {cnt} | {s.get('same_result', '-')} | {diff} |")
        L += ["", "### 답별 실행 결과", ""]
        for s in flaky:
            L.append(f"- **{s['qid']}** {s['text']}")
            for v in s["variants"]:
                L.append(f"  - {v['label']} ×{v['count']}: {v.get('exec')}" + (f", 정답 대비 EX={v['ex_vs_gold']}" if "ex_vs_gold" in v else ""))
    L += ["", "## 전체", "", "| 질의 | 회차별 답 | 혼자 처리(o/x) |", "|---|---|---|"]
    L += [f"| {s['qid']} {s['text'][:50]} | {s['seq']} | {s['alone_flags']} |" for s in summary]
    if errs:
        L += ["", "## 오류", ""] + [f"- {r['qid']} rep{r['rep']}: {r['error']}" for r in errs]
    (ROOT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:6]))


if __name__ == "__main__":
    main()
