"""정답 SQL → 사용 테이블 (sqlglot, PostgreSQL dialect).

sqlglot의 scope 분석으로 각 SELECT 범위의 실제 테이블 소스만 모은다. 그래서
- CTE 이름(`WITH t AS (...) SELECT ... FROM t`)은 테이블로 안 센다 (CTE가 실제 테이블과
  같은 이름이어도 CTE 참조와 CTE 본문 안의 실제 테이블을 구분한다)
- 서브쿼리·UNION 각 분기·EXISTS 안쪽까지 다 들어간다
- 별칭(person p)·스키마 접두어(cdm.person)·따옴표("Person")는 테이블 이름만 소문자로 남는다
대상 테이블 8개 외(concept, concept_ancestor 등 어휘 테이블)는 버린다.
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import traverse_scope

from eval.common import EVAL_DIR, sha256_text

TARGET_TABLES = (
    "person", "observation_period", "visit_occurrence", "condition_occurrence",
    "drug_exposure", "procedure_occurrence", "measurement", "death",
)
CACHE_PATH = EVAL_DIR / ".cache" / "sql_tables.json"


def all_tables(sql: str) -> set[str]:
    """SQL이 참조하는 모든 실제 테이블 이름(소문자). 파싱 실패 시 sqlglot 예외를 그대로 올린다."""
    tree = sqlglot.parse_one(sql, read="postgres")
    if tree is None:
        raise sqlglot.errors.ParseError("빈 SQL")
    found = set()
    for scope in traverse_scope(tree):
        for source in scope.sources.values():
            if isinstance(source, exp.Table):
                found.add(source.name.lower())
    if not found:
        # scope로 못 잡는 구문(DML 등) 대비: CTE 이름을 뺀 Table 노드 전부
        ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
        found = {t.name.lower() for t in tree.find_all(exp.Table) if t.name.lower() not in ctes}
    return found


def target_tables(sql: str) -> list[str]:
    tables = all_tables(sql)
    return [t for t in TARGET_TABLES if t in tables]


class TableCache:
    """sql 해시 → {"tables": [...]} 또는 {"error": "..."}. sqlglot 버전이 바뀌면 캐시를 버린다."""

    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else CACHE_PATH
        self.data: dict = {}
        self.dirty = False
        if path and path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("sqlglot") == sqlglot.__version__:
                self.data = raw.get("entries", {})

    def get(self, sql: str) -> dict:
        key = sha256_text(sql)
        if key not in self.data:
            try:
                self.data[key] = {"tables": target_tables(sql)}
            except Exception as exc:  # noqa: BLE001 - 파싱 실패 SQL은 목록으로 따로 보고한다
                self.data[key] = {"error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"}
            self.dirty = True
        return self.data[key]

    def save(self) -> None:
        if self.path and self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"sqlglot": sqlglot.__version__, "entries": self.data},
                                            ensure_ascii=False), encoding="utf-8")
            self.dirty = False
