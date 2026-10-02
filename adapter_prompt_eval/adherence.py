"""[질의]/[재료] 프롬프트 1건에 대해, 모델이 생성한 SQL이 그 프롬프트의 "재료"를
얼마나 잘 반영했는지 채점한다.

여기서 쓰는 presence/usage/correctness 3단계 정의와 정규식(_ANCHOR_LINE,
_extract_slot_spans)은 automl-llm/scripts/compute_adherence.py가 학습 중
checkpoint별 "Concept-ID Prompt Adherence"를 계산할 때 쓰는 것과 동일하게
맞췄다 — 체크포인트 선택 기준(학습 쪽)과 이 평가(평가 쪽)가 같은 잣대를
쓰지 않으면 "concept-id score가 가장 높은 체크포인트"라는 선택 자체가
이 평가에서 재현되지 않는다.

재료 텍스트를 구조화된 JSON이 아니라 정규식으로 직접 파싱하는 이유: 테스트셋
파일이 갖춰야 할 필드를 {id, prompt, query}만으로 최소화하기 위함이다 (RAG
API 응답의 concepts/tables/joins 필드를 요구하지 않음 — 학습 데이터와 똑같이
"재료" 텍스트 한 덩어리만 있으면 채점 가능).

세 범주:
  - concept-id adherence : 개념 값 조건(앵커)이 생성 SQL에 반영됐는가
                           (presence/usage/correctness, compute_adherence.py와 동일)
  - 쿼리문 하위 전개 반영도 : 그 앵커 조건이 concept_ancestor 서브쿼리로
                           하위 개념까지 확장됐는가 (위와 별개 축 - 값은 맞아도
                           이 형식을 안 쓸 수 있고, 반대로 이 형식을 써도 값이
                           틀릴 수 있다)
  - schema adherence      : 재료에 나열된 테이블/컬럼/조인 범위 안에서만
                           SQL을 작성했는가 (presence/correctness/usage)
"""
from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

_ANCHOR_LINE = re.compile(
    r'"[^"]*"\s*→\s*(?P<table>\w+)\.(?P<column>\w+)\s*'
    r'(?:IN\s*\((?P<in_vals>[^)]*)\)|=\s*(?P<eq_val>[\'"]?[\w.]+[\'"]?))'
)
_TABLE_HEADER_RE = re.compile(r'^\s*#\s*(?P<table>\w+)\(')
_COLUMN_LINE_RE = re.compile(r'^\s*-\s*(?P<column>\w+)\s')
_JOIN_LINE_RE = re.compile(r'^\s*-\s*(?P<left>\w+\.\w+)\s*=\s*(?P<right>\w+\.\w+)')

# 재료의 테이블 목록에는 안 나오지만, 시스템 프롬프트가 앵커 하위 개념 확장용으로
# 항상 쓰라고 지시하는 시스템 테이블 - 재료에 없다는 이유로 "환각"으로 잡으면 안 됨.
_ALWAYS_ALLOWED_TABLES = {"concept_ancestor"}


def split_prompt(prompt: str) -> tuple[str, str]:
    """"[질의]\\n...\\n\\n[재료]\\n..." 형태를 (자연어 질의, 재료 텍스트)로 분리.
    "[재료]" 마커가 없으면 재료 텍스트는 빈 문자열(스키마/concept 검증은 전부
    N/A 처리되고 SQL Validity/EM/EX만 채점됨)."""
    query_part, marker, material_part = prompt.partition("[재료]")
    nl_query = query_part.replace("[질의]", "").strip()
    return nl_query, (material_part.strip() if marker else "")


