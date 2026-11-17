"""같은 요청(시스템 프롬프트 + 질의 + 재료)을 N번 반복해 보내 답이 얼마나 달라지는지 본다.

조건:
  t0_seq  : temperature 0, 한 번에 하나씩 순차 요청 (평가 스크립트와 같은 설정)
  t0_par  : temperature 0, N개를 동시에 요청 (서버 배치 크기가 달라질 때)
  default : temperature/top_p 미지정 (서버/모델 generation_config 기본값으로 샘플링)
실행: python3 run_repeat.py <test_set.jsonl> <case_id> [N] [모델...]
"""
import json, sys, time, pathlib
from concurrent.futures import ThreadPoolExecutor
import requests

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "adapter_prompt_eval"))
import adherence as ad  # noqa: E402

API = "http://10.1.1.69:8007/v1/chat/completions"
SP = (ROOT.parent / "results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt").read_text(encoding="utf-8").strip()

ts, cid = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 10
models = sys.argv[4:] or ["by-loss", "final-step"]
case = next(c for c in map(json.loads, open(ts, encoding="utf-8")) if str(c["id"]) == cid)
user = ad.build_prompt(case)


def call(model, temp_zero):
    body = {"model": model, "max_tokens": 512,
            "messages": [{"role": "system", "content": SP}, {"role": "user", "content": user}]}
    if temp_zero:
        body["temperature"] = 0
    t = time.perf_counter()
    r = requests.post(API, json=body, timeout=300).json()
    return {"sql": r["choices"][0]["message"]["content"], "sec": round(time.perf_counter() - t, 2),
            "finish": r["choices"][0].get("finish_reason")}


out = ROOT / "outputs" / cid
out.mkdir(parents=True, exist_ok=True)
(out / "request_user_message.txt").write_text(user, encoding="utf-8")
(out / "gold.sql").write_text(case["query"], encoding="utf-8")
for m in models:
    res = {"t0_seq": [call(m, True) for _ in range(N)]}
    with ThreadPoolExecutor(N) as ex:
        res["t0_par"] = list(ex.map(lambda _: call(m, True), range(N)))
    res["default"] = [call(m, False) for _ in range(N)]
    with open(out / f"{m}.jsonl", "w", encoding="utf-8") as f:
        for cond, rows in res.items():
            for i, row in enumerate(rows):
                f.write(json.dumps({"model": m, "cond": cond, "run": i + 1, **row}, ensure_ascii=False) + "\n")
    for cond, rows in res.items():
        print(m, cond, "distinct:", len({r["sql"] for r in rows}), "/", N)
