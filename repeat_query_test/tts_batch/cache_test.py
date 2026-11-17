"""prefix cache 영향 확인: seed_103 요청을 (1) 요청마다 다른 cache_salt → 캐시 못 씀, (2) 같은 새 salt로 순서대로 → 첫 번째만 캐시 없음.
vLLM 의 cache_salt 는 salt 가 다르면 prefix cache 를 공유하지 않게 한다. temperature 0.0, max_tokens 4096 그대로."""
import json, time, uuid, pathlib, requests
ROOT = pathlib.Path(__file__).resolve().parent
API = "http://10.1.1.69:8007/v1/chat/completions"
req = json.load(open(ROOT / "requests.json", encoding="utf-8"))["seed_103_test_paraphrase"]
ref = next(json.loads(l)["sql"] for l in open(ROOT / "responses.jsonl", encoding="utf-8")
           if '"seed_103_test_paraphrase"' in l)            # seq 1회차(A)
out = open(ROOT / "cache_test.jsonl", "w", encoding="utf-8")
same_salt = uuid.uuid4().hex
for cond, salts in [("unique_salt", [uuid.uuid4().hex for _ in range(5)]), ("same_new_salt", [same_salt] * 5)]:
    for i, s in enumerate(salts):
        r = requests.post(API, json={**req, "cache_salt": s}, timeout=600)
        r.raise_for_status(); r = r.json(); sql = r["choices"][0]["message"]["content"]
        row = {"cond": cond, "run": i + 1, "salt": s, "label": "A" if sql == ref else ("B" if "INTERVAL '14' AS" in sql else "?"),
               "sql": sql, "completion_tokens": r["usage"]["completion_tokens"]}
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        print(cond, i + 1, row["label"], row["completion_tokens"], flush=True)
