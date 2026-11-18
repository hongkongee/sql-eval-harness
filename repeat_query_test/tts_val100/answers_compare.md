# 갈린 질의 10개: 답 원문 비교 (3차, 2026-11-18)

`report_summary.md`에서 답이 갈린 10개 질의의 **모델 응답 원문**을 그대로 옮겼습니다. 응답은 한 줄이라 코드 블록이 옆으로 깁니다. 원본은 `responses.jsonl`(순차), `responses_par.jsonl`(병렬)의 `sql` 필드입니다. 자리표시자 복원 전후(`sql`, `sql_restored`)가 1,400건 모두 같아서 원문 하나만 싣습니다.

- 답 이름: 순차 1회차 답을 A로 하고, 이후 처음 나온 순서대로 B, C를 붙였습니다.
- 나온 곳: `순차 n` = 순차 n회차, `mixed n`/`same n` = 병렬 n회차. (x)는 외부 요청과 겹친 응답, 표시가 없으면 우리 요청만 처리된 응답입니다.
- A와 다른 부분: A 원문을 기준으로 `[-빠진 것-]`, `[+들어간 것+]`로 표시했습니다. 같은 부분이 길면 ` … `로 줄였습니다.
- 실행 결과와 정답 일치(EX)는 샌드박스 DB에서 확인한 값입니다.

