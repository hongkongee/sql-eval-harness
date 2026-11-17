# TTS 프롬프트 고정, 50개 질의 × 5번 순차 반복 (준비만 됨, 아직 실행 안 함)

TTS(`/Users/seo/Developer/mpx-cdm-tts`)가 `POST /nl2sql`에서 NL2SQL 모델에 보내는 것과 같은 요청을, 같은 프롬프트로 하나씩 순서대로 반복해 보냅니다. 병렬 영향을 빼고, temperature 0에서 모델 답이 갈리는지 봅니다.

## 순서

1. **프롬프트 고정 (`prepare.py`):** 질의마다 TTS `/rag`를 **한 번만** 불러 user 프롬프트를 받습니다(`rag/<qid>.json`). 실패한 질의(개념 못 찾음 등)는 버리고 다음 후보로 50개를 채웁니다. 호출 사이에 3초 쉽니다.
2. **LLM 순차 반복 (`run_seq.py`):** 고정한 요청을 질의마다 5번, 한 번에 하나씩 모델 서버에 보냅니다. `/rag`는 다시 부르지 않습니다.
3. **정리 (`analyze.py`):** `report.md`, `summary.json`을 만듭니다.

## TTS와 같은 요청을 만드는 방법

따라 만든 사본이 아니라 TTS 프로젝트 코드를 직접 import 해서 씁니다(`common.py`).

| 항목 | 출처 (TTS 코드) |
|---|---|
| system + user 메시지 | `app/services/text2sql/prompt_builder.build_messages(materials, dialect=NL2SQL_SQL_DIALECT, mask=True)` — `/nl2sql`의 `generator.generate_sql`과 같은 호출 |
| user 내용 | `/rag` 응답의 `prompt` (TTS 안에서 `_render_materials`로 만든 것) |
| 요청 본문 | `client.ChatClient.complete`와 같은 `{model, messages, max_tokens, temperature}` |
| 설정값 | `app/core/config.py`: `NL2SQL_BASE_URL`, `NL2SQL_MODEL`, `NL2SQL_TEMPERATURE`, `NL2SQL_MAX_TOKENS` (지금 값: `http://10.1.1.69:8007/v1`, `by-loss`, `0.0`, `4096`) |
| 긴 concept_id 목록 | `mask=True`로 `:CONCEPT_IDS_N`으로 가려 보내고, 응답 뒤 원래 id로 되돌림 (TTS와 같음) |

검증: 지난번 `tts_batch`의 `/rag` 응답 10개로 요청을 만들어 보니, 지난번 요청과 10개 모두 같았습니다.

## 병렬 영향을 빼는 방법

- 제 쪽에서는 한 번에 하나씩만 보냅니다.
- 다른 사용자나 TTS 요청이 모델 서버에 들어와 있으면 같이 묶여 처리될 수 있습니다. 그래서 보내기 전에 서버 `/metrics`의 처리 중·대기 요청이 0이 될 때까지 기다립니다(최대 120초).
- 처리되는 동안 0.5초마다 `/metrics`를 읽어 동시에 돈 요청 수의 최댓값을 기록합니다. 다른 요청과 겹친 회차는 `alone=False`로 표시되고, `report.md`에서 "혼자 처리된 요청만 봐도 갈렸는지"를 따로 셉니다.

## 실행 방법 (퇴근 전)

```bash
cd /Users/seo/Developer/automl/sql-eval-harness/repeat_query_test/tts_seq50
export TTS_API_KEY='<TTS API 키>'               # 환경변수로만 받음, 파일에 저장하지 않음
nohup ./run_all.sh > run_all.log 2>&1 &         # 터미널을 닫아도 계속 돎
tail -f run_all.log                             # 진행 상황 (남은 시간 표시)
```

- 노트북이 잠들면 멈춥니다. 맥이면 `caffeinate -i ./run_all.sh`처럼 실행하거나 전원을 연결해 두세요.
  예: `nohup caffeinate -i ./run_all.sh > run_all.log 2>&1 &`
