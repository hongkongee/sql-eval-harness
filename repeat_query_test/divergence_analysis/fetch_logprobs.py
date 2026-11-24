"""고정 요청(1·2차 100개 + tts_batch 10개)을 질의당 1번만, logprobs(top 5)를 켜서 순차로 보낸다.
각 토큰 위치에서 1위 후보와 2위 후보의 logprob 차이(margin)를 보면 모델이 어디서 망설이는지 알 수 있다.
요청 본문은 시험 때와 같고 logprobs/top_logprobs 만 더한다. 이미 받은 질의는 건너뜀.
실행: python3 fetch_logprobs.py
"""
import json, pathlib, sys, time
import requests
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tts_seq50"))
from run_seq import wait_idle, load            # noqa: E402  서버가 빌 때까지 기다림(병렬 영향 배제)
from common import llm_url                     # noqa: E402

OUT = HERE / "logprobs.jsonl"
src = {}
for run, f in (("1차", "tts_seq50/requests.json"), ("2차", "tts_seq50_b/requests.json")):
    for q, v in json.load(open(HERE.parent / f, encoding="utf-8")).items():
        src[q] = (run, v["body"])
for q, v in json.load(open(HERE.parent / "tts_batch/requests.json", encoding="utf-8")).items():
    src[q] = ("tts_batch", v)
done = {json.loads(l)["qid"] for l in open(OUT, encoding="utf-8")} if OUT.exists() else set()
todo = [q for q in src if q not in done]
print(f"{len(todo)}건 보냄 → {llm_url()}", flush=True)
with open(OUT, "a", encoding="utf-8") as fo:
    for i, q in enumerate(todo, 1):
        run, body = src[q]
        wait_idle(120)
        b = {**body, "logprobs": True, "top_logprobs": 5}
        t = time.perf_counter()
        r = requests.post(llm_url(), json=b, timeout=600); r.raise_for_status()
        c = r.json()["choices"][0]
        toks = [{"t": x["token"], "lp": x["logprob"],
                 "top": [[y["token"], y["logprob"]] for y in x["top_logprobs"]]} for x in c["logprobs"]["content"]]
        fo.write(json.dumps({"qid": q, "run": run, "sql": c["message"]["content"], "tokens": toks,
                             "sec": round(time.perf_counter() - t, 2), "after_load": load()}, ensure_ascii=False) + "\n")
        fo.flush()
        print(f"[{i}/{len(todo)}] {q} {len(toks)}tok", flush=True)
