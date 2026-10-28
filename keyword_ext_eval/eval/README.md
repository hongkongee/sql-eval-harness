# 키워드 추출 API 커버리지 평가

키워드 추출 API(`POST /keyword-extraction`, gliner-entity-router의 `app/`)가 내는 **schema 키워드**가 정답 SQL이 쓰는 테이블을 얼마나 가리키는지 잽니다. 사전(`schema_keywords.yaml`)을 반복해서 보강할 때 씁니다. 비교 기준선으로 zero-shot GLiNER(스키마 라벨)와 개발서버 Qwen을 같은 기준으로 채점합니다.

- **기준점은 실행 중인 API의 응답입니다.** 평가 도구에는 사전 매칭 로직이 없습니다. 사전 파일은 키워드가 어느 묶음에 속하는지 판정할 때 읽기만 합니다.
- **추출과 채점이 분리돼 있습니다.** 세 추출기는 같은 형식의 JSONL을 내고, 채점기는 그 파일만 읽습니다.
- 서비스 코드와 사전은 수정하지 않습니다.

모든 명령은 `keyword_ext_eval/`에서 실행합니다. Python은 `../.venv`를 쓰고(`make`가 자동으로 고릅니다), 필요한 패키지는 `requirements.txt`에 있습니다.

## 지금 가능한 것 / 서버가 필요한 것

| 명령 | 지금 | 필요한 것 |
|---|---|---|
| `make extract-api` | ✅ | 키워드 추출 API(:8001). gliner-entity-router에서 `docker compose up -d keyword-extraction` |
| `make extract-gliner` | ✅ (CPU) | GLiNER `/extract` 하네스(:8000). `docker compose up -d entity-router` (multi-v2.1) |
| `make extract-qwen` | ❌ | 개발서버 Qwen 접근 (`QWEN_BASE_URL`, `QWEN_MODEL`) |
| `make extract-qwen-mock` | ✅ | 없음. 가짜 응답으로 흐름만 확인 (`qwen_mock.jsonl`) |
| `make score` | ✅ | `eval/outputs/`에 결과 파일 |
| `make candidates` | Qwen 결과가 있을 때 | `eval/outputs/qwen.jsonl`, `api.jsonl` |
| `make loop` | ✅ (candidates는 Qwen 결과가 있을 때만) | API |
| `make test` | ✅ | 없음 (가짜 서버, mock 사용) |

변수는 이렇게 바꿉니다: `make extract-api DATA="../test_set/slot.jsonl" EXTRA="--limit 10"`.

- `DATA`: 평가 데이터. 기본값은 `../test_set/`의 시드(`proposed_input_train`, `proposed_input_val`)와 변형 테스트셋(`paraphrase`, `restructure`, `concept`, `slot`)을 합친 2,236건입니다.
- `OUT`: 결과 폴더. 기본값 `eval/outputs`.
- `RUN_DIR`: 채점 결과 폴더. 기본값 `eval/runs/<타임스탬프>`.
- `QWEN_OUT`: Qwen 결과 파일. 기본값 `eval/outputs/qwen.jsonl`. 모델을 바꿀 때 따로 둡니다.
- 서버 주소, 모델, 시스템 프롬프트는 make 변수가 아니라 `.env`에서 읽습니다 (아래 "설정" 참고).
- `SERVICE_DIR`: gliner-entity-router 경로. 기본값 `../../../gliner-entity-router`.

## 설정 (`.env`)

서버 주소, 모델명, 시스템 프롬프트 같은 설정은 `keyword_ext_eval/.env`에 둡니다. 세 CLI가 실행될 때 이 파일을 읽습니다.

```bash
cp .env.example .env   # 값을 채운다. .env는 .gitignore 처리돼 있음
```

- 형식은 `scripts/eval_api_model.py`의 `.env`와 같습니다: `KEY=VALUE`, `#` 주석, 값 앞뒤 따옴표 허용, 한 줄 값 안의 리터럴 `\n`은 줄바꿈으로 바뀜.
- **셸에서 `export`한 값이 `.env`보다 우선합니다.** 빈 값은 없는 것으로 봅니다.
- 상대 경로는 `keyword_ext_eval/` 기준입니다.

