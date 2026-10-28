# 키워드 추출 응답 인터페이스 (llm-compat · 운영 LLM)

- 작성일: 2026-10-28
- 대상: Text-to-SQL 엔진이 받는 키워드 추출 결과의 형식. 이 형식을 내는 구현은 두 가지다.
  - **운영 LLM** (`prod-llm`): 지금 운영 중인 프롬프트 기반 LLM. 이 형식의 원래 출처다
  - **KE-r3 llm-compat**: 키워드 추출 API의 `POST /keyword-extraction/llm-compat`. 운영 LLM을 대체할 후보다
- 근거:
  - 운영 시스템 프롬프트의 출력 규칙
  - 서비스 코드(gliner-entity-router `5708649`의 `LlmCompatItem`, `API.md`)
  - 50문장 실제 응답(`eval/outputs/kw50_prod_llm.jsonl`, `kw50_ke-r3_compat.jsonl`)

이 문서의 1~4절이 **표준**이고, 5절은 두 구현이 표준을 실제로 어떻게 지키는지다. 표준을 바꾸려면 엔진과 두 구현을 함께 바꿔야 한다.

## 1. 데이터 형식 (표준)

응답은 **JSON 배열 하나**다. 각 원소는 키워드 하나다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `keyword` | string | 예 | 질의 원문에 나온 표현 그대로. 정규화·의역하지 않는다 |
| `label` | string (enum) | 예 | 아래 10개 중 하나 (2절) |
| `table` | string \| null | 예 (키는 항상 존재) | `label`이 EVENT/ATTRIBUTE/ENTITY면 CDM 테이블명(3절). 그 외에는 `null` |

**배열 규칙**
- **순서:** 질의에 등장한 순서대로 둔다.
- **빈 결과:** 키워드가 없으면 `[]`를 낸다.
- **반복:** 같은 표현이 질의에 여러 번 나오면 나온 만큼 낸다(중복 제거 안 함).
- **다른 내용 없음:** 배열 밖에 설명이나 다른 키를 두지 않는다.