def build_prompt(case: dict) -> str:
    """automl-llm의 LLaMA Factory 학습 데이터셋과 동일한 물리 필드명
    (dataset_info.json의 nl_sql_train/nl_sql_val 등록 기준 — "text"는 자연어
    질의, "input"은 재료, "query"는 정답 SQL)으로 된 테스트 케이스에서, 모델이
    실제로 받을 프롬프트("[질의]\\n{text}\\n\\n[재료]\\n...")를 조립한다.

    테스트 케이스가 이미 완성된 "prompt" 필드를 들고 있으면(예: RAG API가
    돌려준 그대로를 저장해둔 독립 테스트셋) 그걸 그대로 쓰고 조립하지 않는다
    — "text"+"input"을 합치는 건 어디까지나 학습 데이터 형태 그대로 넘어온
    케이스를 위한 편의 기능이다.

    "input" 필드가 이미 "[재료]"로 시작하면(실제 nl_sql_train.jsonl이 그렇다)
    그대로 뒤에 붙이고, 아니면 "[재료]\\n"를 직접 붙인다 — 어느 쪽으로 와도
    최종 프롬프트 포맷이 같아지게 하기 위함."""
    if case.get("prompt"):
        return case["prompt"]

    text = (case.get("text") or case.get("instruction") or "").strip()
    if not text:
        raise KeyError(
            "테스트 케이스에 'prompt'도 'text'/'instruction'도 없습니다 "
            f"(id={case.get('id')!r}). 테스트셋 스키마를 README 참고해 맞출 것."
        )

    material = (case.get("input") or case.get("materials") or "").strip()
    if not material:
        return f"[질의]\n{text}"
    if not material.startswith("[재료]"):
        material = f"[재료]\n{material}"
    return f"[질의]\n{text}\n\n{material}"


def resolve_gold_query(case: dict) -> str:
    """정답 SQL 필드명도 "query"(학습 데이터셋 물리 필드명) 또는 "output"
    (일반 alpaca 포맷) 둘 다 받아준다."""
    return case.get("query") or case.get("output") or ""


def parse_anchors(material_text: str) -> list[dict[str, Any]]:
    """재료의 "개념 값 조건:" 줄에서 '"용어" → table.column IN (ids)' / '= id'
    형태의 앵커를 모두 뽑는다 (automl-llm/scripts/compute_adherence.py의
    parse_anchors와 동일한 패턴)."""
    anchors = []
    for m in _ANCHOR_LINE.finditer(material_text):
        if m.group("in_vals") is not None:
            values = {v.strip().strip("'\"") for v in m.group("in_vals").split(",")}
        else:
            values = {m.group("eq_val").strip().strip("'\"")}
        anchors.append({
            "table": m.group("table"),
            "column": m.group("column"),
            "values": values,
        })
    return anchors


def parse_schema_section(material_text: str) -> dict[str, set[str]]:
    """재료의 "테이블(컬럼 전체):" 섹션에서 table -> column 집합을 뽑는다."""
    schema: dict[str, set[str]] = {}
    current_table: str | None = None
    in_section = False
    for line in material_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("테이블"):
            in_section = True
            continue
        if stripped.startswith(("조인", "개념 값 조건")):
            in_section = False
            continue
        if not in_section:
            continue
        header = _TABLE_HEADER_RE.match(line)
        if header:
            current_table = header.group("table").lower()
            schema.setdefault(current_table, set())
            continue
        col = _COLUMN_LINE_RE.match(line)
        if col and current_table:
            schema[current_table].add(col.group("column").lower())
    return schema


def parse_joins_section(material_text: str) -> list[tuple[str, str]]:
    """재료의 "조인:" 섹션에서 (table.column, table.column) 쌍을 뽑는다."""
    joins = []
    in_section = False
    for line in material_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("조인"):
            in_section = True
            continue
        if stripped.startswith(("테이블", "개념 값 조건")):
            in_section = False
            continue
        if not in_section:
            continue
        m = _JOIN_LINE_RE.match(line)
        if m:
            joins.append((m.group("left").lower(), m.group("right").lower()))
    return joins