| 이름 | 기본값 | 용도 |
|---|---|---|
| `KEYWORD_API_URL` | `http://localhost:8001` | 기준 API |
| `KEYWORD_API_CONTAINER` | `gliner-entity-router-keyword-extraction-1` | API가 쓰는 사전 해시·설정을 `docker exec`로 읽을 컨테이너 |
| `SCHEMA_KEYWORDS_PATH` | `../../../gliner-entity-router/app/config/schema_keywords.yaml` | 사전 파일 (읽기 전용) |
| `KEYWORD_SERVICE_DIR` | `../../../gliner-entity-router` | 서비스 `settings.py` 기본값을 읽을 위치 |
| `GLINER_EXTRACT_URL` | `http://localhost:8000` | GLiNER 기준선 (`entity-router-biomed`를 쓰려면 `:8002`) |
| `QWEN_BASE_URL` | 없음 (필수) | 예: `http://<서버 IP>:<포트>/v1`. 요청은 `{QWEN_BASE_URL}/chat/completions`로 갑니다 |
| `QWEN_MODEL` | 없음 (필수) | vLLM의 served model name. 지금은 `Flash-Next-FP8` |
| `QWEN_API_KEY` | 없음 (선택) | 있으면 `Authorization: Bearer …` 헤더로 보냅니다 |
| `QWEN_SYSTEM_PROMPT_FILE` | 없음 | 시스템 프롬프트 파일(여러 줄 가능). `.env.example`은 임시 파일 `eval/prompts/qwen_system_temp.txt`를 가리킴 |
| `QWEN_SYSTEM_PROMPT` | 없음 | 시스템 프롬프트 한 줄 값(리터럴 `\n` 허용). `_FILE`이 있으면 무시 |
| `QWEN_PROMPT_FILE` | `eval/prompts/qwen_schema_keywords.txt` | 작업 프롬프트(지시·예시·`{text}`) |
| `QWEN_MAX_TOKENS` / `QWEN_TIMEOUT` / `QWEN_MAX_RETRIES` | 512 / 60초 / 4 | 요청 옵션 |
| `QWEN_CONCURRENCY` | 4 | 동시 요청 수 (`--concurrency`가 우선) |
| `QWEN_EXTRA_BODY` | 없음 | 요청 본문에 합칠 추가 필드(JSON). 예: `{"chat_template_kwargs": {"enable_thinking": false}}` |

## 1. 추출 — `python -m eval.extract`

```bash
python -m eval.extract --system {api|gliner|qwen} --data <경로> [--data ...] --out eval/outputs/<이름>.jsonl \
    [--limit N] [--overwrite] [--concurrency N] [--timeout S]
```

결과는 질의당 한 줄입니다.

```json
{"id": "paraphrase:seed_3_test_paraphrase", "dataset": "paraphrase", "system": "api",
 "schema_keywords": ["투약", "환자"],
 "concept_spans": [{"text": "발사르탄", "start": 0, "end": 4, "score": 0.96, "label": null}],
 "latency_ms": 712.3, "attempts": 1}
```

- **id는 `<데이터 파일 이름>:<원래 id>`입니다.** 파일마다 id 체계가 달라서(시드는 정수) 여러 파일을 섞어도 겹치지 않게 했습니다. 한 파일 안에 같은 id가 또 나오면 `#2`를 붙입니다. 지금은 `restructure`의 `seed_528`, `concept`의 `seed_420`이 해당합니다.
- `schema_keywords`는 표면형 기준으로 중복을 제거해 처음 나온 순서대로 담습니다.
- 시스템마다 추가 필드가 있습니다.
  - gliner: `schema_labels`(`[{text, label, score}]`)
  - qwen: `keyword_tables`(모델이 단 테이블 추측. 채점에는 쓰지 않음), `dropped_keywords`(질의에 글자 그대로 없어서 버린 단어)
- `<이름>.meta.json`에는 시스템, 실행 시각(세션별), 하드웨어, 설정을 담습니다.
  - api: API URL, 사전 경로, 로컬 사전 해시와 API 컨테이너 사전 해시, 일치 여부, GLiNER 모델·라벨·threshold. 컨테이너 환경변수를 먼저 보고, 없으면 서비스 `settings.py` 기본값을 import 없이 읽습니다.
  - gliner: URL, 모델명(`/health` 응답), 라벨, threshold
  - qwen: base URL, 모델, 프롬프트 파일 해시, temperature, max_tokens
- `<이름>.failed.jsonl`에는 실패한 id와 에러, Qwen 원문 응답(`raw`)을 남깁니다.
- **이어하기를 지원합니다.** 결과 파일에 이미 있는 id는 건너뜁니다. 실패한 id는 결과 파일에 쓰지 않으므로 다시 실행하면 그것만 다시 시도합니다. 사전 해시, 모델, 라벨, threshold, 프롬프트 중 하나라도 기존 meta와 다르면 결과가 섞이지 않도록 멈춥니다. 이때는 `--overwrite`로 새로 시작하거나 `--out`을 바꿉니다.

