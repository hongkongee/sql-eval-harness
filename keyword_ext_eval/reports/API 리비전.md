# 키워드 추출 API 리비전

평가 결과를 비교할 때 기준이 되는 API 구성을 리비전 단위로 기록한다. API 코드, 사전, 모델, threshold 중 하나라도 바뀌면 새 리비전으로 올리고 같은 정답셋으로 다시 평가한다.

## 리비전 표

| 항목 | v1 | v2 |
|---|---|---|
| 확정일 | 2026-10-27 | 2026-10-28 |
| 서비스 코드 | gliner-entity-router `3292344` ("spans에 category 필드 추가…"). 실행 중인 컨테이너의 `app/` 파일 sha256이 이 커밋과 일치함을 확인 | `3292344` + **커밋 안 된 변경** (`app/core/keyword_extraction.py`, `schema_keyword_matcher.py`, `settings.py`, `concept_keywords.yaml` 신규). 컨테이너 파일 sha256이 작업 트리와 일치함을 확인 |
| 실행 환경 | Docker `gliner-entity-router-keyword-extraction-1`, 이미지 2026-10-27 14:22 KST 빌드, 컨테이너 17:40 KST 생성, gliner 0.2.29 | 같은 컨테이너 이름, 이미지·컨테이너 2026-10-28 08:51 KST 빌드/생성, gliner 0.2.29 |
| 엔드포인트 | `POST http://localhost:8001/keyword-extraction`, 요청 `{"text": "<자연어 질의>"}` | v1과 같음 |
| 응답 형식 | `{text, spans: [{type, text, start, end, category, score?}]}`. `type`은 `schema` 또는 `concept`. `category`는 schema면 사전 대표 키워드, concept면 GLiNER 라벨. `score`는 concept만 | v1과 같음 (필드 추가 없음). 사전 concept는 `type: concept`, `category: 방문 유형/성별`, `score` 없음 |
| 스키마 경로 | 사전 최장 일치(pyahocorasick). `app/config/schema_keywords.yaml` **사전 v1** (sha256 `b16306906cd3…`, 대표 키워드 13개 / 표면형 39개). 표면형을 원문 그대로 출력하고 위치별로 전부 반환 | v1과 같음 (사전 v1, 해시 동일) |
| concept 경로 | GLiNER `Ihor/gliner-biomed-large-v1.0` (제로샷, 파인튜닝 없음), `multi_label=True` | v1과 같음 (GLiNER) + **사전 매칭** (`app/config/concept_keywords.yaml`, sha256 `19ba444c8948…`, 방문 유형 표면형 3개 / 성별 2개, schema와 같은 최장 일치 함수 재사용) |
| concept 라벨 | 진단명 또는 질병명 / 약물명 / 검사명 또는 측정 항목 / 시술명 또는 수술명 (4개) | GLiNER는 v1과 같음 (4개). 사전 category 2개 추가: 방문 유형 / 성별 |
| concept threshold | **0.3**. 컨테이너 환경변수 `GLINER_THRESHOLD=0.3` (docker-compose 기본값 `KEYWORD_EXTRACTION_THRESHOLD:-0.3`). 코드 기본값은 0.2 | v1과 같음 (0.3, GLiNER에만 적용) |
| concept 후처리 | concept span 양 끝에 붙은 스키마 단어를 잘라냄. 잘라낸 결과가 비거나 스키마 span과 같아지면 버림. 같은 위치에 라벨이 여럿이면 최고 점수 하나만 남김 | v1 규칙 + 사전 concept span과 **정확히 같은 위치**의 GLiNER span은 버림. 사전 concept span은 schema span과 같은 위치여도 유지 (예: "입원") |
| Visit/Gender 값 (입원·외래·응급실, 여성·남성 등) | **없음**. "입원"·"방문"·"성별"은 스키마 사전으로만 잡힘 | **사전 매칭으로 추가**. 다만 응답에는 도메인(category)만 있고 값(입원/외래, 여성/남성)이나 concept_id는 없음 |
| 대체 스키마 (concept 라벨 → 묶음) | **없음** | **없음** |
| 평가 | [키워드 추출 API 평가 (정답셋 50)](키워드%20추출%20API%20평가%20(정답셋%2050).md) | [키워드 추출 API 평가 (정답셋 50) — API v2](키워드%20추출%20API%20평가%20(정답셋%2050)%20—%20API%20v2.md) |
| 핵심 수치 (정답셋 50) | 스키마 P 98.3 / R 94.3 / F1 96.3 · concept P 87.1 / R 91.4 / F1 89.2 · Visit/Gender R 0 (미구현) · 테이블 커버리지 42% (대체 스키마 모의 시 82%) | 스키마·concept(GLiNER) v1과 동일 · **Visit/Gender P 100 / R 52.2 / F1 68.6** · 테이블 커버리지 42% (대체 스키마 모의 시 84%) |

## 주의

- **threshold 0.3은 서비스 레포에 아직 커밋되지 않은 값이다.** gliner-entity-router의 `docker-compose.yml` 변경(0.2 → 0.3)이 작업 트리에만 있다. v1을 재현하려면 이 변경을 커밋하거나, 띄울 때 `KEYWORD_EXTRACTION_THRESHOLD=0.3`을 줘야 한다.
- **v2도 서비스 레포에 커밋되지 않았다** (2026-10-28 기준). 사전 concept 코드와 `concept_keywords.yaml`이 작업 트리에만 있다. 커밋하면 이 표의 서비스 코드 칸을 그 커밋 해시로 바꾼다.
- v1 → v2는 사전 concept 경로만 바뀌었다. 50문장에서 schema span과 GLiNER span은 v1과 글자 하나 다르지 않다. 그래서 두 리비전의 차이는 전부 사전 concept 경로의 효과다.
- 정답셋 50은 v2까지 사전을 만드는 데 쓰지 않았다. v2 보고서의 FN 목록을 보고 사전을 고친다면, v3부터 이 셋은 개발셋으로 보고 성능은 새 held-out 셋으로 잰다.
- 사전 v1 평가(`스키마 키워드 추출 평가 (사전 v1).md`, 2026-10-24)는 v1 이전 API로 돌렸다. 당시에는 응답에 `category`가 없었다. 사전은 v1과 같다. 그 평가는 스키마 경로만 보므로 스키마 수치는 비교할 수 있다. concept 수치는 threshold가 달라 비교할 수 없다.

## 새 리비전을 올릴 때

1. 위 표에 열(v2 …)을 추가하고, 바뀐 항목을 적는다.
2. 서비스 커밋과 컨테이너 파일이 일치하는지 확인한다. 사전은 평가 도구의 해시 확인(`--strict-dict`)으로 확인한다.
3. 같은 정답셋으로 평가해 보고서를 남기고, 핵심 수치 행을 채운다.
