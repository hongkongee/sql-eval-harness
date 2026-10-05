# adapter_prompt_eval

[질의]/[재료] 형태의 프롬프트를 입력으로 받도록 파인튜닝한 모델(기존 방식이
아니라 "프롬프트 반영 + concept 랜덤화"로 학습한 새 방식 모델)을, **RAG를
붙이지 않고** 체크포인트(어댑터) 단독으로 테스트하기 위한 도구다. 모델은
로컬에서 로드하지 않고, `automl-llm/scripts/serve_vllm.sh`로 베이스 모델 +
체크포인트 여러 개를 이미 띄워둔 원격 vLLM 서버에 OpenAI 호환
`/v1/chat/completions`로 요청만 보낸다 (아래 "원격 서빙 전제" 참고).
`../scripts/`, `../eval_harness/`가 이미 하는 일(API로 서빙 중인 모델 테스트,
EM/EX/Validity 채점기)과 겹치지 않는 부분만 새로 만들었고, 가능한 곳은 그대로
가져다 썼다 (아래 "기존 코드 재사용" 참고).

## 원격 서빙 전제

이 도구는 모델을 직접 로드하지 않는다. 아래처럼 베이스 모델 + 체크포인트들이
**이미 같은 vLLM 서버에 동시에 떠 있다고 가정**하고, 체크포인트별로 등록된
`model` 이름만 바꿔가며 HTTP 요청을 보낸다 (`automl-llm/README.md` "서빙"
섹션, `automl-llm/scripts/serve_vllm.sh` 참고):

```bash
# automl-llm 쪽에서 (베이스 모델 + best_by_loss/final_step/best_by_adherence 자동 등록)
./scripts/serve_vllm.sh -d
# → http://<서버 IP>:<VLLM_PORT>/v1 에서, model 필드: by-loss / final-step / by-adherence
```

등록된 모델 확인(`GET /v1/models`)이나 직접 curl로 찔러보면:

```bash
curl -s http://<vLLM 서버 IP>:<포트>/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model": "by-loss", "messages": [{"role": "user", "content": "여기에 NL2SQL 질문+스키마 input"}]}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

이 도구는 테스트 케이스마다 위 curl과 똑같은 요청을, `--adapter`로 지정한
체크포인트 수만큼(+ 기본적으로 베이스 모델까지 한 번 더) `model` 필드만 바꿔서
자동으로 반복한다 — `python run_eval.py --adapter a=X --adapter b=Y --testset t=f.jsonl`
한 번이면 체크포인트 2개 × 테스트셋 1개 = 2개의 결과 CSV가 나오고, 테스트셋을
여러 개 주면(`--testset t1=... --testset t2=...`) 체크포인트 수 × 테스트셋 수
만큼 CSV가 나온다. 여기에 베이스 모델 비교까지 켜져 있으면(기본값) 체크포인트
수에 +1이 된다.

## .env 설정

이 폴더 전용 설정은 `../.env`(공용 — `eval_api_model.py` 계열이 쓰는
`LLM_API_URL`, `SANDBOX_DB_*`)와 분리된 `adapter_prompt_eval/.env`에 둔다 —
이 도구가 말 거는 vLLM 서버(체크포인트 여러 개를 동시에 올려둔 평가용 서버)는
보통 운영 서빙 엔드포인트(`LLM_API_URL`)와 다른 서버이기 때문이다. 샌드박스
DB 설정(`SANDBOX_DB_*`)은 여러 도구가 공유하는 설정이라 그대로 `../.env`에
남아있고, 이 도구도 그걸 그대로 읽는다 — `../.env`도 같이 채워둘 것.

```bash
cd adapter_prompt_eval
cp .env.example .env   # VLLM_HOST/VLLM_PORT/CHECKPOINT_*/BASE_MODEL_NAME 값 채우기
```

| 변수 | 의미 |
|---|---|
| `VLLM_HOST` / `VLLM_PORT` | 체크포인트들을 서빙 중인 vLLM 서버 주소. `http://{HOST}:{PORT}/v1/chat/completions`로 조립해 기본 `--api-url`로 쓴다 |
| `CHECKPOINT_EVAL_LOSS` / `CHECKPOINT_CONCEPT_ID` / `CHECKPOINT_FINAL_STEP` | `serve_vllm.sh`가 등록한 체크포인트별 served model 이름. `--adapter`를 하나도 안 주면 이 중 값이 채워진 것만 자동으로 쓴다 |
| `BASE_MODEL_NAME` | 베이스 모델(파인튜닝 전) 자체의 served model 이름(`serve_vllm.sh`의 `{STUDY_NAME}`). 값이 있으면 `--no-base`를 안 주는 한 체크포인트들과 나란히 자동으로 비교 평가된다 |