### api (기준점)
- 실행 중인 API에 질의를 그대로 보내고 응답의 schema/concept span을 기록합니다.
- **`latency_ms`는 HTTP 왕복 시간입니다.** 클라이언트에서 잰 값이라 네트워크와 직렬화가 포함되고, 서버 내부 추론 시간과는 다릅니다. 같은 기계에서 잰 값끼리만 비교하세요.
- API가 떠 있지 않으면 `/health` 확인 단계에서 안내 메시지를 내고 종료 코드 2로 끝납니다.
- 시작할 때 **API 컨테이너 안의 사전 해시와 현재 사전 파일 해시를 비교**합니다. 다르면 경고하고, `--strict-dict`(`make loop`가 씀)를 주면 중단합니다.

### gliner (비교 기준선)
- gliner-entity-router의 eval 전용 하네스(`service/`, `POST /extract`)를 HTTP로 호출합니다. 로컬에 torch를 설치할 필요가 없습니다.
- 라벨은 `환자 또는 대상자, 진단 행위, 처방 또는 투약 행위, 측정 또는 검사 행위`, threshold는 0.3입니다. 둘 다 요청마다 보내므로 컨테이너 기본값과 상관없습니다. `--labels`, `--threshold`로 바꿀 수 있습니다.
- 모델을 바꾸려면 컨테이너를 바꿉니다. 기본값은 `entity-router`(:8000)의 `urchade/gliner_multi-v2.1`이고, `GLINER_EXTRACT_URL=http://localhost:8002`로 주면 BioMed 컨테이너를 씁니다. 출력 파일명을 `gliner_biomed.jsonl`처럼 바꾸면 채점 표에 시스템이 따로 나옵니다.

### qwen (비교 기준선, 서버 필요)
- **가정:** OpenAI 호환 chat completions(vLLM)를 씁니다. 레포의 기존 호출 코드(`adapter_prompt_eval/inference.py`, `scripts/eval_api_model.py`)와 같은 방식입니다: `temperature 0`, `choices[0].message.content`.
- **메시지 구성:** 질의 하나당 `[system, user]` 두 메시지를 보냅니다.
  ```json
  {"model": "<QWEN_MODEL>", "temperature": 0, "max_tokens": 512,
   "messages": [
     {"role": "system", "content": "<QWEN_SYSTEM_PROMPT_FILE 내용>"},
     {"role": "user",   "content": "<작업 지시 + 예시 1개>\n\n질의: <평가할 자연어>"}]}
  ```
  - **작업 지시(테이블 8개 설명, 추출 규칙, 출력 형식, 예시)는 user 쪽에 있습니다.** 그래서 시스템 프롬프트를 확정된 것으로 바꿔도 지시는 그대로 남습니다.
  - **시스템 프롬프트는 아직 임시입니다** (`eval/prompts/qwen_system_temp.txt`). 실행할 때마다 경고를 냅니다. 확정되면 파일 내용을 교체하거나 `QWEN_SYSTEM_PROMPT_FILE`을 바꿉니다. 우선순위는 `QWEN_SYSTEM_PROMPT_FILE` > `QWEN_SYSTEM_PROMPT` > 작업 프롬프트 파일의 `### SYSTEM` > 없음(user만 보냄)입니다.
  - **작업 프롬프트도 초안입니다** (`eval/prompts/qwen_schema_keywords.txt`). 레포에 기존 키워드 추출 프롬프트가 없어서 새로 썼습니다. `### USER` / `### ASSISTANT` 줄로 메시지를 더 나눌 수 있고, 마지막 USER의 `{text}`에 질의가 들어갑니다.
  - 출력 형식은 `{"schema_keywords": [{"text", "table"}]}`이고, 질의에 글자 그대로 있는 단어만 남깁니다.
  - 사전 표면형 목록은 일부러 프롬프트에 넣지 않았습니다. Qwen이 사전에 없는 표현을 찾게 하는 것이 목적이기 때문입니다.
