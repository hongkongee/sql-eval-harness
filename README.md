# sql-eval-harness

NL-to-SQL 시스템의 성능을 **EM / EX / SQL Validity**로 채점하는, 시스템에 종속되지 않는 평가 도구입니다.
베이스 모델 zero-shot, RAG 파이프라인, [automl-llm](../automl-llm)으로 파인튜닝한 모델 등 — SQL을 생성하는 방식이 무엇이든 상관없이, 동일한 테스트셋·DB·채점 로직으로 공정하게 비교하기 위해 만들었습니다.

## 설계: 예측 결과만 받는다

이 도구는 "SQL이 어떻게 생성됐는지"는 전혀 모릅니다. 아래 스키마의 `predictions.jsonl` 파일만 받으면 채점합니다.

```json
{"id": "seed_001", "predicted_sql": "SELECT COUNT(*) FROM person"}
```

평가하려는 시스템(automl-llm이든, RAG 프로젝트든) 쪽에서 `data/testset.jsonl`의 각 `id`에 대해 SQL을 생성해 이 형식으로 저장하기만 하면 됩니다. 이 harness가 소유하는 것은:

- **테스트셋** (`data/testset.jsonl`) — 자연어 질문 + 정답 SQL + 메타데이터
- **DB 스키마 원본** (`data/fixtures/*.sql`) — 샌드박스 PostgreSQL DB를 준비할 때 쓰는 스키마+샘플데이터 원본 문서 (harness가 자동으로 적재하지는 않음)
- **채점 로직** (`eval_harness/`) — Validity / EM / EX 계산

## 지표 정의

| 지표 | 의미 | 계산 방식 |
|---|---|---|
| **SQL Validity** | 문법적으로 컴파일 가능한 SQL인가 | 샌드박스 PostgreSQL DB에서 `EXPLAIN <sql>` 실행 성공 여부 (`eval_harness/validity.py`) |
| **EM** (Exact Match) | 정답 SQL과 문자열이 일치하는가 | 공백/대소문자/후행 세미콜론 정규화 후 문자열 비교 (`eval_harness/exact_match.py`) |
| **EX** (Execution Accuracy) | 실행 결과가 정답과 같은가 | 샌드박스 PostgreSQL DB에서 둘 다 실행해 결과 행 비교. 정답에 `ORDER BY`가 있으면 순서까지, 없으면 순서 무관 비교 (`eval_harness/execution.py`) |

**알아둘 점**: EM은 문자열 정규화 비교라 의미는 같지만 표현이 다른 쿼리(컬럼 순서, 별칭 등)는 불일치로 잡힙니다. 그래서 EM만으로 판단하지 말고 EX와 같이 보는 걸 권장합니다 — EM은 낮아도 EX가 높으면 "표현은 다르지만 결과는 맞는" 경우일 수 있습니다.

## 사용법

```bash
pip install -r requirements.txt

# testset의 db_id가 가리키는 샌드박스 PostgreSQL DB 접속 정보
export DATABASE_URL="postgresql://user:password@localhost:5432/sandbox_db"

# 예시 예측 결과로 스모크 테스트 (테스트셋 10개 중 5개만 채점됨)
python -m eval_harness.score \
    --predictions examples/predictions.example.jsonl

# 실제 시스템의 예측 결과 채점 + 상세 리포트 저장
python -m eval_harness.score \
    --predictions /path/to/your_system_predictions.jsonl \
    --report report.json
```

`DATABASE_URL`이 가리키는 PostgreSQL DB에 스키마+데이터가 미리 적재되어 있어야 합니다. 지금 testset은 OMOP CDM v5.3 스키마(`data/fixtures/omop_cdm_v53_ddl.sql`, 테이블 정의만 있고 데이터는 없음 — 실제 데이터는 Synthea 등으로 별도 ETL해서 샌드박스에 적재)를 기준으로 합니다. Validity/EX 모두 이 DB에 연결해 검증하며, `eval_harness/db.py`의 `DB_REGISTRY`는 testset의 `db_id`가 이 DB에 실제로 준비돼 있는지 확인하는 용도로만 쓰입니다.

## LoRA 파인튜닝 모델 추론 + 평가

[automl-llm](../automl-llm)에서 LLaMA Factory로 학습한 산출물(`output/<study>/best_model/`)은 병합된 모델이 아니라 `adapter_config.json` + `adapter_model.safetensors` 형태의 **PEFT LoRA adapter**입니다. `scripts/infer_lora.py`가 베이스 모델 위에 이 adapter를 얹어 테스트셋 질문에 대한 SQL을 생성하고 `predictions.jsonl`을 만들어줍니다.

### 스모크 테스트 (파이프라인이 도는지만 빠르게 확인)

