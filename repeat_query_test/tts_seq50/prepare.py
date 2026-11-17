"""1단계: 질의마다 TTS /rag 를 '한 번만' 불러 프롬프트를 고정하고 requests.json 을 만든다.

- 질의 출처: --source tts      → TTS 프로젝트 tests/test_queries_100.txt (기본)
             --source testset  → test_set/eval_ready/*.jsonl (정답 SQL 있음, 4종 고르게)
- /rag 가 실패(개념 못 찾음 등)한 질의는 버리고 다음 후보로 넘어가 --n 개를 채운다.
- 외부 노출 서버라 호출 사이에 --delay 초 쉰다. 이미 받은 rag/*.json 은 다시 부르지 않는다(재실행 안전).
- API 키는 환경변수 TTS_API_KEY 로만 받는다(파일에 저장하지 않음).
실행: TTS_API_KEY=... python3 prepare.py [--n 50] [--source tts|testset] [--delay 3]
"""
import argparse, json, os, random, time
import requests
from common import ROOT, HARNESS, TTS_DIR, TTS_URL, RAG_DIR, REQUESTS, build_request, llm_url, tts_config


def candidates(source):
    if source == "tts":
        lines = [l.strip() for l in open(TTS_DIR / "tests/test_queries_100.txt", encoding="utf-8") if l.strip()]
        out = [{"qid": f"q{i + 1:03d}", "text": t, "gold": None} for i, t in enumerate(lines)]
        random.Random(0).shuffle(out)       # 파일이 유형별로 묶여 있어(앞쪽은 '처방 이력' 위주) 고르게 섞어서 뽑는다
        return out
    out, rng = [], random.Random(0)
    per = {}
    for f in sorted((HARNESS / "test_set/eval_ready").glob("*.jsonl")):
        rows = [json.loads(l) for l in open(f, encoding="utf-8")]
        rng.shuffle(rows); per[f.stem] = rows
    seen = set()
    while any(per.values()):                                   # 4종을 번갈아 하나씩, seed 중복 없이
        for k in list(per):
            while per[k]:
                r = per[k].pop()
                if r["seed_id"] not in seen:
                    seen.add(r["seed_id"]); out.append({"qid": r["id"], "text": r["text"], "gold": r["query"]}); break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--source", choices=["tts", "testset"], default="tts")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--top-k", type=int, default=5)
    a = ap.parse_args()
    key = os.environ.get("TTS_API_KEY")
    if not key:
        raise SystemExit("TTS_API_KEY 환경변수가 필요합니다.")
    RAG_DIR.mkdir(exist_ok=True)
    ok, calls = [], 0
    for c in candidates(a.source):
        if len(ok) >= a.n:
            break
        f = RAG_DIR / f"{c['qid']}.json"
        if f.exists():
            d = json.load(open(f, encoding="utf-8"))
        else:
            body = {"query": c["text"], "top_k": a.top_k}
            try:
                r = requests.post(f"{TTS_URL}/rag", json=body, timeout=180,
                                  headers={"Content-Type": "application/json", "X-API-Key": key})
                if r.status_code in (401, 403):                 # 키 문제 → 바로 중단 (실패를 저장하지 않음)
                    raise SystemExit(f"/rag 인증 실패 {r.status_code}: {r.text[:200]} — TTS_API_KEY·TTS_URL({TTS_URL}) 확인")
                resp = r.json()
                http_ok = r.status_code in (200, 422)             # 422 = 개념 못 찾음 등 '질의 자체' 실패 → 저장
            except SystemExit:
                raise
            except Exception as e:                                # noqa: BLE001
                resp, http_ok = {"success": False, "error": f"{type(e).__name__}: {e}"}, False
            calls += 1
            d = {**c, "rag_request": body, "rag_response": resp, "fetched_at": time.strftime("%F %T")}
            if http_ok:                                           # 서버 오류·타임아웃은 저장 안 함 → 재실행 때 다시 시도
                json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            time.sleep(a.delay)
        resp = d["rag_response"]
        good = bool(resp.get("success") and resp.get("prompt"))
        print(f"{c['qid']:28} {'OK  ' if good else 'SKIP'} {resp.get('status')} {resp.get('error_kind') or ''} | {c['text'][:50]}", flush=True)
        if good:
            ok.append(d)
    reqs = {}
    for d in ok:
        body, restore = build_request(d["rag_response"])
        reqs[d["qid"]] = {"text": d["text"], "gold": d["gold"], "body": body, "restore": restore}
    json.dump(reqs, open(REQUESTS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n/rag 호출 {calls}번, 프롬프트 확보 {len(ok)}/{a.n}개 → {REQUESTS.name}")
    print(f"LLM 설정 (TTS config): {llm_url()} model={tts_config.NL2SQL_MODEL} "
          f"temperature={tts_config.NL2SQL_TEMPERATURE} max_tokens={tts_config.NL2SQL_MAX_TOKENS}")
    if len(ok) < a.n:
        print(f"주의: 후보가 모자라 {len(ok)}개만 확보했습니다.")


if __name__ == "__main__":
    main()
