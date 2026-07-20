# sql-eval-harness

NL-to-SQL 시스템의 성능을 **EM / EX / SQL Validity**로 채점하는, 시스템에 종속되지 않는 평가 도구입니다.
베이스 모델 zero-shot, RAG 파이프라인, [automl-llm](../automl-llm)으로 파인튜닝한 모델 등 — SQL을 생성하는 방식이 무엇이든 상관없이, 동일한 테스트셋·DB·채점 로직으로 공정하게 비교하기 위해 만들었습니다.

## 설계: 예측 결과만 받는다

이 도구는 "SQL이 어떻게 생성됐는지"는 전혀 모릅니다. 아래 스키마의 `predictions.jsonl` 파일만 받으면 채점합니다.

```json
{"id": "nlsql_001", "predicted_sql": "SELECT name FROM employees WHERE salary >= 50000000;"}
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

# 예시 예측 결과로 스모크 테스트 (테스트셋 30개 중 5개만 채점됨)
python -m eval_harness.score \
    --predictions examples/predictions.example.jsonl

# 실제 시스템의 예측 결과 채점 + 상세 리포트 저장
python -m eval_harness.score \
    --predictions /path/to/your_system_predictions.jsonl \
    --report report.json
```

`DATABASE_URL`이 가리키는 PostgreSQL DB에 `data/fixtures/*.sql`의 스키마+샘플데이터가 미리 적재되어 있어야 합니다 (예: `psql "$DATABASE_URL" -f data/fixtures/company_db.sql`). Validity/EX 모두 이 DB에 연결해 검증하며, `eval_harness/db.py`의 `DB_REGISTRY`는 testset의 `db_id`가 이 DB에 실제로 준비돼 있는지 확인하는 용도로만 쓰입니다.

## 구조

```
.
├── data/
│   ├── testset.jsonl          # 30개 NL→SQL 문항 (id, text, query, db_id, tables, difficulty, domain)
│   └── fixtures/
│       └── company_db.sql     # testset의 db_id="company_db"용 스키마+샘플데이터 원본 (샌드박스 DB 적재용, PostgreSQL 문법 호환)
├── eval_harness/
│   ├── db.py                  # db_id → 샌드박스 PostgreSQL 커넥션 (DATABASE_URL 사용, 신규 도메인 추가 시 DB_REGISTRY에 등록)
│   ├── validity.py            # SQL Validity
│   ├── exact_match.py         # EM
│   ├── execution.py           # EX
│   └── score.py                # CLI 진입점
└── examples/
    └── predictions.example.jsonl  # 스모크 테스트용 샘플 예측 (일부러 EM만 실패/문법 오류 케이스 포함)
```

## 새 도메인(DB) 추가하기

1. `data/fixtures/<db_id>.sql`에 `CREATE TABLE` + `INSERT` 작성
2. 샌드박스 PostgreSQL DB(`DATABASE_URL`)에 `psql "$DATABASE_URL" -f data/fixtures/<db_id>.sql`로 적재
3. `eval_harness/db.py`의 `DB_REGISTRY`에 등록
4. `data/testset.jsonl`에 해당 `db_id`를 참조하는 문항 추가

## 알려진 한계

- `data/testset.jsonl`은 지금 [automl-llm](../automl-llm)의 `data/datasets/nl_sql_demo.jsonl`과 동일한 30개 데모 문항입니다. 파인튜닝 학습에 이 30개를 그대로 쓰면 학습에 쓴 데이터로 평가하는 셈이라(data leakage) 점수가 실제보다 낙관적으로 나올 수 있습니다. 엄밀하게 하려면 이 테스트셋은 어떤 시스템의 학습/파인튜닝에도 쓰지 않는 **held-out 셋**으로 분리해서 관리하세요.
- EX 비교는 결과 행 집합만 보고, `SELECT *`처럼 컬럼 구성 자체가 다른 경우까지는 검증하지 않습니다.
- 지금은 `company_db` 스키마 하나만 있습니다.
- 모든 db_id가 같은 `DATABASE_URL` 연결(=같은 DB) 안에서 채점됩니다. 도메인이 여러 개로 늘어나 테이블명이 겹치면 스키마(`search_path`) 분리가 필요합니다.
