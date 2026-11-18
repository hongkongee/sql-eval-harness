# TTS 프롬프트 고정 반복 요청: 질의 100개, 순차 vs 병렬 (1·2차 합산)

NL2SQL 모델(`by-loss`)에 TTS와 똑같은 요청을 같은 프롬프트로 반복해 보냈습니다. temperature 0.0에서도 답이 달라지는지, 동시 요청이 영향을 주는지 확인했습니다.

- **1차:** 2026-11-17, 질의 50개 (`tts_seq50/`)
- **2차:** 2026-11-18, 다른 질의 50개 (`tts_seq50_b/`)
- 방법과 스크립트는 두 번 모두 같습니다. 자세한 설명은 `tts_seq50/README.md`에 있습니다.

## 방법

| 항목 | 내용 |
|---|---|
| 질의 | TTS `tests/test_queries_100.txt`(실제 서비스 형태 질의 120개)를 섞어서 순서대로 100개. `/rag`가 개념을 못 찾은 4개(q113~q117의 "~의 최고 측정값 조회")는 뺌 |
| 프롬프트 고정 | 질의마다 TTS `/rag`(`http://10.1.1.106:8080`)를 **한 번만** 불러 user 프롬프트를 저장하고, 이후 같은 프롬프트만 반복 사용 |
| 요청 형태 | TTS 코드(`prompt_builder.build_messages(..., mask=True)`)를 그대로 import 해서 만듦. system = TTS system 프롬프트(+자리표시자 규칙), user = `/rag` 프롬프트 |
| 모델·설정 | `http://10.1.1.69:8007`, `by-loss`, temperature 0.0, max_tokens 4096 (TTS `config.py` 값) |
| 순차 | 질의당 5번, 한 번에 하나씩. 보내기 전에 서버가 빌 때까지 기다리고, 처리 중 다른 요청과 겹치지 않았는지 기록. **500건 모두 서버에서 혼자 처리됨** |
| 병렬 mixed | 라운드마다 질의를 섞어 서로 다른 질의 4개씩 동시에. 질의당 5번, 500건. 212건은 외부 요청과도 겹침 |
| 병렬 same | 같은 질의 요청 4개를 동시에. 400건 |

동시 4개는 TTS의 LLM 동시 요청 상한(`LLM_CONCURRENCY=4`)에 맞춘 값입니다. 질의마다 응답이 14개씩, 모두 1,400건이고 오류는 없었습니다. 기준 답(A)은 순차 1회차의 답입니다.

## 결과

| 구분 | 결과 |
|---|---|
| 14번 모두 같은 답 | **95/100개** |
| 순차(하나씩)에서도 갈린 질의 | **2개** (q081, q120). 둘 다 실행 결과 같음 |
| 순차에선 5번 다 같았는데 병렬에서만 갈린 질의 | **3개** (q026, q094, q118) |
| 병렬 응답 중 순차에 없던 답 | **5/900건 (약 0.6%)**. mixed 4/500, same 1/400 |
| 실행 결과까지 달라진 질의 | **2개** (q026 행 수 다름, q094 문법 오류). q118은 반환 컬럼이 달라짐 |

### 갈린 질의 5개

| 질의 | 순차 | mixed | same | 무엇이 달라졌나 | 실행 결과 |
|---|---|---|---|---|---|
| q081 여성이고 알츠하이머병 진단인 환자 | AAA**BB** | AAAAA | AAAA | 성별 조건을 `gender_concept_id IN (SELECT descendant … 8532)` 대신 `= 8532`로 씀 | 같음 (1,911행) |
| q120 요추 T-score 측정 기록의 측정일과 측정값 | AA**BBB** | **BBBBB** | **B**A**B**A | 끝 세미콜론(`;`) 유무만 다름 | 같음 (0행)\* |
| q026 2014-01-01부터 2018-12-31까지 메트포르민 처방 이력 | AAAAA | A**BB**AA | **B**AAA | 기간 끝 조건을 `drug_exposure_start_date` 대신 **`drug_exposure_end_date`**`<= '2018-12-31'`로 씀 | **다름** (15,539 → 15,416행) |
| q094 현재 연도 기준 55세 이상 75세 미만, 이상지질혈증 진단 | AAAAA | **B**AAAA | AAAA | `EXTRACT(YEAR FROM p.birth_datetime')`처럼 따옴표 하나가 끼어듦 | **문법 오류** (`unterminated quoted string`) |
| q118 LDL 콜레스테롤 측정 기록의 측정일과 측정값 | AAAAA | A**B**AAA | AAAA | 단위 컬럼을 `unit_concept_id` 대신 `unit_source_value`로 반환 | 샌드박스에선 같음. **반환 컬럼이 달라** 실제 DB에선 다르게 보일 수 있음 |

