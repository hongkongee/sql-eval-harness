"""운영 LLM 기준선: 설정(.env) → 요청 → 응답 해석 → API 형식 spans → 정답 CSV 채점."""

import csv
import json

import pytest

from eval import csv_keyword_eval
from eval.common import read_jsonl
from eval.extractors import ExtractError, PreflightError
from eval.extractors.prod_llm import (ParseError, ProdLLMExtractor, _MockResponse, load_category_map,
                                      parse_response, to_spans)

CMAP = load_category_map()


def test_parse_formats():
    # 키 이름으로 경로 구분 + 코드 펜스/think 제거
    c = '<think>..</think>```json\n{"schema_keywords": ["환자", "처방"], "concept_keywords": [{"text": "메트포르민", "category": "약물"}]}\n```'
    assert parse_response(c) == [{"type": "schema", "text": "환자", "category": None},
                                 {"type": "schema", "text": "처방", "category": None},
                                 {"type": "concept", "text": "메트포르민", "category": "약물"}]
    # API와 같은 spans 형식
    assert parse_response('{"spans": [{"type": "schema", "text": "환자"}, {"type": "concept", "text": "고혈압", "label": "질병"}]}') \
        == [{"type": "schema", "text": "환자", "category": None}, {"type": "concept", "text": "고혈압", "category": "질병"}]
    # 카테고리가 키인 형식, 한국어 키, type에 카테고리를 넣은 경우
    assert parse_response('{"스키마": ["진단"], "컨셉": {"진단명": ["당뇨병"], "성별": ["여성"]}}')[1:] \
        == [{"type": "concept", "text": "당뇨병", "category": "진단명"}, {"type": "concept", "text": "여성", "category": "성별"}]
    assert parse_response('{"concepts": [{"keyword": "입원", "type": "visit"}]}') \
        == [{"type": "concept", "text": "입원", "category": "visit"}]
    # 앞뒤 설명 문장이 붙어도 첫 JSON만 읽는다
    assert parse_response('결과입니다:\n{"schema": ["환자"]}\n이상입니다.')[0]["text"] == "환자"
    with pytest.raises(ParseError):
        parse_response('{"keywords": ["환자"]}')  # 어느 경로인지 모르는 키
    with pytest.raises(ParseError):
        parse_response("키워드 없음")


def test_to_spans_locates_maps_and_drops():
    text = "고혈압 진단 후 혈압 측정, 고혈압 재진단인 여자 환자"
    items = [{"type": "concept", "text": "고혈압", "category": "질병"},
             {"type": "concept", "text": "혈압", "category": "measurement"},
             {"type": "concept", "text": "고혈압", "category": "Condition"},
             {"type": "concept", "text": "여자", "category": "gender"},
             {"type": "schema", "text": "진단", "category": "진단"},
             {"type": "concept", "text": "본태성 고혈압", "category": "질병"}]  # 원문에 없음
    spans, dropped = to_spans(items, text, CMAP)
    got = [(s["type"], s["text"], s["start"], s["category"]) for s in spans]
    assert ("concept", "고혈압", 0, "진단명 또는 질병명") in got
    assert ("concept", "혈압", text.index("혈압 측정"), "검사명 또는 측정 항목") in got  # 고혈압 안이 아니라 다음 위치
    assert ("concept", "고혈압", text.index("고혈압 재"), "진단명 또는 질병명") in got  # 두 번째는 다음 등장 위치
    assert ("concept", "여자", text.index("여자"), "성별") in got
    assert ("schema", "진단", 4, "진단") in got  # schema category는 바꾸지 않음
    assert dropped == ["본태성 고혈압"]


def _env(monkeypatch, tmp_path, **extra):
    sysfile = tmp_path / "prod_system.local.txt"
    sysfile.write_text("운영 시스템 프롬프트\n둘째 줄", encoding="utf-8")
    monkeypatch.setenv("PROD_LLM_BASE_URL", "http://llm.test:9000/v1")
    monkeypatch.setenv("PROD_LLM_MODEL", "prod-model")
    monkeypatch.setenv("PROD_LLM_SYSTEM_PROMPT_FILE", str(sysfile))
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


