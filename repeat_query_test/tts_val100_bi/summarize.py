"""요약 집계: 순차와 병렬을 서로 독립적으로 센다 (summary_all.json).

- 각 조건(순차 / 병렬 전체 / mixed / same) 안에서만 질의별 서로 다른 답 개수를 센다.
  병렬은 순차 답을 기준으로 삼지 않고, 순차에서 갈린 질의도 빼지 않는다.
- '소수 답' = 그 조건 안에서 가장 많이 나온 답과 다른 응답 수.
- 외부 요청 없이 처리된 응답(순차 alone, 병렬 only_ours)만 놓고도 따로 센다.
- 답 이름(A, B, …)은 질의마다 순차 1회차 답을 A로, 그 뒤 처음 나온 순서대로 붙인 것으로 표 읽기용일 뿐이다.
실행: python3 summarize.py
"""
import collections, json
from common import ROOT, RESPONSES, REQUESTS, read_jsonl

reqs = json.load(open(REQUESTS, encoding="utf-8"))
seq = [r for r in read_jsonl(RESPONSES) if r.get("sql_restored") is not None]
par = [r for r in read_jsonl(ROOT / "responses_par.jsonl") if r.get("sql_restored") is not None]


def stats(rows):
    c = collections.Counter(r["sql_restored"] for r in rows)
    top = c.most_common(1)[0][1] if c else 0
    return {"n": len(rows), "distinct": len(c), "minority": len(rows) - top}


out = []
for q, meta in reqs.items():
    s_rows = sorted([r for r in seq if r["qid"] == q], key=lambda r: r["rep"])
    p_rows = sorted([r for r in par if r["qid"] == q], key=lambda r: (r["mode"], r["rep"]))
    order = list(dict.fromkeys(r["sql_restored"] for r in s_rows + p_rows))
    lab = {s: chr(65 + i) for i, s in enumerate(order)}
    mixed = [r for r in p_rows if r["mode"] == "mixed"]
    same = [r for r in p_rows if r["mode"] == "same"]
    item = {"qid": q, "text": meta["text"], "set": meta.get("set"), "section": meta.get("section"),
            "difficulty": meta.get("difficulty"),
            "seq_answers": "".join(lab[r["sql_restored"]] for r in s_rows),
            "mixed_answers": "".join(lab[r["sql_restored"]] for r in mixed),
            "mixed_flags": "".join("o" if r.get("only_ours") else "x" for r in mixed),
            "same_answers": "".join(lab[r["sql_restored"]] for r in same),
            "same_flags": "".join("o" if r.get("only_ours") else "x" for r in same)}
    for name, rows, ours in [("seq", s_rows, [r for r in s_rows if r.get("alone")]),
                             ("par", p_rows, [r for r in p_rows if r.get("only_ours")]),
                             ("mixed", mixed, [r for r in mixed if r.get("only_ours")]),
                             ("same", same, [r for r in same if r.get("only_ours")])]:
        item[name] = stats(rows)
        item[name + "_ours"] = stats(ours)
    out.append(item)

json.dump(out, open(ROOT / "summary_all.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for name in ["seq", "par", "mixed", "same"]:
    for suf in ["", "_ours"]:
        k = name + suf
        n = sum(i[k]["n"] for i in out); m = sum(i[k]["minority"] for i in out)
        flaky = [i["qid"] for i in out if i[k]["distinct"] > 1]
        print(f"{k:10} 응답 {n:4} 소수답 {m:3} ({m / n * 100 if n else 0:.1f}%) 갈린 질의 {len(flaky):2} {flaky}")