\* q120의 A는 순차 분석 때 샌드박스에서 시간 초과가 났습니다. 다시 실행하니 B와 같은 0행이었습니다.

A와 다른 답이 나온 회차는 두 번(q026 mixed 2회차, q120 mixed 5회차)을 빼면 모두 외부 요청 없이 우리 요청만 처리되던 때였습니다. 이 두 번도 같은 답이 다른 회차에서는 우리 요청만 처리될 때 나왔습니다. 다른 사용자 요청이 섞여야만 생기는 현상은 아니라는 뜻입니다.

## 갈린 질의 5개 자세히

아래 SQL은 읽기 쉽게 줄을 바꾼 것입니다. 실제 응답은 한 줄이고, 원문은 각 폴더의 `responses*.jsonl`에 있습니다. 바뀐 부분에는 `-- ←` 주석을 달았습니다.

### 1. q081 여성이고 알츠하이머병 진단인 환자 (1차, 순차에서도 갈림)

| | 순차 | mixed | same | 횟수 |
|---|---|---|---|---|
| 답 | AAA**BB** | AAAAA | AAAA | A 12번, B 2번 |

A:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE p.gender_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                              WHERE ancestor_concept_id IN (8532))          -- ← 성별을 하위 개념 포함 방식으로
  AND EXISTS (SELECT 1 FROM condition_occurrence co
              WHERE co.person_id = p.person_id
                AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                                WHERE ancestor_concept_id IN (378419)));
```
B:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE p.gender_concept_id = 8532                                            -- ← 성별을 값 하나로
  AND EXISTS (SELECT 1 FROM condition_occurrence co
              WHERE co.person_id = p.person_id
                AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                                WHERE ancestor_concept_id IN (378419)));
```

- **다른 점:** 여성(8532) 조건을 쓰는 방식만 다릅니다. A는 진단 개념처럼 `concept_ancestor`로 하위 개념까지 포함해 걸었고, B는 `= 8532`로 걸었습니다.
- **결과:** 성별 개념에는 하위 개념이 없어서 둘 다 1,911행으로 같습니다.
- **어느 쪽이 맞나:** 재료에 성별 컬럼의 허용값이 `8507=남성, 8532=여성`으로 나와 있으므로 B(`= 8532`)가 더 자연스럽습니다. 비슷한 질의인 q076(남성 + 골다공증)과 q077(여성 + 심부전)은 14번 모두 같은 답이었습니다.
- **해석:** 모델이 "개념 조건은 항상 `concept_ancestor`로 건다"는 습관과 "허용값은 `=`로 건다" 사이에서 망설이는 지점입니다.

### 2. q120 요추 T-score 측정 기록의 측정일과 측정값을 조회 (2차, 순차에서도 갈림)

| | 순차 | mixed | same | 횟수 |
|---|---|---|---|---|
| 답 | AA**BBB** | **BBBBB** | **B**A**B**A | A 4번, B 10번 |

A:
```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.unit_source_value
FROM measurement m
WHERE m.measurement_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                   WHERE ancestor_concept_id IN (3049654));  -- ← 세미콜론 있음
```
B:
```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.unit_source_value
FROM measurement m
WHERE m.measurement_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                   WHERE ancestor_concept_id IN (3049654))   -- ← 세미콜론 없음
```

- **다른 점:** 끝 세미콜론 하나만 다릅니다.
- **결과:** 실행 결과는 같습니다.
- **해석:** 문장이 끝나는 위치에서 `;`를 붙일지 바로 끝낼지는, 다른 질의에서도 응답마다 섞여 나옵니다. 모델이 원래 반반으로 고르는 지점이라 순차로 보내도 갈렸습니다. 기준 답 A보다 B가 더 많이 나왔습니다.

### 3. q026 2014-01-01부터 2018-12-31까지 메트포르민 처방 이력이 있는 환자 (1차, 병렬에서만 갈림)

| | 순차 | mixed | same | 횟수 |
|---|---|---|---|---|
| 답 | AAAAA | A**BB**AA | **B**AAA | A 11번, B 3번 |

A:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE EXISTS (SELECT 1 FROM drug_exposure de
              WHERE de.person_id = p.person_id
                AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                           WHERE ancestor_concept_id IN (1503297))
                AND de.drug_exposure_start_date >= DATE '2014-01-01'
                AND de.drug_exposure_start_date <= DATE '2018-12-31');      -- ← 처방 "시작일"이 기간 안
```
B:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE EXISTS (SELECT 1 FROM drug_exposure de
              WHERE de.person_id = p.person_id
                AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                           WHERE ancestor_concept_id IN (1503297))
                AND de.drug_exposure_start_date >= DATE '2014-01-01'
                AND de.drug_exposure_end_date <= DATE '2018-12-31');        -- ← 처방 "종료일"이 기간 끝 이전
```

- **다른 점:** 기간 끝(2018-12-31) 조건을 어떤 날짜 컬럼에 거는지만 다릅니다.
  - A: 처방을 **시작한 날**이 2014~2018년 안에 있으면 포함합니다.
  - B: 2014년 이후에 시작해서 2018년 말까지 **끝난** 처방만 포함합니다. 2018년에 시작해 2019년까지 이어진 처방은 빠집니다.
- **결과:** A는 15,539명, B는 15,416명입니다. **B가 123명 적습니다.**
- **어느 쪽이 맞나:** "2014~2018년 사이 처방 이력"은 보통 기간 안에 처방이 시작된 것(A)으로 봅니다. B는 기간에 걸친 처방을 빼므로 의도보다 좁습니다.
- **해석:** 같은 형태의 질의 8개 중 6개는 처음부터 B 방식(종료일)을, q026과 q030만 A 방식(시작일)을 썼습니다. 모델 안에 두 방식이 다 있고, q026은 둘이 거의 비슷한 지점이라 병렬 처리 때의 작은 오차로 뒤집혔습니다.
- **재료 문제:** `/rag` 재료의 기간 조건이 `"2014-01-01부터 2018-12-31까지" → 2014-01-01 이전`으로 잘못 나와 있어서, 기간 끝을 어떻게 걸지 모델에게 아무 안내가 없었습니다.

### 4. q094 현재 연도 기준 연령 55세 이상이고 75세 미만이고 이상지질혈증 진단인 환자 (1차, 병렬에서만 갈림)

| | 순차 | mixed | same | 횟수 |
|---|---|---|---|---|
| 답 | AAAAA | **B**AAAA | AAAA | A 13번, B 1번 |

A:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE (EXTRACT(YEAR FROM DATE '2026-11-17') - EXTRACT(YEAR FROM p.birth_datetime)) >= 55
  AND (EXTRACT(YEAR FROM DATE '2026-11-17') - EXTRACT(YEAR FROM p.birth_datetime)) < 75
  AND EXISTS (SELECT 1 FROM condition_occurrence co
              WHERE co.person_id = p.person_id
                AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                                WHERE ancestor_concept_id IN (4159131)))
```
B:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE (EXTRACT(YEAR FROM DATE '2026-11-17') - EXTRACT(YEAR FROM p.birth_datetime)) >= 55
  AND (EXTRACT(YEAR FROM DATE '2026-11-17') - EXTRACT(YEAR FROM p.birth_datetime')) < 75   -- ← birth_datetime 뒤에 ' 가 끼어듦
  AND EXISTS (SELECT 1 FROM condition_occurrence co
              WHERE co.person_id = p.person_id
                AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                                WHERE ancestor_concept_id IN (4159131)))
```

- **다른 점:** 두 번째 나이 조건의 `p.birth_datetime` 뒤에 작은따옴표(`'`) 하나가 끼어들었습니다. 바로 앞에 `DATE '2026-11-17'`처럼 따옴표로 끝나는 날짜가 반복돼서, 그 패턴이 섞여 들어간 것으로 보입니다.
- **결과:** B는 따옴표가 닫히지 않아 **문법 오류**(`unterminated quoted string`)로 실행되지 않습니다.
- **두 답 모두의 문제:** 재료는 나이 조건을 이렇게 주었습니다.
  ```
  - [나이] "55세 이상" → person.birth_datetime <= DATE '1971-11-17'  (그대로 WHERE 에 쓴다)
  - [나이] "75세 미만" → person.birth_datetime > DATE '1951-11-17'   (그대로 WHERE 에 쓴다)
  ```
  재료대로라면 `WHERE p.birth_datetime <= DATE '1971-11-17' AND p.birth_datetime > DATE '1951-11-17'`이 되어야 합니다. 그런데 모델은 매번 출생연도 차이를 계산하는 식으로 바꿨습니다. 이 방식은 생일이 지났는지를 따지지 않고, 식이 길어져서 이번처럼 토큰이 하나 잘못 끼어들 여지도 커집니다. 나이 조건이 있는 질의 7개(q088~q094) 모두 같은 방식이었습니다.

