# NL2SQL 어댑터 평가 — 종합 보고서

> 학습셋, validation 셋, 변형 테스트셋 결과를 한곳에서 비교하는 문서예요. 테스트셋별 상세 분석은 각 보고서에 있어요.

## 보고서 목록

| 테스트셋 | 파일 | 데이터 | 문항 수 | 상태 |
|---|---|---|---:|---|
| 학습셋 | [01_train.md](01_train.md) | `test_set/proposed_input_train.jsonl` (실제 학습 데이터) | 612 | ✅ 완료 |
| validation 셋 | [02_val.md](02_val.md) | `test_set/proposed_input_val.jsonl` | 68 (집계 63*) | ✅ 완료 |
| 변형 · 자연어 패러프레이즈 | [03_test.md](03_test.md) 3.1절 | `test_set/paraphrase.jsonl` | 573 (집계 568*) | 🔄 FT0만 완료 |
| 변형 · SQL 변형 | [03_test.md](03_test.md) 3.2절 | `test_set/restructure.jsonl` | 387 (집계 384*) | 🔄 FT0만 완료 |
| 변형 · concept_id 변형 | [03_test.md](03_test.md) 3.4절 | `test_set/concept.jsonl` | 455 (집계 451*) | 🔄 FT0만 완료 |
| 변형 · 슬롯 치환 (날짜 등) | [03_test.md](03_test.md) 3.3절 | `test_set/slot.jsonl` | 141 (집계 138*) | 🔄 FT0만 완료 |

변형 테스트셋은 학습 데이터를 네 가지 방식으로 변형한 파일 4개예요. 원본이 같아서 상세 분석은 `03_test.md` 한 문서에서 변형별 절로 나눠 비교해요.

| 변형 | 확인하는 능력 | 특히 볼 지표 |
|---|---|---|
| 자연어 패러프레이즈 | 같은 뜻을 다른 말로 물어도 같은 SQL을 만드는가 | EX |
| SQL 변형 | 자연어·재료는 그대로 두고 정답 SQL만 같은 뜻의 다른 작성 방식으로 바꿔요. 모델 입력이 원본과 같아서, 모델보다 채점 방식(EM과 EX의 차이)을 확인하는 변형이에요 | EX, EM |
| concept_id 변형 | 재료에 주어진 코드를 그대로 옮겨 쓰는가, 학습 때 외운 코드를 쓰는가 | concept_id Correctness, EX |
| 슬롯 치환 (날짜 등) | 질문의 날짜·기간·숫자를 정확히 반영하는가 | EX |

\* validation 셋 68건 중 5건(id 290·535·721·447·299)은 base+시스템 프롬프트의 few-shot 예시로 쓰였어요. 공정한 비교를 위해 모든 모델에서 이 5건을 빼고 집계해요. 변형 테스트셋도 같은 기준으로, 이 5건의 시드에서 나온 변형을 빼고 집계해요.

## 평가 대상 모델

