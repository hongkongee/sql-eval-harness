# 키워드 추출 API 평가 (정답셋 50) — KE-r3 llm-compat

- 평가일: 2026-10-28
- 대상: **KE-r3** = KE-r2 + 운영 LLM 호환 출력 엔드포인트 `POST /keyword-extraction/llm-compat` (gliner-entity-router `5708649`). 구성은 [API 리비전](01_API%20리비전.md) 참고
- 비교 기준: [KE-r2](05_키워드%20추출%20API%20평가%20(정답셋%2050)%20—%20KE-r2.md) (같은 추출 결과의 기존 형식), [운영 LLM](06_운영%20LLM%20키워드%20추출%20평가%20(정답셋%2050).md) (같은 출력 형식)
- 원자료: `eval/outputs/kw50_ke-r3.jsonl` (기존 엔드포인트), `eval/outputs/kw50_ke-r3_compat.jsonl` (새 엔드포인트, 응답 원문 `raw` 포함), 채점 결과 `eval/runs/kw50_ke-r3_compat/`

## 요약

KE-r3는 사전·GLiNER·threshold가 KE-r2와 같고, 새 엔드포인트 하나만 추가했다. 그래서 두 가지를 쟀다.

1. **회귀 확인: 이상 없음.** 기존 `/keyword-extraction` 응답이 50문장 모두 KE-r2와 완전히 같다.
2. **새 엔드포인트: 운영 LLM과 같은 형식으로 처음 나란히 비교했다.**

| 지표 | KE-r3 llm-compat | 운영 LLM | KE-r2 (기존 형식) |
|---|---|---|---|
| 스키마 키워드 (겹침) P / R / F1 | **94.9 / 90.2 / 92.5** | 85.5 / 86.2 / 85.8 | 98.3 / 94.3 / 96.3 |
| concept (의료 4라벨) P / R / F1 | 87.1 / 91.4 / 89.2 | **90.9 / 98.8 / 94.7** | 87.1 / 91.4 / 89.2 |
| 방문·성별 도메인 맞음 (23개 중) | 12 | **16** | 12 |
| 테이블 (응답의 table 그대로) P / R / F1 | **68.0 / 60.3 / 63.9** | 66.3 / 59.5 / 62.7 | 67.6 / 62.9 / 65.2 (사전 매핑) |
| └ 커버리지 | **40%** | 36% | 42% |
| 테이블 + 다운스트림 추론 (가정) 커버리지 | 84% | **90%** | 84% |
| 조건 항목 (VALUE / OPERATOR / TIME) | 내지 않음 | 48개 | — |
| 평균 응답 시간 | **0.67초** | 1.70초 | 0.63초 |

- 같은 형식으로 비교하면 **스키마 단어와 테이블은 KE-r3가, 의료 라벨과 방문·성별은 운영 LLM이 낫다.** 형식이 달랐던 06 보고서의 결론과 같다.
- KE-r2 대비 스키마 재현율이 94.3 → 90.2로 떨어졌다. 원인은 변환 규칙의 겹침 처리 2번(긴 span 안의 schema span 제거)이다. **사전 concept뿐 아니라 GLiNER span 안의 스키마 단어까지 지워서** 테이블 단서 4개를 잃었다(3.2절).

## 1. 실행 조건

| 항목 | 값 |
|---|---|
| 서비스 코드 | gliner-entity-router `5708649` ("운영 LLM 호환 출력 엔드포인트(/keyword-extraction/llm-compat) 추가"). 컨테이너 `app/` 파일 sha256이 커밋과 일치함을 확인 |
| 컨테이너 | `gliner-entity-router-keyword-extraction-1`, 2026-10-28 11:38 KST 생성, `GLINER_THRESHOLD=0.3` |
| 사전 | schema-dict v1 (`b16306906cd3…`), concept-dict v1 (`19ba444c8948…`). 둘 다 KE-r2와 같음 |
| 변환 설정 | `llm_compat_map.yaml` (`eb76be02c49d…`), `llm_compat_exclude.yaml` (`e4c19435b3cb…`, 제외어 9개) |
| 추출 | `--system ke-compat`. 응답 배열을 운영 LLM과 **같은 해석기**(`eval/extractors/prod_llm.py`)로 읽어 span으로 바꿈. 50건 모두 해석 성공, 원문에서 못 찾은 키워드 0개 |

## 2. 채점 방법

