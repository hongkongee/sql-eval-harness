# 다양한 유형 질의 100개로 순차·병렬 반복 (3차, 2026-11-18)

1·2차(`../tts_seq50`, `../tts_seq50_b`, 합산 `../tts_seq_100_report.md`)는 TTS `tests/test_queries_100.txt`에서 뽑은 짧은 단일 조건 질의였습니다. 이번에는 연구설계 섹션 5개와 EASY~HARD를 고르게 섞은 질의 100개로 같은 시험을 했습니다. 방법, 요청 형태, 설정(`by-loss`, temperature 0.0, 동시 4개)은 1·2차와 같습니다.

## 결과 요약

> 순차와 병렬을 따로 센 요약 보고서는 **`report_summary.md`**에 있습니다. 아래 표의 병렬 숫자는 순차 1회차 답을 기준으로 센 것입니다.

- 실행: 2026-11-18 11:32~13:06 (약 1시간 34분). `/rag` 105번 호출(개념 재시도 5번), 100개 모두 프롬프트 확보, 예비 후보는 안 씀. LLM 응답 1,400건, 오류 0건
- 순차 500건은 모두 서버에서 혼자 처리됨. 병렬 900건 중 356건은 외부 요청과 겹침
- 자동 리포트: `report.md`(순차), `report_par.md`(병렬)

### 1·2차와 비교

| 구분 | 1·2차 (TTS 짧은 질의 100개) | **3차 (다양한 유형 100개)** |
|---|---|---|
| 14번 모두 같은 답 | 95/100 | **90/100** |
| 순차(하나씩)에서도 갈린 질의 | 2 | **4** (val_441, val_445, val_261, seed_547) |
| 병렬에서만 갈린 질의 | 3 | **6** (val_420, val_720, val_468, seed_598, seed_747, seed_690) |
| 병렬 응답 중 순차에 없던 답 | 5/900 (0.6%) | **25/900 (2.8%)**. mixed 16/500, same 9/400 |
| └ 외부 요청 없이 우리 요청만 돌 때 | 4/900 | **14/900** |
| 실행 결과까지 달라진 질의 | 2 | **5** (val_441, val_261, val_420, val_468, seed_598) |

질의가 길고 다양해지자 갈림이 약 2배, 병렬에서 새 답이 나오는 비율은 약 4배가 됐습니다. 1·2차 질의로는 갈림 빈도를 낮게 봤던 셈입니다.

### 갈린 질의 10개

A = 순차 1회차 답. o/x = 그 요청이 우리 요청만으로 처리됐는지(o) 외부 요청과 겹쳤는지(x).

| 질의 | 섹션·난이도 | 순차 | mixed | same | 달라진 점 | 실행 결과 | 정답 일치(EX) |
|---|---|---|---|---|---|---|---|
| **val_441** 사쿠비트릴·발사르탄 처방 이력 → 노출군 | 노출군 MEDIUM | A**BCCC** | **BBC**AA | **CCCC** | B: `HAVING COUNT(*) >= 1` 추가 / C: **발사르탄 단일제(1308842)를 OR로 추가** | **다름** (A·B 1,120행, C 13,041행) | A·B pass, **C fail** |
| **val_261** 인슐린 처방인 환자 | 연구대상자 MEDIUM | AAAA**B** | **B**AA**B**A | **BBB**A | 끝에 닫는 괄호 `)` 하나 더 | **B 문법 오류** | 둘 다 fail |
| **val_420** 유방절제술 최초 시행일 기준 신규 시행 + 유방암 진단 이력 | 비교군 MEDIUM | AAAAA | A**BB**AA | AAAA | B: 유방암 진단 조건에서 `condition_start_date <= procedure_date`(기준일 이전) 빠짐 | **다름** (A 시간 초과, B 645행) | 둘 다 fail |
| **val_468** 고관절 골관절염 코호트의 측정일·측정값 | 결과 EASY | AAAAA | A**B**AA**B** | AAAA | 반환 컬럼 `range_low, range_high` → `unit_source_value` | **다름** (행 수 같고 컬럼 다름) | 둘 다 fail |
| **seed_598** 합병증 없는 당뇨병 코호트 중 관찰기간 기록 | 기간설정 EASY | AAAAA | AA**B**AA | **B**AAA | B: `EXCEPT 합병증 동반 당뇨(442793)` 빠짐 | **다름** (53,832 → 71,615행) | 둘 다 fail |
| val_445 심부전 또는 입원의 최초 발생일 | 결과 MEDIUM | A**BB**A**B** | **BBB**A**B** | AAAA | `MIN(CASE WHEN …)` ↔ `WHERE … MIN()` | 같음 (18,573행) | 둘 다 fail |
| val_720 전이성 악성 신생물 최초 발생일 | 결과 MEDIUM | AAAAA | **BBBBB** | **BBB**A | B는 `WITH outcome_events` CTE로 씀 | 같음 (6,421행) | 둘 다 pass |
| seed_747 생존 여부와 사망일 | 결과 MEDIUM | AAAAA | **B**AA**BB** | **B**AAA | B: 조인 조건의 `death_date <= 기준일` 빠짐 | 같음 (79,941행) | 둘 다 pass |
| seed_690 procedure 기록 있는 환자 → 비교군 | 비교군 EASY | AAAAA | **BC**AA**B** | **BBBB** | `FROM procedure_occurrence` ↔ `person … WHERE EXISTS` | 같음 (66,454행) | 모두 pass |
| seed_547 trimetazidine 기준 추적 종료 | 기간설정 HARD | AAA**BB** | **BBB**A**B** | **BBBB** | 첫 CTE의 `select/min/group by` 소문자 ↔ 대문자 | 같음 (0행) | 둘 다 pass |

