"""rag/<id>.json 의 고정 프롬프트(TTS와 같은 system+user, temperature 0.0, max_tokens 4096)를 by-loss 에 반복 전송.
조건:
  seq        : 질의별로 5번 순서대로 (서버에 이 요청 하나만 있을 때)
  par_same   : 질의별로 같은 요청 5개를 동시에
  par_mixed  : 10개 질의 × 5번 = 50개를 한꺼번에 동시에 (다른 사용자 요청이 섞여 들어오는 상황)
실행: python3 run_batch.py [횟수=5]
"""
import json, sys, time, pathlib, random, requests
from concurrent.futures import ThreadPoolExecutor
ROOT = pathlib.Path(__file__).resolve().parent
P = pathlib.Path("/Users/seo/Developer/mpx-cdm-tts/app/services/text2sql/prompts")
API = "http://10.1.1.69:8007/v1/chat/completions"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
SYS = P.joinpath("system_prompt.txt").read_text(encoding="utf-8").replace("{dialect}", "PostgreSQL")
PROTO = P.joinpath("placeholder_protocol.txt").read_text(encoding="utf-8")

reqs = {}
for f in sorted((ROOT / "rag").glob("*.json")):
    d = json.load(open(f, encoding="utf-8"))
    resp = d["tries"][-1]["response"]; user = d["prompt"]
    system = f"{SYS}\n\n{PROTO}" if ("{{" in user or resp.get("concepts")) else SYS   # prompt_builder.build_messages 와 동일
    reqs[d["id"]] = {"model": "by-loss", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                     "max_tokens": 4096, "temperature": 0.0}
json.dump(reqs, open(ROOT / "requests.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def call(job):
    cid, cond, run = job
    t = time.perf_counter(); r = requests.post(API, json=reqs[cid], timeout=900).json(); c = r["choices"][0]
    return {"id": cid, "cond": cond, "run": run, "sql": c["message"]["content"], "sec": round(time.perf_counter() - t, 2),
            "finish": c.get("finish_reason"), "completion_tokens": r["usage"]["completion_tokens"],
            "cached_tokens": (r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens")}

out = open(ROOT / "responses.jsonl", "w", encoding="utf-8")
def save(rows):
    for row in rows: out.write(json.dumps(row, ensure_ascii=False) + "\n")
    out.flush()

for cid in reqs:                                                   # seq
    save([call((cid, "seq", i + 1)) for i in range(N)]); print("seq", cid, flush=True)
with ThreadPoolExecutor(N) as ex:                                  # par_same
    for cid in reqs:
        save(list(ex.map(call, [(cid, "par_same", i + 1) for i in range(N)]))); print("par_same", cid, flush=True)
jobs = [(cid, "par_mixed", i + 1) for cid in reqs for i in range(N)]
random.Random(0).shuffle(jobs)
with ThreadPoolExecutor(len(jobs)) as ex:                          # par_mixed
    save(list(ex.map(call, jobs))); print("par_mixed done", flush=True)
