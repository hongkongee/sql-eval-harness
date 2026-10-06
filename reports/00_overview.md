# NL2SQL 어댑터 평가 — 종합 보고서

> 학습셋, validation 셋, 변형 테스트셋 결과를 한곳에서 비교하는 문서입니다. 핵심만 추린 요약은 [summary.md](summary.md)에 있습니다. 테스트셋별 상세 분석은 각 보고서에 있습니다.

## 보고서 목록

| 테스트셋 | 파일 | 데이터 | 문항 수 | 상태 |
|---|---|---|---:|---|
| 학습셋 | [01_train.md](01_train.md) | `test_set/proposed_input_train.jsonl` (실제 학습 데이터) | 612 | ✅ 완료 |
| validation 셋 | [02_val.md](02_val.md) | `test_set/proposed_input_val.jsonl` | 68 (집계 63*) | ✅ 완료 |
| 변형 · 자연어 패러프레이즈 | [03_test.md](03_test.md) 3.1절 | `test_set/paraphrase.jsonl` | 573 (집계 568*) | ✅ 완료 |
| 변형 · SQL 변형 | [03_test.md](03_test.md) 3.2절 | `test_set/restructure.jsonl` | 387 (집계 384*) | ✅ 완료 |
| 변형 · concept_id 변형 | [03_test.md](03_test.md) 3.4절 | `test_set/concept.jsonl` | 455 (집계 451*) | ✅ 완료 |
| 변형 · 슬롯 치환 (날짜·기간·나이·수치) | [03_test.md](03_test.md) 3.3절 | `test_set/slot.jsonl` | 141 (집계 138*) | ✅ 완료 |

변형 테스트셋은 학습 데이터를 네 가지 방식으로 변형한 파일 4개. 원본이 같아서 상세 분석은 `03_test.md` 한 문서에서 변형별 절로 나눠 비교합니다.

| 변형 | 확인하는 능력 | 특히 볼 지표 |
|---|---|---|
| 자연어 패러프레이즈 | 같은 뜻을 다른 말로 물어도 같은 SQL을 만드는가 | EX |
| SQL 변형 | 자연어·재료는 그대로 두고 정답 SQL만 같은 뜻의 다른 작성 방식으로 바꿉니다. 모델 입력이 원본과 같아서, 모델보다 채점 방식(EM과 EX의 차이)을 확인하는 변형입니다 | EX, EM |
| concept_id 변형 | 재료에 주어진 코드를 그대로 옮겨 쓰는가, 학습 때 외운 코드를 쓰는가 | concept_id Correctness, EX |
| 슬롯 치환 (날짜·기간·나이·수치) | 질문의 숫자 값(날짜, 추적기간, 나이, 검사 수치)을 바꿔도 SQL에 정확히 반영하는가. concept_id는 바꾸지 않습니다 | EX |

\* validation 셋 68건 중 5건(id 290·535·721·447·299)은 base+시스템 프롬프트의 few-shot 예시로 쓰였습니다. 공정한 비교를 위해 모든 모델에서 이 5건을 빼고 집계합니다. 변형 테스트셋도 같은 기준으로, 이 5건의 시드에서 나온 변형을 빼고 집계합니다.

## 평가 대상 모델

