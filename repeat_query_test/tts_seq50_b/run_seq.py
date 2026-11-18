"""2단계: requests.json 의 고정 요청을 질의마다 --reps 번, 한 번에 하나씩(순차) LLM 에 보낸다.

병렬 영향 배제:
- 요청을 보내기 전에 모델 서버 /metrics 에서 처리 중(running)·대기(waiting) 요청이 0 이 될 때까지
  기다린다(최대 --idle-wait 초, 넘으면 그냥 보내고 기록).
- 요청이 처리되는 동안 /metrics 를 0.5초마다 읽어 서버에서 동시에 돈 요청 수의 최댓값을 기록한다.
  max_running > 1 이면 다른 요청과 같이 처리된 것(alone=False).
재실행 안전: responses.jsonl 에 이미 있는 (qid, rep) 은 건너뛴다. 중간에 끊겨도 다시 실행하면 이어서 한다.
실행: python3 run_seq.py [--reps 5] [--idle-wait 120]
"""
import argparse, json, re, threading, time
import requests
from common import REQUESTS, RESPONSES, llm_url, metrics_url, read_jsonl

_PAT = re.compile(r'^vllm:num_requests_(running|waiting)\{[^}]*\}\s+([0-9.eE+-]+)', re.M)


def load():
    """(running, waiting) — 모델이 여러 개 떠 있으면 합계. 실패하면 (None, None)."""
    try:
        txt = requests.get(metrics_url(), timeout=5).text
    except Exception:                                            # noqa: BLE001
        return None, None
    v = {"running": 0.0, "waiting": 0.0}
    for k, n in _PAT.findall(txt):
        v[k] += float(n)
    return int(v["running"]), int(v["waiting"])


def wait_idle(limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        r, w = load()
        if r is None or (r == 0 and w == 0):
            return r, w, round(time.time() - t0, 1)
        time.sleep(2)
    r, w = load()
    return r, w, round(time.time() - t0, 1)


def call(body):
    peak = {"running": 0, "waiting": 0}
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            r, w = load()
            if r is not None:
                peak["running"] = max(peak["running"], r); peak["waiting"] = max(peak["waiting"], w)
            stop.wait(0.5)
    th = threading.Thread(target=watch, daemon=True); th.start()
    t = time.perf_counter()
    try:
        last = None
        for attempt in range(3):                                # 연결 오류만 재시도
            try:
                resp = requests.post(llm_url(), json=body, timeout=600)
                resp.raise_for_status()
                r = resp.json(); c = r["choices"][0]
                return {"sql": c["message"]["content"], "finish": c.get("finish_reason"),
                        "completion_tokens": r.get("usage", {}).get("completion_tokens"),
                        "prompt_tokens": r.get("usage", {}).get("prompt_tokens"),
                        "sec": round(time.perf_counter() - t, 2), "attempts": attempt + 1, "error": None,
                        "peak_running": peak["running"], "peak_waiting": peak["waiting"]}
            except Exception as e:                              # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:300]}"
                time.sleep(10 * (attempt + 1))
        return {"sql": None, "error": last, "sec": round(time.perf_counter() - t, 2), "attempts": 3,
                "peak_running": peak["running"], "peak_waiting": peak["waiting"]}
    finally:
        stop.set(); th.join()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--idle-wait", type=float, default=120)
    a = ap.parse_args()
    reqs = json.load(open(REQUESTS, encoding="utf-8"))
    done = {(r["qid"], r["rep"]) for r in read_jsonl(RESPONSES) if r.get("sql") is not None}
    todo = [(q, i + 1) for q in reqs for i in range(a.reps) if (q, i + 1) not in done]
    print(f"질의 {len(reqs)}개 × {a.reps}번 = {len(reqs) * a.reps}건, 남은 {len(todo)}건 → {llm_url()}", flush=True)
    t_all = time.time()
    with open(RESPONSES, "a", encoding="utf-8") as f:
        for n, (q, rep) in enumerate(todo, 1):
            r0, w0, waited = wait_idle(a.idle_wait)
            res = call(reqs[q]["body"])
            sql = res["sql"]
            for ph, ids in reqs[q]["restore"].items():           # TTS generator 처럼 :CONCEPT_IDS_N 복원
                sql = sql.replace(ph, ids) if sql else sql
            row = {"qid": q, "rep": rep, "ts": time.strftime("%F %T"), "idle_waited_sec": waited,
                   "before_running": r0, "before_waiting": w0, **res, "sql_restored": sql,
                   "alone": (r0 == 0 and w0 == 0 and res["peak_running"] <= 1 and res["peak_waiting"] == 0)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush()
            eta = (time.time() - t_all) / n * (len(todo) - n) / 60
            print(f"[{n}/{len(todo)}] {q} rep{rep} {res['sec']}s tok={res.get('completion_tokens')} "
                  f"alone={row['alone']} peak={res['peak_running']}/{res['peak_waiting']} "
                  f"{'ERR ' + res['error'] if res['error'] else ''} (남은 약 {eta:.0f}분)", flush=True)
    print(f"끝. {(time.time() - t_all) / 60:.1f}분", flush=True)


if __name__ == "__main__":
    main()
