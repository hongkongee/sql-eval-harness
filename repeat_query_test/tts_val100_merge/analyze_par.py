"""병렬 결과(responses_par.jsonl)를 순차 결과(responses.jsonl)와 비교 → summary_par.json + report_par.md

질의마다 답에 라벨을 붙인다: 순차에서 나온 답이 먼저(A=순차 1회차), 병렬에서 처음 나온 답은 그 뒤 글자.
핵심 지표:
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의 (= 병렬이 만든 흔들림)
- 병렬 답 중 순차에서 한 번도 안 나온 '새 답'의 비율
- 외부 요청이 섞인 묶음(only_ours=False)을 빼고 본 결과
실행: python3 analyze_par.py [--no-exec]   (순차 결과가 없으면 병렬 안에서만 비교)
"""
import argparse, hashlib, json, sys
from common import ROOT, HARNESS, REQUESTS, RESPONSES, read_jsonl
from analyze import first_diff


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-exec", action="store_true"); a = ap.parse_args()
    reqs = json.load(open(REQUESTS, encoding="utf-8"))
    seq = [r for r in read_jsonl(RESPONSES) if r.get("sql_restored") is not None]
    par = [r for r in read_jsonl(ROOT / "responses_par.jsonl") if r.get("sql_restored") is not None]
    errs = [r for r in read_jsonl(ROOT / "responses_par.jsonl") if r.get("sql") is None]
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

    modes = [m for m in ("mixed", "same") if any(r["mode"] == m for r in par)]
    summary = []
    for q, meta in reqs.items():
        s_rows = sorted([r for r in seq if r["qid"] == q], key=lambda r: r["rep"])
        p_rows = [r for r in par if r["qid"] == q]
        if not p_rows:
            continue
        order = list(dict.fromkeys([r["sql_restored"] for r in s_rows] + [r["sql_restored"] for r in p_rows]))
        lab = {s: chr(65 + i) for i, s in enumerate(order)}
        seq_set = {r["sql_restored"] for r in s_rows}
        item = {"qid": q, "text": meta["text"], "seq": "".join(lab[r["sql_restored"]] for r in s_rows),
                "seq_distinct": len(seq_set)}
        for m in modes:
            pr = sorted([r for r in p_rows if r["mode"] == m], key=lambda r: r["rep"])
            item[m] = "".join(lab[r["sql_restored"]] for r in pr)
            item[m + "_flags"] = "".join("o" if r["only_ours"] else "x" for r in pr)
            item[m + "_new"] = sum(r["sql_restored"] not in seq_set for r in pr) if s_rows else None
            item[m + "_new_ours"] = sum(r["sql_restored"] not in seq_set for r in pr if r["only_ours"]) if s_rows else None
            item[m + "_distinct"] = len({r["sql_restored"] for r in pr})
        item["variants"] = []
        for s in order:
            v = {"label": lab[s], "in_seq": s in seq_set, "sql": s,
                 "diff_vs_A": None if lab[s] == "A" else first_diff(order[0], s)}
            if run and len(order) > 1:
                v["exec"] = run(s)
            item["variants"].append(v)
        summary.append(item)
    json.dump(summary, open(ROOT / "summary_par.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    has_seq = bool(seq)
    L = ["# 병렬 결과 (자동 생성: analyze_par.py)", "",
         f"- 질의 {len(summary)}개, 병렬 응답 {len(par)}건 (오류 {len(errs)}건), "
         f"외부 요청이 섞인 응답 {sum(not r['only_ours'] for r in par)}건",
         f"- 순차 결과: {'있음 (responses.jsonl, A = 순차 1회차 답)' if has_seq else '없음 — 병렬 안에서만 비교'}", ""]
    for m in modes:
        n = sum(len(s[m]) for s in summary)
        if has_seq:
            stable = [s for s in summary if s["seq_distinct"] == 1]
            moved = [s for s in stable if s[m + "_new"]]
            new = sum(s[m + "_new"] for s in summary); new_o = sum(s[m + "_new_ours"] for s in summary)
            L += [f"## {m} ({'서로 다른 질의를 섞어 동시에' if m == 'mixed' else '같은 질의를 동시에'})", "",
                  f"- 순차 답에 없던 새 답: **{new}/{n}건** (외부 요청 없이 우리 요청만 돈 묶음 기준 {new_o}건)",
                  f"- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **{len(moved)}/{len(stable)}개**", ""]
        else:
            L += [f"## {m}", "", f"- 병렬 안에서 답이 갈린 질의: {sum(s[m + '_distinct'] > 1 for s in summary)}/{len(summary)}개", ""]
    shaky = [s for s in summary if len(s["variants"]) > 1]
    if shaky:
        hdr = "| 질의 | 순차 | " + " | ".join(f"{m} (o/x)" for m in modes) + " | 첫 차이 (A → 다른 답) | 실행 결과 |"
        L += ["## 답이 하나라도 갈린 질의", "", hdr, "|" + "---|" * (3 + len(modes) + 1)]
        for s in shaky:
            cols = " | ".join(f"{s[m]} ({s[m + '_flags']})" for m in modes)
            diff = "<br>".join(f"{v['label']}{'' if v['in_seq'] else '(병렬만)'}: `{v['diff_vs_A']}`"
                               for v in s["variants"] if v["diff_vs_A"])
            ex = "<br>".join(f"{v['label']}: {v.get('exec')}" for v in s["variants"])
            L.append(f"| {s['qid']} {s['text'][:35]} | {s['seq']} | {cols} | {diff} | {ex} |")
    L += ["", "## 전체", "", "| 질의 | 순차 | " + " | ".join(modes) + " |", "|" + "---|" * (2 + len(modes))]
    L += [f"| {s['qid']} {s['text'][:45]} | {s['seq']} | " + " | ".join(s[m] for m in modes) + " |" for s in summary]
    if errs:
        L += ["", "## 오류", ""] + [f"- {r['mode']} {r['qid']} rep{r['rep']}: {r['error']}" for r in errs]
    (ROOT / "report_par.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()
