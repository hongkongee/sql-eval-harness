from eval.visit_gender_eval import GENDER, VISIT, build_gold, score_label, sql_concepts

DESC = "SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN ({})"


def test_sql_concepts_forms():
    sql = (f"... vo.visit_concept_id IN ({DESC.format('9201, 262')}) AND p.gender_concept_id = 8532 "
           "AND x.visit_concept_id IN (9202)")
    assert sql_concepts(sql) == {("visit_concept_id", 9201), ("visit_concept_id", 262),
                                 ("visit_concept_id", 9202), ("gender_concept_id", 8532)}


def test_gold_longest_first_and_no_overlap():
    sql = f"visit_concept_id IN ({DESC.format('262')}) OR visit_concept_id IN ({DESC.format('9201')})"
    gold, missing = build_gold("응급실 입원 방문이고 입원 방문인 환자.", sql)
    assert [(g["text"], g["concept"]) for g in gold] == [("응급실 입원 방문", 262), ("입원 방문", 9201)]
    assert missing == []


def test_gold_only_when_sql_filters():
    # SQL이 방문을 안 거르면 "외래"가 있어도 정답이 아니다 (시술명 속 "외래")
    gold, missing = build_gold("만성 외래 복막투석 카테터 삽입술 시행 환자.", "SELECT * FROM procedure_occurrence")
    assert gold == [] and missing == []
    gold, missing = build_gold("남성 환자.", "gender_concept_id = 8532")
    assert gold == [] and missing == ["gender_concept_id=8532"]


def test_score_label_overlap_exact_and_query_counts():
    items = [
        {"gold": [{"start": 0, "end": 5, "label": VISIT}],
         "pred": [{"start": 0, "end": 2, "label": VISIT, "score": 0.6},
                  {"start": 7, "end": 9, "label": GENDER, "score": 0.9}]},
        {"gold": [], "pred": [{"start": 0, "end": 2, "label": VISIT, "score": 0.4}]},
    ]
    m = score_label(items, VISIT, 0.3)
    assert (m["tp_pred"], m["n_pred"], m["tp_gold"], m["n_gold"]) == (1, 2, 1, 1)
    assert m["query"] == {"pos": 1, "pos_all_hit": 1, "neg": 1, "neg_with_fp": 1}
    assert score_label(items, VISIT, 0.5)["precision"] == 1.0
    assert score_label(items, VISIT, 0.3, exact=True)["recall"] == 0.0
    assert score_label(items, GENDER, 0.5)["precision"] == 0.0