06 보고서(운영 LLM)와 완전히 같다. EVENT / ATTRIBUTE / ENTITY는 schema, DISEASE 등 4개는 concept으로 채점하고, 응답의 `table`은 "응답의 table 그대로" 테이블 지표로 쓴다. 방문·성별은 형식에 값이 없으므로 형식과 무관한 "도메인 맞음"으로 센다.

- 성별: ATTRIBUTE / person
- 방문: EVENT / visit_occurrence

## 3. 결과

### 3.1 회귀 확인 (기존 엔드포인트)

`/keyword-extraction` 응답을 KE-r2 결과(`kw50_ke-r2.jsonl`)와 문장별로 비교했다. 50문장 모두 span 목록이 완전히 같다. 기존 엔드포인트의 점수는 KE-r2와 같으므로 다시 적지 않는다.

### 3.2 스키마 키워드: KE-r2 대비 빠진 것

| 지표 | TP | FP | FN | P | R | F1 |
|---|---|---|---|---|---|---|
| 정확 일치 | 109 | 8 | 14 | 93.2 | 88.6 | 90.8 |
| 겹침 | 111 | 6 | 12 | 94.9 | 90.2 | 92.5 |

**FP 8개는 모두 형식 차이다.** 방문·성별 값이 schema 라벨로 나간 것이다.
- 여성 ×4, 남성 ×2: ATTRIBUTE / person
- 응급실 방문, 외래 방문: EVENT / visit_occurrence

이를 빼면 정밀도는 100%다. 운영 LLM에도 같은 형식 차이가 있다.

**KE-r2 대비 새로 생긴 FN 7개는 모두 겹침 규칙 2번 때문이다.**

| id | 빠진 schema 단어 | 덮은 긴 span | 덮은 span 출처 | 테이블 영향 |
|---|---|---|---|---|
| K001 | 방문 | 응급실 방문 | concept 사전 (방문 유형) | 없음 (긴 span이 visit_occurrence) |
| K049 | 방문 | 외래 방문 | concept 사전 (방문 유형) | 없음 (위와 같음) |
| K016 | 수술 | 응급수술 | **GLiNER** (시술명) | procedure_occurrence 잃음 |
| K035 | 측정 | 혈압 측정일 | **GLiNER** (검사명) | measurement 잃음 |
| K044 | 수치 | 호중구 수치 | **GLiNER** (검사명) | measurement 잃음 |
| K028 | 환자 | 흉통 환자 | **GLiNER** (진단명, 경계 오류) | person FP가 빠짐 (이 문장은 정답에 person 없음) |
| K022 | 검사 | 위내시경 검사 | **GLiNER** (시술명) | measurement FP가 빠짐 (정답은 procedure) |

정답 schema 키워드에는 없어 FN으로 세지 않았지만, 같은 이유로 K039 "관상동맥질환" 안의 "질환"(진단)도 빠졌다. 이 때문에 K039는 condition_occurrence를 잃어 커버리지에서 빠졌다.

- **K001·K049는 구현 요청에 적은 의도대로다.** 사전 concept 안의 "방문"을 지운 경우다.
- **나머지 6건은 의도보다 넓다.** 요청서에는 "schema span이 더 긴 **사전 concept** span 안에 완전히 들어가면"이라고 적었다. 그런데 구현(`app/core/llm_compat.py`의 `_resolve_overlaps`)은 **모든 긴 span**에 적용한다. concept 항목의 table은 항상 null이다. 그래서 GLiNER span에 흡수된 스키마 단어가 사라지면 그 테이블 단서도 같이 사라진다.
- 이렇게 하면 운영 LLM의 경향과 비슷해지기는 한다. 운영 LLM도 "INR 수치", "응급수술"을 한 덩어리 concept으로 낸다(06 보고서 3.1절). 하지만 테이블 단서를 잃는 쪽으로 닮는 것이다.

### 3.3 concept (의료 4라벨)

KE-r2와 같다(P 87.1 / R 91.4 / F1 89.2, 라벨 오류 7). 변환이 concept span을 바꾸지 않기 때문이다. 운영 LLM(F1 94.7, 라벨 오류 1)과의 격차는 그대로다.

### 3.4 방문·성별

포착 14 / 23, 도메인 맞음 12 / 23이다. KE-r2와 같은 사전 결과가 EVENT·ATTRIBUTE로 바뀌어 나갈 뿐이다. 운영 LLM은 도메인 맞음 16 / 23이다.