- **val_420 A의 시간 초과**는 다시 실행해도 같았습니다(샌드박스 제한 30초). 정답은 유방절제술 개념 1개로 0초에 224행이 나오는데, 모델은 후보 5개를 모두 넣어 느려졌습니다. B는 조건이 하나 빠졌으므로 A와 결과가 다릅니다.
- `/rag` 재시도로 확정 개념을 넣은 5개 질의(val_421, val_466, val_471, seed_408, seed_361)는 하나도 갈리지 않았습니다.

### 결과가 달라진 5개: A와 B

**val_441** (순차 5번 중 3번, same 4번 모두 틀린 C가 나옴)
```sql
-- A (정답과 같음)
SELECT p.person_id FROM person p
WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id
              AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (46275719)))
GROUP BY p.person_id
-- C
SELECT p.person_id FROM person p
WHERE EXISTS (… ancestor_concept_id IN (46275719) …)
   OR EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id
              AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (1308842)))  -- ← 발사르탄 단일제
GROUP BY p.person_id HAVING COUNT(*) >= 1;
```
`/rag` 후보 2순위가 `1308842 valsartan / 제네프리필름코팅정200밀리그램(사쿠비트릴·발사르탄나트륨염수화물)`입니다. 영문명은 발사르탄 단일 성분인데 한글명이 복합제 제품명이라, 모델이 둘 다 맞는 개념으로 보고 OR로 합치기도 합니다. 발사르탄 단일제 처방 환자까지 들어가 12배 가까이 늘어납니다.

**val_261**
```sql
-- A
SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (SELECT 1 FROM drug_exposure de WHERE de.person_id = p.person_id
  AND de.drug_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (19013926, 1502905, 35602717, 19090244, 1516976)) );
-- B
… ancestor_concept_id IN (19013926, 1502905, 35602717, 19090244, 1516976))));   -- ← 닫는 괄호 하나 더 → 문법 오류
```
A·B 모두 후보 5개를 다 넣었습니다(정답은 `46221581` 하나). 괄호를 하나 더 닫느냐는 점수가 비슷한 지점이어서, same에서는 4번 중 3번이 B였습니다.

**val_420**
```sql
-- A
… AND EXISTS (SELECT 1 FROM condition_occurrence co WHERE co.person_id = po.person_id
              AND co.condition_concept_id IN (… 4112853 …)
              AND co.condition_start_date <= po.procedure_date )   -- 정답에도 있는 조건
GROUP BY po.person_id;
-- B
… AND EXISTS (SELECT 1 FROM condition_occurrence co WHERE co.person_id = po.person_id
              AND co.condition_concept_id IN (… 4112853 …) )       -- ← 날짜 조건 빠짐
GROUP BY po.person_id;
```

