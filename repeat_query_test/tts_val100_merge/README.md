# LoRA 병합 모델로 3차 시험 반복 (5차)

`../tts_val100`(3차)과 같은 시험을 `by-loss` LoRA를 베이스에 병합해 단독 서빙한 서버(batch-invariant 꺼짐)에서 다시 합니다.

## 3차와 같은 점

- **질의와 프롬프트:** `requests.json`과 `rag/`를 3차에서 그대로 복사했습니다. `/rag`는 다시 부르지 않으므로 프롬프트가 글자까지 같습니다.
- **반복 조건:** 순차 5번, mixed 5번(동시 4개), same 4번입니다. 질의마다 14번, 모두 1,400건입니다.
- **mixed 묶음:** 3차와 같은 질의끼리 묶입니다. 회차 번호를 시드로 섞기 때문입니다.
- **스크립트:** 3차 스크립트를 그대로 복사했습니다. 결과 파일은 이 폴더에 따로 쌓입니다.

## 실행

```bash
cd /Users/seo/Developer/automl/sql-eval-harness/repeat_query_test/tts_val100_merge
nohup caffeinate -i ./run_merge.sh > run_merge.log 2>&1 &
tail -f run_merge.log
```

- `/rag`를 부르지 않으므로 `TTS_API_KEY`와 `TTS_URL`은 필요 없습니다.
- 중간에 끊기면 같은 명령으로 다시 실행하면 됩니다. 이미 받은 응답은 건너뜁니다.
- 3차는 순차 50분, 병렬 35분이 걸렸습니다. 실제로는 순차 46.4분, 병렬 32.4분이 걸렸습니다. 결과는 `report_summary.md`를 보세요.

## 실행 전 확인

```bash
# batch-invariant 모드가 꺼져 있는지: 아무것도 안 나와야 함 (서버에서)
docker exec vllm-serve sh -c 'tr "\0" "\n" < /proc/1/environ | grep VLLM_BATCH'

# 병합본인지: root 가 …/merged, parent 가 null 이어야 함
curl -s http://10.1.1.69:8007/v1/models | python3 -m json.tool

# 요청 모델 이름(by-loss)이 등록돼 있는지 (서버에서)
curl -s localhost:8007/v1/models | python3 -m json.tool | grep '"id"'
```
