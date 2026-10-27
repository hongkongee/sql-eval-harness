"""샘플 8건으로 extract(api, gliner, qwen-mock) → score → candidates 전체 흐름."""

import csv
import json

from eval import candidates, extract, score
from eval.common import read_jsonl
from tests.conftest import SAMPLE


def _csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_full_flow(fake_server_labels, tmp_path):
    srv = fake_server_labels
    outs = tmp_path / "outputs"
    common = ["--data", str(SAMPLE)]
    assert extract.main(["--system", "api", "--api-url", srv.url, "--out", str(outs / "api.jsonl")] + common) == 0
    assert extract.main(["--system", "gliner", "--gliner-url", srv.url, "--out", str(outs / "gliner.jsonl")] + common) == 0
    assert extract.main(["--system", "qwen", "--mock", "--out", str(outs / "qwen.jsonl")] + common) == 0

    runs = tmp_path / "runs"
    run1 = runs / "20260101-000000"
    preds = [str(outs / f"{n}.jsonl") for n in ("api", "gliner", "qwen")]
    args = common + sum((["--pred", p] for p in preds), []) + ["--concept"]
    assert score.main(args + ["--run-dir", str(run1)]) == 0

    s = json.loads((run1 / "scores.json").read_text())
    assert set(s["results"]) == {"api", "api_concept", "gliner", "gliner_label", "qwen"}
    assert s["parse_failures"] == [] and s["n_records"] == 8
    api = s["results"]["api"]["scopes"]["__all__"]
    assert api["all"]["n"] == 8
    # 440 "심부전 진단 또는 입원 방문인 환자." → person, condition, visit 모두 덮임
    pq = {r["id"]: r for r in read_jsonl(run1 / "per_query_api.jsonl")}
    assert pq["sample:440"]["covered"] is True
    # 슬롯/재구성 변형(130 vs 170/180)은 숫자 마스킹 후 같은 템플릿 → 중복 제거 시 줄어든다
    assert api["dedup"]["n"] < api["all"]["n"]
    # concept 라벨이 있으면 measurement가 concept(수축기혈압)로 추가로 덮인다
    pt = s["results"]["api"]["scopes"]["__all__"]["all"]["per_table"]["measurement"]
    pt_c = s["results"]["api_concept"]["scopes"]["__all__"]["all"]["per_table"]["measurement"]
    assert pt_c["hit"] >= pt["hit"]
    assert s["results"]["api_concept"]["scopes"]["__all__"]["all"]["coverage"] >= api["all"]["coverage"]
    # gliner의 "방문 이력"(라벨: 환자)은 keyword 기준으로는 "방문" 포함 → visit_occurrence
    g = {r["id"]: r for r in read_jsonl(run1 / "per_query_gliner.jsonl")}
    assert "visit_occurrence" in g["sample:seed_1_test_paraphrase"]["pred"]
    gl = {r["id"]: r for r in read_jsonl(run1 / "per_query_gliner_label.jsonl")}
    assert "visit_occurrence" not in gl["sample:seed_1_test_paraphrase"]["pred"]

    md = (run1 / "scores.md").read_text()
    assert "| api |" in md and "gliner_label" in md and "직전 run 없음" in md
    misses = _csv(run1 / "misses_api.csv")
    assert misses and set(misses[0]) >= {"id", "text", "gold_tables", "schema_keywords", "missing_tables"}
    order = [m["missing_table"] for m in misses]
    assert order == sorted(order, key=["person", "observation_period", "visit_occurrence", "condition_occurrence",
                                       "drug_exposure", "procedure_occurrence", "measurement", "death"].index)
    # qwen mock의 "이력"/"발생"은 사전에 없는 단어 → 미매핑
    assert s["unmapped"]["qwen"].get("이력")

    # candidates: qwen만 뽑은 단어 중 사전에 없는 것
    cand_out = run1 / "candidates.csv"
    assert candidates.main(common + ["--base", preds[0], "--ref", preds[2], "--out", str(cand_out)]) == 0
    cands = {r["candidate"]: r for r in _csv(cand_out)}
    assert "이력" in cands and "발생" in cands
    assert "환자" not in cands  # 이미 사전에 있음
    assert "condition_occurrence" in cands["발생"]["gold_tables"] and cands["발생"]["example_1"]
    counts = [int(r["count"]) for r in _csv(cand_out)]
    assert counts == sorted(counts, reverse=True)

    # 두 번째 run: api 결과를 바꿔(한 질의의 키워드를 지움) 회귀가 diff에 잡히는지
    rows = read_jsonl(outs / "api.jsonl")
    for r in rows:
        if r["id"] == "sample:440":
            r["schema_keywords"] = ["환자"]
    (outs / "api.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    run2 = runs / "20260102-000000"
    assert score.main(args + ["--run-dir", str(run2)]) == 0
    diff = (run2 / "diff_prev_api.md").read_text()
    assert "새로 깨진 질의(회귀) 1건" in diff and "sample:440" in diff


def test_concept_without_labels_warns(fake_server, tmp_path, capsys):
    out = tmp_path / "api.jsonl"
    assert extract.main(["--system", "api", "--api-url", fake_server.url, "--data", str(SAMPLE), "--out", str(out)]) == 0
    run = tmp_path / "runs" / "r1"
    assert score.main(["--data", str(SAMPLE), "--pred", str(out), "--concept", "--run-dir", str(run)]) == 0
    s = json.loads((run / "scores.json").read_text())
    assert set(s["results"]) == {"api"}
    assert any("라벨 없음으로 계산 불가" in w for w in s["warnings"])


def test_table_prf():
    from eval.score import compute

    items = [
        {"gold": {"person", "drug_exposure"}, "pred": {"person"}, "noise": [], "unmapped": [], "latency": 1.0},
        {"gold": {"person"}, "pred": {"person", "measurement"}, "noise": ["값"], "unmapped": [], "latency": 3.0},
    ]
    m = compute(items)
    assert m["micro"] == {"tp": 2, "fp": 1, "fn": 1, "precision": 2 / 3, "recall": 2 / 3, "f1": 2 / 3}
    assert m["per_table"]["measurement"]["precision"] == 0.0 and m["per_table"]["measurement"]["recall"] is None
    assert m["per_table"]["drug_exposure"]["recall"] == 0.0 and m["per_table"]["drug_exposure"]["f1"] == 0.0
    assert m["per_table"]["death"]["f1"] is None
    assert m["coverage"] == 0.5
