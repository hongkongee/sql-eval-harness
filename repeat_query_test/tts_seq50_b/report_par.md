# 병렬 결과 (자동 생성: analyze_par.py)

- 질의 50개, 병렬 응답 450건 (오류 0건), 외부 요청이 섞인 응답 104건
- 순차 결과: 있음 (responses.jsonl, A = 순차 1회차 답)

## mixed (서로 다른 질의를 섞어 동시에)

- 순차 답에 없던 새 답: **1/250건** (외부 요청 없이 우리 요청만 돈 묶음 기준 1건)
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **1/49개**

## same (같은 질의를 동시에)

- 순차 답에 없던 새 답: **0/200건** (외부 요청 없이 우리 요청만 돈 묶음 기준 0건)
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **0/49개**

## 답이 하나라도 갈린 질의

| 질의 | 순차 | mixed (o/x) | same (o/x) | 첫 차이 (A → 다른 답) | 실행 결과 |
|---|---|---|---|---|---|
| q120 요추 T-score 측정 기록의 측정일과 측정값을 조회. | AABBB | BBBBB (oooox) | BABA (oooo) | B: `…( 3049654 ) ) ;…  →  …( 3049654 ) )…` | A: {'rows': 0, 'hash': 'd7517139'}<br>B: {'rows': 0, 'hash': 'd7517139'} |
| q118 LDL 콜레스테롤 측정 기록의 측정일과 측정값을 조회. | AAAAA | ABAAA (ooxxo) | AAAA (oooo) | B(병렬만): `…value_as_number , m . unit_concept_id FROM measurement m WHERE…  →  …value_as_number , m . unit_source_value FROM measurement m WHERE…` | A: {'rows': 230206, 'hash': '64bf535a'}<br>B: {'rows': 230206, 'hash': '64bf535a'} |

## 전체

| 질의 | 순차 | mixed | same |
|---|---|---|---|
| q089 현재 연도 기준 연령 75세 이상이고 천식 진단인 환자. | AAAAA | AAAAA | AAAA |
| q095 골다공증 진단이고 메트포르민 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q016 알츠하이머병 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q015 백내장 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q110 PSA 값이 4.0 이상인 환자. | AAAAA | AAAAA | AAAA |
| q059 2020년 이후 알츠하이머병 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q084 입원 기록이 있고 이상지질혈증 진단인 환자. | AAAAA | AAAAA | AAAA |
| q005 데노수맙 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q082 외래 방문 기록이 있고 알츠하이머병 진단인 환자. | AAAAA | AAAAA | AAAA |
| q083 응급실 방문 기록이 있고 협심증 진단인 환자. | AAAAA | AAAAA | AAAA |
| q042 최근 3년 이내 천식 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q032 2011-01-01부터 2015-12-31까지 엠파글리플로진 처방 이력이 있는 환 | AAAAA | AAAAA | AAAA |
| q087 주상병이 만성신장질환인 환자. | AAAAA | AAAAA | AAAA |
| q064 2019년에 유방절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q001 메트포르민 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q111 C-반응성 단백질 값이 10 초과인 환자. | AAAAA | AAAAA | AAAA |
| q012 심부전 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q002 아토르바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q093 현재 연도 기준 연령 60세 이상이고 80세 미만이고 협심증 진단인 환자. | AAAAA | AAAAA | AAAA |
| q008 시타글립틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q067 천식의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| q057 2022년 이후 치매 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q120 요추 T-score 측정 기록의 측정일과 측정값을 조회. | AABBB | BBBBB | BABA |
| q071 아토르바스타틴 최초 처방일을 조회. | AAAAA | AAAAA | AAAA |
| q027 2016-01-01부터 2020-12-31까지 아토르바스타틴 처방 이력이 있는 환 | AAAAA | AAAAA | AAAA |
| q079 여성이고 치매 진단인 환자. | AAAAA | AAAAA | AAAA |
| q041 최근 2년 이내 심부전 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q056 2019년 이후 천식 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q106 수축기혈압 값이 140 이상인 환자. | AAAAA | AAAAA | AAAA |
| q090 현재 연도 기준 연령 80세 이상이고 치매 진단인 환자. | AAAAA | AAAAA | AAAA |
| q072 심바스타틴 최초 처방일을 조회. | AAAAA | AAAAA | AAAA |
| q061 2020년에 슬관절 치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q043 최근 5년 이내 치매 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q088 현재 연도 기준 연령 70세 이상이고 심부전 진단인 환자. | AAAAA | AAAAA | AAAA |
| q010 타목시펜 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q118 LDL 콜레스테롤 측정 기록의 측정일과 측정값을 조회. | AAAAA | ABAAA | AAAA |
| q040 최근 1년 이내 골다공증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q019 인공고관절전치환술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q078 남성이고 천식 진단인 환자. | AAAAA | AAAAA | AAAA |
| q091 현재 연도 기준 연령 40세 이상이고 60세 미만이고 백내장 진단인 환자. | AAAAA | AAAAA | AAAA |
| q069 알츠하이머병의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| q033 2018-01-01부터 2022-12-31까지 시타글립틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q080 남성이고 백내장 진단인 환자. | AAAAA | AAAAA | AAAA |
| q013 천식 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q097 천식 진단이고 심바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q102 총콜레스테롤 값이 240 이상인 환자. | AAAAA | AAAAA | AAAA |
| q037 관찰기간이 2013-07-01부터 2017-05-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| q018 이상지질혈증 진단 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
| q065 2016년에 전립선절제술을 받은 환자. | AAAAA | AAAAA | AAAA |
| q028 2013-01-01부터 2019-12-31까지 심바스타틴 처방 이력이 있는 환자. | AAAAA | AAAAA | AAAA |
