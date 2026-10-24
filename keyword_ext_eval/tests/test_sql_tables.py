import pytest
import sqlglot

from eval.sql_tables import TableCache, all_tables, target_tables


def test_cte_names_are_not_tables():
    sql = """WITH idx AS (SELECT person_id FROM drug_exposure), base AS (SELECT * FROM idx)
             SELECT * FROM base b JOIN person p ON p.person_id = b.person_id"""
    assert all_tables(sql) == {"drug_exposure", "person"}


def test_cte_shadowing_real_table_name():
    # CTE 이름이 실제 테이블과 같아도, CTE 본문 안의 실제 테이블은 센다
    sql = "WITH measurement AS (SELECT * FROM measurement WHERE value_as_number > 1) SELECT * FROM measurement"
    assert target_tables(sql) == ["measurement"]
    sql2 = "WITH death AS (SELECT person_id FROM person) SELECT * FROM death"
    assert target_tables(sql2) == ["person"]


def test_subquery_and_exists():
    sql = """SELECT DISTINCT p.person_id FROM person p WHERE EXISTS (
               SELECT 1 FROM condition_occurrence co WHERE co.person_id = p.person_id AND co.condition_concept_id IN (
                 SELECT descendant_concept_id FROM concept_ancestor WHERE ancestor_concept_id IN (1)))
             AND p.person_id IN (SELECT person_id FROM (SELECT person_id FROM measurement) m)"""
    assert target_tables(sql) == ["person", "condition_occurrence", "measurement"]


def test_alias_and_case():
    assert target_tables("SELECT v.person_id FROM Visit_Occurrence AS v") == ["visit_occurrence"]


def test_union_branches():
    sql = "SELECT person_id FROM death UNION ALL SELECT person_id FROM procedure_occurrence UNION SELECT 1"
    assert target_tables(sql) == ["procedure_occurrence", "death"]


def test_schema_prefix_and_quotes():
    sql = 'SELECT * FROM cdm.person p JOIN "cdm"."Observation_Period" op ON op.person_id = p.person_id'
    assert all_tables(sql) == {"person", "observation_period"}


def test_vocabulary_tables_excluded():
    sql = "SELECT * FROM concept c JOIN concept_ancestor ca ON 1=1 JOIN drug_exposure d ON 1=1"
    assert target_tables(sql) == ["drug_exposure"]


def test_parse_failure_raises_and_is_cached_as_error(tmp_path):
    with pytest.raises(sqlglot.errors.ParseError):
        all_tables("SELEC broken FROM")
    cache = TableCache(tmp_path / "c.json")
    assert "error" in cache.get("SELEC broken FROM")
    assert cache.get("SELECT * FROM person") == {"tables": ["person"]}
    cache.save()
    again = TableCache(tmp_path / "c.json")
    assert again.data == cache.data and not again.dirty