세 `CHECKPOINT_*` 전부와 `BASE_MODEL_NAME`을 채워두면, `--adapter`/`--api-url`
없이 `--testset`만 주고 돌려도 체크포인트 3개 + 베이스 모델까지 자동으로
비교된다 (아래 "사용법"의 첫 예시).

## 이 도구가 하는 일

같은 파인튜닝 run에서 고른 체크포인트 여러 개(보통 3개: eval_loss 최저 /
concept-id score 최고 / final step)를, 사용자가 지정한 테스트셋 파일
여러 개(학습셋 재현 / MPX 독립 테스트셋 / LLM 생성 테스트셋 등)에 대해
한 번에 돌려서 아래를 측정한다.

| 분류 | 지표 | 비고 |
|---|---|---|
| SQL Validity | 문법 (sqlglot) | 항상 실행 |
| | 샌드박스 DB 실행검증 (EXPLAIN) | `SANDBOX_DB_HOST` 등 미설정 시 자동 skip |
| 쿼리문 하위 전개 반영도 | concept_ancestor 서브쿼리로 하위 개념까지 확장했는가 | 개념 값 조건(앵커)이 있는 케이스에서만 |
| 프롬프트 반영도 — concept-id Adherence | Presence / Correctness / Usage | 정의는 `automl-llm/scripts/compute_adherence.py`와 동일 (아래 참고) |
| 프롬프트 반영도 — 스키마 Adherence | Presence / Correctness / Usage | 재료에 나열된 테이블/컬럼/조인 범위 준수 여부 |
| EM / EX | 테스트 케이스에 정답 SQL(`query`)이 있을 때만 | `../scripts/eval_api_model.py`의 채점 로직 재사용 |
| 응답 속도 | 체크포인트별 API 호출(`/v1/chat/completions`) 소요 시간 | |

## 테스트셋 파일 스키마

JSONL, 한 줄에 한 케이스. **두 가지 형태 중 하나**를 쓰면 된다 — 어느 쪽을
쓰든 이 스크립트가 내부적으로 같은 최종 프롬프트("[질의]\n{text}\n\n[재료]\n...")로
조립한 뒤 똑같이 채점한다 (`adherence.build_prompt()`).

### A. 학습 데이터셋과 동일한 필드로 주기 (권장)

automl-llm이 실제로 학습에 쓰는 물리 필드명을 그대로 쓴다 —
`automl-llm/data/datasets/dataset_info.json`에 등록된 `nl_sql_train`/`nl_sql_val`
기준으로 `"prompt"` 역할 = `text` 필드, `"query"` 역할(재료) = `input` 필드,
`"response"` 역할(정답) = `query` 필드다. 실제 `nl_sql_val.jsonl`의 한 줄:

```json
{"id": "...", "text": "외래 방문 방문이고 입원 방문인 환자.", "input": "[재료]\n개념 값 조건:\n  - \"외래 방문\" → visit_occurrence.visit_concept_id IN (9202)\n  ...\n테이블(컬럼 전체):\n  ...\n조인:\n  ...", "query": "SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (...)"}
```

- **`text`** (별칭 `instruction`도 허용): 자연어 질의. 최종 프롬프트의
  `[질의]` 아래에 그대로 들어간다.