- **모델·프롬프트 변경:**
  - 실제로 보내는 메시지 전체의 해시, 모델명, max_tokens, extra_body가 기존 결과와 다르면 이어하기를 멈춥니다. 섞이지 않게 하기 위해서입니다.
  - 모델을 바꿀 때는 결과 파일을 따로 두는 것을 권장합니다: `make extract-qwen QWEN_OUT=eval/outputs/qwen_<모델>.jsonl`. `make score`는 `eval/outputs/`의 파일을 모두 채점하므로 모델끼리 나란히 비교됩니다. `make candidates`도 `QWEN_OUT`을 따릅니다.
  - 추론(thinking) 모델이 답 앞에 `<think>…</think>`를 붙여도 떼고 파싱합니다. thinking을 끄는 옵션이 필요하면 `QWEN_EXTRA_BODY`로 넣습니다.
- **재시도:** 타임아웃, 연결 오류, 408/409/425/429/5xx는 지수 백오프(1s, 2s, 4s, 8s…)로 다시 보냅니다. 기본 `--max-retries 4`입니다. 그 밖의 4xx와 파싱 실패는 temperature 0이라 다시 보내도 같은 결과가 나오므로 바로 실패 처리합니다.
- **동시 요청:** `--concurrency`로 정합니다. `make`의 기본값은 `QWEN_CONCURRENCY=4`입니다.
- **mock:** `--mock`을 주면 서버 없이 질의 속 일부 단어를 돌려주는 가짜 응답으로 실행합니다. 흐름 확인용입니다.

## 2. 채점 — `python -m eval.score`

```bash
python -m eval.score --data <경로> [--data ...] --pred eval/outputs/api.jsonl [--pred ...] [--concept] [--run-dir DIR]
```

**판정은 테이블 단위 커버리지입니다.** 정답 SQL이 쓰는 대상 테이블마다, 그 테이블을 가리키는 키워드가 하나 이상 있으면 덮인 것으로 봅니다.

- **대상 테이블 8개:** person, observation_period, visit_occurrence, condition_occurrence, drug_exposure, procedure_occurrence, measurement, death. concept, concept_ancestor 같은 어휘 테이블은 뺍니다.
- **정답 SQL에서 테이블 뽑기** (`eval/sql_tables.py`):
  - sqlglot(PostgreSQL)의 scope 분석을 씁니다. CTE 이름은 테이블로 세지 않고, 서브쿼리·UNION·EXISTS 안쪽까지 들어갑니다. 별칭, 스키마 접두어, 따옴표를 처리하고 소문자로 맞춥니다.
  - 결과는 `eval/.cache/sql_tables.json`에 캐시합니다. sqlglot 버전이 바뀌면 캐시를 버립니다.
  - 파싱에 실패한 SQL은 `sql_parse_failures.csv`로 따로 냅니다. 지금 기본 데이터 2,236건은 실패 0건입니다.
- **키워드에서 테이블 판정** (`eval/keyword_map.py`): 표면형 → 사전 묶음(`schema_keywords.yaml`을 읽음) → 테이블(`eval/maps/schema_keyword_table_map.yaml`) 순서입니다.
  - 사전에 있는데 매핑에 없는 묶음은 경고합니다.
  - 사전에 없는 단어(GLiNER·Qwen 결과)는 단어 안에 사전 표면형이 들어 있으면 그 묶음으로 봅니다. 긴 표면형을 먼저 보고, 겹치지 않으면 여러 개도 됩니다. 예: "심부전 진단" → 진단. 하나도 없으면 **미매핑 단어**로 집계하고, 테이블을 덮지 못한 것으로 칩니다.
  - `추적기간: []`처럼 테이블이 없는 묶음은 미매핑이 아닙니다.
- **변형:** pred 파일 하나에서 여러 줄이 나옵니다. 시스템 이름은 pred 파일 이름입니다.
  - `<이름>`: schema_keywords 기준
  - `<이름>_label`: gliner의 `schema_labels`로 판정 (`eval/maps/gliner_schema_label_table_map.yaml`)
  - `<이름>_concept`: `--concept`이고 concept span에 `label`이 있을 때, schema에 concept 라벨(`eval/maps/concept_label_table_map.yaml`)을 더해 판정. **지금 API에는 label이 없어서** "라벨 없음으로 계산 불가" 경고만 내고 스키마 커버리지만 냅니다. label 필드가 생기면 코드 변경 없이 바로 계산됩니다.
