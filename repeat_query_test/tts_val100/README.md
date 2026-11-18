# 다양한 유형 질의 100개로 순차·병렬 반복 (준비만 됨, 아직 실행 안 함)

1·2차(`../tts_seq50`, `../tts_seq50_b`)는 TTS `tests/test_queries_100.txt`에서 뽑은 짧은 단일 조건 질의였습니다. 이번에는 연구설계 섹션 5개와 EASY~HARD를 고르게 섞은 질의 100개로 같은 시험을 합니다. 방법, 요청 형태, 설정(`by-loss`, temperature 0.0)은 1·2차와 같습니다.

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
- val 문항 52개에 `input_repairs`(RAG가 못 찾은 개념을 보충한 기록)가 있어서, 다시 부르는 경우가 꽤 나올 것으로 예상합니다.

## 실행 (1·2차와 같은 한 줄, 폴더만 다름)

```bash
cd /Users/seo/Developer/automl/sql-eval-harness/repeat_query_test/tts_val100
export TTS_API_KEY='<TTS API 키>'
export TTS_URL=http://10.1.1.106:8080
nohup caffeinate -i sh -c './run_all.sh && ./run_par_all.sh' > run_both.log 2>&1 &
tail -f run_both.log
```

- **예상 시간: 약 2시간~2시간 30분.** 질의가 100개로 늘고 SQL도 길어서, 1·2차(각 30분)보다 오래 걸립니다.

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