- **`input`** (별칭 `materials`도 허용): 재료 텍스트. 이미 `[재료]`로
  시작하면(실제 데이터셋이 그렇다) 그대로 이어붙이고, 안 그러면 이 스크립트가
  `[재료]\n`를 자동으로 붙인다.
- **`query`** (별칭 `output`도 허용): 정답 SQL. 모르면(LLM 생성 테스트셋에서
  아직 검증 안 된 신규 질의 등) 빈 문자열로 두면 EM/EX가 자동으로 "N/A"
  처리된다.
- **`id`**: 결과 CSV에서 문항을 식별하는 키. (원본 데이터셋에 `scenario_name`
  등 다른 필드가 더 있어도 무시되니, 학습용 jsonl을 그대로 가리켜도 된다.)

### B. 이미 조립된 프롬프트로 주기

RAG API가 실시간으로 돌려준 프롬프트를 캡처해 저장해둔 경우처럼, `[질의]`/`[재료]`가
이미 합쳐진 한 덩어리 텍스트가 있으면 `prompt` 필드에 그대로 넣는다 — 있으면
이 필드를 최우선으로 쓰고 `text`/`input`은 보지 않는다:

```json
{"id": "seed_001", "prompt": "[질의]\n당뇨 환자의 사망일\n\n[재료]\n개념 값 조건:\n  ...", "query": "SELECT ... (정답 SQL, 모르면 \"\")"}
```

둘 다 `[재료]`가 전혀 없으면(순수 자연어 질의만 있으면) concept-id/스키마
Adherence와 하위 전개 반영도는 전부 N/A 처리되고 SQL Validity/EM/EX만
채점된다.

세 가지 테스트셋(학습 데이터 재현 / MPX 독립 테스트셋 / LLM 생성 테스트셋)
전부 이 두 스키마 중 하나만 따르면 된다 — 이 스크립트는 파일 경로만 받고,
어떤 테스트셋인지는 `--testset LABEL=PATH`의 LABEL로만 구분한다(채점 로직
자체는 테스트셋 종류에 따라 달라지지 않음). 학습 데이터 재현 테스트는 사실상
`automl-llm/data/datasets/nl_sql_train.jsonl`(또는 그 일부)을 그대로
`--testset train_repro=...`에 넘기면 된다.

## 지표 정의 (Presence / Correctness / Usage)

**concept-id Adherence**는 `automl-llm/scripts/compute_adherence.py`가 학습
중 checkpoint별 "Concept-ID Prompt Adherence"를 계산할 때 쓰는 정의를
그대로 가져왔다 — 체크포인트 선택 기준(학습 쪽)과 이 평가(평가 쪽)가 같은
잣대를 쓰지 않으면 "concept-id score가 가장 높아서 고른 체크포인트"라는
선택이 이 평가에서 재현되지 않기 때문이다. 앵커(재료의 "개념 값 조건:" 한
줄) 하나당:

- **presence**: 정답 concept_id 값이 생성 SQL 어딘가에 등장하는가
- **usage**: 같은 컬럼(테이블/alias 접두사 무시)에 연산자(IN/=)로 값이
  바인딩된 "슬롯"이 SQL에 존재하는가
- **correctness**: 그 슬롯에 들어간 값(들)이 정답 concept_id(들)과 정확히
  일치하는가 (슬롯이 없으면 correctness도 거짓)

**쿼리문 하위 전개 반영도**는 그 슬롯 안에 `concept_ancestor` 테이블 참조가
있는지만 추가로 본다 — usage/correctness와 독립적인 축이다(올바른 값을
리터럴 IN으로 써도 usage/correctness는 참이지만 하위 전개는 안 한 것이고,
반대로 엉뚱한 값을 서브쿼리로 써도 하위 전개는 했지만 correctness는 거짓).

**스키마 Adherence**는 같은 presence/correctness/usage 틀을 재료의
테이블/컬럼/조인에 적용한, 이 프로젝트에서 새로 정의한 지표다 (코드 작성
시점의 해석이니 실제 데이터로 돌려보고 다르게 쓰고 싶으면 `adherence.py`의
`score_schema_adherence()`만 고치면 됨):