**val_468**
```sql
-- A
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.range_low, m.range_high FROM measurement m WHERE …
-- B
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.unit_source_value FROM measurement m WHERE …
-- 정답
SELECT m.person_id, m.measurement_concept_id, m.measurement_date, m.value_as_number, m.unit_concept_id FROM measurement m WHERE …
```
"측정값과 측정일"만 물었는데 뒤에 붙이는 컬럼이 갈립니다. 1·2차의 q118(`unit_concept_id` ↔ `unit_source_value`)과 같은 유형입니다. 두 답 모두 개념도 상위개념 `80180`(골관절염)을 골라 정답(`4079749` 고관절 골관절염)과 다릅니다.

**seed_598**
```sql
-- A
SELECT op.person_id, op.observation_period_start_date, op.observation_period_end_date FROM observation_period op
WHERE op.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (… 4008576, 201254, 4193704, 4096042 …)
                        EXCEPT SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (… 442793 …) );
-- B
… WHERE op.person_id IN ( SELECT person_id FROM condition_occurrence WHERE condition_concept_id IN (… 4008576, 201254, 4193704, 4096042 …) );  -- ← EXCEPT 없음
```
`/rag` 후보 5번째에 `442793 Complication due to diabetes mellitus`(합병증 동반 당뇨)가 섞여 있어서, 이를 "빼야 할 개념"으로 쓸지 말지가 갈렸습니다. 정답은 `4008576` 하나만 씁니다.

### 해석

1. **갈림은 여전히 "모델이 원래 애매한 지점"에서만 생깁니다.** 다만 질의가 다양해지자 그런 지점이 많아졌습니다.
   - **애매한 개념 후보:** val_441(한글명이 복합제인 단일 성분), seed_598(반대 뜻의 개념이 후보에 섞임)
   - **후보를 1개 고르라는 지시를 안 따름:** val_261, val_420, val_445, seed_598은 후보 5개를 모두 IN에 넣었습니다. 이것 자체는 매번 같았지만 SQL이 길고 복잡해져 다른 갈림(괄호, 조건 누락)이 생길 여지가 커집니다.
   - **덧붙이는 컬럼·조건:** val_468(단위/범위 컬럼), seed_747·val_420(날짜 조건)
   - **표기만 다름:** 대소문자, CTE, EXISTS, CASE 위치 등. 결과는 같습니다.
2. **"결과" 섹션이 16개 중 4개로 가장 많이 갈렸습니다.** 측정값·최초 발생일 조회처럼 출력 형태(컬럼, 집계 방식)를 질의가 정하지 않는 유형입니다. HARD는 16개 중 1개(seed_547, 대소문자 차이)만 갈려 난이도와는 관계가 약했습니다.
3. **같은 질의를 4개 동시에 보내면(same) 순차와 다른 답으로 한꺼번에 기우는 경우가 있습니다.** seed_690 BBBB, seed_547 BBBB, val_441 CCCC, val_261 BBBA, val_720 BBBA. 모두 우리 요청만 처리될 때였습니다. 함께 처리하는 요청 수가 바뀌면 계산 경로가 바뀌어, 점수가 비슷한 두 후보 중 다른 쪽으로 일관되게 넘어가는 것으로 보입니다.
4. **외부 요청이 섞여야만 생기는 현상은 아닙니다.** 순차(모두 혼자 처리)에서도 4개가 갈렸고, 병렬 새 답 25건 중 14건은 우리 요청만 돌 때 나왔습니다.
5. **위험한 경우는 다수결로도 못 막습니다.** val_441은 틀린 C가 순차 3/5, same 4/4로 오히려 다수였습니다. 반복 요청으로 고르기보다, 애매한 후보를 줄이는 쪽(재료 정리, 후보 1개 선택 지시 강화)이 효과가 있을 것입니다.

### 갈린 질의 분포

| 구분 | 갈린 수 / 전체 |
|---|---|
| 출처 | val 6/68 · eval_ready 4/32 |
| 섹션 | 4.결과 **4/16** · 3.비교군 2/19 · 5.기간설정 2/30 · 2.노출군 1/18 · 1.연구대상자 1/17 |
| 난이도 | MEDIUM 6/50 · EASY 3/34 · HARD 1/16 |

