# 같은 질의 반복 요청 시 SQL이 달라지는지 확인

- 날짜: 2026-11-12
- 서버: `http://10.1.1.69:8007` (vLLM, 베이스 `XGenerationLab/XiYanSQL-QwenCoder-14B-2504` + LoRA)
- 모델: `by-loss`, `final-step` (`proposed-random-augment-v2`의 체크포인트 두 개)
- 요청 형태: 평가 때와 같음. system = 학습 때 쓴 시스템 프롬프트(`results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt`), user = `[질의]` + `[재료]`(`adherence.build_prompt`로 조립), max_tokens 512

## 조건 (조건마다 10번씩, 모델 2개 × 문항 2개)

| 조건 | 설명 |
|---|---|
| `t0_seq` | temperature 0, 한 번에 하나씩 순서대로 요청 (평가 스크립트 설정) |
| `t0_par` | temperature 0, 10개를 동시에 요청 (서버가 한 번에 묶어 처리할 때) |
| `default` | temperature를 보내지 않음 → 서버 기본값으로 샘플링 |

## 문항

| 문항 | 질의 |
|---|---|
| `seed_104_test_slot` (HARD) | 사망·자료 관찰 종료·추적기간(30일) 도달 중 가장 먼저 오는 시점 (기준: 경피관상동맥중재술(PCI) 시술일) |
| `seed_240_test_paraphrase` (MEDIUM) | 현재 연도를 기준으로 연령이 80세 초과인 환자, 제2형 당뇨병 진단 이력이 있는 환자, 또는 크레아티닌 측정값이 50 미만인 환자를 추출하시오. |

## 결과: 10번 중 서로 다른 SQL 개수

| 문항 | 모델 | t0_seq | t0_par | default |
|---|---|---|---|---|
| seed_104 | by-loss | 1 | 1 | **4** (같은 답 7번 + 다른 답 3개) |
| seed_104 | final-step | 1 | 1 | **2** (같은 답 9번 + 다른 답 1개) |
| seed_240 | by-loss | 1 | 1 | 1 |
| seed_240 | final-step | 1 | 1 | 1 |

- **temperature 0에서는 120번 모두 같은 답**이 나왔습니다. 순서대로 보내든 동시에 보내든 같았습니다.
- 답이 달라진 경우는 **temperature를 보내지 않았을 때, 긴 쿼리(seed_104)에서만**이었습니다.
- temperature 0 답은 두 문항 모두 정답 SQL과 글자까지 같았습니다(학습 데이터와 겹치는 문항일 수 있음).

### seed_104에서 달라진 답의 모양

뜻은 같고 쓰는 방식만 다릅니다. 샌드박스 DB에서 실행해 보면 **5가지 답 모두 정답과 결과가 같습니다**(EX pass, `outputs/*/ex.json`).

| 답 | 정답과 다른 점 |
|---|---|
| 1 (대부분) | 정답과 같음 |
| 2 | `index_dates` 안에 `SELECT DISTINCT ... 1 AS is_index` 서브쿼리를 한 겹 더 두르고 `WHERE d.is_index = 1`로 거름(불필요하지만 결과 같음), 별칭에 `AS` 붙임 |
| 3 | `select/min/group by`를 대문자로 씀 (나머지 같음) |
| 4 | CTE(`WITH`)를 쓰지 않고 같은 내용을 FROM 안 서브쿼리로 넣음 |
| 5 (final-step) | `po` 대신 `d`라는 별칭을 씀 (나머지 같음) |

## 해석

1. 이번 시험에서는 **temperature 0이면 반복해도 같은 SQL**이 나왔습니다. "계속 다르게 나온다"는 현상은 temperature를 안 보냈을 때 재현됐습니다.
2. 베이스 모델의 `generation_config.json`에 temperature가 지정돼 있지 않습니다(`null`). 그래서 요청에 temperature를 안 넣으면 vLLM 기본값 **temperature 1.0**으로 샘플링될 가능성이 큽니다(서버 실행 옵션은 직접 확인하지 못했음). 쿼리를 받는 쪽 코드에서 `"temperature": 0`을 넣고 있는지 먼저 확인해 보면 좋겠습니다.
3. 짧은 쿼리(seed_240)는 기본 샘플링에서도 30번 모두 같았고, 긴 쿼리(seed_104)에서만 달라졌습니다. 쿼리가 길수록 토큰을 많이 뽑으니 갈림길도 많아집니다.
4. 그 밖에 답이 달라질 수 있는 원인(이번 시험 범위 밖):
   - 시스템 프롬프트가 다르거나 빠진 경우 (EVAL_GUIDE: 빠지면 모델 기본 문구가 들어가 점수가 떨어짐)
   - `[재료]`가 요청마다 달라지는 경우 (예: 앞단 검색 결과가 바뀜)
   - 모델 이름을 `xiyansql-qwencoder-14b-proposed-random-augment-v2`로 보낸 경우: `/v1/models`에서 이 이름은 LoRA가 없는 **베이스 모델**이고, 파인튜닝된 모델은 `by-loss`, `final-step`입니다.
   - temperature 0이어도 서버가 많이 바쁠 때(요청을 묶어 처리하는 크기가 달라질 때) 드물게 소수점 오차로 답이 갈릴 수 있습니다. 이번 동시 요청 10개로는 재현되지 않았습니다.