- **지표** (변형마다, 데이터 파일별과 전체):
  - 질의 단위 커버리지: 정답 테이블이 **모두** 덮인 질의 비율
  - 테이블별 재현율 8개
  - 템플릿 중복 제거 버전: 날짜·숫자와 concept를 가린 문장 기준으로 첫 질의만 남긴 뒤 같은 지표. concept 문자열은 데이터의 `input`([재료] 개념 값 조건)에서 가져와 시스템과 무관하게 같은 기준을 씁니다. `input`이 없는 데이터에서는 API의 concept span을 씁니다.
  - 잡음: 정답에 없는 테이블만 가리키는 키워드 수. 오류가 아니라 참고 지표입니다.
  - 처리 속도: `latency_ms` 평균과 p95
  - pred가 없는 질의는 평가에서 빼고, 건수를 경고로 냅니다.

**출력** (`eval/runs/<타임스탬프>/`):

| 파일 | 내용 |
|---|---|
| `scores.json` | 모든 지표, 미매핑 단어 빈도, 실행 메타데이터 |
| `scores.md` | 시스템 비교 표 (커버리지 / 테이블별 재현율 / 데이터 파일별 / 잡음 / 속도 / 미매핑 상위 / 메타 요약) |
| `misses_<시스템>.csv` | 덮이지 않은 (질의, 테이블) 쌍. 누락 테이블 순으로 정렬. 열: `missing_table, id, dataset, text, gold_tables, schema_keywords, pred_tables, missing_tables` |
| `diff_prev_<시스템>.md` | 같은 시스템의 직전 run 대비 새로 덮인 질의 / 새로 깨진 질의(회귀) |
| `unmapped_<시스템>.csv` | 미매핑 단어와 빈도 |
| `per_query_<시스템>.jsonl` | 질의별 판정. 다음 run의 diff 기준 |

CSV는 엑셀에서 바로 열리도록 UTF-8 BOM으로 저장합니다.

## 3. 보강 후보 — `python -m eval.candidates`

```bash
python -m eval.candidates --data <경로> --base eval/outputs/api.jsonl --ref eval/outputs/qwen.jsonl [--out ...] [--concept-min-score 0.3]
```

- ref(Qwen)는 뽑았는데 base(API)의 schema_keywords에는 없는 단어를 모읍니다.
- 이미 사전에 있는 표면형, 질의 안에서 base의 concept span과 겹치는 단어는 뺍니다.
- `candidates.csv`의 열: `candidate, count, gold_tables`(그 단어가 나온 문장의 정답 테이블 분포), `ref_tables`(Qwen이 단 테이블), `contains_dict_group`(단어 안에 든 기존 묶음. "처방 이력"처럼 이미 덮이는 확장형을 걸러 볼 때), `example_1~3`. count 내림차순입니다.
- `--concept-min-score`: API threshold가 0.1로 낮아서 "이력", "코호트" 같은 일반 단어가 낮은 점수의 concept로 잡히는 경우가 있습니다(스모크 테스트에서 확인). 그러면 그 단어가 후보에서 빠지므로, 이 값 미만인 concept span은 겹침 판정에 쓰지 않게 합니다. 기본값 0은 모든 span을 씁니다.
- **사전에 자동으로 추가하지 않습니다.** 사람이 검토해서 넣습니다.

## 4. 사전 보강 루프

1. `schema_keywords.yaml`을 수정합니다. 새 묶음을 추가했다면 `eval/maps/schema_keyword_table_map.yaml`에도 추가합니다.
2. **API를 다시 빌드합니다.** API는 사전을 프로세스에 캐시하고, 사전 파일이 Docker 이미지에 들어 있어서 볼륨 마운트가 없습니다. 그래서 재시작만으로는 반영되지 않습니다.
   ```bash
   cd ../../../gliner-entity-router && docker compose up -d --build keyword-extraction
   ```
3. `make loop`를 실행합니다. 내부적으로 `extract-api --overwrite --strict-dict` → `score` → `candidates` 순서로 돕니다. API 사전 해시가 현재 파일과 다르면(재빌드를 안 했으면) 추출 단계에서 중단합니다.
4. `scores.md`, `misses_api.csv`, `diff_prev_api.md`(회귀 확인), `candidates.csv`를 검토합니다.
5. 1번으로 돌아가 반복합니다.

## 5. 정답 CSV 채점과 운영 LLM 기준선 — `python -m eval.csv_keyword_eval`

사람이 만든 키워드 정답 CSV(`../test_set/keyword_ext/keyword_eval_samples_50.csv`)로 schema / concept(GLiNER) / concept(Visit·Gender) / 테이블을 따로 채점합니다. API 리비전(v1, v2 …)과 운영 LLM을 같은 기준으로 비교합니다.