def test_settings_and_request(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, PROD_LLM_USER_TEMPLATE="질의: {text}", PROD_LLM_API_KEY="k",
         PROD_LLM_EXTRA_BODY='{"top_p": 1}', PROD_LLM_MAX_TOKENS="300")
    sent = []

    def post(url, **kw):
        sent.append((url, kw["json"], kw["headers"]))
        return _MockResponse(200, {"choices": [{"message": {"content": '{"schema": ["환자"], "concept": []}'}}]})

    ex = ProdLLMExtractor(post=post)
    ex.preflight()
    out = ex.extract("치매 환자")
    url, body, headers = sent[0]
    assert url == "http://llm.test:9000/v1/chat/completions"
    assert body["model"] == "prod-model" and body["temperature"] == 0 and body["max_tokens"] == 300 and body["top_p"] == 1
    assert body["messages"] == [{"role": "system", "content": "운영 시스템 프롬프트\n둘째 줄"},
                                {"role": "user", "content": "질의: 치매 환자"}]
    assert headers == {"Authorization": "Bearer k"}
    assert out["spans"] == [{"type": "schema", "text": "환자", "start": 3, "end": 5, "category": None}]
    assert ex.config()["system_prompt_sha256"]  # 프롬프트가 바뀌면 이어하기가 막히도록


def test_preflight_errors(monkeypatch, tmp_path):
    with pytest.raises(PreflightError, match="PROD_LLM_BASE_URL"):
        ProdLLMExtractor().preflight()
    _env(monkeypatch, tmp_path, PROD_LLM_SYSTEM_PROMPT_FILE=str(tmp_path / "없는파일.txt"))
    with pytest.raises(PreflightError, match="시스템 프롬프트 파일 없음"):
        ProdLLMExtractor().preflight()


def test_parse_failure_is_extract_error(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    ex = ProdLLMExtractor(post=lambda url, **kw: _MockResponse(200, {"choices": [{"message": {"content": "모르겠습니다"}}]}))
    with pytest.raises(ExtractError) as e:
        ex.extract("환자")
    assert e.value.raw == "모르겠습니다"


GOLD_COLS = ["id", "query", "gold_schema_keywords", "gold_concept_gliner", "gold_concept_dict",
             "gold_derived_schema", "gold_tables", "case_type", "note"]


def _gold_csv(path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(GOLD_COLS)
        w.writerow(["K1", "입원 중 메트포르민을 처방받은 당뇨병 여성 환자.", "입원|처방|환자",
                    "메트포르민:약물명|당뇨병:진단명 또는 질병명", "입원:Visit:입원|여성:Gender:여성",
                    "처방|진단|방문|성별", "visit_occurrence|drug_exposure|condition_occurrence|person", "기본형", ""])
    return path


def test_mock_end_to_end_and_resume_guard(monkeypatch, tmp_path):
    gold = _gold_csv(tmp_path / "gold.csv")
    out = tmp_path / "llm.jsonl"
    args = ["extract", "--system", "prod-llm", "--mock", "--csv", str(gold), "--out", str(out)]
    assert csv_keyword_eval.main(args) == 0
    row = read_jsonl(out)[0]
    assert {s["category"] for s in row["spans"] if s["type"] == "concept"} == {"약물명", "진단명 또는 질병명",
                                                                               "방문 유형", "성별"}
    meta = json.loads(out.with_suffix(".meta.json").read_text())
    assert meta["config"]["system"] == "prod-llm" and meta["config"]["mock"] is True

    run = tmp_path / "run"
    assert csv_keyword_eval.main(["score", "--csv", str(gold), "--pred", str(out), "--out-dir", str(run)]) == 0
    s = json.loads((run / "kw50_scores.json").read_text())
    assert s["concept"]["recall"] == 1.0 and s["concept_dict"]["recall"] == 1.0
    # mock은 "입원"을 concept(방문)로만 내서 schema 정답 "입원"은 FN, 테이블은 대체 스키마로 덮인다
    assert s["schema"]["fn"] == 1 and s["coverage"]["schema+derived"] == 1.0

    # 설정(모델 등)이 바뀌었는데 같은 파일에 이어 쓰려 하면 멈춘다
    monkeypatch.setenv("PROD_LLM_MODEL", "other-model")
    assert csv_keyword_eval.main(args) == 2
    assert csv_keyword_eval.main(args + ["--overwrite"]) == 0


def test_ignore_concept_label_option(tmp_path):
    gold = _gold_csv(tmp_path / "gold.csv")
    pred = tmp_path / "p.jsonl"
    q = "입원 중 메트포르민을 처방받은 당뇨병 여성 환자."
    spans = [{"type": "concept", "text": "메트포르민", "start": q.index("메트"), "end": q.index("메트") + 5, "category": "기타"}]
    pred.write_text(json.dumps({"id": "K1", "text": q, "spans": spans}, ensure_ascii=False) + "\n", encoding="utf-8")
    for flag, recall in (([], 0.0), (["--ignore-concept-label"], 0.5)):
        run = tmp_path / f"run{len(flag)}"
        assert csv_keyword_eval.main(["score", "--csv", str(gold), "--pred", str(pred), "--out-dir", str(run)] + flag) == 0
        assert json.loads((run / "kw50_scores.json").read_text())["concept"]["recall"] == recall