**JSON Schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "KeywordExtractionResult",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["keyword", "label", "table"],
    "additionalProperties": false,
    "properties": {
      "keyword": {"type": "string", "minLength": 1},
      "label": {"enum": ["DISEASE", "DRUG", "MEASUREMENT", "PROCEDURE",
                         "EVENT", "ATTRIBUTE", "ENTITY",
                         "VALUE", "OPERATOR", "TIME"]},
      "table": {"type": ["string", "null"]}
    },
    "allOf": [
      {"if": {"properties": {"label": {"enum": ["EVENT", "ATTRIBUTE", "ENTITY"]}}},
       "else": {"properties": {"table": {"type": "null"}}}}
    ]
  }
}
```

## 2. label

| 분류 | label | 뜻 | 예 | table |
|---|---|---|---|---|
| 의료 개체값 | `DISEASE` | 질병·진단명 | 고혈압, 제2형 당뇨병 | null |
| | `DRUG` | 약물명 | 메트포르민, 와파린 | null |
| | `MEASUREMENT` | 검사·측정 항목 | 당화혈색소, 수축기혈압 | null |
| | `PROCEDURE` | 시술·수술명 | 관상동맥우회술, 위내시경 | null |
| 데이터 구조 참조 | `EVENT` | 기록·행위 | 진단, 처방, 측정, 외래 방문, 사망 | 테이블명 |
| | `ATTRIBUTE` | 속성·항목 | 연령, 성별, 여성, 측정값 | 테이블명 |
| | `ENTITY` | 주체 | 환자 | 테이블명 (보통 person) |
| 조건 | `VALUE` | 값 | 70세 이상, 140 | null |
| | `OPERATOR` | 비교·논리·집계 | 이상, 미만, 또는, 최초 | null |
| | `TIME` | 시점·기간 | 2020년 이후, 30일 이내 | null |

- **방문 유형·성별:** 이 체계에는 값(입원/외래/응급실, 남성/여성)을 담는 라벨이 없다. 방문 유형은 `EVENT` / visit_occurrence, 성별 값은 `ATTRIBUTE` / person으로 낸다. 값이 필요하면 받는 쪽이 `keyword`를 다시 해석해야 한다.

## 3. table

`table`에 올 수 있는 값은 아래 CDM 테이블 이름이다. 목록에 맞는 게 없으면 `null`이다.

| table | 한글명 |
|---|---|
| person | 환자 |
| observation_period | 관찰기간 |
| visit_occurrence | 방문 |
| condition_occurrence | 진단 |
| drug_exposure | 약물 처방 |
| procedure_occurrence | 시술 |
| device_exposure | 기기 |
| measurement | 측정 |
| observation | 관찰 |
| death | 사망 |

- **⚠ 대체본 목록:** 운영 프롬프트의 테이블 목록(`_catalog()`)은 아직 받지 못했다. 이 표는 평가에 쓴 대체본이라 운영 목록을 받으면 갱신한다.
- **table은 참고용 힌트다.** 서비스 쪽 결정(2026-10)에 따라 스키마 RAG가 문맥을 보고 다시 판단한다. "위내시경 검사"의 "검사"처럼 문맥에 따라 다른 테이블이 맞는 경우가 있다.

## 4. 내용 규칙 (표준)

1. **원문 그대로:** `keyword`는 질의의 부분 문자열이어야 한다.
2. **제외:** 아래는 키워드로 내지 않는다.
   - 연구설계 용어: 노출군, 비교군, 대조군, 정의, 기준, 여부
   - 데이터모델 메타 언급: OMOP, CDM, OMOP CDM, 데이터모델
   - 원자료에 없고 계산으로 얻는 값: 재원일수, 재원기간, 나이차 등
3. **table 지정 대상:** schema 라벨(EVENT/ATTRIBUTE/ENTITY)에만 table을 넣는다. 의료 개체값과 조건 라벨에는 넣지 않는다(`null`).

## 5. 구현별 차이

### 5.1 호출 방식

| 항목 | 운영 LLM | KE-r3 llm-compat |
|---|---|---|
| 프로토콜 | OpenAI 호환 `POST {base}/chat/completions` | `POST /keyword-extraction/llm-compat` |
| 요청 | `messages`: system = 운영 프롬프트, user = 질의. `temperature 0`, `chat_template_kwargs.enable_thinking=false` | `{"text": "<질의>"}` |
| 배열이 담기는 곳 | `choices[0].message.content` **문자열 안**. 받는 쪽이 JSON으로 디코딩해야 함 | HTTP 응답 본문 자체 (`application/json`) |
| 빈 질의 | 모델 동작에 따름 | `200`, `[]` |
| 요청 형식 오류 | 서버 구현에 따름 | `422` (`text` 누락 등) |
| 실패 형태 | 비어 있는 content(thinking을 켜면 `finish_reason: length`), JSON 아닌 텍스트 가능 | HTTP 오류 코드. 성공 시 스키마 위반 없음 (서버가 `LlmCompatItem`으로 검증) |
| 결정성 | temperature 0이라도 보장 안 됨 | 같은 입력이면 같은 출력 |
| 평균 응답 시간 (50문장) | 1.70초 (원격, 동시 4) | 0.67초 (로컬) |

### 5.2 표준 준수 (50문장 실제 응답 기준)

| 규칙 | 운영 LLM | KE-r3 llm-compat |
|---|---|---|
| 배열 형식, JSON 파싱 | 50 / 50 성공 (코드 펜스 없음) | 50 / 50 |
| `table` 키 항상 존재 | **위반 13건** (의료 개체 항목에서 키 자체를 뺌) | 205 / 205 준수 |
| 의료 개체·조건 라벨의 table = null | **위반 2건** (MEASUREMENT에 measurement) | 준수 |
| `keyword`가 원문에 있음 | 262 / 262 | 205 / 205 |
| 등장 순서 | 대체로 지킴 (모델 출력이라 보장 안 됨) | 시작 위치 순, 같으면 긴 것 먼저 (코드로 보장) |
| 사용하는 label | 10개 모두 | **7개.** VALUE / OPERATOR / TIME은 내지 않음 |
| 실제로 나온 table | 8개: person, observation_period, visit_occurrence, condition_occurrence, drug_exposure, procedure_occurrence, measurement, death | 같은 8개. 묶음별로 고정 (`llm_compat_map.yaml`) |
| 제외 규칙 | 프롬프트 지시로 처리 | `llm_compat_exclude.yaml` 9개 단어와 완전 일치할 때만 제외. 파생 계산값(재원기간 등)은 목록에 없으면 안 걸러짐 |

### 5.3 내용 차이 (형식은 같지만 값이 다른 것)

| 항목 | 운영 LLM | KE-r3 llm-compat |
|---|---|---|
| 키워드 단위 | 구 단위 ("외래 방문 기록", "최초 처방일", "INR 수치") | 사전·모델이 찾은 표면형 ("외래 방문", "처방", "INR" + "수치") |
| label 결정 | 문맥으로 판단 (예: "최초 처방일" → ATTRIBUTE) | 사전 묶음별 고정 매핑 (예: 처방 → 항상 EVENT) |
| table 결정 | 프롬프트의 테이블 목록에서 문맥으로 고름 | 사전 묶음별 고정 매핑 |
| 긴 span 안의 schema 단어 | 의료 개체와 묶어 하나로 내는 경향 ("응급수술" → PROCEDURE 하나) | 지움 (겹침 규칙 2번. 사전 concept뿐 아니라 GLiNER span에도 적용, 07 보고서 3.2절) |

## 6. 예시

질의: "2020년 이후 외래 방문 기록이 있는 70세 이상 여성 고혈압 환자 수"

**운영 LLM** (`choices[0].message.content`를 디코딩한 값)
```json
[
  {"keyword": "2020년 이후", "label": "TIME", "table": null},
  {"keyword": "외래 방문 기록", "label": "EVENT", "table": "visit_occurrence"},
  {"keyword": "70세 이상", "label": "VALUE", "table": null},
  {"keyword": "여성", "label": "ATTRIBUTE", "table": "person"},
  {"keyword": "고혈압", "label": "DISEASE", "table": null},
  {"keyword": "환자", "label": "ENTITY", "table": "person"}
]
```

**KE-r3 llm-compat** (HTTP 응답 본문)
```json
[
  {"keyword": "외래 방문", "label": "EVENT", "table": "visit_occurrence"},
  {"keyword": "여성", "label": "ATTRIBUTE", "table": "person"},
  {"keyword": "고혈압", "label": "DISEASE", "table": null},
  {"keyword": "환자", "label": "ENTITY", "table": "person"}
]
```

## 7. 받는 쪽(엔진) 권장 처리

두 구현을 갈아 끼워도 엔진이 똑같이 동작하게 하려면, 받는 쪽에서 아래처럼 너그럽게 읽는 게 안전하다.

1. `table` 키가 없으면 `null`로 본다 (운영 LLM의 키 누락 대응).
2. 의료 개체·조건 라벨의 `table` 값은 무시한다 (운영 LLM의 규칙 위반 대응).
3. 순서에 의존해야 한다면 `keyword`의 원문 위치로 다시 정렬한다.
4. VALUE / OPERATOR / TIME이 없어도 동작해야 한다 (KE-r3는 내지 않음). 엔진이 이 항목을 쓴다면 대체 전에 따로 확인이 필요하다.
5. `table`은 힌트로만 쓰고, 최종 테이블은 스키마 RAG와 concept RAG 결과로 정한다.
