"""사용자가 쓰던 curl과 똑같은 형태로 요청한다: system + user만 보내고
temperature/top_p/max_tokens는 넣지 않는다(서버 기본값 사용).
실행: python3 run_curl_style.py <test_set.jsonl> <case_id> [반복 횟수=5] [모델=by-loss]
"""
import json, sys, time, pathlib
import requests

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "adapter_prompt_eval"))
import adherence as ad  # noqa: E402

API = "http://10.1.1.69:8007/v1/chat/completions"
SP = (ROOT.parent / "results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt").read_text(encoding="utf-8").strip()
ts, cid = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 5
model = sys.argv[4] if len(sys.argv) > 4 else "by-loss"
case = next(c for c in map(json.loads, open(ts, encoding="utf-8")) if str(c["id"]) == cid)
user = ad.build_prompt(case)

out = ROOT / "outputs" / cid
out.mkdir(parents=True, exist_ok=True)
(out / "request_user_message.txt").write_text(user, encoding="utf-8")
(out / "gold.sql").write_text(case["query"], encoding="utf-8")
with open(out / f"curl_style_{model}.jsonl", "w", encoding="utf-8") as f:
    for i in range(N):
        body = {"model": model, "messages": [{"role": "system", "content": SP}, {"role": "user", "content": user}]}
        t = time.perf_counter()
        r = requests.post(API, json=body, timeout=300).json()
        c = r["choices"][0]
        row = {"model": model, "cond": "curl_style", "run": i + 1, "sql": c["message"]["content"],
               "sec": round(time.perf_counter() - t, 2), "finish": c.get("finish_reason"),
               "completion_tokens": r.get("usage", {}).get("completion_tokens")}
        f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
        print(i + 1, row["sec"], row["finish"], row["completion_tokens"], flush=True)
