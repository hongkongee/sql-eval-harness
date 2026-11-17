"""병렬 시험: requests.json 의 고정 요청(순차 시험과 같은 프롬프트)을 --conc 개씩 '동시에' 보낸다.

모드:
  mixed : 매 라운드마다 질의 순서를 섞어 --conc 개씩 묶어 동시에 보낸다. 같은 질의가 라운드마다 다른 질의들과
          함께 처리된다(여러 사용자가 동시에 쓰는 상황). 라운드 --reps 번 → 질의당 답 --reps 개.
  same  : 같은 질의 요청 --conc 개를 동시에 보낸다(같은 질의를 여러 명이 동시에). 질의당 답 --conc 개.
동시 4개 = TTS 기본 LLM_CONCURRENCY(4) 와 같은 최대 동시 수.

- 묶음을 보내기 전에 서버가 빌 때까지 기다린다(최대 --idle-wait 초). 묶음 안의 요청은 Barrier 로 같은 순간에 출발.
- 처리되는 동안 /metrics 의 최대 동시 처리 수를 기록. peak_running > --conc 이거나 대기가 생기면 외부 요청이
  섞인 것으로 보고 only_ours=False.
- 재실행 안전: responses_par.jsonl 에 이미 있는 (mode, qid, rep) 은 건너뛴다(묶음 단위로 이어서 함).
실행: python3 run_par.py [--mode mixed|same|both] [--conc 4] [--reps 5]
"""
import argparse, json, random, threading, time
from concurrent.futures import ThreadPoolExecutor
import requests
from common import ROOT, REQUESTS, llm_url, read_jsonl
from run_seq import load, wait_idle

OUT = ROOT / "responses_par.jsonl"


def send(body, barrier):
    barrier.wait()
    t = time.perf_counter()
    try:
        r = requests.post(llm_url(), json=body, timeout=900); r.raise_for_status(); r = r.json(); c = r["choices"][0]
        return {"sql": c["message"]["content"], "finish": c.get("finish_reason"),
                "completion_tokens": r.get("usage", {}).get("completion_tokens"),
                "sec": round(time.perf_counter() - t, 2), "error": None}
    except Exception as e:                                       # noqa: BLE001
        return {"sql": None, "sec": round(time.perf_counter() - t, 2), "error": f"{type(e).__name__}: {str(e)[:300]}"}


def run_group(reqs, group, conc):
    """group: [(mode, qid, rep), ...] 를 동시에 보내고 행 목록 반환."""
    peak = {"running": 0, "waiting": 0}; stop = threading.Event()

    def watch():
        while not stop.is_set():
            r, w = load()
            if r is not None:
                peak["running"] = max(peak["running"], r); peak["waiting"] = max(peak["waiting"], w)
            stop.wait(0.5)
    th = threading.Thread(target=watch, daemon=True); th.start()
    barrier = threading.Barrier(len(group))
    with ThreadPoolExecutor(len(group)) as ex:
        res = list(ex.map(lambda g: send(reqs[g[1]]["body"], barrier), group))
    stop.set(); th.join()
    gid = time.strftime("%H%M%S") + f"-{random.randrange(1000):03d}"
    rows = []
    for (mode, q, rep), r in zip(group, res):
        sql = r["sql"]
        for ph, ids in reqs[q]["restore"].items():
            sql = sql.replace(ph, ids) if sql else sql
        rows.append({"mode": mode, "qid": q, "rep": rep, "group": gid, "group_qids": [g[1] for g in group],
                     "ts": time.strftime("%F %T"), **r, "sql_restored": sql,
                     "peak_running": peak["running"], "peak_waiting": peak["waiting"],
                     "only_ours": peak["running"] <= len(group) and peak["waiting"] == 0})
    return rows


def plan(mode, qids, conc, reps):
    groups = []
    if mode == "mixed":
        for rep in range(1, reps + 1):
            order = qids[:]; random.Random(rep).shuffle(order)
            groups += [[("mixed", q, rep) for q in order[i:i + conc]] for i in range(0, len(order), conc)]
    else:
        groups = [[("same", q, k) for k in range(1, conc + 1)] for q in qids]
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mixed", "same", "both"], default="both")
    ap.add_argument("--conc", type=int, default=4)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--idle-wait", type=float, default=120)
    a = ap.parse_args()
    reqs = json.load(open(REQUESTS, encoding="utf-8")); qids = list(reqs)
    done = {(r["mode"], r["qid"], r["rep"]) for r in read_jsonl(OUT) if r.get("sql") is not None}
    modes = ["mixed", "same"] if a.mode == "both" else [a.mode]
    groups = [g for m in modes for g in plan(m, qids, a.conc, a.reps)]
    todo = [g for g in groups if not all(x in done for x in g)]
    print(f"묶음 {len(groups)}개(동시 {a.conc}), 남은 {len(todo)}개 → {llm_url()}", flush=True)
    t_all = time.time()
    with open(OUT, "a", encoding="utf-8") as f:
        for n, g in enumerate(todo, 1):
            r0, w0, waited = wait_idle(a.idle_wait)
            rows = run_group(reqs, g, a.conc)
            for row in rows:
                row.update(before_running=r0, before_waiting=w0, idle_waited_sec=waited)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            eta = (time.time() - t_all) / n * (len(todo) - n) / 60
            errs = sum(r["error"] is not None for r in rows)
            print(f"[{n}/{len(todo)}] {g[0][0]} {[x[1] for x in g]} max={max(r['sec'] for r in rows)}s "
                  f"peak={rows[0]['peak_running']}/{rows[0]['peak_waiting']} only_ours={rows[0]['only_ours']}"
                  f"{f' ERR×{errs}' if errs else ''} (남은 약 {eta:.0f}분)", flush=True)
    print(f"끝. {(time.time() - t_all) / 60:.1f}분", flush=True)


if __name__ == "__main__":
    main()