## 추가 시험: 실제로 쓰던 curl 형태로 by-loss에 5번 (2026-11-12)

평소 요청하던 curl과 똑같이 보냈습니다. 모델은 `by-loss`이고, system 메시지와 user 메시지(`[질의]` + `[재료]`)만 넣었습니다. **temperature, top_p, max_tokens는 넣지 않았습니다.** 베이스 모델 `generation_config.json`에 temperature와 top_p가 둘 다 `null`이라 vLLM 기본값 1.0으로 샘플링되는 상태입니다.

- 문항: `seed_729_test_restructure` — "위약/비노출 대조군: 연구 약물(유방절제술) 미노출 — 대상: 유방암"
- 스크립트: `python3 run_curl_style.py ../test_set/eval_ready/restructure.jsonl seed_729_test_restructure 5 by-loss`
- 원본: `outputs/seed_729_test_restructure/curl_style_by-loss.jsonl`

| 회차 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 답 | A | A | A | **B** | A |
| 생성 토큰 수 | 97 | 97 | 97 | 134 | 97 |

**5번 중 1번(4회차)이 다른 쿼리로 나왔습니다.** 두 답 모두 샌드박스 DB에서 정답과 결과가 같습니다(EX pass).

답 A (4번):
```sql
SELECT DISTINCT co.person_id FROM condition_occurrence co
WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4112853))
  AND NOT EXISTS ( SELECT 1 FROM procedure_occurrence po WHERE po.person_id = co.person_id
                   AND po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4066543)) );
```

답 B (1번):
```sql
WITH breast_cancer_person AS (SELECT DISTINCT co.person_id FROM condition_occurrence co WHERE co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4112853))),
     mammoplasty_procedure_person AS (SELECT DISTINCT po.person_id FROM procedure_occurrence po WHERE po.procedure_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (4066543)))
SELECT b.person_id FROM breast_cancer_person b LEFT JOIN mammoplasty_procedure_person m ON m.person_id = b.person_id WHERE m.person_id IS NULL
```
(줄바꿈은 읽기 좋게 넣은 것이고 실제 응답은 한 줄입니다.)

차이:
- **구조:** A는 `NOT EXISTS` 한 문장으로 썼고, B는 CTE 두 개를 만든 뒤 `LEFT JOIN … IS NULL`로 "미노출"을 걸렀습니다.
- **CTE 이름:** B는 유방절제술(mastectomy) 대신 `mammoplasty`(유방성형술)라는 이름을 붙였습니다. concept_id(4066543)는 같아서 결과에는 영향이 없지만, 이름만 보면 다른 시술로 오해할 수 있습니다.
- **끝 세미콜론:** B는 `;` 없이 끝납니다.

**정리:** temperature를 안 넣고 보내면 짧은 쿼리에서도 5번에 1번꼴로 다른 SQL이 나옵니다. 앞의 temperature 0 시험(120번 모두 같음)과 함께 보면, 쿼리가 달라지는 원인은 기본 샘플링 temperature 1.0으로 보입니다. 요청에 `"temperature": 0`을 넣으면 같은 답이 나옵니다. 서버 쪽에서 막으려면 vLLM을 띄울 때 `--override-generation-config '{"temperature": 0}'`로 기본값을 바꾸는 방법도 있습니다(직접 적용해 보지는 않음).

## 파일

| 파일 | 내용 |
|---|---|
| `run_repeat.py` | 반복 요청 스크립트. `python3 run_repeat.py <테스트셋.jsonl> <문항 id> [반복 횟수] [모델...]` |
| `run_curl_style.py` | 평소 쓰던 curl과 같은 형태(temperature 등 미지정)로 반복 요청. `python3 run_curl_style.py <테스트셋.jsonl> <문항 id> [횟수=5] [모델=by-loss]` |
| `check_ex.py` | 서로 다른 답마다 샌드박스 DB에서 실행해 정답과 비교. `python3 check_ex.py <문항 id>` |
| `outputs/<문항 id>/request_user_message.txt` | 실제로 보낸 user 메시지(질의 + 재료) |
| `outputs/<문항 id>/gold.sql` | 정답 SQL |
| `outputs/<문항 id>/<모델>.jsonl` | 요청 하나당 한 줄 (`cond`, `run`, `sql`, `sec`, `finish`) |
| `outputs/<문항 id>/ex.json` | 서로 다른 답별 실행 결과 비교 |