| # | 질의 | 답 종류 | 순차 | mixed | same | 실행 결과 달라짐 | concept_id 갈림 |
|---|---|---|---|---|---|---|---|
| 1 | [val_441](#1-val_441) 사쿠비트릴·발사르탄 처방 이력이 있는 환자를 노출군으로 | 3 | ABCCC | BBCAA | CCCC | **예** | **예** |
| 2 | [val_445](#2-val_445) 심부전 또는 입원의 최초 발생일을 조회. | 2 | ABBAB | BBBAB | AAAA | 아니오 | 아니오 |
| 3 | [val_261](#3-val_261) 인슐린 처방인 환자. | 2 | AAAAB | BAABA | BBBA | **예** | 아니오 |
| 4 | [val_420](#4-val_420) 유방절제술 최초 시행일을 기준일(index date)로 | 2 | AAAAA | ABBAA | AAAA | **예** | 아니오 |
| 5 | [val_720](#5-val_720) 전이성 악성 신생물의 최초 발생일을 조회. | 2 | AAAAA | BBBBB | BBBA | 아니오 | 아니오 |
| 6 | [val_468](#6-val_468) 고관절 골관절염 대상 코호트에서 OMOP CDM mea | 2 | AAAAA | ABAAB | AAAA | **예** | 아니오 |
| 7 | [seed_598](#7-seed_598) 합병증을 동반하지 않은 당뇨병 대상 코호트 중 OMOP | 2 | AAAAA | AABAA | BAAA | **예** | **예** |
| 8 | [seed_747](#8-seed_747) 각 환자의 생존 여부(사망 또는 생존)와 사망일을 조회 | 2 | AAAAA | BAABB | BAAA | 아니오 | 아니오 |
| 9 | [seed_690](#9-seed_690) OMOP CDM procedure 도메인 기록이 있는  | 3 | AAAAA | BCAAB | BBBB | 아니오 | 아니오 |
| 10 | [seed_547](#10-seed_547) 기준시점(trimetazidine  최초 처방일)부터  | 2 | AAABB | BBBAB | BBBB | 아니오 | 아니오 |


## 1. val_441

**질의:** 사쿠비트릴·발사르탄 처방 이력이 있는 환자를 노출군으로 정의.  
**출처·섹션·난이도:** val · 2.노출군 · MEDIUM

| 순차 | mixed | same |
|---|---|---|
| ABCCC | BBCAA | CCCC |

**차이 요약:** B는 A 끝에 `HAVING COUNT(*) >= 1`만 붙임(결과 같음). C는 발사르탄 단일제 `1308842`를 OR로 추가해 결과가 12배 가까이 늘어남. `/rag` 후보 2순위 `1308842`의 한글명이 복합제 제품명이라 생긴 갈림.

### val_441 — 답 A (3번)

- 나온 곳: 순차 1, mixed 4, mixed 5 (x)
- 생성 토큰 수: 66
- 실행 결과: 1,120행 / 정답 일치: pass

```sql
SELECT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (46275719))) GROUP BY p.person_id
```

### val_441 — 답 B (3번)

- 나온 곳: 순차 2, mixed 1, mixed 2
- 생성 토큰 수: 74
- 실행 결과: 1,120행 (A와 같음) / 정답 일치: pass

```sql
SELECT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (46275719))) GROUP BY p.person_id HAVING COUNT(*) >= 1;
```

A와 다른 부분:

```diff
SELECT p.person_id FROM person p WH … N (46275719))) GROUP BY p.person_id[+ HAVING COUNT(*) >= 1;+]
```

### val_441 — 답 C (8번)

- 나온 곳: 순차 3, 순차 4, 순차 5, mixed 3, same 1, same 2, same 3, same 4
- 생성 토큰 수: 126
- 실행 결과: **13,041행** / 정답 일치: fail

```sql
SELECT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (46275719))) OR EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (1308842))) GROUP BY p.person_id HAVING COUNT(*) >= 1;
```

A와 다른 부분:

```diff
SELECT p.person_id FROM person p WH … ncestor_concept_id IN (46275719))) [+OR EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (1308842))) +]GROUP BY p.person_id[+ HAVING COUNT(*) >= 1;+]
```

### val_441 — 정답 SQL

```sql
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS ( SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (46275719)) );
```

## 2. val_445

**질의:** 심부전 또는 입원의 최초 발생일을 조회.  
**출처·섹션·난이도:** val · 4.결과 · MEDIUM

| 순차 | mixed | same |
|---|---|---|
| ABBAB | BBBAB | AAAA |

**차이 요약:** 심부전 조건을 `MIN(CASE WHEN …)`과 `HAVING`으로 거르느냐(A), `WHERE`로 먼저 거르느냐(B)의 차이. 결과 같음. 둘 다 '입원'(visit)을 빠뜨려 정답과 다름.

### val_445 — 답 A (7번)

- 나온 곳: 순차 1, 순차 4, mixed 4 (x), same 1, same 2, same 3, same 4
- 생성 토큰 수: 172
- 실행 결과: 18,573행 / 정답 일치: fail

```sql
SELECT co.person_id, MIN(CASE WHEN co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (316139, 314378, 318445, 439846, 4273632)) THEN co.condition_start_date END) AS first_event_date FROM condition_occurrence co GROUP BY co.person_id HAVING COUNT(CASE WHEN co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (316139, 314378, 318445, 439846, 4273632)) THEN 1 END) > 0;
```

### val_445 — 답 B (7번)

- 나온 곳: 순차 2, 순차 3, 순차 5, mixed 1 (x), mixed 2 (x), mixed 3, mixed 5 (x)
- 생성 토큰 수: 91
- 실행 결과: 18,573행 (A와 같음) / 정답 일치: fail

```sql
SELECT co.person_id, MIN(co.condition_start_date) AS first_event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (316139, 314378, 318445, 439846, 4273632)) GROUP BY co.person_id;
```

A와 다른 부분:

```diff
SELECT co.person_id, MIN([-CASE-][+co.condition_start_date)+] [-WHEN-][+AS first_event_date FROM condition_occurrence co WHERE+] co.condition_concept_id IN (SELECT …  314378, 318445, 439846, 4273632)) [-THEN co.condition_start_date END) AS first_event_date FROM condition_occurrence co -]GROUP BY co.person_id[- HAVING COUNT(CASE WHEN co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (316139, 314378, 318445, 439846, 4273632)) THEN 1 END) > 0-];
```

### val_445 — 정답 SQL

```sql
WITH outcome_events AS ( SELECT co.person_id, co.condition_start_date AS event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (316139)) UNION ALL SELECT vo.person_id, vo.visit_start_date AS event_date FROM visit_occurrence vo WHERE vo.visit_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (9201)) ) SELECT oe.person_id, MIN(oe.event_date) AS first_event_date FROM outcome_events oe GROUP BY oe.person_id;
```

## 3. val_261

**질의:** 인슐린 처방인 환자.  
**출처·섹션·난이도:** val · 1.연구대상자 · MEDIUM

| 순차 | mixed | same |
|---|---|---|
| AAAAB | BAABA | BBBA |

**차이 요약:** B는 맨 끝에 닫는 괄호 `)`가 하나 더 있어 실행되지 않음. 둘 다 후보 5개를 모두 넣어 정답(`46221581`)과 다름.

### val_261 — 답 A (8번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, mixed 2 (x), mixed 3 (x), mixed 5 (x), same 4
- 생성 토큰 수: 101
- 실행 결과: 9,103행 / 정답 일치: fail

```sql
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (19013926, 1502905, 35602717, 19090244, 1516976)) );
```

### val_261 — 답 B (6번)

- 나온 곳: 순차 5, mixed 1 (x), mixed 4 (x), same 1, same 2, same 3
- 생성 토큰 수: 101
- 실행 결과: **문법 오류** (`syntax error at or near ")"`) / 정답 일치: fail

```sql
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (19013926, 1502905, 35602717, 19090244, 1516976))));
```

A와 다른 부분:

```diff
SELECT DISTINCT p.person_id FROM pe … 2905, 35602717, 19090244, 1516976))[- -][+)+]);
```

### val_261 — 정답 SQL

```sql
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (46221581)));
```

## 4. val_420

**질의:** 유방절제술 최초 시행일을 기준일(index date)로 하고 기준일 이전 동일 시행 이력이 없는 환자이며 유방암 진단 이력이 있는 환자.  
**출처·섹션·난이도:** val · 3.비교군 · MEDIUM

| 순차 | mixed | same |
|---|---|---|
| AAAAA | ABBAA | AAAA |

**차이 요약:** B는 유방암 진단이 기준일(시술일) 이전이어야 한다는 조건 `co.condition_start_date <= po.procedure_date`가 빠짐. 정답에는 이 조건이 있음. A는 후보 5개를 모두 넣어 샌드박스에서 시간 초과(정답은 개념 1개로 0초, 224행).

### val_420 — 답 A (12번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, 순차 5, mixed 1 (x), mixed 4, mixed 5 (x), same 1, same 2, same 3, same 4
- 생성 토큰 수: 263
- 실행 결과: **시간 초과** (샌드박스 30초 제한, 다시 실행해도 같음) / 정답 일치: fail

```sql
SELECT po.person_id, MIN(po.procedure_date) AS index_date FROM procedure_occurrence po WHERE po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (37164749, 4066543, 4129188, 4275911, 4322169)) AND NOT EXISTS ( SELECT 1 FROM procedure_occurrence prior_po WHERE prior_po.person_id = po.person_id AND prior_po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (37164749, 4066543, 4129188, 4275911, 4322169)) AND prior_po.procedure_date < po.procedure_date ) AND EXISTS ( SELECT 1 FROM condition_occurrence co WHERE co.person_id = po.person_id AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4112853)) AND co.condition_start_date <= po.procedure_date ) GROUP BY po.person_id;
```

### val_420 — 답 B (2번)

- 나온 곳: mixed 2, mixed 3
- 생성 토큰 수: 253
- 실행 결과: 645행 / 정답 일치: fail

```sql
SELECT po.person_id, MIN(po.procedure_date) AS index_date FROM procedure_occurrence po WHERE po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (37164749, 4066543, 4129188, 4275911, 4322169)) AND NOT EXISTS ( SELECT 1 FROM procedure_occurrence prior_po WHERE prior_po.person_id = po.person_id AND prior_po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (37164749, 4066543, 4129188, 4275911, 4322169)) AND prior_po.procedure_date < po.procedure_date ) AND EXISTS ( SELECT 1 FROM condition_occurrence co WHERE co.person_id = po.person_id AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4112853)) ) GROUP BY po.person_id;
```

A와 다른 부분:

```diff
SELECT po.person_id, MIN(po.procedu …  ancestor_concept_id IN (4112853)) [-AND co.condition_start_date <= po.procedure_date -]) GROUP BY po.person_id;
```

### val_420 — 정답 SQL

```sql
SELECT po.person_id, MIN(po.procedure_date) AS index_date FROM procedure_occurrence po WHERE po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4066543)) AND NOT EXISTS ( SELECT 1 FROM procedure_occurrence prior_po WHERE prior_po.person_id = po.person_id AND prior_po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4066543)) AND prior_po.procedure_date < po.procedure_date ) AND EXISTS ( SELECT 1 FROM condition_occurrence co WHERE co.person_id = po.person_id AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4112853)) AND co.condition_start_date <= po.procedure_date ) GROUP BY po.person_id;
```

## 5. val_720

**질의:** 전이성 악성 신생물의 최초 발생일을 조회.  
**출처·섹션·난이도:** val · 4.결과 · MEDIUM

| 순차 | mixed | same |
|---|---|---|
| AAAAA | BBBBB | BBBA |

**차이 요약:** B는 같은 내용을 `WITH outcome_events` CTE로 씀(정답과 같은 모양). 결과 같음.

### val_720 — 답 A (6번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, 순차 5, same 4
- 생성 토큰 수: 58
- 실행 결과: 6,421행 / 정답 일치: pass

```sql
SELECT co.person_id, MIN(co.condition_start_date) AS first_event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (432851)) GROUP BY co.person_id;
```

### val_720 — 답 B (8번)

- 나온 곳: mixed 1 (x), mixed 2 (x), mixed 3 (x), mixed 4 (x), mixed 5 (x), same 1, same 2, same 3
- 생성 토큰 수: 80
- 실행 결과: 6,421행 (A와 같음) / 정답 일치: pass

```sql
WITH outcome_events AS ( SELECT co.person_id, co.condition_start_date AS event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (432851)) ) SELECT oe.person_id, MIN(oe.event_date) AS first_event_date FROM outcome_events oe GROUP BY oe.person_id;
```

A와 다른 부분:

```diff
[+WITH outcome_events AS ( +]SELECT co.person_id, [-MIN(-]co.condition_start_date[-)-] AS [-first_event_date-][+event_date+] FROM condition_occurrence co WHERE … E ancestor_concept_id IN (432851)) [+) SELECT oe.person_id, MIN(oe.event_date) AS first_event_date FROM outcome_events oe +]GROUP BY [-co-][+oe+].person_id;
```

### val_720 — 정답 SQL

```sql
WITH outcome_events AS ( SELECT co.person_id, co.condition_start_date AS event_date FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (432851)) ) SELECT oe.person_id, MIN(oe.event_date) AS first_event_date FROM outcome_events oe GROUP BY oe.person_id;
```

## 6. val_468

**질의:** 고관절 골관절염 대상 코호트에서 OMOP CDM measurement 테이블의 측정일과 측정값을 확인.  
**출처·섹션·난이도:** val · 4.결과 · EASY

| 순차 | mixed | same |
|---|---|---|
| AAAAA | ABAAB | AAAA |

**차이 요약:** A는 `range_low, range_high`, B는 `unit_source_value`를 덧붙임. 정답은 `unit_concept_id`. 둘 다 상위개념 `80180`(골관절염)을 골라 정답 `4079749`(고관절 골관절염)와 다름.

### val_468 — 답 A (12번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, 순차 5, mixed 1 (x), mixed 3 (x), mixed 4, same 1, same 2, same 3, same 4
- 생성 토큰 수: 76
- 실행 결과: 1,278,608행 / 정답 일치: fail

```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.range_low, m.range_high FROM measurement m WHERE m.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (80180)) );
```

### val_468 — 답 B (2번)

- 나온 곳: mixed 2 (x), mixed 5 (x)
- 생성 토큰 수: 73
- 실행 결과: 1,278,608행, **반환 컬럼 다름** / 정답 일치: fail

```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.unit_source_value FROM measurement m WHERE m.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (80180)) );
```

A와 다른 부분:

```diff
SELECT m.person_id, m.measurement_c … urement_date, m.value_as_number, m.[-range_low, m.range_high-][+unit_source_value+] FROM measurement m WHERE m.person_ …  ancestor_concept_id IN (80180)) );
```

### val_468 — 정답 SQL

```sql
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.unit_concept_id FROM measurement m WHERE m.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4079749)) );
```

## 7. seed_598

**질의:** 합병증을 동반하지 않은 당뇨병 대상 코호트 중 OMOP CDM에 관찰기간이 기록된 환자.  
**출처·섹션·난이도:** eval_ready · 5.기간설정 · EASY

| 순차 | mixed | same |
|---|---|---|
| AAAAA | AABAA | BAAA |

**차이 요약:** A는 합병증 동반 당뇨 `442793` 환자를 `EXCEPT`로 뺌. B는 빼지 않음. 둘 다 후보 1~4를 모두 넣어 정답(`4008576` 하나)과 다름.

### seed_598 — 답 A (12번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, 순차 5, mixed 1 (x), mixed 2 (x), mixed 4 (x), mixed 5, same 2, same 3, same 4
- 생성 토큰 수: 133
- 실행 결과: 53,832행 / 정답 일치: fail

```sql
SELECT op.person_id, op.observation_period_start_date, op.observation_period_end_date FROM observation_period op WHERE op.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4008576, 201254, 4193704, 4096042)) EXCEPT SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (442793)) );
```

### seed_598 — 답 B (2번)

- 나온 곳: mixed 3, same 1
- 생성 토큰 수: 94
- 실행 결과: **71,615행** / 정답 일치: fail

```sql
SELECT op.person_id, op.observation_period_start_date, op.observation_period_end_date FROM observation_period op WHERE op.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4008576, 201254, 4193704, 4096042)) );
```

A와 다른 부분:

```diff
SELECT op.person_id, op.observation … 008576, 201254, 4193704, 4096042)) [-EXCEPT SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (442793)) -]);
```

### seed_598 — 정답 SQL

```sql
SELECT op.person_id, op.observation_period_start_date, op.observation_period_end_date FROM observation_period op WHERE op.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4008576)) );
```

## 8. seed_747

**질의:** 각 환자의 생존 여부(사망 또는 생존)와 사망일을 조회해 주세요.  
**출처·섹션·난이도:** eval_ready · 4.결과 · MEDIUM

| 순차 | mixed | same |
|---|---|---|
| AAAAA | BAABB | BAAA |

**차이 요약:** B는 사망 테이블 조인 조건의 `d.death_date <= DATE '2026-11-18'`이 빠짐. 미래 사망일이 없어 결과 같음.

### seed_747 — 답 A (10번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, 순차 5, mixed 2 (x), mixed 3 (x), same 2, same 3, same 4
- 생성 토큰 수: 87
- 실행 결과: 79,941행 / 정답 일치: pass

```sql
SELECT p.person_id, CASE WHEN d.death_date IS NOT NULL AND d.death_date <= DATE '2026-11-18' THEN '사망' ELSE '생존' END AS survival_status, d.death_date FROM person p LEFT JOIN death d ON d.person_id = p.person_id AND d.death_date <= DATE '2026-11-18';
```

### seed_747 — 답 B (4번)

- 나온 곳: mixed 1, mixed 4 (x), mixed 5 (x), same 1
- 생성 토큰 수: 69
- 실행 결과: 79,941행 (A와 같음) / 정답 일치: pass

```sql
SELECT p.person_id, CASE WHEN d.death_date IS NOT NULL AND d.death_date <= DATE '2026-11-18' THEN '사망' ELSE '생존' END AS survival_status, d.death_date FROM person p LEFT JOIN death d ON d.person_id = p.person_id;
```

A와 다른 부분:

```diff
SELECT p.person_id, CASE WHEN d.dea … eath d ON d.person_id = p.person_id[- AND d.death_date <= DATE '2026-11-18'-];
```

### seed_747 — 정답 SQL

```sql
SELECT p.person_id, CASE WHEN d.death_date IS NOT NULL AND d.death_date is not null THEN '사망' ELSE '생존' END AS survival_status, d.death_date FROM person p LEFT JOIN death d ON d.person_id = p.person_id;
```

## 9. seed_690

**질의:** OMOP CDM procedure 도메인 기록이 있는 환자를 비교군으로 설정.  
**출처·섹션·난이도:** eval_ready · 3.비교군 · EASY

| 순차 | mixed | same |
|---|---|---|
| AAAAA | BCAAB | BBBB |

**차이 요약:** A는 `procedure_occurrence`에서 바로, B·C는 `person`에서 `EXISTS`로 고름. B와 C는 괄호 안 공백 하나만 다름. 결과 같음.

### seed_690 — 답 A (7번)

- 나온 곳: 순차 1, 순차 2, 순차 3, 순차 4, 순차 5, mixed 3 (x), mixed 4
- 생성 토큰 수: 12
- 실행 결과: 66,454행 / 정답 일치: pass

```sql
SELECT DISTINCT po.person_id FROM procedure_occurrence po;
```

### seed_690 — 답 B (6번)

- 나온 곳: mixed 1, mixed 5 (x), same 1, same 2, same 3, same 4
- 생성 토큰 수: 29
- 실행 결과: 66,454행 (A와 같음) / 정답 일치: pass

```sql
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM procedure_occurrence po WHERE po.person_id = p.person_id);
```

A와 다른 부분:

```diff
SELECT DISTINCT [-po-][+p+].person_id[+ FROM person p WHERE EXISTS (SELECT 1+] FROM procedure_occurrence po[+ WHERE po.person_id = p.person_id)+];
```

### seed_690 — 답 C (1번)

- 나온 곳: mixed 2 (x)
- 생성 토큰 수: 29
- 실행 결과: 66,454행 (A와 같음) / 정답 일치: pass

```sql
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS ( SELECT 1 FROM procedure_occurrence po WHERE po.person_id = p.person_id );
```

A와 다른 부분:

```diff
SELECT DISTINCT [-po-][+p+].person_id[+ FROM person p WHERE EXISTS ( SELECT 1+] FROM procedure_occurrence po[+ WHERE po.person_id = p.person_id )+];
```

### seed_690 — 정답 SQL

```sql
WITH procedure_persons AS (SELECT DISTINCT person_id FROM procedure_occurrence) SELECT person_id FROM procedure_persons;
```

## 10. seed_547

**질의:** 기준시점(trimetazidine  최초 처방일)부터 사망·자료 관찰 종료 중 최초까지 추적  
**출처·섹션·난이도:** eval_ready · 5.기간설정 · HARD

| 순차 | mixed | same |
|---|---|---|
| AAABB | BBBAB | BBBB |

**차이 요약:** 첫 CTE의 `select / min / as / from / where / group by`가 A는 소문자, B는 대문자. 나머지 같음.

### seed_547 — 답 A (4번)

- 나온 곳: 순차 1, 순차 2, 순차 3, mixed 4 (x)
- 생성 토큰 수: 244
- 실행 결과: 0행 / 정답 일치: pass

```sql
WITH index_dates AS ( select de.person_id, min(de.drug_exposure_start_date) as index_date from drug_exposure de where de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (19005626)) group by de.person_id ), follow_up_candidates AS ( SELECT i.person_id, i.index_date, d.death_date, op.observation_period_end_date FROM index_dates i JOIN observation_period op ON op.person_id = i.person_id AND i.index_date BETWEEN op.observation_period_start_date AND op.observation_period_end_date LEFT JOIN death d ON d.person_id = i.person_id AND d.death_date >= i.index_date ) SELECT f.person_id, f.index_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date THEN f.death_date ELSE f.observation_period_end_date END AS follow_up_end_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date THEN 'DEATH' ELSE 'OBSERVATION_END' END AS follow_up_end_reason FROM follow_up_candidates f;
```

### seed_547 — 답 B (10번)

- 나온 곳: 순차 4, 순차 5, mixed 1, mixed 2 (x), mixed 3 (x), mixed 5, same 1, same 2, same 3, same 4
- 생성 토큰 수: 244
- 실행 결과: 0행 (A와 같음) / 정답 일치: pass

```sql
WITH index_dates AS ( SELECT de.person_id, MIN(de.drug_exposure_start_date) AS index_date FROM drug_exposure de WHERE de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (19005626)) GROUP BY de.person_id ), follow_up_candidates AS ( SELECT i.person_id, i.index_date, d.death_date, op.observation_period_end_date FROM index_dates i JOIN observation_period op ON op.person_id = i.person_id AND i.index_date BETWEEN op.observation_period_start_date AND op.observation_period_end_date LEFT JOIN death d ON d.person_id = i.person_id AND d.death_date >= i.index_date ) SELECT f.person_id, f.index_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date THEN f.death_date ELSE f.observation_period_end_date END AS follow_up_end_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date THEN 'DEATH' ELSE 'OBSERVATION_END' END AS follow_up_end_reason FROM follow_up_candidates f;
```

A와 다른 부분:

```diff
WITH index_dates AS ( [-select-][+SELECT+] de.person_id, [-min-][+MIN+](de.drug_exposure_start_date) [-as-][+AS+] index_date [-from-][+FROM+] drug_exposure de [-where-][+WHERE+] de.drug_concept_id IN (SELECT desc … ancestor_concept_id IN (19005626)) [-group-][+GROUP+] [-by-][+BY+] de.person_id ), follow_up_candidat … reason FROM follow_up_candidates f;
```

### seed_547 — 정답 SQL

```sql
SELECT f.person_id, f.index_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date THEN f.death_date ELSE f.observation_period_end_date END AS follow_up_end_date, CASE WHEN f.death_date IS NOT NULL AND f.death_date <= f.observation_period_end_date THEN 'DEATH' ELSE 'OBSERVATION_END' END AS follow_up_end_reason FROM (SELECT i.person_id, i.index_date, d.death_date, op.observation_period_end_date FROM (SELECT de.person_id, MIN(de.drug_exposure_start_date) AS index_date FROM drug_exposure de WHERE de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (19005626)) GROUP BY de.person_id) i JOIN observation_period op ON op.person_id = i.person_id AND i.index_date BETWEEN op.observation_period_start_date AND op.observation_period_end_date LEFT JOIN death d ON d.person_id = i.person_id AND d.death_date >= i.index_date) f;
```