## 질의 100개 고르는 방법 (`select_queries.py` → `candidates.json`)

1. **`test_set/proposed_input_val.jsonl` 68개 전부**
2. **`test_set/eval_ready`에서 32개.** 아래 조건으로 서로 최대한 다른 유형을 고릅니다.
   - **유형의 정의:** 섹션, 질의유형, 난이도에 정답 SQL 구조를 더해서 봅니다. SQL 구조는 쓰는 테이블과 `WITH`, `GROUP BY`, `MIN`, `NOT EXISTS`, `INTERVAL`, `LEFT JOIN` 같은 구문입니다.
   - **val 68개에 없는 유형만** 고릅니다. 문장 틀이 val과 같은 질의도 뺍니다. 문장 틀은 개념 이름, 숫자, 날짜, 끝 동사를 지운 문장입니다.
   - 섹션×난이도 칸을 번갈아 돌며 **유형당 1개**씩 고릅니다. 칸 안에서는 문항이 많은 유형, 즉 흔한 유형부터 고릅니다.
   - seed와 시나리오는 각각 1개씩만 씁니다. 고른 질의끼리도 문장 틀이 겹치지 않게 합니다.
   - 증강 방식(concept/paraphrase/restructure/slot)이 고르게 섞이도록 고릅니다.
3. **예비 후보:** 같은 방식으로 이어서 고른 30개를 뒤에 붙여 둡니다. `/rag`가 실패한 질의를 대신합니다.

| 항목 | 100개 구성 |
|---|---|
| 섹션 | 5.기간설정 30 · 3.비교군 19 · 2.노출군 18 · 1.연구대상자 17 · 4.결과 16 |
| 질의유형 | COHORT_EXTRACTION 54 · STATISTICAL_AGGREGATION 26 · VALUE_RETRIEVAL 13 · EXPLORATORY_SEARCH 7 |
| 난이도 | MEDIUM 50 · EASY 34 · HARD 16 |
| 문장 틀 | 73종 |

1·2차 TTS 질의와 비교하면 이렇습니다.
- **SQL 길이:** 70~130토큰 → 정답 기준 평균 약 500자, 최대 1,400자
- **새로 들어간 유형:** 신규 사용자 정의, 대조군(미노출), 추적 종료 시점(HARD), 최초 발생일 집계, 측정값 평균 차이, 사망·생존 조회

### eval_ready에서 고른 32개

