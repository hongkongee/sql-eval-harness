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