def _extract_slot_spans(sql: str, column: str) -> list[str]:
    """column 뒤에 오는 IN(...)/=... 슬롯의 안쪽 텍스트를 전부 찾는다. OMOP
    쿼리는 'IN (SELECT descendant_concept_id FROM concept_ancestor WHERE
    ancestor_concept_id IN (id))'처럼 IN(...) 안에 서브쿼리가 중첩되는 게
    흔해서, 괄호 깊이를 세어 짝이 맞는 지점까지 수동으로 읽는다."""
    head_pattern = re.compile(rf'(?:\w+\.)?{re.escape(column)}\s*(IN\s*\(|=\s*)', re.IGNORECASE)
    spans = []
    for m in head_pattern.finditer(sql):
        start = m.end()
        if m.group(1).strip().upper().startswith("IN"):
            depth = 1
            i = start
            while i < len(sql) and depth > 0:
                if sql[i] == "(":
                    depth += 1
                elif sql[i] == ")":
                    depth -= 1
                i += 1
            spans.append(sql[start:i - 1])
        else:
            scalar = re.match(r"\s*('?\"?[\w.]+'?\"?)", sql[start:])
            spans.append(scalar.group(1) if scalar else "")
    return spans


def score_anchor(sql: str, anchor: dict[str, Any]) -> dict[str, bool]:
    column = anchor["column"]
    expected = anchor["values"]

    presence = any(re.search(rf'\b{re.escape(v)}\b', sql) for v in expected)

    spans = _extract_slot_spans(sql, column)
    correctness = any(
        all(re.search(rf'\b{re.escape(v)}\b', span) for v in expected) for span in spans
    )
    subexpansion = any("concept_ancestor" in span.lower() for span in spans)

    return {
        "presence": presence,
        "usage": bool(spans),
        "correctness": correctness,
        "subexpansion": subexpansion,
    }


def score_concept_adherence(sql: str, anchors: list[dict[str, Any]]) -> dict[str, Any]:
    """앵커가 없으면(재료에 개념 값 조건이 없는 질의) 전부 None(N/A)."""
    if not anchors:
        return {
            "presence_rate": None, "usage_rate": None, "correctness_rate": None,
            "score": None, "subexpansion_rate": None, "detail": "재료에 개념 값 조건 없음",
        }

    scored = [score_anchor(sql, a) for a in anchors]
    n = len(scored)
    presence_rate = sum(s["presence"] for s in scored) / n
    usage_rate = sum(s["usage"] for s in scored) / n
    correctness_rate = sum(s["correctness"] for s in scored) / n
    subexpansion_rate = sum(s["subexpansion"] for s in scored) / n
    score = sum((s["presence"] + s["usage"] + s["correctness"]) / 3 for s in scored) / n

    missing = [a["column"] for a, s in zip(anchors, scored) if not s["presence"]]
    detail = f"앵커 {n}개" + (f" | 미반영: {', '.join(missing)}" if missing else "")

    return {
        "presence_rate": presence_rate, "usage_rate": usage_rate,
        "correctness_rate": correctness_rate, "score": score,
        "subexpansion_rate": subexpansion_rate, "detail": detail,
    }


def _resolve_join_tables(sql_join: exp.Join, alias_to_table: dict[str, str]) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    on = sql_join.args.get("on")
    if on is None:
        return pairs
    for eq in on.find_all(exp.EQ):
        left, right = eq.this, eq.expression
        if isinstance(left, exp.Column) and isinstance(right, exp.Column):
            lt = alias_to_table.get((left.table or "").lower())
            rt = alias_to_table.get((right.table or "").lower())
            if lt and rt:
                pairs.add(frozenset({f"{lt}.{left.name.lower()}", f"{rt}.{right.name.lower()}"}))
    return pairs