### 3.5 테이블

| 지표 | KE-r3 llm-compat | 운영 LLM |
|---|---|---|
| 응답의 table 그대로: P / R / F1 | 68.0 / 60.3 / 63.9 | 66.3 / 59.5 / 62.7 |
| └ 커버리지 | **40%** | 36% |
| └ person 제외 P / R | 98.3 / 57.8 | 98.2 / 53.9 |
| + 다운스트림 추론 (가정): P / R / F1 | 72.5 / 93.1 / 81.5 | 73.0 / 95.7 / 82.8 |
| └ 커버리지 | 84% | **90%** |

테이블별 재현율 (응답 table → + 모의)

| 테이블 | KE-r3 llm-compat | 운영 LLM |
|---|---|---|
| person | 79 → 79 | 100 → 100 |
| observation_period | 100 → 100 | 100 → 100 |
| visit_occurrence | 77 → 77 | 77 → 77 |
| condition_occurrence | 32 → 100 | 34 → 100 |
| drug_exposure | 86 → 93 | 93 → 93 |
| procedure_occurrence | 20 → 100 | 20 → 100 |
| measurement | 73 → 93 | 40 → 100 |
| death | 100 → 100 | 88 → 88 |

- **응답에 실린 table만 보면 KE-r3가 운영 LLM보다 조금 낫다** (커버리지 40% vs 36%). 차이는 주로 measurement다(73 vs 40). "측정", "수치" 같은 스키마 단어를 LLM보다 많이 남기기 때문이다.
- **KE-r2의 사전 매핑(42%)보다는 낮다.** 3.2절의 GLiNER 흡수로 K039(condition)를 잃었다.
- 다운스트림이 concept에서 테이블을 정한다고 가정하면, 운영 LLM이 90%로 높다. 방문·성별과 검사명 라벨 차이 때문이다.

### 3.6 운영 LLM에만 있는 것

- **VALUE / OPERATOR / TIME:** KE-r3는 내지 않는다(구현 1단계 범위 밖). 운영 LLM은 50문장에서 48개를 냈다(VALUE 16, OPERATOR 20, TIME 12). 엔진이 이 항목을 쓰는지에 따라 대체 가능 여부가 갈린다.
- **제외어 9개:** 이번 50문장에서는 하나도 걸리지 않았다. 효과를 재려면 연구설계 용어가 들어간 문장이 필요하다.

## 4. 결론

1. **기존 엔드포인트에 회귀는 없다.** 50문장 응답이 KE-r2와 완전히 같다.
2. **운영 LLM과 같은 형식으로 비교하면 스키마 단어(F1 92.5 vs 85.8)와 응답 table 커버리지(40% vs 36%)는 KE-r3가 낫다.** 의료 라벨(89.2 vs 94.7)과 방문·성별(12 vs 16)은 운영 LLM이 낫다. 응답 시간은 KE-r3가 2.5배 빠르다.
3. **겹침 규칙 2번의 적용 범위가 요청보다 넓다.** GLiNER span 안의 스키마 단어까지 지워서 KE-r2보다 스키마 재현율이 4%p 떨어지고, 테이블 단서 4개(procedure 1, measurement 2, condition 1)를 잃었다. 규칙을 **사전 concept span 안에만** 적용하면 K001·K049는 그대로 처리되고 나머지 6건은 되살아난다. 서비스 코드 변경이라 판단을 남긴다.
4. **운영 LLM을 대체하려면 남은 격차는 세 가지다.** 검사명 라벨 오류, 방문·성별 어휘, 그리고 엔진이 쓴다면 VALUE / OPERATOR / TIME이다.

## 5. 재현

```bash
C=../test_set/keyword_ext/keyword_eval_samples_50.csv
python -m eval.csv_keyword_eval extract --csv $C --out eval/outputs/kw50_ke-r3.jsonl                            # 기존 엔드포인트 (회귀 확인)
python -m eval.csv_keyword_eval extract --system ke-compat --csv $C --out eval/outputs/kw50_ke-r3_compat.jsonl  # 새 엔드포인트
python -m eval.csv_keyword_eval score --csv $C --pred eval/outputs/kw50_ke-r3_compat.jsonl --out-dir eval/runs/kw50_ke-r3_compat
```
회귀 비교(3.1절)와 방문·성별 도메인 맞음(3.4절)은 채점기에 아직 없어서 출력 jsonl로 따로 계산했다.