### 5. q118 LDL 콜레스테롤 측정 기록의 측정일과 측정값을 조회 (2차, 병렬에서만 갈림)

| | 순차 | mixed | same | 횟수 |
|---|---|---|---|---|
| 답 | AAAAA | A**B**AAA | AAAA | A 13번, B 1번 |

A:
```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number,
       m.unit_concept_id                                                    -- ← 단위 "개념 ID"
FROM measurement m
WHERE m.measurement_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                   WHERE ancestor_concept_id IN (3028437, 3009966, 3028288));
```
B:
```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number,
       m.unit_source_value                                                  -- ← 단위 "원본 문자열"
FROM measurement m
WHERE m.measurement_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor
                                   WHERE ancestor_concept_id IN (3028437, 3009966, 3028288));
```

- **다른 점:** 마지막 출력 컬럼만 다릅니다.
  - A: 단위를 개념 ID(`unit_concept_id`, 숫자)로 돌려줍니다.
  - B: 원본 단위 문자열(`unit_source_value`, 예: `mg/dL`)로 돌려줍니다.
- **결과:** 샌드박스 비교에서는 같게 나왔지만, 이유는 확인하지 않았습니다. 반환하는 컬럼 자체가 다르므로 실제 DB에서는 화면에 보이는 값이 달라질 수 있습니다.
- **어느 쪽이 맞나:** 질의는 "측정일과 측정값"만 물었으므로 단위 컬럼은 둘 다 질의에 없는 덧붙임입니다.
- **해석:** 같은 형태의 질의 q120은 매번 B 방식(`unit_source_value`)을 썼습니다. 측정값 조회에서 단위 컬럼을 어떤 것으로 붙일지 정해진 규칙이 없어, 모델이 질의마다 다르게 고르는 지점입니다.

### 다섯 개를 묶어 보면

| 유형 | 질의 | 실제 영향 |
|---|---|---|
| 표기 습관이 반반인 곳 (세미콜론, `IN` vs `=`) | q120, q081 | 없음 (실행 결과 같음) |
| 규칙이 없어 질의마다 다르게 고르는 곳 (기간 끝 날짜 컬럼, 단위 컬럼) | q026, q118 | 결과 행 수 또는 반환 컬럼이 달라짐 |
| 재료를 무시하고 긴 식을 직접 만드는 곳 (나이) | q094 | 토큰 하나가 잘못 끼어 문법 오류 |

## 갈린 곳의 공통점: 원래 모델이 애매하게 고르는 지점

갈린 곳은 무작위로 퍼져 있지 않았습니다. 같은 형태의 다른 질의에서도 모델이 질의마다 다르게 고르는 지점이었습니다.

- **처방 기간의 끝 날짜 컬럼 (q026):** "YYYY-MM-DD부터 YYYY-MM-DD까지 ○○ 처방 이력" 형태의 질의는 8개입니다. 질의마다 답은 거의 고정이지만, 질의끼리는 일관되지 않았습니다.
  - 기간 끝을 `drug_exposure_end_date`로 건 질의(6개): q027, q028, q029, q031, q032, q033
  - `drug_exposure_start_date`로 건 질의(2개): q026, q030
  - q026은 이 둘 사이에서 흔들렸습니다.
  - 또 8개 모두 `/rag` 재료의 [TIME] 조건이 `"2014-01-01부터 2018-12-31까지" → 2014-01-01 이전`처럼 잘못 만들어져 있습니다. 기간이 "시작일 이전" 하나로 줄어든 상태입니다.
- **측정값 조회의 단위 컬럼 (q118):** 같은 형태인 q120은 `unit_source_value`, q118은 주로 `unit_concept_id`를 씁니다.
- **나이 조건 (q094):** 나이가 들어간 질의 7개(q088~q094) 모두, 재료가 "그대로 WHERE 에 쓴다"고 준 `person.birth_datetime <= DATE '…'` 조건을 쓰지 않았습니다. 대신 매번 `EXTRACT(YEAR …) - EXTRACT(YEAR …)`로 바꿨습니다. 이 표현을 직접 길게 만들다 보니 q094처럼 따옴표가 끼어드는 오류가 날 수 있습니다.

