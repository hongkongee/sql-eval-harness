from eval.csv_keyword_eval import locate, score_row
from eval.keyword_map import KeywordTableMap


def test_locate_skips_spans_already_taken():
    q = "외래에서 처음 고혈압 진단을 받은 날짜와 첫 혈압 측정일"
    used = []
    assert locate(q, "고혈압", used) == (8, 11)
    assert locate(q, "혈압", used) == (q.index("첫 혈압") + 2, q.index("첫 혈압") + 4)


def test_score_row_paths():
    g = {"id": "K", "query": "응급실 방문한 여성 환자 중 혈당 측정", "case_type": "기본형",
         "schema": ["방문", "환자", "측정"], "gliner": [{"text": "혈당", "label": "검사명 또는 측정 항목"}],
         "dict": [{"text": "여성", "domain": "Gender", "value": "여성"}], "derived": ["측정", "성별"],
         "tables": ["visit_occurrence", "measurement", "person"]}
    pred = {"spans": [
        {"type": "schema", "text": "방문", "start": 4, "end": 6},
        {"type": "schema", "text": "환자", "start": 12, "end": 14},
        {"type": "concept", "text": "혈당", "start": 17, "end": 19, "category": "진단명 또는 질병명", "score": 0.8},
        {"type": "schema", "text": "측정", "start": 20, "end": 22},
    ]}
    r = score_row(g, pred, KeywordTableMap(warn=False), 0.0)
    assert r["schema"]["fn"] == [] and r["schema"]["fp"] == []
    # 위치는 맞고 라벨이 틀림 → FN + FP + 라벨 오류
    assert r["concept"]["fn"] == ["혈당"] and r["concept"]["label_err"] == ["혈당→진단명 또는 질병명"]
    assert r["concept"]["fp"][0]["on_gold"] is True
    assert r["concept_dict"]["fn"] == ["여성:Gender"]
    assert r["derived"] == {"tp": [], "fn": ["성별", "측정"], "fp": ["진단"]}
    assert r["tables"]["schema"]["covered"] is True
    assert r["tables"]["schema+derived"]["fp"] == ["condition_occurrence"]


def test_score_row_dict_concepts_ke_r2():
    g = {"id": "K", "query": "외래 방문한 여자 환자", "case_type": "기본형", "schema": ["방문", "환자"], "gliner": [],
         "dict": [{"text": "외래", "domain": "Visit", "value": "외래"}, {"text": "여자", "domain": "Gender", "value": "여성"}],
         "derived": ["방문", "성별"], "tables": ["visit_occurrence", "person"]}
    pred = {"spans": [
        {"type": "concept", "text": "외래 방문", "start": 0, "end": 5, "category": "방문 유형"},
        {"type": "schema", "text": "방문", "start": 3, "end": 5, "category": "방문"},
        {"type": "concept", "text": "여자", "start": 7, "end": 9, "category": "방문 유형"},
        {"type": "schema", "text": "환자", "start": 10, "end": 12, "category": "환자"},
    ]}
    r = score_row(g, pred, KeywordTableMap(warn=False), 0.0)
    # 사전 concept는 GLiNER concept 채점에 섞이지 않는다
    assert r["concept"]["fp"] == []
    assert r["concept_dict"]["tp"] == ["외래:Visit"] and r["concept_dict"]["fn"] == ["여자:Gender"]
    assert r["concept_dict"]["fp"] == ["여자:방문 유형"] and r["concept_dict"]["label_err"] == ["여자→방문 유형"]
    assert r["derived"]["tp"] == ["방문"] and r["derived"]["fn"] == ["성별"]


def test_ke_compat_extractor_maps_llm_format(monkeypatch):
    """KE-r3 /keyword-extraction/llm-compat 응답을 운영 LLM과 같은 해석기로 span화한다."""
    import argparse
    from eval import csv_keyword_eval as m
    from eval.httpclient import Response

    body = [{"keyword": "외래 방문", "label": "EVENT", "table": "visit_occurrence"},
            {"keyword": "여성", "label": "ATTRIBUTE", "table": "person"},
            {"keyword": "고혈압", "label": "DISEASE", "table": None}]
    monkeypatch.setattr(m, "post_json", lambda url, payload, **kw: Response(body=body, latency_ms=3.0, attempts=1))
    call, config = m._make_extractor(argparse.Namespace(system="ke-compat", url="http://x/llm-compat", timeout=1))
    out = call("외래 방문한 여성 고혈압 환자")
    assert config == {"system": "ke-compat", "url": "http://x/llm-compat"}
    assert [(s["type"], s["text"], s["category"], s.get("table")) for s in out["spans"]] == [
        ("schema", "외래 방문", "EVENT", "visit_occurrence"),
        ("schema", "여성", "ATTRIBUTE", "person"),
        ("concept", "고혈압", "진단명 또는 질병명", None)]