| 이름 | 설명 |
|---|---|
| FT0 (baseline·1ep) | input(재료) 없이 질문만으로 학습한 기준선 파인튜닝 모델. 재료를 넣는 학습 방식의 효과를 확인하는 용도입니다. 평가는 다른 모델과 똑같이 재료를 포함한 프롬프트로 합니다 |
| FT1 (input·1ep) | 첫 번째 LoRA 파인튜닝 모델(아래 파인튜닝 실험 목록 참고). 검증 손실(eval_loss)이 가장 낮은 체크포인트(`by-loss`)로 대표합니다* |
| FT2 (random·1ep) | concept_id 랜덤화 데이터로 학습한 파인튜닝 모델. `by-loss` 체크포인트만 평가합니다 |
| FT3 (random_augment·1ep) | FT2의 학습 데이터(`proposed_random`)를 증강한 데이터로 학습한 파인튜닝 모델 (⏳ 학습 중) |
| base | 파인튜닝 전 베이스 모델 (`XiYanSQL-QwenCoder-14B-2504`). 파인튜닝 모델과 같은 시스템 프롬프트(학습 때 문구)를 받습니다 |
| base+시스템 프롬프트 | 베이스 모델 + 직접 설계한 규칙·few-shot 시스템 프롬프트 ([요청 프롬프트 구성](#요청-프롬프트-구성)) |

\* FT1은 한 번의 학습에서 eval_loss / concept_id 반영도 / 마지막 지점 기준으로 체크포인트 3개를 뽑아 모두 평가했지만, 대부분의 문항에서 똑같은 SQL을 만들어 사실상 같은 모델이었습니다. 그래서 모든 표에서 eval_loss 체크포인트 하나로 적습니다(근거: [01_train.md](01_train.md) 3절).

### 파인튜닝 실험 목록

표에서는 짧은 ID로 적습니다. FT0 → FT1 → FT2 순서로 조건을 하나씩 더해서, 재료(input)와 concept_id 랜덤화가 각각 얼마나 효과가 있는지 비교합니다. 학습 조건을 바꿔 새로 학습할 때마다 한 줄씩 추가합니다. 학습 데이터 이름 뒤에 `_train`/`_val`을 붙인 파일이 각각 학습용과 검증용입니다.

- **공통 조건:** AutoML(HPO) trials 수 5로 고정

| ID | 학습 데이터 | epoch | 대표 체크포인트 (서빙 이름) | 상태 | 비고 |
|---|---|---:|---|---|---|
| FT0 | `baseline` (`proposed_input`과 같은 612건, input 없음) | 1 | eval_loss 최저 (`by-loss`) | ✅ 평가 완료 | 기준선. FT1과 학습 조건을 똑같이 맞추고 학습 데이터에서 input만 뺌. 평가 프롬프트는 동일 |
| FT1 | `proposed_input` (input에 RAG 프롬프트 포함, 증강 없음) | 1 | eval_loss 최저 (`by-loss`) | ✅ 평가 완료 | 빠른 검증용 첫 학습. 체크포인트 3개(`by-loss`·`by-adherence`·`final-step`)를 모두 평가했지만 사실상 같아서 하나로 대표 |
| FT2 | `proposed_random` (`proposed_input`의 concept_id를 랜덤화, 4배) | 1 | eval_loss 최저 (`by-loss`) | ✅ 평가 완료 | 빠른 테스트를 위해 `by-loss`만 평가. 학습 데이터 2,202건 = 원본 612 + 랜덤화 사본 3×530 |
| FT3 | `random_augment` (`proposed_random`을 증강) | 1 | eval_loss 최저 (`by-loss`) | ⏳ 학습 중 | 증강 방식과 학습 데이터 건수는 학습이 끝나면 적습니다 |

- 공통 설정: max_tokens 512, temperature 0, 동시 요청 1
- **모든 모델은 같은 사용자 메시지(질의 + 재료)를 받습니다. 다른 건 시스템 프롬프트뿐입니다.** 파인튜닝 모델과 base는 파인튜닝 학습 때 쓴 시스템 프롬프트(한 문단)를 받고, base+시스템 프롬프트는 그 대신 규칙과 few-shot이 담긴 긴 시스템 프롬프트를 받습니다. 이름의 "+시스템 프롬프트"는 이 차이를 뜻합니다(→ [요청 프롬프트 구성](#요청-프롬프트-구성)).

---

## 지표 설명

평가할 때 모델은 질문과 함께 **재료**를 받습니다. 재료에는 ① 질문에 필요한 의학 개념의 코드 번호(예: 발사르탄 → 약물 코드 1308842), ② 사용할 수 있는 테이블과 컬럼, ③ 테이블끼리 조인하는 방법(조인 키)이 들어 있습니다. 아래 지표들은 모델이 이 재료를 SQL에 제대로 반영했는지와, 최종 결과가 맞는지를 확인합니다.

### concept_id 반영도 — 재료의 개념 코드를 제대로 썼는가

**핵심 지표 (이 평가에서 가장 중요하게 보는 값)**

재료에 주어진 개념 코드를 "정답 SQL이 실제로 쓰는 코드(필요한 코드)"와 "정답이 쓰지 않는 코드(불필요한 코드)"로 나눠서 봅니다.

| 지표 | 의미 | 판정 방법 |
|---|---|---|
| **올바른 반영률** | 필요한 코드를 정답 형식으로, 실행되는 SQL에 넣었는가 | 필요한 코드마다 ① 해당 컬럼의 조건 안에 코드가 있고 ② 하위 전개(`concept_ancestor`) 형식이며 ③ SQL이 실행검증을 통과하면 통과. 필요한 코드 전체 중 통과 비율 |
| 필요한 코드 반영률 | 필요한 코드를 빠뜨리지 않았는가 (형식 무관) | 위 ①만 확인 |
| 불필요한 코드 사용률 | 정답이 쓰지 않는 코드를 넣었는가 (낮을수록 좋음) | 불필요한 코드 중 조건 안에 들어간 비율 |

- 올바른 반영률이 "프롬프트에 적힌 concept_id를 답변 쿼리에 알맞게 반영했는가"를 가장 직접적으로 보여줍니다.
- 필요한 코드 반영률과 올바른 반영률의 차이는 코드는 넣었지만 하위 전개를 하지 않았거나 SQL이 실행되지 않은 경우입니다.

**참고 지표 (Presence / Usage / Correctness)**

재료에 주어진 개념 코드 하나하나에 대해 아래 세 가지를 확인합니다. 필요한 코드와 불필요한 코드를 구분하지 않고, 하위 전개 여부와 실행 가능 여부도 보지 않습니다. 그래서 재료의 코드를 형식과 상관없이 다 넣는 모델이 점수를 더 받습니다. 참고용으로만 봅니다.

| 지표 | 의미 | 판정 방법 |
|---|---|---|
| Presence | 코드 번호가 SQL에 들어 있는가 | 생성된 SQL 어딘가에 그 코드 번호가 적혀 있으면 통과 |
| Usage | 그 코드로 대상을 거르는 조건을 실제로 걸었는가 | 해당 컬럼(예: `drug_concept_id`)에 `IN (...)` 같은 필터 조건이 있으면 통과. 들어간 코드 값이 맞는지는 보지 않습니다 |
| Correctness | 그 조건에 들어간 코드가 재료의 코드와 일치하는가 | 조건 안에 재료의 코드가 빠짐없이 들어 있으면 통과. 조건 자체가 없으면 실패 |

- **계산:** 한 문항에 코드가 여러 개면 코드별 통과 여부를 평균 내서 그 문항의 점수(0~1)로 삼습니다. 표의 값은 이 점수를 전체 문항에 대해 평균 낸 것입니다. 개념 코드가 있는 532문항만 대상입니다.
- **참고:** 재료에는 정답에 필요 없는 코드가 섞여 있을 때가 있어서, 정답 SQL도 100%가 나오지 않습니다(약 93%). 자세한 내용은 [학습셋 보고서](01_train.md) 4.1절에 있습니다.

### 스키마 반영도 — 재료가 허용한 테이블·컬럼·조인만 썼는가

문항마다 SQL 한 개에 대해 통과/실패를 한 번 판정합니다. 표의 값은 통과한 문항의 비율입니다.

| 지표 | 의미 | 판정 방법 |
|---|---|---|
| Presence | 재료의 테이블을 사용했는가 | 재료에 있는 테이블을 하나라도 썼으면 통과. 재료를 무시하고 다른 테이블만 쓰면 실패 |
| Correctness | 재료에 없는 테이블이나 컬럼을 쓰지 않았는가 | SQL에 쓴 테이블과 컬럼이 모두 재료 목록 안에 있으면 통과. 하나라도 재료 밖이면 실패 |
| Usage | 조인 키가 재료와 같은가 | 테이블을 2개 이상 쓴 문항만 평가합니다. 조인 조건의 컬럼 쌍(예: `drug_exposure.person_id = person.person_id`)이 재료에 적힌 조인 방법과 맞으면 통과. 의미가 다른 컬럼끼리 조인하면(예: `drug_exposure.visit_occurrence_id = person.person_id`) 실패. `JOIN ... ON`뿐 아니라 `EXISTS`·`IN (SELECT ...)` 안의 연결 조건도 조인으로 봅니다 |

- **참고:** 처음에는 Usage 계산이 조인 작성 방식 중 `JOIN ... ON`만 인식해서 정답 SQL도 대부분 실패로 나왔습니다. 지금은 고쳐서 정답 SQL이 모두 통과하고, 기존 결과도 이 기준으로 다시 채점했습니다([학습셋 보고서](01_train.md) 5절).

### 그 밖의 지표

| 지표 | 의미 |
|---|---|
| SQL 문법 | SQL 문장이 형식상 올바른가 |
| 샌드박스 실행검증 | 테스트용 데이터베이스에서 오류 없이 실행되는가. 결과가 맞는지는 보지 않습니다 |
| 하위 전개 반영도 | 재료에는 대표 코드(예: 고혈압)만 주어지는데, 그 아래 세부 코드(예: 이차성 고혈압)까지 포함하도록 조회했는가 |
| EM | 정답 SQL과 문장이 똑같은가. 결과가 같아도 작성 방식이 다르면 실패라서 실제 정확도보다 낮게 나옵니다 |
| EX | 정답 SQL과 실행 결과가 같은가. **실제 정확도를 가장 잘 보여주는 지표입니다** |

### 정답 SQL 채점값(참고)

각 보고서의 지표 표에 있는 열입니다. 테스트셋의 정답 SQL을 모델 답변과 같은 방식으로 채점한 값입니다. 재료에 정답에 필요 없는 코드가 섞여 있어서 정답 SQL도 concept_id 지표는 100%가 나오지 않습니다. 그래서 이 값은 "이 지표에서 현실적으로 기대할 수 있는 수준"을 보여주는 참고값입니다. 모델 점수가 이 값보다 높다고 정답보다 나은 건 아닙니다. 정답이 쓰지 않은 불필요한 코드까지 SQL에 넣었다는 뜻입니다.

---

## 테스트셋 간 비교

### EX (실행 결과 정확도)

| 모델 | 학습셋 | val | 패러프레이즈 | SQL 변형 | concept_id 변형 | 슬롯 치환 | 변형 전체(참고) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 62.58% | 63.49% | 66.90% | 69.27% | 53.22% | 64.49% | 63.27% |
| FT1 (input·1ep) | 71.57% | 74.60% | 76.06% | 81.51% | 72.28% | 51.45% | 74.11% |
| FT2 (random·1ep) | **94.12%** | **92.06%** | **90.32%** | **97.40%** | **92.90%** | **97.10%** | **93.45%** |
| base | 26.14% | 23.81% | 31.51% | 29.69% | 13.75% | 23.91% | 25.18% |
| base+시스템 프롬프트 | 66.18% | 63.49% | 73.77% | 75.00% | 66.52% | 60.87% | 70.80% |

- **모든 파인튜닝 모델과 base는 학습 때 쓴 시스템 프롬프트로 평가한 값입니다**([요청 프롬프트 구성](#요청-프롬프트-구성)). Qwen 기본 문구로 평가했던 기존 값(FT0 학습셋 56.5% / val 46.0%, FT1 68.0% / 58.7%, FT2 88.4% / 88.9%)보다 모두 높습니다.
- **FT2가 모든 테스트셋에서 가장 높습니다(90~97%).** 학습하지 않은 val과 변형 4개에서도 학습셋(94.1%)과 거의 같은 수준을 유지합니다.
- 모든 값은 전체 문항 기준입니다. 샌드박스 DB의 공유 메모리를 늘린 뒤 인프라 오류 문항을 다시 판정했습니다. 정답 쿼리가 무거워 재판정 때도 시간 초과가 난 문항(`seed_422_test_concept` 등, 모델별 0~3건)은 실패로 셌습니다. 모델 SQL이 30초 제한을 넘긴 경우는 너무 느린 SQL로 보고 실패로 셌습니다.
- "변형 전체(참고)"는 변형 테스트셋 4개를 합친 값입니다. 변형마다 문항 수와 난이도가 달라서 참고용으로만 봅니다. 판단은 변형별 열로 합니다.

### concept_id 핵심 지표

| 모델 | 학습셋 올바른 반영률 | val 올바른 반영률 | 학습셋 필요한 코드 반영률 | val 필요한 코드 반영률 | 학습셋 불필요한 코드 사용률 ↓ | val 불필요한 코드 사용률 ↓ |
|---|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 61.1% | 67.1% | 94.5% | 96.2% | 63.0% | 54.5% |
| FT1 (input·1ep) | 86.9% | 87.3% | 91.0% | 88.6% | 48.9% | 45.5% |
| FT2 (random·1ep) | **96.2%** | **94.9%** | 96.9% | 94.9% | **17.4%** | **36.4%** |
| base | 0.0% | 0.0% | **98.2%** | **100%** | 71.7% | 90.9% |
| base+시스템 프롬프트 | 90.8% | 93.7% | 94.3% | 94.9% | 67.4% | 81.8% |

- 분모: 학습셋 필요한 코드 731개·불필요한 코드 92개, val 필요한 코드 79개·불필요한 코드 11개(few-shot 5건 제외)입니다.
- **FT0는 코드를 찾는 건 잘하지만 정답 형식으로 옮기지 못합니다.** 재료의 리터럴 형식(`IN (9202)`)을 그대로 베껴서 하위 전개를 빠뜨리거나 괄호가 깨진 SQL을 만듭니다. 그래서 필요한 코드 반영률은 높지만 올바른 반영률은 61~67%에 그칩니다. 학습 때 재료를 같이 보여주는 기법(FT1·FT2)이 가르치는 게 바로 이 변환입니다.
- **base는 하위 전개를 전혀 하지 않아 올바른 반영률이 0%입니다.**
- **FT2는 세 지표 모두 가장 좋거나 거의 같습니다.** 필요한 코드는 빠뜨리지 않으면서 불필요한 코드는 가장 적게 씁니다. 변형 테스트셋에서도 올바른 반영률 96.6~99.2%입니다([03_test.md](03_test.md) 2.3절).

### 핵심 지표

**학습셋** (상세: [01_train.md](01_train.md))

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 94.28% | 86.93% | 73.24% | 94.70% | 94.28% | 34.64% | 62.58% |
| FT1 (input·1ep) | 98.69% | 92.97% | 92.79% | 89.29% | 98.53% | 33.01% | 71.57% |
| FT2 (random·1ep) | **99.84%** | **99.67%** | **96.91%** | 93.11% | **99.84%** | **77.45%** | **94.12%** |
| base | 99.67% | 91.50% | 0.00% | **97.15%** | 98.86% | 0.00% | 26.14% |
| base+시스템 프롬프트 | **99.84%** | 96.57% | 96.70% | 94.85% | 97.06% | 10.13% | 66.18% |

**validation 셋** (상세: [02_val.md](02_val.md), few-shot 5건 제외 63건)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 90.48% | 82.54% | 74.41% | 94.05% | 90.48% | 41.27% | 63.49% |
| FT1 (input·1ep) | **100%** | 96.83% | 91.38% | 86.02% | **100%** | 47.62% | 74.60% |
| FT2 (random·1ep) | **100%** | **100%** | **98.52%** | 91.38% | **100%** | **76.19%** | **92.06%** |
| base | **100%** | 93.65% | 0.00% | **99.41%** | 98.41% | 0.00% | 23.81% |
| base+시스템 프롬프트 | **100%** | 98.41% | 97.93% | 96.12% | 96.83% | 9.52% | 63.49% |

**변형 · 자연어 패러프레이즈** (상세: [03_test.md](03_test.md) 3.1절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 94.19% | 88.91% | 72.81% | 97.44% | 93.84% | 37.32% | 66.90% |
| FT1 (input·1ep) | 97.89% | 91.73% | 95.32% | 93.89% | 97.54% | 32.22% | 76.06% |
| FT2 (random·1ep) | 99.47% | **98.06%** | **98.16%** | 96.66% | **99.30%** | **65.85%** | **90.32%** |
| base | **99.82%** | 91.55% | 0.00% | **97.87%** | 98.06% | 0.00% | 31.51% |
| base+시스템 프롬프트 | 99.65% | 96.13% | 97.82% | 96.90% | 97.89% | 7.39% | 73.77% |

**변형 · SQL 변형** (상세: [03_test.md](03_test.md) 3.2절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 91.93% | 88.54% | 67.01% | 98.82% | 91.93% | 0.00% | 69.27% |
| FT1 (input·1ep) | 99.22% | 96.35% | 96.04% | 94.84% | 99.22% | 0.00% | 81.51% |
| FT2 (random·1ep) | **100%** | **100%** | **99.21%** | 97.85% | **100%** | **0.26%** | **97.40%** |
| base | **100%** | 96.35% | 0.00% | **99.53%** | 99.74% | 0.00% | 29.69% |
| base+시스템 프롬프트 | **100%** | 98.96% | 98.63% | 98.16% | 98.18% | **0.26%** | 75.00% |

**변형 · concept_id 변형** (상세: [03_test.md](03_test.md) 3.4절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 93.13% | 84.48% | 73.61% | 99.19% | 93.13% | 31.04% | 53.22% |
| FT1 (input·1ep) | 98.89% | 92.68% | 95.71% | 95.24% | 98.89% | 38.14% | 72.28% |
| FT2 (random·1ep) | 99.33% | **99.33%** | **99.52%** | 98.93% | **99.33%** | **78.27%** | **92.90%** |
| base | **100%** | 90.91% | 0.00% | **99.56%** | 99.11% | 0.00% | 13.75% |
| base+시스템 프롬프트 | **100%** | 96.01% | 97.16% | 96.79% | 94.24% | 13.75% | 66.52% |

**변형 · 슬롯 치환 (날짜·기간·나이·수치)** (상세: [03_test.md](03_test.md) 3.3절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 92.03% | 87.68% | 81.63% | 96.22% | 92.03% | 47.10% | 64.49% |
| FT1 (input·1ep) | 98.55% | 93.48% | 88.27% | 87.76% | 98.55% | 10.14% | 51.45% |
| FT2 (random·1ep) | **100%** | **100%** | 96.53% | 96.02% | **100%** | **91.30%** | **97.10%** |
| base | **100%** | 88.41% | 0.00% | **97.45%** | 99.28% | 0.00% | 23.91% |
| base+시스템 프롬프트 | **100%** | 94.20% | **97.96%** | **97.45%** | **100%** | 16.67% | 60.87% |

---

## 종합 결론

### 한눈에 보기

1. **FT2(concept_id 랜덤화 데이터, 4배)가 모든 테스트셋에서 가장 좋습니다.** EX는 학습셋 94.1%, val 92.1%, 변형 90.3~97.4%로, 다음으로 높은 FT1(71.6% / 74.6% / 51.4~81.5%)과 base+시스템 프롬프트(66.2% / 63.5% / 60.9~75.0%)를 크게 앞섭니다.
2. **학습 때 재료를 보여주는 방식은 효과가 있습니다.** FT0 → FT1에서 EX가 학습셋 +9.0%p, val +11.1%p, 변형 전체 +10.8%p 오릅니다.
3. **학습 때와 같은 시스템 프롬프트로 평가해야 합니다.** 시스템 메시지를 빼면(Qwen 기본 문구) 파인튜닝 모델의 EX가 3~18%p 낮게 나옵니다. 배포할 때도 학습 때 문구를 그대로 넣어야 합니다.

### 학습셋에서 확인된 점 (요약)

1. **파인튜닝 효과는 뚜렷합니다.** base 대비 EX가 26.1%에서 FT1 71.6%, FT2 94.1%로 올랐습니다. 출력 형식 준수, 하위 전개, 정답 SQL 스타일 학습이 주된 원인입니다.
2. **체크포인트 세 개는 사실상 같은 모델이라 eval_loss 하나로 대표합니다.** 92.6%의 문항에서 SQL이 완전히 같았습니다.
3. **시스템 프롬프트를 잘 설계한 base(66.2%)는 FT1(71.6%)에 근접하지만 FT2(94.1%)에는 크게 못 미칩니다.** 실행 안정성과 concept_id 반영은 FT1보다 좋습니다.
4. 학습셋은 파인튜닝 모델에 가장 유리한 조건이라, 일반화는 validation 셋과 변형 테스트셋 결과로 판단합니다.

### FT0(input 없이 학습한 기준선)에서 확인된 점 (요약)

1. **학습 때 재료를 보여주는 방식은 효과가 있습니다.** EX가 FT0 → FT1에서 학습셋 62.6% → 71.6%(+9.0%p), val 63.5% → 74.6%(+11.1%p)로 오릅니다.
2. **효과는 "코드를 찾는 능력"이 아니라 "코드를 정답 형식으로 옮기는 능력"에서 나옵니다.** FT0도 평가 때 재료를 받아서 필요한 코드는 95% 가까이 넣지만, 재료의 리터럴 형식(`IN (9202)`)을 그대로 베껴서 하위 전개를 자주 빠뜨리고(학습셋 73.2%), 괄호가 깨진 SQL을 만듭니다.
3. 그래서 concept_id Correctness만 보면 FT0가 높아 보입니다(학습셋 94.7%). 불필요한 코드까지 넣는 경향 때문에 생기는 지표 착시라서, concept_id 반영도는 "올바른 반영률", "필요한 코드 반영률", "불필요한 코드 사용률"로 나눠 봐야 합니다.
4. **FT0는 concept_id 변형에서 가장 많이 떨어지는 파인튜닝 모델입니다(−6.9%p).**

### FT2(concept_id 랜덤화 데이터)에서 확인된 점 (요약)

1. **FT2가 모든 비교 대상 중 가장 좋습니다.** EX는 학습셋 94.1%, val 92.1%, 변형 전체 93.4%입니다.
2. **학습하지 않은 데이터에서도 점수가 유지됩니다.** val(−2.1%p)과 변형(원본 대비 −4.9~+1.4%p) 모두 학습셋과 비슷합니다. FT2 학습 데이터에 val 문항·시나리오는 없습니다.
3. **처음 보는 코드도 잘 옮겨 씁니다.** concept_id 변형에서 학습 때 본 적 없는 코드로 바뀐 문항의 EX가 89.3%로, FT1(67.9%)과 base+시스템 프롬프트(60.5%)보다 20%p 이상 높습니다. 바뀌기 전 코드를 쓴 문항은 0건입니다.
4. **약점은 문장 표현 변화입니다.** 패러프레이즈에서 원본 대비 −4.9%p로 가장 많이 떨어졌고, 대부분 바뀐 표현을 따라 반환 컬럼을 다르게 만든 경우입니다. 학습 데이터의 문장 틀에 맞춰진 영향으로 보입니다.
5. **향상의 원인은 아직 완전히 구분할 수 없습니다.** 데이터가 3.6배라 같은 1 epoch이어도 학습 횟수가 그만큼 늘었습니다. 랜덤화 효과만 따로 보려면 FT1을 같은 학습량(epoch 늘림)으로 학습해 비교해야 합니다.

### validation 셋에서 확인된 점 (요약)

1. **base 대비 파인튜닝 효과는 학습하지 않은 데이터에서도 유지됩니다**(EX base 23.8% → FT1 74.6%, FT1만 맞힌 문항 33건 vs base만 맞힌 문항 1건).
2. **FT1도 base+시스템 프롬프트보다 높습니다**(74.6% vs 63.5%). Qwen 기본 문구로 평가했던 기존 결과(58.7%)에서는 base+시스템 프롬프트가 약간 높았는데, 시스템 프롬프트 불일치가 원인이었습니다.
3. **파인튜닝 모델은 학습셋 대비 하락이 없습니다**(FT0 +0.9%p, FT1 +3.0%p, FT2 −2.1%p).

### validation 셋·변형 테스트셋으로 확인할 질문

| 질문 | 판단 기준 | 결론 |
|---|---|---|
| 파인튜닝 모델은 학습하지 않은 데이터에서도 성능을 유지하는가? | 학습셋 대비 EX 하락폭 | **유지됩니다.** val에서 FT0 +0.9%p, FT1 +3.0%p, FT2 −2.1%p입니다. 변형 테스트셋에서도 원본 대비 FT1 −1.8~+0.8%p, FT2 −4.9~+1.4%p입니다 |
| 파인튜닝과 base+시스템 프롬프트 중 어느 쪽이 일반화가 더 잘 되는가? | 두 모델의 EX와 하락폭 비교 | **파인튜닝이 우세합니다.** val에서 FT2 92.1%, FT1 74.6%, base+시스템 프롬프트 63.5%입니다. 변형에서도 FT2가 모든 변형에서, FT1이 슬롯 치환을 뺀 세 변형에서 base+시스템 프롬프트보다 높습니다 |
| 어떤 변형에 가장 취약한가? 파인튜닝 모델과 base+시스템 프롬프트의 약점이 다른가? | 변형별 EX 하락폭 | **모델마다 다릅니다.** FT2는 패러프레이즈(−4.9%p, 반환 형식 흔들림), FT0·base·base+시스템 프롬프트는 concept_id 변형(−6.9 / −8.0 / −3.8%p)에서 가장 많이 떨어집니다. FT1은 모든 변형에서 −1.8%p 이내입니다. 슬롯 치환은 원래 어려운 5.기간설정 문항이 많아 FT1(51.4%)이 낮습니다([03_test.md](03_test.md)) |
| 파인튜닝 모델이 개념 코드를 외워서 쓰고 있지는 않은가? | concept_id 변형에서의 concept_id 반영과 EX | **외운 흔적은 없습니다.** 모든 모델에서 바뀌기 전 코드를 쓴 문항이 0건입니다. "학습 때 본 코드"와 "처음 보는 코드"의 EX 차이(FT0 3.9, FT1 8.4, FT2 6.9%p)도 학습하지 않은 base+시스템 프롬프트(11.5%p)보다 작습니다 |
| 체크포인트 선택 기준(eval_loss / concept_id / final_step)에 따라 차이가 생기는가? | 세 체크포인트 간 EX 차이와 SQL 일치율 | **차이 없음.** 학습셋 92.6%, val 61/63건에서 SQL이 똑같고 val에서는 맞힌 문항까지 같습니다. 그래서 eval_loss로 대표합니다. epoch을 늘린 학습에서는 다시 비교합니다 |
| 하위 전개와 concept_id 반영이 새로운 문항에서도 유지되는가? | 하위 전개 반영도, 올바른 반영률 | **유지됩니다.** FT2는 val과 변형에서 하위 전개 96.5~99.5%, 올바른 반영률 94.9~99.2%입니다. FT1도 하위 전개 88~96%, 올바른 반영률 86.8~94.3%로 학습셋과 비슷합니다 |

### 최종 권고

1. **FT2 방식(concept_id 랜덤화 데이터)을 기본 학습 방식으로 삼는 걸 권합니다.** 모든 테스트셋에서 가장 높고, 처음 보는 코드에도 강합니다.
2. **랜덤화 효과와 학습량 효과를 나눠 확인합니다.** FT1을 FT2와 같은 학습량(약 3.6 epoch)으로 학습해 비교하면, 랜덤화 자체의 효과를 알 수 있습니다.
3. **문장 표현 다양성을 학습 데이터에 더합니다.** FT2의 유일한 약점이 패러프레이즈라, 패러프레이즈 증강을 함께 넣으면 보완될 가능성이 있습니다.
4. **배포와 평가 모두 학습 때 쓴 시스템 프롬프트를 그대로 넣습니다.** 빠뜨리면 성능이 크게 떨어집니다.

---

## 공통 참고 사항

- **결과 파일 위치:** `results/adapter_eval/` 아래에 테스트셋별로 정리합니다. `train/`·`val/`·`variant/`(문항별 상세 CSV, `adapter_eval_<모델>_<테스트셋>.csv`), `summaries/`(실행별 전체 집계 JSON), `prompts/`(시스템 프롬프트 원문), `aborted_default_sysprompt/`(중단된 실행의 일부 결과). 평가 스크립트는 `results/` 바로 아래에 결과를 쓰기 때문에, 실행이 끝나면 이 구조로 옮깁니다.
- **summary JSON 값을 그대로 쓰면 안 되는 경우:** 모델이 SQL 대신 설명문으로 답한 문항은 집계에서 빠져서 점수가 부풀려집니다. 보고서의 수치는 이런 문항을 실패로 넣어 전체 문항 기준으로 다시 계산한 값입니다.
- **샌드박스 DB 설정:** 처음에는 DB 공유 메모리(64MB)가 부족해서 정답 쿼리가 실행되지 못하는 문항이 생겼습니다. 1GB로 늘린 뒤 해당 문항을 다시 판정했습니다(`adapter_prompt_eval/rescore_ex.py`). 앞으로의 테스트는 바뀐 설정에서 돌립니다.
- **변형 테스트셋의 문항 단위 비교:** 변형 데이터에 원본 문항 id(예: `source_id`)가 있으면, "원본에서는 맞혔는데 변형 후 틀린 문항 수"를 변형별로 함께 적습니다. 평균 점수 비교보다 노이즈가 적고 원인을 짚기 쉽습니다.
- **SQL 변형:** 질문과 재료는 그대로 두고 정답 SQL만 같은 뜻의 다른 작성 방식으로 바꾸는 변형이라면, 모델이 아니라 채점 방식(EM)을 시험하는 셈이라 해석에 주의해야 합니다. 변형 내용이 확정되면 위 "확인하는 능력" 표를 채웁니다.
- **알려진 지표 한계:** concept_id 지표는 불필요한 코드까지 쓴 모델이 점수를 더 받습니다(상세: [01_train.md](01_train.md) 4.1절). 스키마 Usage는 고친 뒤 모든 모델이 거의 100%라 모델 간 차이를 보여주지는 못합니다.

---

## 요청 프롬프트 구성

모든 테스트셋(학습셋, val, 변형 4개)에서 같은 방식으로 요청합니다. 모델에 보내는 메시지는 **시스템 프롬프트 + 사용자 메시지** 두 부분입니다.

| 모델 | 시스템 프롬프트 | 사용자 메시지 |
|---|---|---|
| FT1 | 학습 때 쓴 시스템 프롬프트 (아래 1) — ✅ 재평가 완료 (표의 FT1은 이 조건) | 질의 + 재료 (아래 3) |
| FT0 · FT2 | 학습 때 쓴 시스템 프롬프트 (아래 1) — ✅ 재평가 완료 | 질의 + 재료 (아래 3) |
| base | 학습 때 쓴 시스템 프롬프트 (아래 1) — ✅ 재평가 완료 (표의 base는 이 조건) | 질의 + 재료 (아래 3) |
| base+시스템 프롬프트 | 직접 설계한 시스템 프롬프트 (아래 2) | 질의 + 재료 (아래 3) |

- 공통 설정: temperature 0, max_tokens 512, 동시 요청 1

### 1. 학습 때 쓴 시스템 프롬프트 (FT0 · FT1 · FT2 · base)

파인튜닝 학습 설정(`.env`의 `DEFAULT_SYSTEM_PROMPT`)이 모든 학습 예시에 넣은 시스템 프롬프트입니다. 원문 파일: `results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt`

```text
당신은 OMOP-CDM v5.3 스키마 기반 임상 데이터베이스를 위한 SQL 생성 전문가입니다. 사용자의 질문에 대해 정확하고 실행 가능한 SQL 쿼리를 작성하세요. 스키마 정보나 concept_id 후보가 함께 제공되는 경우, 반드시 그 정보를 우선적으로 참고하여 SQL을 작성하세요. 부연 설명 없이 SQL 코드만 출력하세요.
```

**처음 평가 때는 FT0·FT1·FT2·base가 이 문구가 아니라 Qwen 기본 문구로 평가됐습니다.** 평가 스크립트가 시스템 메시지를 보내지 않아서, 모델의 채팅 템플릿이 아래 기본 문구를 자동으로 넣었습니다(vLLM `/tokenize`로 확인).

```text
You are Qwen, created by Alibaba Cloud. You are a helpful assistant.
```

- 지금 보고서의 표는 모두 학습 때 문구로 다시 평가한 값입니다(`--system-prompt`로 명시해서 보냄).
- 기존 결과는 "시스템 프롬프트 불일치 시 성능"으로 `results/adapter_eval/{train,val,variant}/`에 남겨 두었습니다(`adapter_eval_{ft0_baseline,eval_loss,ft2_random,base}_*.csv`). 불일치 때 EX가 FT0 −6.0~−17.5%p, FT1 −3.6~−15.9%p, FT2 −3.2~−5.7%p(학습셋·val 기준) 낮았습니다.

### 2. 직접 설계한 시스템 프롬프트 (base+시스템 프롬프트)

원문 파일: `results/adapter_eval/prompts/adapter_eval_base_sysprompt_v2_system_prompt.txt`

- **하위 전개 규칙:** `*_concept_id`에 숫자를 직접 비교하는 건 `=`든 `IN (숫자)`든 모두 금지라고 금지 예시와 함께 명시했습니다. 앵커가 1개이거나 성별·방문 유형 같은 단순 코드여도 예외 없이 서브쿼리를 쓰게 했습니다.
- **데이터셋 스타일 규칙:** 환자 조건은 `person` 기준 `EXISTS`로, 제외 조건은 `NOT EXISTS`로, 서로 다른 개념의 사건은 `UNION ALL`로 합치게 했습니다.
- **PostgreSQL 규칙:** 주 단위는 일수로 환산(`INTERVAL 'N' WEEK`·`DATE_ADD` 금지)하고, 가장 이른 날짜는 `CASE WHEN`으로 고르고(`MIN(a, b)` 금지), 별칭은 모두 선언하게 했습니다.
- **few-shot 5개:** validation 셋(id 290·535·721·447·299)에서 골랐습니다. 단순 코호트, 기준일, UNION ALL로 결과 합치기, 관찰기간 겹침, 추적 종료일 예시입니다. 그래서 val과 변형 테스트셋에서는 이 5건(과 그 시드의 변형)을 모든 모델에서 빼고 집계합니다.
- 이전 버전(v1, 하위 전개 규칙만 있고 few-shot 없음)도 학습셋으로 테스트했습니다(`results/adapter_eval/prompts/adapter_eval_base_sysprompt_system_prompt.txt`). 성능이 낮아서 보고서에는 v2만 반영했습니다([01_train.md](01_train.md) 2.2절).

<details>
<summary>시스템 프롬프트 전문 보기</summary>

```text
당신은 OMOP CDM(PostgreSQL) 기반 Text-to-SQL 전문가입니다. [질의]는 사용자의 자연어 질문이고, [재료]에는 질의에 필요한 개념(concept)의 대표(앵커) concept_id, 사용 가능한 테이블/컬럼 스키마, 테이블 간 조인 관계가 이미 정리되어 있습니다.

[재료]의 concept_id는 그 개념 전체를 대표하는 상위(앵커) 코드만 주어지며, 하위(descendant) 코드는 생략되어 있습니다. 앵커 코드를 그대로 비교하면 하위 개념이 전부 빠지므로, 모든 개념 조건은 concept_ancestor 테이블로 하위 개념까지 확장해서 조회해야 합니다.

다음을 반드시 지키세요:
1. *_concept_id 컬럼에 숫자를 직접 비교하는 것은 형태와 관계없이 모두 금지입니다.
   - 금지: drug_concept_id = 1308842
   - 금지: drug_concept_id IN (1308842)
   - 금지: drug_concept_id IN (1308842, 1332418)
   앵커가 1개뿐이어도, 성별(gender_concept_id)·방문 유형(visit_concept_id) 같은 단순 코드여도 예외 없이 항상 아래 형태만 쓰세요:
   <컬럼> IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (<앵커 concept_id>))
2. [재료]에 나열된 테이블/컬럼만 사용하세요. 나열되지 않은 테이블/컬럼을 추측해서 만들지 마세요.
3. 환자 조건은 person 테이블을 기준으로 EXISTS (SELECT 1 FROM ... WHERE x.person_id = p.person_id AND ...) 형태로 거세요. 제외 조건은 NOT EXISTS를 쓰고, NOT IN은 쓰지 마세요.
4. 서로 다른 개념의 사건을 함께 모을 때는 개념마다 별도 SELECT를 만들어 UNION ALL로 합치세요.
5. PostgreSQL 문법만 쓰세요.
   - 기간 더하기: INTERVAL 'N' DAY / INTERVAL 'N' MONTH / INTERVAL 'N' YEAR만 사용하세요. 주(week) 단위는 일수로 환산하세요(예: 12주 → INTERVAL '84' DAY). DATE_ADD, INTERVAL 'N' WEEK는 쓰지 마세요.
   - 여러 날짜 중 가장 이른 날짜는 CASE WHEN으로 비교하세요. MIN(a, b)처럼 집계함수에 인자를 두 개 넣지 마세요.
   - SELECT/WHERE에서 쓰는 테이블 별칭은 모두 FROM/JOIN에 선언돼 있어야 합니다. 여러 테이블에 있는 컬럼(person_id 등)은 항상 별칭을 붙이세요.
6. 다른 설명 없이 SQL 쿼리 하나만 답하세요.

아래는 올바른 답변 예시입니다([재료]는 개념 값 조건만 발췌).

[예시 1]
[질의] 현재 연도 기준 연령 65세 이상이고 여성 기록이고 골다공증 진단인 환자.
[재료] 개념 값 조건:
  - "골다공증" → condition_occurrence.condition_concept_id IN (80502)
  - "여성" → person.gender_concept_id IN (8532)
[SQL]
SELECT DISTINCT p.person_id FROM person p WHERE (EXTRACT(YEAR FROM CURRENT_DATE) - p.year_of_birth) >= 65 AND p.gender_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (8532)) AND EXISTS (SELECT 1 FROM condition_occurrence co WHERE co.person_id = p.person_id AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (80502)));

[예시 2]
[질의] 백내장 최초 진단일을 기준 시점으로 정의.
[재료] 개념 값 조건:
  - "백내장" → condition_occurrence.condition_concept_id IN (375545)
[SQL]
SELECT co.person_id, MIN(co.condition_start_date) AS index_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (375545)) GROUP BY co.person_id;

[예시 3]
[질의] 유방암 또는 전립선암의 최초 발생일을 조회.
[재료] 개념 값 조건:
  - "유방암" → condition_occurrence.condition_concept_id IN (4112853)
  - "전립선암" → condition_occurrence.condition_concept_id IN (4163261)
[SQL]
WITH outcome_events AS ( SELECT co.person_id, co.condition_start_date AS event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4112853)) UNION ALL SELECT co.person_id, co.condition_start_date AS event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4163261)) ) SELECT oe.person_id, MIN(oe.event_date) AS first_event_date FROM outcome_events oe GROUP BY oe.person_id;

[예시 4]
[질의] 관찰기간이 2021-01-14부터 2022-12-31까지의 기간과 겹치는 환자.
[재료] 개념 값 조건: 없음
[SQL]
SELECT op.person_id, op.observation_period_start_date, op.observation_period_end_date FROM observation_period op WHERE op.observation_period_start_date <= DATE '2022-12-31' AND op.observation_period_end_date >= DATE '2021-01-14';

[예시 5]
[질의] 기준시점(로모소주맙 최초 처방일)부터 사망·자료 관찰 종료 중 최초까지 추적 (추적기간: 24개월)
[재료] 개념 값 조건:
  - "로모소주맙" → drug_exposure.drug_concept_id IN (1511251)
[SQL]
WITH index_dates AS ( SELECT de.person_id, MIN(de.drug_exposure_start_date) AS index_date FROM drug_exposure de WHERE de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (1511251)) GROUP BY de.person_id ), follow_up_candidates AS ( SELECT i.person_id, i.index_date, d.death_date, op.observation_period_end_date, i.index_date + INTERVAL '24' MONTH AS maximum_follow_up_date FROM index_dates i JOIN observation_period op ON op.person_id = i.person_id AND i.index_date BETWEEN op.observation_period_start_date AND op.observation_period_end_date LEFT JOIN death d ON d.person_id = i.person_id AND d.death_date >= i.index_date AND d.death_date <= i.index_date + INTERVAL '24' MONTH ) SELECT f.person_id, f.index_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date AND f.death_date <= f.maximum_follow_up_date THEN f.death_date WHEN f.observation_period_end_date <= f.maximum_follow_up_date THEN f.observation_period_end_date ELSE f.maximum_follow_up_date END AS follow_up_end_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date AND f.death_date <= f.maximum_follow_up_date THEN 'DEATH' WHEN f.observation_period_end_date <= f.maximum_follow_up_date THEN 'OBSERVATION_END' ELSE '24_MONTH_END' END AS follow_up_end_reason FROM follow_up_candidates f;
```

</details>

### 3. 사용자 메시지 (모든 모델 공통)

테스트셋의 `text`(질의)와 `input`(재료)을 합쳐서 만듭니다.

```text
[질의]
<자연어 질의>

[재료]
개념 값 조건:
  - "<개념 이름>" → <테이블>.<컬럼> IN (<concept_id>)
테이블(컬럼 전체):
  # <테이블>(<한글 이름>) PK=<기본키>
    - <컬럼> (<한글 이름>) <타입>  [→<참조 테이블>]
조인:
  - <테이블>.<컬럼> = <테이블>.<컬럼>
```

<details>
<summary>실제 예시 (val id 441)</summary>

```text
[질의]
사쿠비트릴·발사르탄 처방 이력이 있는 환자를 노출군으로 정의.

[재료]
개념 값 조건:
  - "사쿠비트릴·발사르탄" → drug_exposure.drug_concept_id IN (1308842)
  - "ARNI(사쿠비트릴/발사르탄)" → drug_exposure.drug_concept_id IN (46275719)
테이블(컬럼 전체):
  # device_exposure(기기 노출) PK=device_exposure_id
    - device_exposure_id (기기 노출 ID) integer  [PK]
    - person_id (환자 ID) integer  [→person]
    … (컬럼 생략)
  # drug_exposure(약물 노출) PK=drug_exposure_id
    - drug_exposure_id (약물 노출 ID) integer  [PK]
    - person_id (환자 ID) integer  [→person]
    - drug_concept_id (약물 개념 ID) integer  [→concept]
    … (컬럼 생략)
  # person(환자) PK=person_id
    - person_id (환자 ID) integer  [PK]
    - gender_concept_id (성별 개념 ID) integer  [→concept]
    - birth_datetime (출생 일시) datetime
    - race_concept_id (인종 개념 ID) integer  [→concept]
조인:
  - device_exposure.person_id = person.person_id
  - drug_exposure.person_id = person.person_id
```

</details>

- **학습 때 형식과의 차이:** 학습 데이터(LLaMA Factory)는 `<질의>` + 줄바꿈 + `[재료]…` 형식이라, 평가 때 붙는 `[질의]` 머리말과 빈 줄이 없습니다. 모든 모델에 똑같이 적용되는 차이라 모델 간 비교에는 영향이 없습니다.
- FT0는 학습 때 재료 없이 질의만 받았지만, 평가 때는 다른 모델과 똑같이 재료를 포함해서 받습니다.
