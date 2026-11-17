"""질의마다 TTS /rag 를 1번 호출해 user 프롬프트를 고정 저장한다 (외부 노출 서버 → 최소 호출).
concept_unmapped 로 실패하면, 테스트셋 input 의 '개념 값 조건'에서 concept_id 를 확정 개념으로 넣어 1번만 재시도.
API 키는 환경변수 TTS_API_KEY 로만 받는다(파일에 남기지 않음).
"""
import json, os, re, sys, pathlib, requests
ROOT = pathlib.Path(__file__).resolve().parent
TS = ROOT.parent.parent / "test_set/eval_ready"
IDS = ["seed_310_test_paraphrase", "seed_103_test_paraphrase", "seed_431_test_paraphrase",
       "seed_263_test_concept", "seed_52_test_concept", "seed_57_test_concept",
       "seed_369_test_slot", "seed_24_test_slot", "seed_162_test_restructure", "seed_120_test_restructure"]
H = {"Content-Type": "application/json", "X-API-Key": os.environ["TTS_API_KEY"]}
cases = {}
for f in TS.glob("*.jsonl"):
    for l in open(f, encoding="utf-8"):
        r = json.loads(l)
        if r["id"] in IDS: cases[r["id"]] = r
out = ROOT / "rag"; out.mkdir(exist_ok=True)
for cid in IDS:
    c = cases[cid]; body = {"query": c["text"], "top_k": 5}
    r = requests.post("http://10.1.1.69:8080/rag", json=body, headers=H, timeout=180).json()
    tries = [{"request": body, "response": r}]
    if not r.get("prompt") and r.get("error_kind") == "concept_unmapped":
        given = [{"keyword": k, "concept_id": int(ids.split(",")[0])}
                 for k, ids in re.findall(r'"([^"]+)" → [\w.]+ IN \(([\d, ]+)\)', c["input"])]
        body = {**body, "concepts": given}
        r = requests.post("http://10.1.1.69:8080/rag", json=body, headers=H, timeout=180).json()
        tries.append({"request": body, "response": r})
    json.dump({"id": cid, "text": c["text"], "gold": c["query"], "tries": tries, "prompt": r.get("prompt")},
              open(out / f"{cid}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(cid, len(tries), r.get("status"), r.get("error_kind"), r.get("error"), len(r.get("prompt") or ""), flush=True)
