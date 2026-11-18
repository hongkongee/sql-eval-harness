# 순차 반복 결과 (자동 생성: analyze.py)

- 질의 50개, 응답 250건 (오류 0건), 서버에서 혼자 처리된 요청 250건
- **답이 갈린 질의: 1/50개**
- 혼자 처리된 요청만 봐도 갈린 질의: 1개

## 갈린 질의

| 질의 | 회차별 답 | 혼자 처리(o/x) | 답별 횟수 | 실행 결과 같음 | 첫 차이 (A → 다른 답) |
|---|---|---|---|---|---|
| q081 여성이고 알츠하이머병 진단인 환자. | AAABB | ooooo | A×3, B×2 | True | B: `…WHERE p . gender_concept_id IN ( SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN ( 8532 ) ) AND…  →  …WHERE p . gender_concept_id = 8532 AND EXISTS (…` |

### 답별 실행 결과

- **q081** 여성이고 알츠하이머병 진단인 환자.
  - A ×3: {'rows': 1911, 'hash': 'da3ce2f6'}
  - B ×2: {'rows': 1911, 'hash': 'da3ce2f6'}

## 전체

| 질의 | 회차별 답 | 혼자 처리(o/x) |
|---|---|---|
| q058 2018년 이후 백내장 진단 이력이 있는 환자. | AAAAA | ooooo |
| q104 혈당 값이 200 이상인 환자. | AAAAA | ooooo |
| q100 알츠하이머병 진단 이력이 있고 슬관절 치환술을 받은 환자. | AAAAA | ooooo |
| q004 로수바스타틴 처방 이력이 있는 환자. | AAAAA | ooooo |
| q112 혈청 또는 혈장 총 칼슘 값이 10.5 이상인 환자. | AAAAA | ooooo |
| q060 2018년에 인공고관절전치환술을 받은 환자. | AAAAA | ooooo |
| q074 데노수맙 최종 처방일을 조회. | AAAAA | ooooo |
| q023 유방절제술을 받은 환자. | AAAAA | ooooo |
| q031 2015-01-01부터 2020-12-31까지 세마글루타이드 처방 이력이 있는 환자. | AAAAA | ooooo |
| q026 2014-01-01부터 2018-12-31까지 메트포르민 처방 이력이 있는 환자. | AAAAA | ooooo |
| q048 지난 6개월 이내 인공고관절전치환술을 받은 환자. | AAAAA | ooooo |
| q070 메트포르민 최초 처방일을 조회. | AAAAA | ooooo |
| q024 전립선절제술을 받은 환자. | AAAAA | ooooo |
| q068 백내장의 최초 발생일을 조회. | AAAAA | ooooo |
| q076 남성이고 골다공증 진단인 환자. | AAAAA | ooooo |
| q017 협심증 진단 이력이 있는 환자. | AAAAA | ooooo |
| q086 주상병이 본태성 고혈압인 환자. | AAAAA | ooooo |
| q030 2012-01-01부터 2016-12-31까지 데노수맙 처방 이력이 있는 환자. | AAAAA | ooooo |
| q003 심바스타틴 처방 이력이 있는 환자. | AAAAA | ooooo |
| q077 여성이고 심부전 진단인 환자. | AAAAA | ooooo |
| q009 도네페질 처방 이력이 있는 환자. | AAAAA | ooooo |
| q108 LDL 콜레스테롤 값이 160 이상인 환자. | AAAAA | ooooo |
| q044 최근 1년 이내 백내장 진단 이력이 있는 환자. | AAAAA | ooooo |
| q085 외래 방문 기록이 있고 뇌졸중 진단인 환자. | AAAAA | ooooo |
| q099 백내장 진단 이력이 있고 인공고관절전치환술을 받은 환자. | AAAAA | ooooo |
| q045 최근 2년 이내 알츠하이머병 진단 이력이 있는 환자. | AAAAA | ooooo |
| q047 최근 5년 이내 이상지질혈증 진단 이력이 있는 환자. | AAAAA | ooooo |
| q081 여성이고 알츠하이머병 진단인 환자. | AAABB | ooooo |
| q038 관찰기간이 2016-11-01부터 2020-04-30까지의 기간과 겹치는 환자. | AAAAA | ooooo |
| q011 골다공증 진단 이력이 있는 환자. | AAAAA | ooooo |
| q025 고관절 부분치환술을 받은 환자. | AAAAA | ooooo |
| q049 지난 12개월 이내 슬관절 치환술을 받은 환자. | AAAAA | ooooo |
| q051 지난 24개월 이내 항암화학요법을 받은 환자. | AAAAA | ooooo |
| q105 eGFR 값이 60 미만인 환자. | AAAAA | ooooo |
| q094 현재 연도 기준 연령 55세 이상이고 75세 미만이고 이상지질혈증 진단인 환자. | AAAAA | ooooo |
| q014 치매 진단 이력이 있는 환자. | AAAAA | ooooo |
| q053 지난 18개월 이내 전립선절제술을 받은 환자. | AAAAA | ooooo |
| q022 항암화학요법을 받은 환자. | AAAAA | ooooo |
| q073 로수바스타틴 최종 처방일을 조회. | AAAAA | ooooo |
| q092 현재 연도 기준 연령 50세 이상이고 70세 미만이고 알츠하이머병 진단인 환자. | AAAAA | ooooo |
| q036 관찰기간이 2019-01-01부터 2022-12-31까지의 기간과 겹치는 환자. | AAAAA | ooooo |
| q020 슬관절 치환술을 받은 환자. | AAAAA | ooooo |
| q007 엠파글리플로진 처방 이력이 있는 환자. | AAAAA | ooooo |
| q103 크레아티닌 값이 1.5 초과인 환자. | AAAAA | ooooo |
| q096 심부전 진단이고 아토르바스타틴 처방 이력이 있는 환자. | AAAAA | ooooo |
| q021 혈액투석을 받은 환자. | AAAAA | ooooo |
| q119 PSA 측정 기록의 측정일과 측정값을 조회. | AAAAA | ooooo |
| q029 2017-01-01부터 2021-12-31까지 로수바스타틴 처방 이력이 있는 환자. | AAAAA | ooooo |
| q035 관찰기간이 2012-06-15부터 2016-02-28까지의 기간과 겹치는 환자. | AAAAA | ooooo |
| q055 2021년 이후 심부전 진단 이력이 있는 환자. | AAAAA | ooooo |