## 결론

1. **temperature 0에서 하나씩 보내면 거의 같은 답이 나옵니다.** 100개 중 2개만 갈렸고, 둘 다 실행 결과가 같은 표기 차이였습니다.
2. **동시에 보내면 드물게 실제로 다른 답이 나옵니다.** 응답 900건 중 5건(약 0.6%), 질의 100개 중 3개였습니다. 그중 1개는 결과 행 수가 바뀌었고, 1개는 실행이 안 되는 SQL이었습니다.
   - TTS는 LLM 요청을 최대 4개까지 동시에 보내므로, 실제 서비스에서도 이 정도로 생길 수 있습니다. 모델 서버를 다른 곳과 같이 쓰면 더 생길 수 있습니다.
   - 원인은 동시에 처리되는 요청 수가 바뀌면서 생기는 GPU 연산의 아주 작은 소수점 오차로 보입니다. 이 오차가 점수가 비슷한 두 토큰 사이의 선택을 뒤집습니다.
3. **"계속 다르게 나온다"는 현상은 이번 조건만으로는 잘 설명되지 않습니다.** 프롬프트를 고정하고 temperature 0이면 갈림은 드뭅니다. 그런 현상이 자주 보인다면 다음 원인을 먼저 의심해야 합니다.
   - temperature를 넣지 않은 요청(기본값 1.0, `../README.md`)
   - 요청마다 `/rag` 재료가 바뀌는 경우(이번 시험 범위 밖)
4. **줄이는 방법:** 서버 설정보다 애매한 지점을 없애는 쪽이 효과가 클 것으로 봅니다.
   - `/rag` [TIME] 기간 재료를 바로잡기
   - 기간 조건과 출력 컬럼 규칙을 학습 데이터나 system 프롬프트에서 하나로 정하기
   - [나이] 재료를 그대로 쓰도록 학습하기
   - 서버 쪽 해결(vLLM batch-invariant 모드)은 속도가 떨어지고, 지금 서버 버전에서 쓸 수 있는지 확인하지 않았습니다.

## 전체 질의 (100개)

굵게 표시한 칸은 기준 답(A)과 다른 답이 섞인 경우입니다.