| 이름 | 설명 |
|---|---|
| FT0 (baseline·1ep) | input(재료) 없이 질문만으로 학습한 기준선 파인튜닝 모델. 재료를 넣는 학습 방식의 효과를 확인하는 용도예요. 평가는 다른 모델과 똑같이 재료를 포함한 프롬프트로 해요 |
| FT1 (input·1ep) | 첫 번째 LoRA 파인튜닝 모델(아래 파인튜닝 실험 목록 참고). 검증 손실(eval_loss)이 가장 낮은 체크포인트(`by-loss`)로 대표해요* |
| FT2 (random·1ep) | concept_id 랜덤화 데이터로 학습한 파인튜닝 모델. `by-loss` 체크포인트만 평가해요 |
| base | 파인튜닝 전 베이스 모델 (`XiYanSQL-QwenCoder-14B-2504`), 모델 기본 시스템 프롬프트만 사용 |
| base+시스템 프롬프트 | 베이스 모델 + 직접 설계한 규칙·few-shot 시스템 프롬프트 ([요청 프롬프트 구성](#요청-프롬프트-구성)) |

\* FT1은 한 번의 학습에서 eval_loss / concept_id 반영도 / 마지막 지점 기준으로 체크포인트 3개를 뽑아 모두 평가했지만, 대부분의 문항에서 똑같은 SQL을 만들어 사실상 같은 모델이었어요. 그래서 모든 표에서 eval_loss 체크포인트 하나로 적어요(근거: [01_train.md](01_train.md) 3절).

### 파인튜닝 실험 목록

표에서는 짧은 ID로 적어요. FT0 → FT1 → FT2 순서로 조건을 하나씩 더해서, 재료(input)와 concept_id 랜덤화가 각각 얼마나 효과가 있는지 비교해요. 학습 조건을 바꿔 새로 학습할 때마다 한 줄씩 추가해요. 학습 데이터 이름 뒤에 `_train`/`_val`을 붙인 파일이 각각 학습용과 검증용이에요.

- **공통 조건:** AutoML(HPO) trials 수 5로 고정

| ID | 학습 데이터 | epoch | 대표 체크포인트 (서빙 이름) | 상태 | 비고 |
|---|---|---:|---|---|---|
| FT0 | `baseline` (`proposed_input`과 같은 612건, input 없음) | 1 | eval_loss 최저 (`by-loss`) | ✅ 학습셋·val 평가 완료 | 기준선. FT1과 학습 조건을 똑같이 맞추고 학습 데이터에서 input만 뺌. 평가 프롬프트는 동일 |
| FT1 | `proposed_input` (input에 RAG 프롬프트 포함, 증강 없음) | 1 | eval_loss 최저 (`by-loss`) | ✅ 평가 완료 | 빠른 검증용 첫 학습. 체크포인트 3개(`by-loss`·`by-adherence`·`final-step`)를 모두 평가했지만 사실상 같아서 하나로 대표 |
| FT2 | `proposed_random` (`proposed_input`의 concept_id를 랜덤화, 4배) | 1 | eval_loss 최저 (`by-loss`) | ✅ 학습셋·val 평가 완료 | 빠른 테스트를 위해 `by-loss`만 평가. 학습 데이터 2,202건 = 원본 612 + 랜덤화 사본 3×530 |

- 공통 설정: max_tokens 512, temperature 0, 동시 요청 1
- **모든 모델은 같은 사용자 메시지(질의 + 재료)를 받아요. 다른 건 시스템 프롬프트뿐이에요.** 파인튜닝 모델과 base는 모델 기본 시스템 프롬프트(한 줄)를 받고, base+시스템 프롬프트는 그 대신 규칙과 few-shot이 담긴 긴 시스템 프롬프트를 받아요. 이름의 "+시스템 프롬프트"는 이 차이를 뜻해요(→ [요청 프롬프트 구성](#요청-프롬프트-구성)).

---

## 지표 설명

평가할 때 모델은 질문과 함께 **재료**를 받아요. 재료에는 ① 질문에 필요한 의학 개념의 코드 번호(예: 발사르탄 → 약물 코드 1308842), ② 사용할 수 있는 데이터 표(테이블)와 그 안의 항목(컬럼), ③ 표끼리 연결하는 방법이 들어 있어요. 아래 지표들은 모델이 이 재료를 SQL에 제대로 반영했는지와, 최종 결과가 맞는지를 확인해요.

### concept_id 반영도 — 재료의 개념 코드를 제대로 썼는가

**핵심 지표 (이 평가에서 가장 중요하게 보는 값)**

재료에 주어진 개념 코드를 "정답 SQL이 실제로 쓰는 코드(필요한 코드)"와 "정답이 쓰지 않는 코드(불필요한 코드)"로 나눠서 봐요.

| 지표 | 의미 | 판정 방법 |
|---|---|---|
| **올바른 반영률** | 필요한 코드를 정답 형식으로, 실행되는 SQL에 넣었는가 | 필요한 코드마다 ① 해당 항목의 조건 안에 코드가 있고 ② 하위 전개(`concept_ancestor`) 형식이며 ③ SQL이 실행검증을 통과하면 통과. 필요한 코드 전체 중 통과 비율 |
| 필요한 코드 반영률 | 필요한 코드를 빠뜨리지 않았는가 (형식 무관) | 위 ①만 확인 |
| 불필요한 코드 사용률 | 정답이 쓰지 않는 코드를 넣었는가 (낮을수록 좋음) | 불필요한 코드 중 조건 안에 들어간 비율 |

- 올바른 반영률이 "프롬프트에 적힌 concept_id를 답변 쿼리에 알맞게 반영했는가"를 가장 직접적으로 보여줘요.
- 필요한 코드 반영률과 올바른 반영률의 차이는 코드는 넣었지만 하위 전개를 하지 않았거나 SQL이 실행되지 않은 경우예요.

**참고 지표 (Presence / Usage / Correctness)**

재료에 주어진 개념 코드 하나하나에 대해 아래 세 가지를 확인해요. 필요한 코드와 불필요한 코드를 구분하지 않고, 하위 전개 여부와 실행 가능 여부도 보지 않아요. 그래서 재료의 코드를 형식과 상관없이 다 넣는 모델이 점수를 더 받아요. 참고용으로만 봐요.

| 지표 | 의미 | 판정 방법 |
|---|---|---|
| Presence | 코드 번호가 SQL에 들어 있는가 | 생성된 SQL 어딘가에 그 코드 번호가 적혀 있으면 통과 |
| Usage | 그 코드로 대상을 거르는 조건을 실제로 걸었는가 | 해당 항목(예: 약물 코드 항목)에 "이 코드에 해당하는 것만" 같은 조건이 있으면 통과. 들어간 코드 값이 맞는지는 보지 않아요 |
| Correctness | 그 조건에 들어간 코드가 재료의 코드와 일치하는가 | 조건 안에 재료의 코드가 빠짐없이 들어 있으면 통과. 조건 자체가 없으면 실패 |

- **계산:** 한 문항에 코드가 여러 개면 코드별 통과 여부를 평균 내서 그 문항의 점수(0~1)로 삼아요. 표의 값은 이 점수를 전체 문항에 대해 평균 낸 거예요. 개념 코드가 있는 532문항만 대상이에요.
- **참고:** 재료에는 정답에 필요 없는 코드가 섞여 있을 때가 있어서, 정답 SQL도 100%가 나오지 않아요(약 93%). 자세한 내용은 [학습셋 보고서](01_train.md) 4.1절에 있어요.

### 스키마 반영도 — 재료가 허용한 표와 항목만 썼는가

문항마다 SQL 한 개에 대해 통과/실패를 한 번 판정해요. 표의 값은 통과한 문항의 비율이에요.

| 지표 | 의미 | 판정 방법 |
|---|---|---|
| Presence | 재료의 표를 사용했는가 | 재료에 있는 표를 하나라도 썼으면 통과. 재료를 무시하고 엉뚱한 표만 쓰면 실패 |
| Correctness | 재료에 없는 표나 항목을 지어내지 않았는가 | SQL에 쓴 표와 항목이 모두 재료 목록 안에 있으면 통과. 하나라도 재료 밖이면 실패 |
| Usage | 표끼리 연결한 기준이 재료와 같은가 | 표를 2개 이상 쓴 문항만 평가해요. 표를 합칠 때 어떤 항목끼리 맞췄는지(예: 약물 표의 환자 번호 = 환자 표의 환자 번호)가 재료에 적힌 연결 방법과 맞으면 통과. 의미가 다른 항목끼리 맞추면(예: 약물 표의 방문 번호 = 환자 표의 환자 번호) 실패 |

- **참고:** 처음에는 Usage 계산이 표를 잇는 작성 방식 중 한 가지만 인식해서 정답 SQL도 대부분 실패로 나왔어요. 지금은 고쳐서 정답 SQL이 모두 통과하고, 기존 결과도 이 기준으로 다시 채점했어요([학습셋 보고서](01_train.md) 5절).

### 그 밖의 지표

| 지표 | 의미 |
|---|---|
| SQL 문법 | SQL 문장이 형식상 올바른가 |
| 샌드박스 실행검증 | 테스트용 데이터베이스에서 오류 없이 실행되는가. 결과가 맞는지는 보지 않아요 |
| 하위 전개 반영도 | 재료에는 대표 코드(예: 고혈압)만 주어지는데, 그 아래 세부 코드(예: 이차성 고혈압)까지 포함하도록 조회했는가 |
| EM | 정답 SQL과 문장이 똑같은가. 결과가 같아도 작성 방식이 다르면 실패라서 실제 정확도보다 낮게 나와요 |
| EX | 정답 SQL과 실행 결과가 같은가. **실제 정확도를 가장 잘 보여주는 지표예요** |

### 정답 SQL 채점값(참고)

각 보고서의 지표 표에 있는 열이에요. 테스트셋의 정답 SQL을 모델 답변과 같은 방식으로 채점한 값이에요. 재료에 정답에 필요 없는 코드가 섞여 있어서 정답 SQL도 concept_id 지표는 100%가 나오지 않아요. 그래서 이 값은 "이 지표에서 현실적으로 기대할 수 있는 수준"을 보여주는 참고값이에요. 모델 점수가 이 값보다 높다고 정답보다 나은 건 아니에요. 정답이 쓰지 않은 불필요한 코드까지 SQL에 넣었다는 뜻이에요.

---

## 테스트셋 간 비교

### EX (실행 결과 정확도)

| 모델 | 학습셋 | val | 패러프레이즈 | SQL 변형 | concept_id 변형 | 슬롯 치환 | 변형 전체(참고) |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 56.54% | 46.03% | 57.04% | 61.20% | 45.01% | 49.28% | 53.86% |
| FT1 (input·1ep) | 67.97% | 58.73% | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| FT2 (random·1ep) | **88.40%** | **88.89%** | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| base | 23.69% | 20.63% | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| base+시스템 프롬프트 | 66.18% | 63.49% | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

- 모든 값은 전체 문항 기준이에요. 샌드박스 DB의 공유 메모리를 늘린 뒤 인프라 오류 문항을 다시 판정해서, 정답 쿼리가 실행되지 못한 문항은 없어요. 모델 SQL이 30초 제한을 넘긴 경우는 너무 느린 SQL로 보고 실패로 셌어요.
- "변형 전체(참고)"는 변형 테스트셋 4개를 합친 값이에요. 변형마다 문항 수와 난이도가 달라서 참고용으로만 봐요. 판단은 변형별 열로 해요.

### concept_id 핵심 지표

| 모델 | 학습셋 올바른 반영률 | val 올바른 반영률 | 학습셋 필요한 코드 반영률 | val 필요한 코드 반영률 | 학습셋 불필요한 코드 사용률 ↓ | val 불필요한 코드 사용률 ↓ |
|---|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 51.2% | 45.6% | 94.9% | **96.2%** | 60.9% | 54.5% |
| FT1 (input·1ep) | 83.6% | 87.3% | 90.8% | 89.9% | 55.4% | 63.6% |
| FT2 (random·1ep) | **94.7%** | **94.9%** | **96.0%** | 94.9% | **25.0%** | **36.4%** |
| base | 0.0% | 0.0% | 92.5% | 91.1% | 76.1% | 72.7% |
| base+시스템 프롬프트 | 90.8% | 93.7% | 94.3% | 94.9% | 67.4% | 81.8% |

- 분모: 학습셋 필요한 코드 731개·불필요한 코드 92개, val 필요한 코드 79개·불필요한 코드 11개(few-shot 5건 제외)예요.
- **FT0는 코드를 찾는 건 잘하지만 정답 형식으로 옮기지 못해요.** 재료의 리터럴 형식(`IN (9202)`)을 그대로 베껴서 하위 전개를 빠뜨리거나 괄호가 깨진 SQL을 만들어요. 그래서 필요한 코드 반영률은 높지만 올바른 반영률은 절반 수준이에요. 학습 때 재료를 같이 보여주는 기법(FT1·FT2)이 가르치는 게 바로 이 변환이에요.
- **base는 하위 전개를 전혀 하지 않아 올바른 반영률이 0%예요.**
- **FT2는 세 지표 모두 가장 좋거나 거의 같아요.** 필요한 코드는 빠뜨리지 않으면서 불필요한 코드는 가장 적게 써요.

### 핵심 지표

**학습셋** (상세: [01_train.md](01_train.md))

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 92.16% | 85.62% | 62.29% | **95.02%** | 91.99% | 28.10% | 56.54% |
| FT1 (input·1ep) | 98.37% | 91.83% | 94.87% | 90.81% | 97.88% | 34.64% | 67.97% |
| FT2 (random·1ep) | 99.67% | **98.53%** | **96.95%** | 93.05% | **99.67%** | **72.22%** | **88.40%** |
| base | 92.32% | 87.09% | 0.00% | 91.05% | 91.18% | 0.00% | 23.69% |
| base+시스템 프롬프트 | **99.84%** | 96.57% | 96.70% | 94.85% | 97.06% | 10.13% | 66.18% |

**validation 셋** (상세: [02_val.md](02_val.md), few-shot 5건 제외 63건)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 90.48% | 80.95% | 56.55% | 94.05% | 90.48% | 23.81% | 46.03% |
| FT1 (input·1ep) | **100%** | 98.41% | 95.84% | 89.59% | 98.41% | 39.68% | 58.73% |
| FT2 (random·1ep) | **100%** | **100%** | **98.52%** | 91.38% | **100%** | **71.43%** | **88.89%** |
| base | 92.06% | 87.30% | 0.00% | 89.00% | 90.48% | 0.00% | 20.63% |
| base+시스템 프롬프트 | **100%** | 98.41% | 97.93% | **96.12%** | 96.83% | 9.52% | 63.49% |

**변형 · 자연어 패러프레이즈** (상세: [03_test.md](03_test.md) 3.1절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 95.60% | 91.73% | 55.04% | 97.68% | 95.42% | 25.18% | 57.04% |
| FT1 (input·1ep) | ⏳ | | | | | | |
| FT2 (random·1ep) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| base | ⏳ | | | | | | |
| base+시스템 프롬프트 | ⏳ | | | | | | |

**변형 · SQL 변형** (상세: [03_test.md](03_test.md) 3.2절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 90.36% | 86.46% | 52.53% | 98.56% | 90.36% | 0.00% | 61.20% |
| FT1 (input·1ep) | ⏳ | | | | | | |
| FT2 (random·1ep) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| base | ⏳ | | | | | | |
| base+시스템 프롬프트 | ⏳ | | | | | | |

**변형 · concept_id 변형** (상세: [03_test.md](03_test.md) 3.4절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 92.46% | 83.81% | 61.75% | 99.30% | 92.24% | 23.28% | 45.01% |
| FT1 (input·1ep) | ⏳ | | | | | | |
| FT2 (random·1ep) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| base | ⏳ | | | | | | |
| base+시스템 프롬프트 | ⏳ | | | | | | |

**변형 · 슬롯 치환 (날짜 등)** (상세: [03_test.md](03_test.md) 3.3절)

| 모델 | SQL 문법 | 실행검증 | 하위 전개 | concept_id Correctness | 스키마 Correctness | EM | EX |
|---|---:|---:|---:|---:|---:|---:|---:|
| FT0 (baseline·1ep) | 84.78% | 76.81% | 64.29% | 96.22% | 84.78% | 36.23% | 49.28% |
| FT1 (input·1ep) | ⏳ | | | | | | |
| FT2 (random·1ep) | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| base | ⏳ | | | | | | |
| base+시스템 프롬프트 | ⏳ | | | | | | |

---

## 종합 결론

### 학습셋에서 확인된 점 (요약)

1. **파인튜닝 효과는 뚜렷해요.** base 대비 EX가 23.7%에서 68.0%로 올랐어요. 출력 형식 준수, 하위 전개, 정답 SQL 스타일 학습이 주된 원인이에요.
2. **체크포인트 세 개는 사실상 같은 모델이라 eval_loss 하나로 대표해요.** 92.6%의 문항에서 SQL이 완전히 같았어요.
3. **시스템 프롬프트를 잘 설계한 base가 파인튜닝 모델에 거의 근접해요**(EX 66.2% vs 68.0%). 실행 안정성과 concept_id 반영은 오히려 더 좋아요. 파인튜닝 모델이 앞서는 건 EM(정답 스타일 재현)과 기간 설정, 기준일 조회 유형이에요.
4. 학습셋은 파인튜닝 모델에 가장 유리한 조건이라, 아래 질문들은 validation 셋과 변형 테스트셋 결과로 판단해야 해요.

### FT0(input 없이 학습한 기준선)에서 확인된 점 (요약)

1. **학습 때 재료를 보여주는 방식은 효과가 있어요.** EX가 FT0 → FT1에서 학습셋 56.5% → 68.0%(+11.5%p), val 46.0% → 58.7%(+12.7%p)로 올라요.
2. **효과는 "코드를 찾는 능력"이 아니라 "코드를 정답 형식으로 옮기는 능력"에서 나와요.** FT0도 평가 때 재료를 받아서 필요한 코드는 95% 가까이 넣지만, 재료의 리터럴 형식(`IN (9202)`)을 그대로 베껴서 하위 전개를 자주 빠뜨리고(학습셋 62.3%), 괄호가 깨진 SQL을 만들어요.
3. 그래서 concept_id Correctness만 보면 FT0가 가장 높아 보여요(학습셋 95.0%). 불필요한 코드까지 넣는 경향 때문에 생기는 지표 착시라서, concept_id 반영도는 "필요한 코드 반영률"과 "불필요한 코드 사용률"로 나눠 봐야 해요.

### FT2(concept_id 랜덤화 데이터)에서 확인된 점 (요약)

1. **FT2가 모든 비교 대상 중 가장 좋아요.** EX는 학습셋 88.4%, val 88.9%로 FT1(68.0% / 58.7%)과 base+시스템 프롬프트(66.2% / 63.5%)를 크게 앞서요.
2. **학습셋과 val의 차이가 없어요**(88.4% vs 88.9%). FT1처럼 학습셋에서만 점수가 높은 현상이 사라졌어요. FT2 학습 데이터에 val 문항·시나리오는 없고, 문장 틀이 겹치는 정도는 FT1 학습 데이터와 같아요.
3. **향상의 원인은 아직 구분할 수 없어요.** 데이터가 3.6배라 같은 1 epoch이어도 학습 횟수가 그만큼 늘었어요. 랜덤화의 효과인지, 학습량이 늘어난 효과인지는 concept_id 변형 테스트셋과 epoch을 늘린 FT1 계열 실험으로 나눠서 봐야 해요.

### validation 셋에서 확인된 점 (요약, FT1 기준)

1. **base 대비 파인튜닝 효과는 학습하지 않은 데이터에서도 유지돼요**(EX 20.6% → 58.7%, 파인튜닝만 맞힌 문항 24건 vs base만 맞힌 문항 0건).
2. **base+시스템 프롬프트가 파인튜닝 모델보다 약간 높아요**(EX 63.5% vs 58.7%). 다만 차이가 3건이라 우열을 가리기 어렵고, few-shot이 val에서 뽑혀 유리했을 수 있어요.
3. **파인튜닝 모델은 짧고 단순한 질문에서 출력 컬럼을 정답과 다르게 만드는 실수가 많아요**(EASY EX 38.9%). 복잡한 코호트 정의(2.노출군)에서는 앞서요.

### validation 셋·변형 테스트셋으로 확인할 질문

| 질문 | 판단 기준 | 결론 |
|---|---|---|
| 파인튜닝 모델은 학습하지 않은 데이터에서도 성능을 유지하는가? | 학습셋 대비 EX 하락폭 | **FT2: 유지(88.4% → 88.9%).** FT1: 부분적으로 유지. 68.0% → 58.7%(−9.2%p). base도 −3.1%p라 문항 난이도 차이를 빼면 실제 하락은 약 6%p. base 대비 효과(EX 20.6% → 58.7%)는 그대로예요 |
| 파인튜닝과 base+시스템 프롬프트 중 어느 쪽이 일반화가 더 잘 되는가? | 두 모델의 EX 하락폭 비교 | **FT2가 크게 우세(val 88.9% vs 63.5%).** FT1 기준으로는 base+시스템 프롬프트가 약간 우세(63.5% vs 58.7%, −2.7%p vs −9.2%p). 다만 차이가 3건이고, few-shot이 val에서 뽑혀 유리했을 수 있어요. 변형 테스트셋에서 다시 확인해요 |
| 어떤 변형에 가장 취약한가? 파인튜닝 모델과 base+시스템 프롬프트의 약점이 다른가? | 변형별 EX 하락폭 | ⏳ |
| 파인튜닝 모델이 개념 코드를 외워서 쓰고 있지는 않은가? | concept_id 변형에서의 concept_id Correctness와 EX | ⏳ |
| 체크포인트 선택 기준(eval_loss / concept_id / final_step)에 따라 차이가 생기는가? | 세 체크포인트 간 EX 차이와 SQL 일치율 | **차이 없음.** 학습셋 92.6%, val 61/63건에서 SQL이 똑같고 val에서는 맞힌 문항까지 같아요. 그래서 eval_loss로 대표해요. epoch을 늘린 학습에서는 다시 비교해요 |
| 하위 전개와 concept_id 반영이 새로운 문항에서도 유지되는가? | 하위 전개 반영도, concept_id Correctness | **val: 유지.** 하위 전개 약 95%, Correctness 약 89%(정답 SQL 채점값 91.4%)로 학습셋과 비슷해요 |

### 최종 권고

⏳ 모든 테스트셋 결과가 나온 뒤 작성해요.

---

## 공통 참고 사항

- **결과 파일 위치:** `results/adapter_eval/` 아래에 테스트셋별로 정리해요. `train/`·`val/`·`variant/`(문항별 상세 CSV, `adapter_eval_<모델>_<테스트셋>.csv`), `summaries/`(실행별 전체 집계 JSON), `prompts/`(시스템 프롬프트 원문), `aborted_default_sysprompt/`(중단된 실행의 일부 결과). 평가 스크립트는 `results/` 바로 아래에 결과를 쓰기 때문에, 실행이 끝나면 이 구조로 옮겨요.
- **summary JSON 값을 그대로 쓰면 안 되는 경우:** 모델이 SQL 대신 설명문으로 답한 문항은 집계에서 빠져서 점수가 부풀려져요. 보고서의 수치는 이런 문항을 실패로 넣어 전체 문항 기준으로 다시 계산한 값이에요.
- **샌드박스 DB 설정:** 처음에는 DB 공유 메모리(64MB)가 부족해서 정답 쿼리가 실행되지 못하는 문항이 생겼어요. 1GB로 늘린 뒤 해당 문항을 다시 판정했어요(`adapter_prompt_eval/rescore_ex.py`). 앞으로의 테스트는 바뀐 설정에서 돌려요.
- **변형 테스트셋의 문항 단위 비교:** 변형 데이터에 원본 문항 id(예: `source_id`)가 있으면, "원본에서는 맞혔는데 변형 후 틀린 문항 수"를 변형별로 함께 적어요. 평균 점수 비교보다 노이즈가 적고 원인을 짚기 쉬워요.
- **SQL 변형:** 질문과 재료는 그대로 두고 정답 SQL만 같은 뜻의 다른 작성 방식으로 바꾸는 변형이라면, 모델이 아니라 채점 방식(EM)을 시험하는 셈이라 해석에 주의해야 해요. 변형 내용이 확정되면 위 "확인하는 능력" 표를 채워요.
- **알려진 지표 한계:** concept_id 지표는 불필요한 코드까지 쓴 모델이 점수를 더 받아요(상세: [01_train.md](01_train.md) 4.1절). 스키마 Usage는 고친 뒤 모든 모델이 거의 100%라 모델 간 차이를 보여주지는 못해요.

---

## 요청 프롬프트 구성

모든 테스트셋(학습셋, val, 변형 4개)에서 같은 방식으로 요청해요. 모델에 보내는 메시지는 **시스템 프롬프트 + 사용자 메시지** 두 부분이에요.

| 모델 | 시스템 프롬프트 | 사용자 메시지 |
|---|---|---|
| FT0 · FT1 · FT2 | 학습 때 쓴 시스템 프롬프트 (아래 1) — ⚠️ 지금까지 결과는 Qwen 기본 문구로 평가됨, 재평가 중 | 질의 + 재료 (아래 3) |
| base | 학습 때 쓴 시스템 프롬프트 (아래 1) — 재평가 중 (지금까지 결과는 Qwen 기본 문구) | 질의 + 재료 (아래 3) |
| base+시스템 프롬프트 | 직접 설계한 시스템 프롬프트 (아래 2) | 질의 + 재료 (아래 3) |

- 공통 설정: temperature 0, max_tokens 512, 동시 요청 1

### 1. 학습 때 쓴 시스템 프롬프트 (FT0 · FT1 · FT2 · base)

파인튜닝 학습 설정(`.env`의 `DEFAULT_SYSTEM_PROMPT`)이 모든 학습 예시에 넣은 시스템 프롬프트예요. 원문 파일: `results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt`

```text
당신은 OMOP-CDM v5.3 스키마 기반 임상 데이터베이스를 위한 SQL 생성 전문가입니다. 사용자의 질문에 대해 정확하고 실행 가능한 SQL 쿼리를 작성하세요. 스키마 정보나 concept_id 후보가 함께 제공되는 경우, 반드시 그 정보를 우선적으로 참고하여 SQL을 작성하세요. 부연 설명 없이 SQL 코드만 출력하세요.
```

**⚠️ 지금까지의 FT0·FT1·FT2·base 결과는 이 문구가 아니라 Qwen 기본 문구로 평가됐어요.** 평가 스크립트가 시스템 메시지를 보내지 않아서, 모델의 채팅 템플릿이 아래 기본 문구를 자동으로 넣었어요(vLLM `/tokenize`로 확인).

```text
You are Qwen, created by Alibaba Cloud. You are a helpful assistant.
```

- 파인튜닝 모델은 학습 때와 다른 시스템 프롬프트를 받은 셈이라, 지금 수치는 실제 배포 조건(학습 때 문구를 그대로 넣음)의 성능과 다를 수 있어요.
- FT1과 base를 학습 때 문구로 다시 평가하고 있어요(학습셋, val, 변형 4개). 결과가 나오면 표를 갱신하고, 기존 결과는 "시스템 프롬프트 불일치 시 성능"으로 따로 남겨요.

### 2. 직접 설계한 시스템 프롬프트 (base+시스템 프롬프트)

원문 파일: `results/adapter_eval/prompts/adapter_eval_base_sysprompt_v2_system_prompt.txt`

- **하위 전개 규칙:** `*_concept_id`에 숫자를 직접 비교하는 건 `=`든 `IN (숫자)`든 모두 금지라고 금지 예시와 함께 명시했어요. 앵커가 1개이거나 성별·방문 유형 같은 단순 코드여도 예외 없이 서브쿼리를 쓰게 했어요.
- **데이터셋 스타일 규칙:** 환자 조건은 `person` 기준 `EXISTS`로, 제외 조건은 `NOT EXISTS`로, 서로 다른 개념의 사건은 `UNION ALL`로 합치게 했어요.
- **PostgreSQL 규칙:** 주 단위는 일수로 환산(`INTERVAL 'N' WEEK`·`DATE_ADD` 금지)하고, 가장 이른 날짜는 `CASE WHEN`으로 고르고(`MIN(a, b)` 금지), 별칭은 모두 선언하게 했어요.
- **few-shot 5개:** validation 셋(id 290·535·721·447·299)에서 골랐어요. 단순 코호트, 기준일, UNION ALL로 결과 합치기, 관찰기간 겹침, 추적 종료일 예시예요. 그래서 val과 변형 테스트셋에서는 이 5건(과 그 시드의 변형)을 모든 모델에서 빼고 집계해요.
- 이전 버전(v1, 하위 전개 규칙만 있고 few-shot 없음)도 학습셋으로 테스트했어요(`results/adapter_eval/prompts/adapter_eval_base_sysprompt_system_prompt.txt`). 성능이 낮아서 보고서에는 v2만 반영했어요([01_train.md](01_train.md) 2.2절).

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

테스트셋의 `text`(질의)와 `input`(재료)을 합쳐서 만들어요.

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

- **학습 때 형식과의 차이:** 학습 데이터(LLaMA Factory)는 `<질의>` + 줄바꿈 + `[재료]…` 형식이라, 평가 때 붙는 `[질의]` 머리말과 빈 줄이 없어요. 모든 모델에 똑같이 적용되는 차이라 모델 간 비교에는 영향이 없어요.
- FT0는 학습 때 재료 없이 질의만 받았지만, 평가 때는 다른 모델과 똑같이 재료를 포함해서 받아요.