| id | 섹션 | 난이도 | 질의유형 | 질의 |
|---|---|---|---|---|
| seed_696_test_concept | 1.연구대상자 | MEDIUM | COHORT_EXTRACTION | 심부전 진단이고 고관절 골관절염 진단인 환자. |
| seed_408_test_paraphrase | 3.비교군 | MEDIUM | COHORT_EXTRACTION | 위약/비노출 대조군 코호트 추출: 유방암 환자 중 연구 약물인 유방암 항암화학요법에 노출되지 않은 대상 — 1차 결과: 치료 실행가능성 |
| seed_164_test_paraphrase | 2.노출군 | EASY | COHORT_EXTRACTION | 관찰 코호트 노출군으로 만성콩팥병 환자를 추출하고, 최초 진단일을 기준일로 계산한다. |
| seed_552_test_concept | 2.노출군 | MEDIUM | COHORT_EXTRACTION | 메트포르민 최초 처방일을 기준일로 하고 기준일 이전 메트포르민 처방 이력이 없는 환자. |
| seed_134_test_concept | 4.결과 | EASY | VALUE_RETRIEVAL | 혈청/혈장 요산 측정 기록의 측정일과 측정값을 조회. |
| seed_649_test_paraphrase | 3.비교군 | EASY | COHORT_EXTRACTION | 별도 대조군을 두지 않은 단일 관찰 코호트에서 고관절 골절 환자를 추출하고, 각 대상자의 지표일은 고관절 골절 최초 진단일로 정의한다. |
| seed_598_test_concept | 5.기간설정 | EASY | EXPLORATORY_SEARCH | 합병증을 동반하지 않은 당뇨병 대상 코호트 중 OMOP CDM에 관찰기간이 기록된 환자. |
| seed_580_test_paraphrase | 5.기간설정 | HARD | STATISTICAL_AGGREGATION | 락툴로오스 최초 처방일을 기준시점으로, 각 환자의 사망일과 자료 관찰 종료일 중 빠른 시점까지의 추적 종료일과 종료 사유를 산출하라. |
| seed_177_test_paraphrase | 4.결과 | MEDIUM | STATISTICAL_AGGREGATION | 환자별로 혈액투석이 최초로 발생한 날짜를 조회해 주세요. |
| seed_735_test_concept | 1.연구대상자 | EASY | COHORT_EXTRACTION | 심부전 환자 대상 |
| seed_611_test_paraphrase | 5.기간설정 | MEDIUM | STATISTICAL_AGGREGATION | 메트포르민 최초 처방일을 기준으로, 각 환자의 사망일과 자료 관찰 종료일 중 더 빠른 날짜를 추적 종료일로 산출하시오. |
| seed_19_test_concept | 4.결과 | HARD | STATISTICAL_AGGREGATION | 신장 최초 측정일의 평균값과 84일 후 평균값의 차이를 조회. |
| seed_229_test_slot | 1.연구대상자 | MEDIUM | COHORT_EXTRACTION | 체질량지수 값이 25 초과 또는 심근경색 진단인 환자. |
| seed_361_test_concept | 3.비교군 | MEDIUM | COHORT_EXTRACTION | 메게스트롤 처방 이력이 있고 사이클로포스파미드 처방 이력이 없는 환자를 비교군으로 정의. |
| seed_326_test_paraphrase | 2.노출군 | EASY | COHORT_EXTRACTION | 유방암 진단력이 있는 환자들을 노출군 코호트로 추출한다. |
| seed_107_test_concept | 2.노출군 | MEDIUM | COHORT_EXTRACTION | 고혈압성 신부전 진단 또는 에날라프릴 처방 이력이 있는 환자를 노출군으로 정의. |
| seed_757_test_paraphrase | 4.결과 | EASY | STATISTICAL_AGGREGATION | 각 환자의 심근경색, 뇌졸중, 저혈당 최초 발생일을 진단별로 집계해줘. |
| seed_97_test_restructure | 3.비교군 | EASY | COHORT_EXTRACTION | OMOP CDM drug_exposure 테이블에 약물 노출 기록이 있는 환자를 비교군으로 정의. |
| seed_492_test_restructure | 5.기간설정 | EASY | EXPLORATORY_SEARCH | 본태성 고혈압 대상 코호트 중 OMOP CDM에 관찰기간이 기록된 환자. |
| seed_35_test_restructure | 5.기간설정 | HARD | STATISTICAL_AGGREGATION | 암로디핀 최초 처방일부터 사망일, 자료 관찰 종료일, 3년 도달일 중 가장 이른 날짜를 추적 종료일로 정의 |
| seed_747_test_paraphrase | 4.결과 | MEDIUM | VALUE_RETRIEVAL | 각 환자의 생존 여부(사망 또는 생존)와 사망일을 조회해 주세요. |
| seed_71_test_slot | 1.연구대상자 | EASY | COHORT_EXTRACTION | 18세 미만 또는 여성인 환자. |
| seed_661_test_concept | 5.기간설정 | MEDIUM | STATISTICAL_AGGREGATION | 심부전 최초 진단일부터 사망일과 자료 관찰 종료일 중 가장 이른 날짜를 추적 종료일로 정의. |
| seed_638_test_slot | 4.결과 | HARD | STATISTICAL_AGGREGATION | metformin 유발 젖산산증(MALA: pH≤7.30 & 동맥 lactate 상승) |
| seed_116_test_slot | 1.연구대상자 | MEDIUM | COHORT_EXTRACTION | 현재 연도 기준 연령 65세 이상이고 75세 이하이고 체질량지수 값이 30 초과이고 심부전 진단인 환자. |
| seed_244_test_paraphrase | 3.비교군 | MEDIUM | COHORT_EXTRACTION | 빌다글립틴 투약 기록이 없는 환자를 비교군으로 추출한다. |
| seed_184_test_restructure | 2.노출군 | EASY | COHORT_EXTRACTION | OMOP CDM procedure_occurrence 테이블에 시술 기록이 있는 환자를 노출군으로 설정. |
| seed_477_test_restructure | 2.노출군 | MEDIUM | COHORT_EXTRACTION | 졸레드론산 최초 처방일을 기준 시점으로 하고 기준일 이전 졸레드론산 처방 이력이 없는 환자이며 골다공증 진단 이력이 있는 환자. |
| seed_618_test_concept | 4.결과 | EASY | STATISTICAL_AGGREGATION | 심근경색·뇌졸중·전심근경색증 신규 발생(예측 대상 사건) |
| seed_690_test_restructure | 3.비교군 | EASY | COHORT_EXTRACTION | OMOP CDM procedure 도메인 기록이 있는 환자를 비교군으로 설정. |
| seed_514_test_concept | 5.기간설정 | EASY | VALUE_RETRIEVAL | 암로디핀 최초 처방일을(를) 기준 시점(index date)으로 정의 (대상: 심근경색전증후군) |
| seed_547_test_restructure | 5.기간설정 | HARD | STATISTICAL_AGGREGATION | 기준시점(trimetazidine  최초 처방일)부터 사망·자료 관찰 종료 중 최초까지 추적 |