```bash
C=../test_set/keyword_ext/keyword_eval_samples_50.csv
# 키워드 추출 API (지금 떠 있는 리비전)
python -m eval.csv_keyword_eval extract --csv $C --out eval/outputs/kw50_api_v2.jsonl
# 운영 LLM (설정은 .env의 PROD_LLM_*, 시스템 프롬프트는 eval/prompts/prod_llm_system.local.txt)
python -m eval.csv_keyword_eval extract --system prod-llm --csv $C --out eval/outputs/kw50_prod_llm.jsonl --concurrency 4
python -m eval.csv_keyword_eval extract --system prod-llm --mock --csv $C --out /tmp/llm_mock.jsonl   # 서버 없이 흐름 확인
# 채점 (같은 채점기)
python -m eval.csv_keyword_eval score --csv $C --pred eval/outputs/kw50_prod_llm.jsonl --out-dir eval/runs/kw50_prod_llm
```

- 운영 LLM 응답은 API와 같은 spans 형식으로 바꿔 저장합니다. LLM이 위치를 주지 않으므로 질의에서 글자 그대로 찾아 붙이고, 못 찾은 단어는 `dropped`에 남깁니다. 원본 응답은 `raw`에 저장합니다.
- 응답 JSON은 `spans`, `schema_keywords`/`concept_keywords`(및 한국어 키), `{카테고리: [단어]}` 형식을 받습니다(`eval/extractors/prod_llm.py` 맨 위 설명 참고). 운영 출력 형식이 이와 다르면 `parse_response`를 맞추고 `tests/test_prod_llm.py`에 예시를 추가합니다.
- LLM의 카테고리 이름은 `eval/maps/llm_category_map.yaml`로 API 라벨에 맞춥니다.
- 이어하기: 모델·시스템 프롬프트·URL 같은 설정이 바뀐 상태로 같은 결과 파일에 이어 쓰면 멈춥니다. 모델이나 프롬프트를 바꾸면 결과 파일을 따로 둡니다.
- `--ignore-concept-label`: concept를 위치만으로 채점합니다(라벨 체계가 다른 LLM 비교용 참고 지표).
- 운영 시스템 프롬프트 파일(`*.local.txt`)은 .gitignore 대상입니다.

## concept span `label` 필드 (보류)

API 응답의 concept span에 GLiNER 라벨(지금 쓰는 4개 중 하나)을 같이 내서 concept도 테이블로 환산하자는 제안이 있었는데, **보류했습니다.** 이전 평가에서 BioMed의 라벨 정확도가 낮았기 때문입니다. 위치는 잘 찾지만 약물을 진단명으로 붙이는 경우가 많아서, 라벨을 테이블로 바꾸면 자주 틀립니다(`GLiNER_제로샷_키워드추출_평가보고서.md` 6절).

`--concept` 옵션은 라벨이 없으면 경고만 내고 스키마 커버리지만 내므로 그대로 둡니다.

## 파일 구조

```
keyword_ext_eval/
├── Makefile, pytest.ini, requirements.txt
├── .env.example           # 설정 템플릿 (복사해서 .env로, .env는 gitignore)
├── eval/
│   ├── extract.py / score.py / candidates.py     # CLI 3개
│   ├── extractors/{api,gliner,qwen}.py           # 추출기 (공통 출력 형식)
│   ├── extractors/prod_llm.py                    # 운영 LLM 기준선 (PROD_LLM_*)
│   ├── csv_keyword_eval.py                       # 정답 CSV 채점 (API 리비전·운영 LLM 비교)
│   ├── visit_gender_eval.py                      # GLiNER 방문·성별 라벨 제로샷 평가
│   ├── sql_tables.py      # 정답 SQL → 테이블 (sqlglot, 캐시)
│   ├── keyword_map.py     # 표면형 → 묶음 → 테이블
│   ├── httpclient.py      # 재시도·백오프 POST
│   ├── common.py          # 데이터 로딩, 해시, 하드웨어 정보
│   ├── maps/*.yaml        # 평가 전용 매핑 (llm_category_map.yaml 포함)
│   ├── prompts/qwen_schema_keywords.txt   # Qwen 작업 프롬프트 (초안)
│   ├── prompts/qwen_system_temp.txt       # Qwen 시스템 프롬프트 (임시, 확정 전)
│   ├── prompts/prod_llm_system.local.txt  # 운영 LLM 시스템 프롬프트 (직접 넣음, gitignore)
│   ├── outputs/  runs/  .cache/           # 산출물 (.gitignore)
└── tests/                 # 가짜 API·GLiNER 서버, Qwen mock, 샘플 8건 통합 테스트
```