- **presence**: 재료가 준 테이블을 하나라도 실제로 썼는가 (완전히 무시하고
  엉뚱한 테이블만 참조한 경우를 잡는다)
- **correctness**: 참조한 모든 테이블/컬럼이 재료 범위 안에 있는가 (재료 밖
  테이블/컬럼 참조 = DB에 실재하는 테이블이라도 이 질의 기준으로는 환각).
  단, `concept_ancestor`는 재료 목록에 없어도 시스템 프롬프트가 하위 개념
  확장용으로 항상 쓰라고 지시하는 테이블이라 예외로 허용한다.
- **usage**: 재료가 준 테이블을 2개 이상 썼다면, 표를 잇는 데 쓴 기준 항목이
  모두 재료의 조인 목록과 맞는가. 연결 조건은 `JOIN ... ON a.x = b.x`뿐 아니라
  `EXISTS`/`WHERE` 안의 `a.x = b.x`(상관 서브쿼리), `a.x IN (SELECT x FROM b ...)`
  형태도 모두 본다 (CTE/서브쿼리 별칭은 원본 테이블까지 되짚음). `_id`로 끝나는
  항목끼리의 조건만 연결로 보고(날짜가 같은 기록을 찾는 조건 등은 제외), 재료의
  조인으로 이어지는 항목끼리는 직접 나열되지 않아도 맞는 연결로 본다(예: 둘 다
  `person.person_id`와 이어지는 두 테이블의 `person_id`). 테이블이 1개뿐이거나,
  재료에 조인 정보가 없거나, 연결 조건 없이 UNION 등으로만 합친 경우는 N/A.
  기존 결과 CSV를 이 기준으로 다시 채점하려면 `rescore_schema.py`를 쓴다
  (모델 재호출 없음). 정답 SQL로 채점하면 평가 대상 전부가 통과한다
  (proposed_input_train 406/406, proposed_input_val 46/46).