val 68개 목록은 `candidates.json` 앞부분이나 `test_set/proposed_input_val.jsonl`에 있습니다.

## `/rag` 실패 처리

- 개념을 못 찾아 실패하면(`concept_unmapped`), 테스트셋 `input`의 "개념 값 조건"에 있는 concept_id를 확정 개념(`concepts`)으로 넣어 **1번만 다시** 부릅니다. 지난번 seed_240·seed_263과 같은 방식입니다.
  - 이렇게 받은 프롬프트는 개념 후보가 아니라 확정 개념이 들어가므로, 모델이 개념을 고를 일이 없습니다. 이런 질의는 `concepts_given=True`로 표시해 결과 해석 때 구분합니다.
- 다시 불러도 실패하면 버리고 예비 후보로 채웁니다.
- 100개 중 88개는 `input`에 개념 조건이 있어 다시 부를 수 있습니다. 나머지 12개는 개념이 필요 없는 질의입니다(예: "OMOP CDM measurement 도메인 기록이 있는 환자").
- 실제로 다시 부른 질의는 5개(val_421, val_466, val_471, seed_408, seed_361)였고 모두 성공했습니다.

## 실행 방법 (1·2차와 같은 한 줄, 폴더만 다름)

```bash
cd /Users/seo/Developer/automl/sql-eval-harness/repeat_query_test/tts_val100
export TTS_API_KEY='<TTS API 키>'
export TTS_URL=http://10.1.1.106:8080
nohup caffeinate -i sh -c './run_all.sh && ./run_par_all.sh' > run_both.log 2>&1 &
tail -f run_both.log
```

- **실제 걸린 시간: 약 1시간 34분** (`/rag` 9분, 순차 50분, 병렬 35분). 아래는 실행 전 예상치입니다.

| 단계 | 내용 | 시간 |
|---|---|---|
| `/rag` | 약 100~130번 (다시 부르는 경우 포함) | 약 15분 |
| 순차 | 500건, 요청당 평균 약 8초 | 약 70분 |
| 병렬 | mixed 125묶음 + same 100묶음 | 약 50분 |

- 중간에 끊기면 같은 명령으로 다시 실행하면 이어서 합니다.
- `select_queries.py`는 이미 실행해 두었습니다(`candidates.json`). 다시 실행해도 같은 결과가 나옵니다.

## 결과 파일

1·2차와 같습니다(`../tts_seq50/README.md`의 "결과 파일" 참고). 이번에는 다음이 추가됩니다.
- `requests.json`: 질의마다 `set`(val/eval_ready), 섹션, 난이도, 질의유형, `concepts_given`이 들어 있습니다.
- `rag/<qid>.json`: `/rag`를 다시 불렀으면 두 번의 요청과 응답이 `tries`에 모두 있습니다.
- 정답 SQL이 있으므로, 갈린 질의는 `report.md`에 답별 정답 일치(EX) 여부가 나옵니다.
