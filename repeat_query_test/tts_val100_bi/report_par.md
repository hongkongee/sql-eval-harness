# 병렬 결과 (자동 생성: analyze_par.py)

- 질의 100개, 병렬 응답 900건 (오류 0건), 외부 요청이 섞인 응답 368건
- 순차 결과: 있음 (responses.jsonl, A = 순차 1회차 답)

## mixed (서로 다른 질의를 섞어 동시에)

- 순차 답에 없던 새 답: **0/500건** (외부 요청 없이 우리 요청만 돈 묶음 기준 0건)
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **0/100개**

## same (같은 질의를 동시에)

- 순차 답에 없던 새 답: **0/400건** (외부 요청 없이 우리 요청만 돈 묶음 기준 0건)
- 순차에선 5번 다 같았는데 병렬에서 다른 답이 나온 질의: **0/100개**


## 전체

| 질의 | 순차 | mixed | same |
|---|---|---|---|
| val_439 외래 방문 방문이고 입원 방문인 환자. | AAAAA | AAAAA | AAAA |
| val_441 사쿠비트릴·발사르탄 처방 이력이 있는 환자를 노출군으로 정의. | AAAAA | AAAAA | AAAA |
| val_440 심부전 진단 또는 입원 방문인 환자. | AAAAA | AAAAA | AAAA |
| val_443 발사르탄 투여군. | AAAAA | AAAAA | AAAA |
| val_445 심부전 또는 입원의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| val_446 심부전 또는 입원의 최초 발생일을 확인. | AAAAA | AAAAA | AAAA |
| val_447 관찰기간이 2021-01-14부터 2022-12-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| val_448 사쿠비트릴·발사르탄 최초 처방일을 기준 시점으로 정의. | AAAAA | AAAAA | AAAA |
| val_444 발사르탄 최초 처방일을 기준일로 하고 기준일 이전 동일 처방 이력이 없는 환자이며 | AAAAA | AAAAA | AAAA |
| val_442 ARNI(사쿠비트릴/발사르탄) 최초 처방일을 기준일로 하고 기준일 이전 ARNI( | AAAAA | AAAAA | AAAA |
| val_449 기준시점(ARNI(사쿠비트릴/발사르탄) 최초 처방일)부터 사망·자료 관찰 종료 중 | AAAAA | AAAAA | AAAA |
| val_291 심부전 진단 또는 뇌졸중 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_290 현재 연도 기준 연령 65세 이상이고 여성 기록이고 골다공증 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_450 사망·자료 관찰 종료·추적기간(2015년) 도달 중 가장 먼저 오는 시점 (기준: | AAAAA | AAAAA | AAAA |
| val_292 로모소주맙 처방 이력이 있는 환자를 노출군으로 정의. | AAAAA | AAAAA | AAAA |
| val_294 졸레드론산 처방 이력이 있는 환자를 비교군으로 정의. | AAAAA | AAAAA | AAAA |
| val_295 위약/비노출 대조군: 연구 약물(로모소주맙) 미노출 — 대상: 골다공증 | AAAAA | AAAAA | AAAA |
| val_297 관찰기간이 2021-09-15부터 2027-03-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| val_298 로모소주맙 최초 처방일을 기준 시점으로 정의. | AAAAA | AAAAA | AAAA |
| val_260 혈당 측정 기록이고 제2형 당뇨병 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_299 기준시점(로모소주맙 최초 처방일)부터 사망·자료 관찰 종료 중 최초까지 추적 (추 | AAAAA | AAAAA | AAAA |
| val_300 사망·자료 관찰 종료·추적기간(24개월) 도달 중 가장 먼저 오는 시점 (기준:  | AAAAA | AAAAA | AAAA |
| val_261 인슐린 처방인 환자. | AAAAA | AAAAA | AAAA |
| val_264 위약/비노출 대조군: 연구 약물(인슐린) 미노출 — 대상: 제2형 당뇨병 | AAAAA | AAAAA | AAAA |
| val_262 인슐린 처방 이력이 있는 환자를 노출군으로 정의. | AAAAA | AAAAA | AAAA |
| val_265 혈당 또는 당화혈색소 측정일과 측정값을 조회. | AAAAA | AAAAA | AAAA |
| val_267 인슐린 최초 처방일을 기준 시점으로 정의. | AAAAA | AAAAA | AAAA |
| val_266 관찰기간이 2018-11-19부터 2021-03-25까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| val_268 기준시점(인슐린 최초 처방일)부터 사망·자료 관찰 종료 중 최초까지 추적 (추적기 | AAAAA | AAAAA | AAAA |
| val_269 사망·자료 관찰 종료·추적기간(6개월) 도달 중 가장 먼저 오는 시점 (기준: 인 | AAAAA | AAAAA | AAAA |
| val_415 현재 연도 기준 연령 60세 이상이고 유방암 진단이고 여성 기록인 환자. | AAAAA | AAAAA | AAAA |
| val_263 인슐린 최초 처방일을 기준일로 하고 기준일 이전 인슐린 처방 이력이 없는 환자이며 | AAAAA | AAAAA | AAAA |
| val_417 유방절제술 시행 이력이 있는 환자를 노출군으로 정의. | AAAAA | AAAAA | AAAA |
| val_416 유방암 진단 또는 심부전 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_419 타목시펜 처방 이력이 있는 환자를 비교군으로 설정. | AAAAA | AAAAA | AAAA |
| val_421 유방암 대상 코호트에서 OMOP CDM measurement 테이블의 측정값과 측 | AAAAA | AAAAA | AAAA |
| val_423 관찰기간이 1993-05-01부터 2010-08-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| val_422 유방암 대상 코호트에서 OMOP CDM measurement 테이블의 측정 일자와 | AAAAA | AAAAA | AAAA |
| val_418 유방절제술 최초 시행일을 기준일로 하고 기준일 이전 동일 시행 이력이 없는 신규  | AAAAA | AAAAA | AAAA |
| val_424 유방절제술 최초 시행일을 기준 시점으로 설정. | AAAAA | AAAAA | AAAA |
| val_425 기준시점(유방절제술 시술일)부터 사망·자료 관찰 종료 중 최초까지 추적 (추적기간 | AAAAA | AAAAA | AAAA |
| val_528 총콜레스테롤 측정 기록이고 LDL 콜레스테롤 측정 기록인 환자. | AAAAA | AAAAA | AAAA |
| val_420 유방절제술 최초 시행일을 기준일(index date)로 하고 기준일 이전 동일 시 | AAAAA | AAAAA | AAAA |
| val_426 사망·자료 관찰 종료·추적기간(17년) 도달 중 가장 먼저 오는 시점 (기준: 유 | AAAAA | AAAAA | AAAA |
| val_530 OMOP CDM measurement 도메인 기록이 있는 환자를 노출군으로 규정. | AAAAA | AAAAA | AAAA |
| val_532 OMOP CDM measurement 도메인 기록이 있는 환자를 비교군으로 규정. | AAAAA | AAAAA | AAAA |
| val_531 환자별 최초 약물 처방일을 기준일로 설정. | AAAAA | AAAAA | AAAA |
| val_529 백내장 진단 또는 치매 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_535 백내장 최초 진단일을 기준 시점으로 정의. | AAAAA | AAAAA | AAAA |
| val_533 백내장 진단 이력이 있는 환자를 비교군으로 정의. | AAAAA | AAAAA | AAAA |
| val_718 방사선치료 시행 이력이 있는 환자를 비교군으로 정의. | AAAAA | AAAAA | AAAA |
| val_720 전이성 악성 신생물의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| val_721 유방암 또는 전립선암의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| val_462 현재 연도 기준 연령 70세 이상이고 고관절 골관절염 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_723 기준시점(방사선치료 시술일)부터 사망·자료 관찰 종료 중 최초까지 추적 | AAAAA | AAAAA | AAAA |
| val_464 골다공증 진단 이력이 있는 환자를 노출군으로 설정. | AAAAA | AAAAA | AAAA |
| val_463 골다공증 진단 또는 고관절 골절 진단인 환자. | AAAAA | AAAAA | AAAA |
| val_717 방사선치료 최초 시행일을 기준일로 하고 기준일 이전 동일 시행 이력이 없는 환자이 | AAAAA | AAAAA | AAAA |
| val_719 유방절제술 최초 시행일을 기준 시점으로 하고 기준일 이전 동일 시행 이력이 없는  | AAAAA | AAAAA | AAAA |
| val_466 인공고관절전치환술(THA) 시술군. | AAAAA | AAAAA | AAAA |
| val_468 고관절 골관절염 대상 코호트에서 OMOP CDM measurement 테이블의 측 | AAAAA | AAAAA | AAAA |
| val_469 외래 방문의 최초 발생일을 조회. | AAAAA | AAAAA | AAAA |
| val_470 관찰기간이 2014-10-01부터 2018-03-31까지의 기간과 겹치는 환자. | AAAAA | AAAAA | AAAA |
| val_471 인공고관절전치환술(THA) 최초 시행일을 기준 시점으로 설정. | AAAAA | AAAAA | AAAA |
| val_465 고관절 전치환술 최초 시행일을 기준 시점으로 하고 기준일 이전 동일 시행 이력이  | AAAAA | AAAAA | AAAA |
| val_472 기준시점(인공고관절전치환술(THA) 시술일)부터 사망·자료 관찰 종료 중 최초까지 | AAAAA | AAAAA | AAAA |
| val_467 고관절 전치환술 최초 시행일을 기준일로 하고 기준일 이전 동일 시행 이력이 없는  | AAAAA | AAAAA | AAAA |
| val_473 사망·자료 관찰 종료·추적기간(5년) 도달 중 가장 먼저 오는 시점 (기준: 인공 | AAAAA | AAAAA | AAAA |
| seed_696_test_concept 심부전 진단이고 고관절 골관절염 진단인 환자. | AAAAA | AAAAA | AAAA |
| seed_408_test_paraphrase 위약/비노출 대조군 코호트 추출: 유방암 환자 중 연구 약물인 유방암 항암화학요법 | AAAAA | AAAAA | AAAA |
| seed_164_test_paraphrase 관찰 코호트 노출군으로 만성콩팥병 환자를 추출하고, 최초 진단일을 기준일로 계산한 | AAAAA | AAAAA | AAAA |
| seed_552_test_concept 메트포르민 최초 처방일을 기준일로 하고 기준일 이전 메트포르민 처방 이력이 없는  | AAAAA | AAAAA | AAAA |
| seed_134_test_concept 혈청/혈장 요산 측정 기록의 측정일과 측정값을 조회. | AAAAA | AAAAA | AAAA |
| seed_649_test_paraphrase 별도 대조군을 두지 않은 단일 관찰 코호트에서 고관절 골절 환자를 추출하고, 각  | AAAAA | AAAAA | AAAA |
| seed_598_test_concept 합병증을 동반하지 않은 당뇨병 대상 코호트 중 OMOP CDM에 관찰기간이 기록된 | AAAAA | AAAAA | AAAA |
| seed_580_test_paraphrase 락툴로오스 최초 처방일을 기준시점으로, 각 환자의 사망일과 자료 관찰 종료일 중  | AAAAA | AAAAA | AAAA |
| seed_177_test_paraphrase 환자별로 혈액투석이 최초로 발생한 날짜를 조회해 주세요. | AAAAA | AAAAA | AAAA |
| seed_735_test_concept 심부전 환자 대상 | AAAAA | AAAAA | AAAA |
| seed_611_test_paraphrase 메트포르민 최초 처방일을 기준으로, 각 환자의 사망일과 자료 관찰 종료일 중 더  | AAAAA | AAAAA | AAAA |
| seed_19_test_concept 신장 최초 측정일의 평균값과 84일 후 평균값의 차이를 조회. | AAAAA | AAAAA | AAAA |
| seed_229_test_slot 체질량지수 값이 25 초과 또는 심근경색 진단인 환자. | AAAAA | AAAAA | AAAA |
| seed_361_test_concept 메게스트롤 처방 이력이 있고 사이클로포스파미드 처방 이력이 없는 환자를 비교군으로 | AAAAA | AAAAA | AAAA |
| seed_326_test_paraphrase 유방암 진단력이 있는 환자들을 노출군 코호트로 추출한다. | AAAAA | AAAAA | AAAA |
| seed_107_test_concept 고혈압성 신부전 진단 또는 에날라프릴 처방 이력이 있는 환자를 노출군으로 정의. | AAAAA | AAAAA | AAAA |
| seed_757_test_paraphrase 각 환자의 심근경색, 뇌졸중, 저혈당 최초 발생일을 진단별로 집계해줘. | AAAAA | AAAAA | AAAA |
| seed_97_test_restructure OMOP CDM drug_exposure 테이블에 약물 노출 기록이 있는 환자를  | AAAAA | AAAAA | AAAA |
| seed_492_test_restructure 본태성 고혈압 대상 코호트 중 OMOP CDM에 관찰기간이 기록된 환자. | AAAAA | AAAAA | AAAA |
| seed_35_test_restructure 암로디핀 최초 처방일부터 사망일, 자료 관찰 종료일, 3년 도달일 중 가장 이른  | AAAAA | AAAAA | AAAA |
| seed_747_test_paraphrase 각 환자의 생존 여부(사망 또는 생존)와 사망일을 조회해 주세요. | AAAAA | AAAAA | AAAA |
| seed_71_test_slot 18세 미만 또는 여성인 환자. | AAAAA | AAAAA | AAAA |
| seed_661_test_concept 심부전 최초 진단일부터 사망일과 자료 관찰 종료일 중 가장 이른 날짜를 추적 종료 | AAAAA | AAAAA | AAAA |
| seed_638_test_slot metformin 유발 젖산산증(MALA: pH≤7.30 & 동맥 lactate  | AAAAA | AAAAA | AAAA |
| seed_116_test_slot 현재 연도 기준 연령 65세 이상이고 75세 이하이고 체질량지수 값이 30 초과이 | AAAAA | AAAAA | AAAA |
| seed_244_test_paraphrase 빌다글립틴 투약 기록이 없는 환자를 비교군으로 추출한다. | AAAAA | AAAAA | AAAA |
| seed_184_test_restructure OMOP CDM procedure_occurrence 테이블에 시술 기록이 있는  | AAAAA | AAAAA | AAAA |
| seed_477_test_restructure 졸레드론산 최초 처방일을 기준 시점으로 하고 기준일 이전 졸레드론산 처방 이력이  | AAAAA | AAAAA | AAAA |
| seed_618_test_concept 심근경색·뇌졸중·전심근경색증 신규 발생(예측 대상 사건) | AAAAA | AAAAA | AAAA |
| seed_690_test_restructure OMOP CDM procedure 도메인 기록이 있는 환자를 비교군으로 설정. | AAAAA | AAAAA | AAAA |
| seed_514_test_concept 암로디핀 최초 처방일을(를) 기준 시점(index date)으로 정의 (대상: 심 | AAAAA | AAAAA | AAAA |
| seed_547_test_restructure 기준시점(trimetazidine  최초 처방일)부터 사망·자료 관찰 종료 중 최 | AAAAA | AAAAA | AAAA |