```bash
pip install -r scripts/requirements-infer.txt

# 앞 5문항만 빠르게 돌려서 추론 → 채점 파이프라인이 정상 동작하는지 확인
python scripts/infer_lora.py \
    --adapter /path/to/output/<study>/best_model \
    --testset data/testset.jsonl \
    --output predictions_smoke.jsonl \
    --limit 5

python -m eval_harness.score \
    --testset data/testset.jsonl \
    --predictions predictions_smoke.jsonl
```

### 실제 모델 평가 (전체 테스트셋)

운영에 올릴 모델을 실제로 평가할 때는 `--limit`을 빼서 테스트셋 전체(현재 10문항)를 돌리고, `--report`로 문항별 상세 결과를 남깁니다.

```bash
python scripts/infer_lora.py \
    --adapter /path/to/output/<study>/best_model \
    --testset data/testset.jsonl \
    --output predictions.jsonl

python -m eval_harness.score \
    --testset data/testset.jsonl \
    --predictions predictions.jsonl \
    --report report.json
```

`--base-model`을 생략하면 adapter 디렉토리의 `adapter_config.json`에 적힌 `base_model_name_or_path`(예: `Qwen/Qwen2.5-0.5B-Instruct`)를 그대로 씁니다. 프롬프트는 adapter 디렉토리에 같이 저장된 `chat_template.jinja`를 tokenizer가 그대로 읽어 적용하므로, 학습 때와 동일한 형식으로 질문이 들어갑니다.

여러 체크포인트/스터디를 비교하고 싶으면 `--adapter`와 `--output`만 바꿔가며 여러 번 돌린 뒤, 각 `report.json`의 `validity_rate`/`em_rate`/`ex_rate`를 비교하면 됩니다 (`--report` 경로를 매번 다르게 지정하세요, 안 그러면 덮어씌워집니다).

## 서빙 중인 모델을 API로 직접 평가 (Syntactic Validity / Format 이탈율 / 스키마 환각 / 응답 속도)

vLLM 등으로 OpenAI 호환 `/v1/chat/completions` API로 서빙 중인 파인튜닝 모델을, EM/EX 없이 **SQL 생성 품질만** 빠르게 점검하고 싶을 때 쓴다. `eval_harness/`와 달리 샌드박스 PostgreSQL DB 접속이 필요 없고, `sqlglot` 정적 분석만으로 4개 지표를 CSV로 뽑는다:

- **Syntactic Validity**: `sqlglot`으로 파싱 가능한 SQL인가
- **Format 이탈율**: SQL이 아닌 자연어로 응답한 비율
- **참조 테이블/컬럼 정확도**: `data/fixtures/omop_cdm_v53_ddl.sql` 기준 존재하지 않는 테이블/컬럼 참조(환각) 여부
- **응답 속도**: API 호출 1건당 걸린 시간

모델이 IN절 concept_id 자리에 의도적으로 남기는 `{{개념명}}` 자연어 플레이스홀더는 검사 전 더미값 `0`으로 치환해 문법/스키마 오류로 오탐되지 않게 한다.

테스트 케이스는 `data/260914/auto_confirmed_val_260914.jsonl`의 증강 paraphrase(1012건)는 건너뛰고 시나리오별 고유 질의(`is_original=true`, 68건)만 쓰며, 데이터셋에 없는 신규 질의 10개(`data/custom_eval_queries.jsonl`, 도메인 이탈·모호한 질의 등 포함)를 더해 총 78건을 평가한다.

```bash
pip install -r scripts/requirements-eval-api.txt
cp .env.example .env   # LLM/RAG 엔드포인트, 샌드박스 DB 등 설정 (필요시 값 수정)

# 스모크 테스트 (앞 5건만)
python scripts/eval_api_model.py --limit 5 --output results/eval_smoke.csv

# 전체 평가 — HARD 난이도 등 응답이 길어서 SQL문법 fail이 많이 뜨면 --max-tokens를 올릴 것.
# --output 생략 시 results/eval_results.csv에 저장됨 (디렉터리는 자동 생성).
python scripts/eval_api_model.py --max-tokens 512

# 문항이 많아 오래 걸리면 --concurrency로 동시 요청 (LLM API가 감당 가능한 선에서 5~10 권장)
python scripts/eval_api_model.py --max-tokens 512 --concurrency 5
```

같은 방식으로 `scripts/eval_api_model_rag.py`(자연어 질의를 RAG API에 먼저 보내 프롬프트를 조립한 뒤 LLM에 넣는 파이프라인)도 `--concurrency`를 지원하며, 결과는 기본적으로 `results/eval_results_rag.csv`에 저장된다. `results/`는 실행할 때마다 쌓이는 산출물이라 `.gitignore` 처리되어 있다.

`--api-url`/`--model`로 다른 엔드포인트·모델명을 지정할 수 있고, `--skip-dataset`/`--skip-custom`으로 한쪽만 돌릴 수도 있다. 결과 CSV 컬럼: 자연어 질의, 모델 답변 쿼리문, 정답 쿼리문(신규 질의는 빈칸), SQL문법 결과/에러 사유, omop-cdm 스키마 오류 여부/에러 사유, 응답 속도, 비고(출처 시나리오·항목·경고).