| 차수 | 질의 | 순차 (5) | mixed (5) | same (4) |
|---|---|---|---|---|
| 2차 | q001 메트포르민 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q002 아토르바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q003 심바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q004 로수바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q005 데노수맙 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q007 엠파글리플로진 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q008 시타글립틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q009 도네페질 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q010 타목시펜 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q011 골다공증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q012 심부전 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q013 천식 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q014 치매 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q015 백내장 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q016 알츠하이머병 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q017 협심증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q018 이상지질혈증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q019 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q020 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q021 혈액투석을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q022 항암화학요법을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q023 유방절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q024 전립선절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q025 고관절 부분치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q026 2014-01-01부터 2018-12-31까지 메트포르민 처방 이력이 있는 환자. | AAAAA | **ABBAA** | **BAAA** |
| 2차 | q027 2016-01-01부터 2020-12-31까지 아토르바스타틴 처방 이력이 있는 환 | AAAAA | AAAAA | AAAA |
| 2차 | q028 2013-01-01부터 2019-12-31까지 심바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q029 2017-01-01부터 2021-12-31까지 로수바스타틴 처방 이력이 있는 환자 | AAAAA | AAAAA | AAAA |
| 1차 | q030 2012-01-01부터 2016-12-31까지 데노수맙 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q031 2015-01-01부터 2020-12-31까지 세마글루타이드 처방 이력이 있는 환 | AAAAA | AAAAA | AAAA |
| 2차 | q032 2011-01-01부터 2015-12-31까지 엠파글리플로진 처방 이력이 있는 환 | AAAAA | AAAAA | AAAA |
| 2차 | q033 2018-01-01부터 2022-12-31까지 시타글립틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q035 관찰기간이 2012-06-15부터 2016-02-28까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q036 관찰기간이 2019-01-01부터 2022-12-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q037 관찰기간이 2013-07-01부터 2017-05-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q038 관찰기간이 2016-11-01부터 2020-04-30까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q040 최근 1년 이내 골다공증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q041 최근 2년 이내 심부전 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q042 최근 3년 이내 천식 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q043 최근 5년 이내 치매 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q044 최근 1년 이내 백내장 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q045 최근 2년 이내 알츠하이머병 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q047 최근 5년 이내 이상지질혈증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q048 지난 6개월 이내 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q049 지난 12개월 이내 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q051 지난 24개월 이내 항암화학요법을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q053 지난 18개월 이내 전립선절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q055 2021년 이후 심부전 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q056 2019년 이후 천식 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q057 2022년 이후 치매 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q058 2018년 이후 백내장 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q059 2020년 이후 알츠하이머병 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q060 2018년에 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q061 2020년에 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q064 2019년에 유방절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q065 2016년에 전립선절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q067 천식의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| 1차 | q068 백내장의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| 2차 | q069 알츠하이머병의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| 1차 | q070 메트포르민 최초 처방일을 조회. | AAAAA | AAAAA | AAAA |
| 2차 | q071 아토르바스타틴 최초 처방일을 조회. | AAAAA | AAAAA | AAAA |
| 2차 | q072 심바스타틴 최초 처방일을 조회. | AAAAA | AAAAA | AAAA |
| 1차 | q073 로수바스타틴 최종 처방일을 조회. | AAAAA | AAAAA | AAAA |
| 1차 | q074 데노수맙 최종 처방일을 조회. | AAAAA | AAAAA | AAAA |
| 1차 | q076 남성이고 골다공증 진단인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q077 여성이고 심부전 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q078 남성이고 천식 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q079 여성이고 치매 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q080 남성이고 백내장 진단인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q081 여성이고 알츠하이머병 진단인 환자. | **AAABB** | AAAAA | AAAA |
| 2차 | q082 외래 방문 기록이 있고 알츠하이머병 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q083 응급실 방문 기록이 있고 협심증 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q084 입원 기록이 있고 이상지질혈증 진단인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q085 외래 방문 기록이 있고 뇌졸중 진단인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q086 주상병이 본태성 고혈압인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q087 주상병이 만성신장질환인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q088 현재 연도 기준 연령 70세 이상이고 심부전 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q089 현재 연도 기준 연령 75세 이상이고 천식 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q090 현재 연도 기준 연령 80세 이상이고 치매 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q091 현재 연도 기준 연령 40세 이상이고 60세 미만이고 백내장 진단인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q092 현재 연도 기준 연령 50세 이상이고 70세 미만이고 알츠하이머병 진단인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q093 현재 연도 기준 연령 60세 이상이고 80세 미만이고 협심증 진단인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q094 현재 연도 기준 연령 55세 이상이고 75세 미만이고 이상지질혈증 진단인 환자. | AAAAA | **BAAAA** | AAAA |
| 2차 | q095 골다공증 진단이고 메트포르민 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q096 심부전 진단이고 아토르바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q097 천식 진단이고 심바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q099 백내장 진단 이력이 있고 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q100 알츠하이머병 진단 이력이 있고 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q102 총콜레스테롤 값이 240 이상인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q103 크레아티닌 값이 1.5 초과인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q104 혈당 값이 200 이상인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q105 eGFR 값이 60 미만인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q106 수축기혈압 값이 140 이상인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q108 LDL 콜레스테롤 값이 160 이상인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q110 PSA 값이 4.0 이상인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q111 C-반응성 단백질 값이 10 초과인 환자. | AAAAA | AAAAA | AAAA |
| 1차 | q112 혈청 또는 혈장 총 칼슘 값이 10.5 이상인 환자. | AAAAA | AAAAA | AAAA |
| 2차 | q118 LDL 콜레스테롤 측정 기록의 측정일과 측정값을 조회. | AAAAA | **ABAAA** | AAAA |
| 1차 | q119 PSA 측정 기록의 측정일과 측정값을 조회. | AAAAA | AAAAA | AAAA |
| 2차 | q120 요추 T-score 측정 기록의 측정일과 측정값을 조회. | **AABBB** | **BBBBB** | **BABA** |

## 파일

| 위치 | 내용 |
|---|---|
| `tts_seq50/` | 1차: 스크립트, `rag/`(`/rag` 응답), `requests.json`(고정 요청), `responses*.jsonl`(응답 원문), `report*.md`(자동 생성 리포트) |
| `tts_seq50_b/` | 2차: 같은 구성 |
