"""outputs/<case_id>/*.jsonl의 서로 다른 답마다 샌드박스 DB에서 실행해 정답과 결과가 같은지(EX) 본다."""
import json, sys, pathlib, collections
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "adapter_prompt_eval"))
from run_eval import base  # noqa: E402
d = ROOT / "outputs" / sys.argv[1]
gold = (d / "gold.sql").read_text(encoding="utf-8")
conn = base.SandboxConnectionPool().get()
res = {}
for f in sorted(d.glob("*.jsonl")):
    if f.name == "ex.json": continue
    for s in {json.loads(l)["sql"] for l in open(f, encoding="utf-8")}:
        if s not in res:
            try: res[s] = base.check_ex(conn, s, gold)
            except Exception as e: res[s] = f"ERR {e}"
(d / "ex.json").write_text(json.dumps([{"sql": s, "ex": str(v)} for s, v in res.items()], ensure_ascii=False, indent=1), encoding="utf-8")
for s, v in res.items(): print(v, "|", s[:90])
