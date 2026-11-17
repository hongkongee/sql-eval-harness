# TTS와 같은 프롬프트로 by-loss 반복 요청 (2026-11-12)

TTS(`mpx-cdm-tts`)가 NL2SQL 모델에 보내는 것과 같은 system + user 메시지를 만들어 `by-loss`에 조건별로 5번씩 보냈습니다.

## 프롬프트 만든 방법

- **system:** TTS의 `app/services/text2sql/prompts/system_prompt.txt`에서 `{dialect}`를 `PostgreSQL`로 바꾸고, 끝에 `placeholder_protocol.txt`를 붙였습니다. 개념 후보가 있을 때 TTS가 하는 방식 그대로입니다.
- **user:** TTS API(`http://10.1.1.69:8080/rag`) 응답의 `prompt` 필드를 그대로 썼습니다. 외부에 노출된 서버라 2번만 호출했습니다.
  1. 질의만 보냄: `'크레아티닌'에 해당하는 개념을 찾지 못했습니다`(`concept_unmapped`)로 실패 (`rag_response_seed_240.json`)
  2. `"concepts": [{"keyword": "크레아티닌", "concept_id": 3016723}]`를 넣어 다시 보냄: 성공 (`rag_response_seed_240_given.json`)
- **질의:** `seed_240_test_paraphrase` — "현재 연도를 기준으로 연령이 80세 초과인 환자, 제2형 당뇨병 진단 이력이 있는 환자, 또는 크레아티닌 측정값이 50 미만인 환자를 추출하시오."
- 요청 본문 전체는 `request_seed_240.json`, user 메시지 원문은 `user_prompt_seed_240.txt`에 있습니다.

## 조건

| 조건 | 설정 |
|---|---|
| `t0` | temperature 0.0, max_tokens 4096 (TTS `config.py` 기본값) |
| `default` | temperature와 max_tokens를 넣지 않음 (서버 기본 temperature 1.0, 사용자 curl 형태) |

## 결과

| 조건 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| t0 | A | A | A | A | A |
| default | **B** | A | **B** | **C** | A |

| 답 | 나온 횟수 | 샌드박스 실행 | 다른 점 |
|---|---|---|---|
| A | 7 | 26,318행 | 기준 답 |
| B | 2 | 26,318행 (A와 같음) | 크레아티닌 조건에서 `measurement_date <= 기준일` 대신 `value_as_number IS NOT NULL`을 씀 |
| C | 1 | **문법 오류** (`syntax error at end of input`) | 당뇨 EXISTS의 닫는 괄호와 `condition_start_date <= 기준일` 조건이 빠지면서 괄호 하나가 안 닫힘 |

답 A:
```sql
SELECT DISTINCT p.person_id FROM person p
WHERE (EXTRACT(YEAR FROM DATE '2026-11-12') - EXTRACT(YEAR FROM p.birth_datetime)) > 80
   OR EXISTS (SELECT 1 FROM condition_occurrence co WHERE co.person_id = p.person_id
              AND co.condition_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (43531010))
              AND co.condition_start_date <= DATE '2026-11-12')
   OR EXISTS (SELECT 1 FROM measurement m WHERE m.person_id = p.person_id
              AND m.measurement_concept_id IN (SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (3016723))
              AND m.value_as_number < 50 AND m.measurement_date <= DATE '2026-11-12');
```
(줄바꿈은 읽기 좋게 넣은 것이고, 원문은 `responses_seed_240.jsonl`에 있습니다.)

## 정리

1. **temperature 0.0이면 5번 모두 같은 답입니다.** TTS 기본 설정이 0.0이라면 TTS 안에서 같은 재료로 반복했을 때 SQL이 달라지지는 않을 것입니다.
2. **temperature를 빼면 5번 중 3번이 달라졌고, 1번은 실행이 안 되는 SQL이었습니다.** 앞의 학습 형식 프롬프트 시험에서는 달라진 답이 모두 실행 결과가 같았는데, 이번에는 문법 오류까지 나왔습니다.
3. **모든 답(temperature 0.0 포함)에 공통으로 보이는 문제:**
   - **나이:** 재료가 `person.birth_datetime <= DATE '1945-11-12'`를 "그대로 WHERE 에 쓴다"고 줬는데, 모델은 출생연도 차이(`EXTRACT(YEAR …) - EXTRACT(YEAR …) > 80`)로 바꿨습니다. system 프롬프트 규칙과 어긋나고, 생일이 지났는지는 따지지 않습니다.
   - **제2형 당뇨병:** RAG 후보에 일반 2형 당뇨(`201826`)가 없어서, 모델이 첫 후보 `43531010`(임신 중 2형 당뇨)을 골랐습니다. system 프롬프트대로라면 `{{제2형 당뇨병}}`로 남겨야 하는 상황입니다.
   - 둘 다 학습 데이터에 없던 형식(재료의 [나이] 조건, 자리표시자 규칙)이라 모델이 따르지 않는 것으로 보입니다. 다만 이 한 문항만 본 결과입니다.

## 파일

| 파일 | 내용 |
|---|---|
| `run_tts_style.py` | 반복 전송 스크립트. `python3 run_tts_style.py request_seed_240.json [횟수]` |
| `request_seed_240.json` | 요청 본문 (system + user, temperature 0.0, max_tokens 4096) |
| `user_prompt_seed_240.txt` | user 메시지 원문 |
| `rag_response_seed_240*.json` | TTS `/rag` 응답 2개 |
| `responses_seed_240.jsonl` | 응답 10개 (`cond`, `run`, `sql`, `sec`, `finish`, `completion_tokens`) |