- 중간에 끊겨도 같은 명령으로 다시 실행하면 이어서 합니다. 이미 받은 `/rag` 응답과 끝난 회차는 건너뜁니다.
- 예상 시간: `/rag` 50~60번(약 5~10분) + LLM 250번(요청당 평균 약 9초, 약 40분) ≈ **1시간 안쪽**. 서버가 바쁘면 기다리는 만큼 늘어납니다.

옵션(환경변수):

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `N` | 50 | 질의 수 |
| `REPS` | 5 | 질의당 반복 횟수 |
| `SOURCE` | `tts` | `tts` = TTS `tests/test_queries_100.txt`(실제 서비스 질의, 정답 없음, 섞어서 고름) / `testset` = `test_set/eval_ready/`(정답 있음, 4종 번갈아) |
| `DELAY` | 3 | `/rag` 호출 간격(초) |
| `IDLE_WAIT` | 120 | 서버가 비기를 기다리는 최대 시간(초) |
| `TTS_URL` | `http://10.1.1.69:8080` | `/rag`를 부를 TTS 서버 |

## 병렬 시험 (순차 시험이 끝난 뒤)

같은 고정 프롬프트(`requests.json`)로 4개씩 동시에 보내고, 순차 답과 비교합니다. `/rag`는 다시 부르지 않습니다.

```bash
nohup caffeinate -i ./run_par_all.sh > run_par.log 2>&1 &
tail -f run_par.log
```

- **동시 4개로 정한 이유:** TTS의 LLM 동시 실행 상한이 기본 4입니다(`config.py`의 `LLM_CONCURRENCY=4`). 실제 서비스에서 모델 서버로 동시에 갈 수 있는 최대치와 같습니다.
- **mixed:** 라운드마다 질의 순서를 섞어 4개씩 묶어 동시에 보냅니다. 같은 질의가 라운드마다 다른 질의들과 함께 처리됩니다(여러 사용자가 동시에 쓰는 상황). 5라운드라 질의당 답이 5개 나옵니다. 50개를 4개씩 묶으면 라운드마다 마지막 묶음은 2개입니다.
- **same:** 같은 질의 요청 4개를 동시에 보냅니다. 질의당 답이 4개 나옵니다.
- 묶음을 보내기 전에 서버가 빌 때까지 기다리고, 묶음 안의 4개는 같은 순간에 출발시킵니다. 처리 중 동시 요청 수가 4를 넘거나 대기가 생기면 외부 요청이 섞인 것으로 표시합니다(`only_ours`).
- **결과 (`report_par.md`):**
  - 순차 답에 없던 "새 답"이 몇 건 나왔는지
  - 순차에선 5번 다 같았는데 병렬에서 달라진 질의가 몇 개인지
  - 갈린 답의 첫 차이와 샌드박스 실행 결과
- **예상 시간:** mixed 65묶음 + same 50묶음, 묶음당 약 10~15초 → **약 25~30분**.
- 옵션(환경변수): `CONC=4`, `REPS=5`, `MODE=both|mixed|same`, `IDLE_WAIT=120`
- 순차와 병렬을 이어서 돌리려면: `nohup caffeinate -i sh -c './run_all.sh && ./run_par_all.sh' > run_both.log 2>&1 &`

## 결과 파일

| 파일 | 내용 |
|---|---|
| `rag/<qid>.json` | 질의, `/rag` 요청·응답 (실패한 것 포함) |
| `requests.json` | 질의별 고정 요청 본문 + 자리표시자 복원맵 |
| `responses.jsonl` | 응답 한 건당 한 줄: SQL, 소요 시간, 토큰 수, 보내기 전 서버 부하, 처리 중 최대 동시 요청 수, `alone` |
| `report.md` | 갈린 질의, 회차별 답(ABBBB 형식), 첫 차이 부분, 답별 샌드박스 실행 결과 |
| `summary.json` | report의 원자료 |
| `run_all.log` | 실행 로그 |
| `responses_par.jsonl` | 병렬 응답 한 건당 한 줄: 모드, 묶음 id, 같이 보낸 질의들, SQL, 최대 동시 처리 수, `only_ours` |
| `report_par.md`, `summary_par.json` | 병렬 결과와 순차 비교 |
| `run_par.log` | 병렬 실행 로그 |
