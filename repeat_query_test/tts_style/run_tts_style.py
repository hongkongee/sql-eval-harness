"""request_<id>.json(TTS와 같은 system+user)을 by-loss에 반복 전송.
조건: t0 = temperature 0.0 / max_tokens 4096 (TTS 기본 설정)
      default = temperature·max_tokens 미지정 (서버 기본값, 사용자 curl 형태)
실행: python3 run_tts_style.py request_seed_240.json [횟수=5]
"""
import json, sys, time, requests
API = "http://10.1.1.69:8007/v1/chat/completions"
src = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
req = json.load(open(src, encoding="utf-8"))
out = src.replace("request_", "responses_").replace(".json", ".jsonl")
with open(out, "w", encoding="utf-8") as f:
    for cond in ("t0", "default"):
        body = dict(req) if cond == "t0" else {"model": req["model"], "messages": req["messages"]}
        for i in range(N):
            t = time.perf_counter(); r = requests.post(API, json=body, timeout=300).json(); c = r["choices"][0]
            row = {"cond": cond, "run": i + 1, "sql": c["message"]["content"], "sec": round(time.perf_counter() - t, 2),
                   "finish": c.get("finish_reason"), "completion_tokens": r.get("usage", {}).get("completion_tokens")}
            f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
            print(cond, i + 1, row["sec"], row["finish"], row["completion_tokens"], flush=True)