## 구조

```
.
├── data/
│   ├── testset.jsonl              # 10개 NL→SQL 문항 (id, text, query, db_id, tables, difficulty, domain 등). db_id="omop_cdm_v53"
│   ├── omop_seed_dataset_10.jsonl # testset.jsonl의 원본 소스 (scenario_name/query_type 등 원본 메타데이터 그대로 보존, 참고용)
│   ├── 260914/auto_confirmed_val_260914.jsonl  # automl-llm 파인튜닝 시 validation으로 쓴 데이터셋 (시나리오별 원본 68건 + 증강 paraphrase, 총 1012건)
│   ├── custom_eval_queries.jsonl  # eval_api_model.py용 신규 작성 질의 10건 (데이터셋에 없는 도메인/모호한 질의 등)
│   └── fixtures/
│       └── omop_cdm_v53_ddl.sql   # OMOP CDM v5.3 스키마 정의 (테이블만, 데이터는 없음 — @cdmDatabaseSchema. 플레이스홀더를 public.으로 치환해둔 상태)
├── eval_harness/
│   ├── db.py                  # db_id → 샌드박스 PostgreSQL 커넥션 (DATABASE_URL 사용, 신규 도메인 추가 시 DB_REGISTRY에 등록)
│   ├── validity.py            # SQL Validity
│   ├── exact_match.py         # EM
│   ├── execution.py           # EX
│   └── score.py                # CLI 진입점
├── scripts/
│   ├── infer_lora.py          # LoRA adapter로 predictions.jsonl 생성 (--limit으로 스모크 테스트, 생략하면 전체 평가)
│   ├── requirements-infer.txt # infer_lora.py 전용 의존성 (torch/transformers/peft — 채점 로직과 분리)
│   ├── eval_api_model.py      # 서빙 중인 모델을 API로 호출해 Syntactic Validity/Format 이탈율/스키마 환각/응답 속도를 CSV로 평가
│   └── requirements-eval-api.txt  # eval_api_model.py 전용 의존성 (requests/sqlglot)
└── examples/
    └── predictions.example.jsonl  # 스모크 테스트용 샘플 예측 (일부러 EM만 실패/문법 오류 케이스 포함)
```

## 새 도메인(DB) 추가하기

1. `data/fixtures/<db_id>_ddl.sql`에 스키마(`CREATE TABLE`) 작성 — 데이터까지 작은 규모로 손으로 채울 수 있으면 `INSERT`도 같이, OMOP처럼 실제 데이터를 별도 ETL로 적재하는 경우 스키마만
2. 샌드박스 PostgreSQL DB(`DATABASE_URL`)에 해당 스키마+데이터를 적재 (`psql "$DATABASE_URL" -f data/fixtures/<db_id>_ddl.sql` 및 필요 시 별도 데이터 적재 과정)
3. `eval_harness/db.py`의 `DB_REGISTRY`에 등록
4. `data/testset.jsonl`에 해당 `db_id`를 참조하는 문항 추가

## 알려진 한계

- 지금 `data/testset.jsonl`(10문항) 중 `seed_003, 005, 006, 007, 008, 010`(당뇨/고혈압/메트포르민/HbA1c를 참조하는 문항)은 샌드박스 DB에 해당 concept_id(제2형 당뇨 `201826`, 고혈압 `316866`, 메트포르민 `1503297`, HbA1c `3004410`)를 가진 데이터가 전혀 없어 **정답 쿼리 자체가 항상 빈 결과(0 rows)** 를 반환합니다. 문법적으로는 유효하고 EM 비교에는 문제없지만, EX는 "둘 다 빈 결과"인 경우를 구분 못하므로 이 6문항은 EX 변별력이 낮습니다 (틀린 로직의 예측 SQL이라도 우연히 빈 결과면 EX가 통과됨). 실제 로드된 데이터는 비뇨기·호흡기 계열 급성질환(바이러스성 부비동염, 급성 인두염, 기관지염 등) 위주의 Synthea 스타일 합성 데이터입니다.
- `data/testset.jsonl`은 지금 automl-llm의 어떤 파인튜닝 데이터셋에도 쓰인 적이 없어 data leakage 걱정은 없지만, 반대로 held-out 셋이 별도로 없습니다. 이 10문항으로 파인튜닝을 하게 되면 그 시점부터는 별도 held-out 셋을 만들어야 합니다.
- EX 비교는 결과 행 집합만 보고, `SELECT *`처럼 컬럼 구성 자체가 다른 경우까지는 검증하지 않습니다.
- 지금은 `omop_cdm_v53` 스키마 하나만 있습니다.
- 모든 db_id가 같은 `DATABASE_URL` 연결(=같은 DB) 안에서 채점됩니다. 도메인이 여러 개로 늘어나 테이블명이 겹치면 스키마(`search_path`) 분리가 필요합니다.