def score_schema_adherence(
    sql: str, schema: dict[str, set[str]], joins: list[tuple[str, str]]
) -> dict[str, Any]:
    """재료가 나열한 테이블/컬럼/조인 범위 안에서만 SQL을 썼는지 채점한다.

    - presence   : 재료가 준 테이블을 하나라도 실제로 썼는가 (완전히 무시하고
                   엉뚱한 테이블만 쓴 경우를 잡는다)
    - correctness: 참조한 모든 테이블/컬럼이 재료 범위 안에 있는가 (재료 밖
                   테이블/컬럼 참조 = 설령 DB에 실재해도 이 질의에는 "환각")
    - usage      : 재료가 준 테이블을 2개 이상 join했다면, 그 join이 재료의
                   조인 목록과 일치하는가 (테이블이 1개뿐이거나 재료에 조인
                   정보가 없으면 평가 대상이 아니라 None)
    """
    if not schema:
        return {
            "presence": None, "correctness": None, "usage": None,
            "detail": "재료에 테이블 정보 없음",
        }

    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as exc:  # noqa: BLE001 - sqlglot 예외를 그대로 사유로 기록
        return {"presence": False, "correctness": False, "usage": None, "detail": f"구문 오류로 확인 불가: {exc}"}
    if parsed is None:
        return {"presence": False, "correctness": False, "usage": None, "detail": "빈 SQL"}

    cte_names = {cte.alias_or_name.lower() for cte in parsed.find_all(exp.CTE)}
    alias_to_table: dict[str, str] = {}
    real_tables: list[str] = []
    for t in parsed.find_all(exp.Table):
        name = t.name.lower()
        if name in cte_names:
            continue
        real_tables.append(name)
        alias_to_table[t.alias_or_name.lower()] = name

    if not real_tables:
        return {"presence": False, "correctness": False, "usage": None, "detail": "참조된 실제 테이블 없음"}

    presence = any(t in schema for t in real_tables)

    unknown_tables = sorted({t for t in real_tables if t not in schema and t not in _ALWAYS_ALLOWED_TABLES})
    sole_table = real_tables[0] if len(set(real_tables)) == 1 else None
    unknown_columns: list[str] = []
    for c in parsed.find_all(exp.Column):
        col_name = c.name.lower()
        qualifier = c.table.lower() if c.table else None
        if qualifier:
            resolved = alias_to_table.get(qualifier)
            if resolved is None:
                continue  # CTE/서브쿼리 별칭 - 스키마 매칭 대상 아님
        elif sole_table:
            resolved = sole_table
        else:
            continue  # 테이블 여러 개인데 별칭 없음 - 판별 불가, 스킵
        if resolved not in schema:
            continue  # 이미 unknown_tables에 잡힘
        if col_name not in schema[resolved]:
            unknown_columns.append(f"{resolved}.{col_name}")
    unknown_columns = sorted(set(unknown_columns))

    correctness = not unknown_tables and not unknown_columns

    used_tables = set(real_tables) & set(schema)
    if len(used_tables) < 2:
        usage = None
        usage_detail = "테이블 1개 이하 참조 - 조인 평가 대상 아님"
    elif not joins:
        usage = None
        usage_detail = "재료에 조인 정보 없음"
    else:
        used_pairs: set[frozenset[str]] = set()
        for j in parsed.find_all(exp.Join):
            used_pairs |= _resolve_join_tables(j, alias_to_table)
        expected_pairs = {frozenset({a, b}) for a, b in joins}
        matched = used_pairs & expected_pairs
        usage = bool(matched) if used_pairs else False
        extra = used_pairs - expected_pairs
        usage_detail = f"일치 조인 {len(matched)}개" + (f", 재료에 없는 조인 {len(extra)}개" if extra else "")

    detail_parts = []
    if unknown_tables:
        detail_parts.append(f"재료에 없는 테이블: {', '.join(unknown_tables)}")
    if unknown_columns:
        detail_parts.append(f"재료에 없는 컬럼: {', '.join(unknown_columns)}")
    if not detail_parts:
        detail_parts.append("재료 범위 내 테이블/컬럼만 사용")
    detail_parts.append(f"조인: {usage_detail}")

    return {"presence": presence, "correctness": correctness, "usage": usage, "detail": " | ".join(detail_parts)}
