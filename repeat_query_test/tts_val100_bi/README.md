# batch-invariant 모드로 3차 시험 반복 (4차)

`../tts_val100`(3차)과 같은 시험을 vLLM batch-invariant 모드(`VLLM_BATCH_INVARIANT=1`)를 켠 서버에서 다시 합니다. 서버 설정 방법은 `../tts_val100/batch_invariant_guide.md`를 보세요.

## 3차와 같은 점

- **질의와 프롬프트:** `requests.json`과 `rag/`를 3차에서 그대로 복사했습니다. `/rag`는 다시 부르지 않으므로 프롬프트가 글자까지 같습니다.
- **반복 조건:** 순차 5번, mixed 5번(동시 4개), same 4번입니다. 질의마다 14번, 모두 1,400건입니다.
- **mixed 묶음:** 3차와 같은 질의끼리 묶입니다. 회차 번호를 시드로 섞기 때문입니다.
- **스크립트:** 3차 스크립트를 그대로 복사했습니다. 결과 파일은 이 폴더에 따로 쌓입니다.

## 실행

```bash
cd /Users/seo/Developer/automl/sql-eval-harness/repeat_query_test/tts_val100_bi
nohup caffeinate -i ./run_bi.sh > run_bi.log 2>&1 &
tail -f run_bi.log
```

- `/rag`를 부르지 않으므로 `TTS_API_KEY`와 `TTS_URL`은 필요 없습니다.
- 중간에 끊기면 같은 명령으로 다시 실행하면 됩니다. 이미 받은 응답은 건너뜁니다.
- 3차는 순차 50분, 병렬 35분이 걸렸습니다. batch-invariant는 느려진다고 알려져 있어 더 걸릴 수 있습니다.

## 실행 전 확인

```bash
# 서버에 batch-invariant 모드가 켜져 있는지 (서버에서)
docker exec vllm-serve sh -c 'tr "\0" "\n" < /proc/1/environ | grep VLLM_BATCH'

# 요청 모델 이름(by-loss)이 등록돼 있는지 (서버에서)
curl -s localhost:8007/v1/models | python3 -m json.tool | grep '"id"'
```
