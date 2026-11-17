"""responses.jsonl → 질의·조건별 서로 다른 답 개수, 답별 샌드박스 실행 결과(행 수·결과 일치 여부) → summary.json"""
import json, sys, pathlib, hashlib, collections
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "adapter_prompt_eval"))
from run_eval import base  # noqa: E402
rows = [json.loads(l) for l in open(ROOT / "responses.jsonl", encoding="utf-8")]
conn = base.SandboxConnectionPool().get()

def run(sql):
    try:
        res = base._run_rows(conn, sql)
        key = hashlib.md5(json.dumps(sorted(map(repr, res))).encode()).hexdigest()[:8]
        return {"rows": len(res), "hash": key}
    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        return {"error": str(e).splitlines()[0][:200]}

summary = []
for cid in dict.fromkeys(r["id"] for r in rows):
    rs = [r for r in rows if r["id"] == cid]
    ref = rs[0]["sql"]                                   # seq 1회차를 기준 답으로
    order = [ref] + [s for s, _ in collections.Counter(r["sql"] for r in rs).most_common() if s != ref]
    label = {s: "ABCDEFGHIJ"[i] for i, s in enumerate(order)}
    variants = [{"label": label[s], "count": sum(r["sql"] == s for r in rs), "exec": run(s), "sql": s} for s in order]
    conds = {c: [label[r["sql"]] for r in sorted(rs, key=lambda r: r["run"]) if r["cond"] == c]
             for c in ("seq", "par_same", "par_mixed")}
    summary.append({"id": cid, "conds": conds, "variants": variants,
                    "tokens": sorted({r["completion_tokens"] for r in rs}), "finish": sorted({r["finish"] for r in rs})})
    print(cid, conds, [(v["label"], v["count"], v["exec"]) for v in variants], flush=True)
json.dump(summary, open(ROOT / "summary.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