concept-id Adherence는 케이스 하나에 앵커가 여러 개면 그 평균 "비율"(0~1)로
기록되고, 스키마 Adherence는 SQL 1건당 단일 pass/fail/N/A로 기록된다 —
둘의 성격이 달라서(개념 조건은 여러 개일 수 있지만 "이 SQL이 재료 범위를
지켰는가"는 SQL 하나당 하나의 판정) CSV 컬럼 포맷도 다르다.

## 사용법

```bash
cd adapter_prompt_eval
pip install -r requirements.txt
cp .env.example .env         # VLLM_HOST/VLLM_PORT/CHECKPOINT_*/BASE_MODEL_NAME 채우기
cp ../.env.example ../.env   # 아직 없다면 (SANDBOX_DB_* 등 공용 설정)

# .env를 다 채웠다면 테스트셋만 지정해도 체크포인트 3개 + 베이스 모델이 전부 돌아간다
python run_eval.py \
    --testset train_repro=/path/to/train_subset.jsonl \
    --testset independent=/path/to/mpx_testset.jsonl \
    --testset llm_generated=/path/to/llm_generated_testset.jsonl

# api-url/adapter/testset만 명시하고 나머지(베이스 모델 비교 여부 등)는 .env 기본값 그대로.
# --base-model-name을 안 줬어도 .env에 BASE_MODEL_NAME이 있으면 베이스 모델이 자동으로 붙는다.
python run_eval.py \
    --api-url http://<vLLM 서버 IP>:<포트>/v1/chat/completions \
    --adapter eval_loss=by-loss \
    --adapter concept_id=by-adherence \
    --adapter final_step=final-step \
    --testset train_repro=/path/to/train_subset.jsonl \
    --testset independent=/path/to/mpx_testset.jsonl \
    --testset llm_generated=/path/to/llm_generated_testset.jsonl

# 스모크 테스트 (한 테스트셋 앞 5건만, 체크포인트 1개만, 베이스 모델 비교는 끔)
python run_eval.py \
    --adapter final_step=final-step \
    --no-base \
    --testset smoke=/path/to/testset.jsonl \
    --limit 5
```

- `--adapter`는 `LABEL=MODEL_NAME` 형태로 여러 번 지정한다. `MODEL_NAME`은
  로컬 경로가 아니라 **원격 vLLM 서버에 등록된 served model 이름**이다
  (`serve_vllm.sh`가 등록하는 `by-loss`/`final-step`/`by-adherence`). `LABEL`은
  결과 파일 이름/CSV의 "체크포인트" 컬럼에 쓰이는 식별자일 뿐이라 자유롭게
  붙이면 된다 (`=`가 없으면 `MODEL_NAME` 자체를 라벨로도 쓴다). 생략하면
  `.env`의 `CHECKPOINT_EVAL_LOSS`/`CHECKPOINT_CONCEPT_ID`/`CHECKPOINT_FINAL_STEP`
  중 값이 채워진 것만 기본값으로 쓴다.
- **베이스 모델(파인튜닝 전) 자체도 기본적으로 같이 비교 평가된다** —
  `--base-model-name`(또는 `.env`의 `BASE_MODEL_NAME`)에 served model 이름을
  주면(`serve_vllm.sh`의 `{STUDY_NAME}`) 체크포인트들 뒤에 `체크포인트=base`로
  자동 추가된다. 끄려면 `--no-base`. **이건 `--api-url`/`--adapter`를 CLI로
  명시했는지와 무관하게 독립적으로 적용된다** — 위 두 번째 예시처럼
  `--api-url`/`--adapter`만 CLI로 주고 `--base-model-name`을 안 줘도,
  `.env`에 `BASE_MODEL_NAME`이 설정돼 있으면 베이스 모델이 자동으로
  섞여 들어간다. 베이스 모델을 빼고 싶으면 CLI 인자를 얼마나 명시했든
  관계없이 `--no-base`를 따로 줘야 한다.
- `--testset`은 `LABEL=PATH` 형태로 여러 번 지정한다 (`=`가 없으면 파일명이
  LABEL이 된다). **체크포인트 수 × 테스트셋 수**만큼 결과 CSV가 생성된다 —
  예를 들어 체크포인트 3개(+베이스 모델 1개) × 테스트셋 3개면 CSV 12개.
- `--api-url`을 생략하면 `.env`의 `VLLM_HOST`/`VLLM_PORT`로 조립한 URL을 쓴다.
- `--system-prompt`를 생략하면 system 메시지 없이 조립된 프롬프트 전체를
  user 메시지로 그대로 보낸다 — `automl-llm/scripts/compute_adherence.py`가
  학습 데이터의 instruction+input을 system 메시지 없이 단일 user 메시지로
  합쳐서 검증하는 방식과 맞춘 것이다. 실제 학습 때 별도 system 메시지를
  썼다면 `--system-prompt`로 지정할 것.
- `--concurrency`로 체크포인트 1개당 동시 요청 수를 올릴 수 있다 (vLLM이
  continuous batching을 지원하면 5~10 권장 — `eval_api_model.py`/
  `eval_api_model_rag.py`와 동일한 옵션). 단, `serve_vllm.sh`는 `--max-loras`를
  지정하지 않아 vLLM 기본값(1)을 쓴다 — **같은 체크포인트로 가는 동시 요청은**
  vLLM이 continuous batching으로 잘 묶어 처리하지만, **서로 다른 체크포인트로
  가는 요청을 동시에 섞으면** 배치에 LoRA가 1개만 들어갈 수 있어 내부적으로
  어댑터를 번갈아 교체하느라 비효율적일 수 있다. 이 스크립트는 체크포인트를
  한 번에 하나씩만 순회하며 그 안에서만 동시 요청을 보내므로(코드 구조상
  체크포인트 간에는 겹치지 않음) 이 제약과 자연스럽게 맞게 돼 있다 — 여러
  체크포인트를 동시에 섞어 보내고 싶다면 `serve_vllm.sh`의 vLLM 실행 인자에
  `--max-loras`를 체크포인트 수만큼 올려야 한다.
- `--resume`을 주면 체크포인트×테스트셋 조합별 결과 CSV가 이미 있을 때 그
  안에 담긴 `id`는 다시 호출하지 않고 나머지만 이어서 돌린다(새 행은 파일
  끝에 append) — API 중간 에러나 프로세스 중단 후 재실행할 때 전체를 처음부터
  다시 돌리지 않아도 된다. 기본값(=`--resume` 없음)은 항상 새로 덮어쓰기이다.
  기존 CSV의 컬럼 구성이 지금 버전과 다르면(옛 버전으로 만든 파일 등) 덮어쓰기
  전에 바로 에러를 내고 멈춘다.
- 결과는 `../results/adapter_eval_<체크포인트>_<테스트셋>.csv`(문항별 상세)와
  `../results/adapter_eval_summary_<시각>.json`(체크포인트×테스트셋 전체 집계)에
  저장된다. `../results/`는 이미 `.gitignore` 처리돼 있다.
  실행이 끝난 결과는 `../results/adapter_eval/{train,val,variant,summaries,prompts}/`로
  옮겨서 보관한다(평가 보고서는 저장소 루트의 `reports/`).

## 기존 코드 재사용

- SQL 문법 검사(sqlglot), 샌드박스 DB 실행검증(EXPLAIN), EM, EX, 그리고 `.env`
  로더 자체(`_load_dotenv`)는 `../scripts/eval_api_model.py`를 그대로
  import해서 쓴다 (`eval_api_model_rag.py`가 이미 쓰는 것과 같은 패턴:
  `sys.path.insert(...); import eval_api_model as base`). import 시점에
  `../.env`(공용 — `SANDBOX_DB_*` 등)가 먼저 로드되고, 그 뒤 같은 로더로
  `adapter_prompt_eval/.env`(이 폴더 전용 — `VLLM_HOST`/`CHECKPOINT_*`/
  `BASE_MODEL_NAME`)를 추가로 로드한다.
- `/v1/chat/completions` 호출 자체(`inference.py`)도 `eval_api_model.py`의
  `call_model()`과 같은 요청 형태를 쓴다 — 차이는 system 메시지 기본값(이
  도구는 기본적으로 안 보냄, 아래 "사용법" 참고)뿐이다.
- `eval_harness/`(`DATABASE_URL` 기반)는 쓰지 않는다 — 이 폴더는 `.env`의
  `SANDBOX_DB_*` 변수(= `eval_api_model.py` 계열이 쓰는 방식)로 통일했다.

## 알려진 한계

- 스키마/조인/앵커 파싱은 전부 "재료" 텍스트의 고정 포맷(`개념 값 조건:` /
  `테이블(컬럼 전체):` / `조인:` 섹션 헤더와 들여쓰기)에 의존하는 정규식
  기반 휴리스틱이다. RAG가 이 포맷을 바꾸면 `adherence.py`의
  `parse_anchors`/`parse_schema_section`/`parse_joins_section`도 같이
  고쳐야 한다.
- Join 일치 여부(`스키마 Usage`)는 `ON a.col = b.col` 형태의 단순 등호
  조인만 인식한다. `USING(...)`나 복합 조건 조인은 "일치 조인 0개"로
  과소평가될 수 있다.
- EM/EX는 정답 SQL(`query`)이 있는 케이스에서만 채점된다 — LLM 생성
  테스트셋처럼 정답을 모르는 케이스는 N/A로 빠지고 나머지 지표만 본다.
- vLLM 서버가 `--adapter`로 지정한 모델 이름을 등록해두지 않았으면(오타,
  아직 `serve_vllm.sh`를 안 돌림 등) 매 요청이 API 에러로 실패하고 "비고"
  컬럼에 에러 메시지가 그대로 남는다 — 전부 fail로 나오면 `GET /v1/models`로
  등록된 이름부터 확인할 것.
