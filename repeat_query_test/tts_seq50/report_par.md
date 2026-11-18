# 병렬 결과 (자동 생성: analyze_par.py)

- 질의 50개, 병렬 응답 450건 (오류 0건), 외부 요청이 섞인 응답 108건
- 순차 결과: 있음 (responses.jsonl, A = 순차 1회차 답)

## mixed (서로 다른 질의를 섞어 동시에)

- 순차 답에 없던 새 답: **3/250건** (외부 요청 없이 우리 요청만 돈 묶음 기준 2건)
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **2/49개**

## same (같은 질의를 동시에)

- 순차 답에 없던 새 답: **1/200건** (외부 요청 없이 우리 요청만 돈 묶음 기준 1건)
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **1/49개**

## 답이 하나라도 갈린 질의

| 질의 | 순차 | mixed (o/x) | same (o/x) | 첫 차이 (A → 다른 답) | 실행 결과 |
|---|---|---|---|---|---|
| q026 2014-01-01부터 2018-12-31까지 메트포르민 처방  | AAAAA | ABBAA (xxoxo) | BAAA (oooo) | B(병렬만): `…'2014-01-01' AND de . drug_exposure_start_date < = DATE '2018-12-31'…  →  …'2014-01-01' AND de . drug_exposure_end_date < = DATE '2018-12-31'…` | A: {'rows': 15539, 'hash': '25f80cd7'}<br>B: {'rows': 15416, 'hash': '41025245'} |
| q081 여성이고 알츠하이머병 진단인 환자. | AAABB | AAAAA (xxxoo) | AAAA (oooo) | B: `…WHERE p . gender_concept_id IN ( SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN ( 8532 ) ) AND…  →  …WHERE p . gender_concept_id = 8532 AND EXISTS (…` | A: {'rows': 1911, 'hash': 'da3ce2f6'}<br>B: {'rows': 1911, 'hash': 'da3ce2f6'} |
| q094 현재 연도 기준 연령 55세 이상이고 75세 미만이고 이상지질혈 | AAAAA | BAAAA (oxxox) | AAAA (oooo) | B(병렬만): `…FROM p . birth_datetime ) ) < 75…  →  …FROM p . birth_datetime ' ) ) < 75…` | A: {'rows': 0, 'hash': 'd7517139'}<br>B: {'error': 'unterminated quoted string at or near "\')) < 75 AND EXISTS (SELECT 1 FROM condition_occurrence co WHERE co.person_id = p.person_id AND co.condition_concept_id IN (SELECT descendant_concept_id FROM con'} |

## 전체

| 질의 | 순차 | mixed | same |
|---|---|---|---|
| q058 2018년 이후 백내장 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q104 혈당 값이 200 이상인 환자. | AAAAA | AAAAA | AAAA |
| q100 알츠하이머병 진단 이력이 있고 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q004 로수바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q112 혈청 또는 혈장 총 칼슘 값이 10.5 이상인 환자. | AAAAA | AAAAA | AAAA |
| q060 2018년에 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q074 데노수맙 최종 처방일을 조회. | AAAAA | AAAAA | AAAA |
| q023 유방절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q031 2015-01-01부터 2020-12-31까지 세마글루타이드 처방 이력이 있는 환 | AAAAA | AAAAA | AAAA |
| q026 2014-01-01부터 2018-12-31까지 메트포르민 처방 이력이 있는 환자. | AAAAA | ABBAA | BAAA |
| q048 지난 6개월 이내 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q070 메트포르민 최초 처방일을 조회. | AAAAA | AAAAA | AAAA |
| q024 전립선절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q068 백내장의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| q076 남성이고 골다공증 진단인 환자. | AAAAA | AAAAA | AAAA |
| q017 협심증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q086 주상병이 본태성 고혈압인 환자. | AAAAA | AAAAA | AAAA |
| q030 2012-01-01부터 2016-12-31까지 데노수맙 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q003 심바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q077 여성이고 심부전 진단인 환자. | AAAAA | AAAAA | AAAA |
| q009 도네페질 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q108 LDL 콜레스테롤 값이 160 이상인 환자. | AAAAA | AAAAA | AAAA |
| q044 최근 1년 이내 백내장 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q085 외래 방문 기록이 있고 뇌졸중 진단인 환자. | AAAAA | AAAAA | AAAA |
| q099 백내장 진단 이력이 있고 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q045 최근 2년 이내 알츠하이머병 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q047 최근 5년 이내 이상지질혈증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q081 여성이고 알츠하이머병 진단인 환자. | AAABB | AAAAA | AAAA |
| q038 관찰기간이 2016-11-01부터 2020-04-30까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| q011 골다공증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q025 고관절 부분치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q049 지난 12개월 이내 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q051 지난 24개월 이내 항암화학요법을 받은 환자. | AAAAA | AAAAA | AAAA |
| q105 eGFR 값이 60 미만인 환자. | AAAAA | AAAAA | AAAA |
| q094 현재 연도 기준 연령 55세 이상이고 75세 미만이고 이상지질혈증 진단인 환자. | AAAAA | BAAAA | AAAA |
| q014 치매 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q053 지난 18개월 이내 전립선절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q022 항암화학요법을 받은 환자. | AAAAA | AAAAA | AAAA |
| q073 로수바스타틴 최종 처방일을 조회. | AAAAA | AAAAA | AAAA |
| q092 현재 연도 기준 연령 50세 이상이고 70세 미만이고 알츠하이머병 진단인 환자. | AAAAA | AAAAA | AAAA |
| q036 관찰기간이 2019-01-01부터 2022-12-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| q020 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q007 엠파글리플로진 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q103 크레아티닌 값이 1.5 초과인 환자. | AAAAA | AAAAA | AAAA |
| q096 심부전 진단이고 아토르바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q021 혈액투석을 받은 환자. | AAAAA | AAAAA | AAAA |
| q119 PSA 측정 기록의 측정일과 측정값을 조회. | AAAAA | AAAAA | AAAA |
| q029 2017-01-01부터 2021-12-31까지 로수바스타틴 처방 이력이 있는 환자 | AAAAA | AAAAA | AAAA |
| q035 관찰기간이 2012-06-15부터 2016-02-28까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| q055 2021년 이후 심부전 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
