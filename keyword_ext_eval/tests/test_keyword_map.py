import yaml

from eval.extractors.api import ApiExtractor
from eval.keyword_map import KeywordTableMap


def test_exact_surface_to_group_to_table():
    km = KeywordTableMap()
    r = km.resolve("투약")  # 표면형 → 묶음 "처방"
    assert (r.how, r.groups, r.tables) == ("exact", ["처방"], ["drug_exposure"])
    assert km.resolve("관찰 기간").tables == ["observation_period"]


def test_group_with_no_table_is_not_unmapped():
    r = KeywordTableMap().resolve("추적기간")
    assert r.how == "exact" and r.tables == []


def test_contains_uses_longest_surface():
    km = KeywordTableMap()
    r = km.resolve("심부전 진단")
    assert (r.how, r.tables) == ("contains", ["condition_occurrence"])
    # "측정값" 안의 "측정"/"값"으로 따로 세지 않는다
    assert km.resolve("수축기혈압 측정값 변화").groups == ["측정값"]
    # 겹치지 않는 표면형이 여럿이면 모두
    assert km.resolve("처방 후 사망").tables == ["drug_exposure", "death"]


def test_unmapped_word():
    r = KeywordTableMap().resolve("코호트")
    assert (r.how, r.tables) == ("unmapped", [])


def test_warns_on_dict_group_missing_from_map(tmp_path, capsys):
    d = tmp_path / "dict.yaml"
    d.write_text(yaml.safe_dump({"환자": ["환자"], "신규묶음": ["신규"]}, allow_unicode=True), encoding="utf-8")
    km = KeywordTableMap(dict_file=d)
    assert km.unmapped_groups == ["신규묶음"]
    assert "신규묶음" in capsys.readouterr().err
    assert km.resolve("신규").tables == []


def test_api_dedups_repeated_schema_spans(fake_server):
    ex = ApiExtractor(url=fake_server.url)
    out = ex.extract({"text": "환자 중 진단 이력이 있는 환자이며 진단일 기준 환자."})
    assert out["schema_keywords"] == ["환자", "진단"]
