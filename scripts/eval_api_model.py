"""HTTP 추론 API로 서빙 중인 파인튜닝 모델의 4개 지표를 자동 측정한다:

  1. Syntactic Validity — 모델 응답이 문법적으로 유효한 SQL인가 (sqlglot 파싱 기준)
  2. Format 이탈율      — SQL이 아닌 자연어로 응답한 비율
  3. 참조 테이블/컬럼 정확도 — OMOP CDM v5.3 표준 스키마에 없는 테이블/컬럼을 참조하는지 (환각 여부)
  4. 응답 속도          — API 호출 1건당 걸린 시간

이 harness(``eval_harness/``)의 Validity/EX는 샌드박스 PostgreSQL DB에 실제로
접속해 ``EXPLAIN``/실행까지 해보는 방식이지만, 이 스크립트는 파인튜닝 모델
자체의 SQL 생성 품질(문법·스키마 환각·응답 속도)만 빠르게 점검하는 용도라
DB 접속 없이 ``sqlglot`` 정적 분석만으로 검사한다. 실행 결과까지 확인하려면
predictions.jsonl로 변환해 ``eval_harness.score``를 함께 돌릴 것.

모델은 IN절에 들어갈 concept_id 리스트 자리에 ``{{암로디핀}}`` 같은 자연어
플레이스홀더를 그대로 남기도록 의도적으로 학습되었다 (RAG가 나중에 실제
concept_id로 치환). 이 플레이스홀더는 그 자체로는 유효한 SQL 토큰이 아니므로,
문법/스키마 검사 전에 더미 리터럴 ``0``으로 치환한 뒤 검사한다.

사용법:
  python scripts/eval_api_model.py \\
      --dataset data/260914/auto_confirmed_val_260914.jsonl \\
      --custom-queries data/custom_eval_queries.jsonl \\
      --output eval_results.csv

  # 앞부분만 빠르게 스모크 테스트
  python scripts/eval_api_model.py --limit 5 --output smoke.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

import requests
import sqlglot
from sqlglot import exp

API_URL = "http://10.1.1.69:8003/v1/chat/completions"
MODEL_NAME = "xiyan-sql-14b-sft-260914"
SYSTEM_PROMPT = (
    "You are a Text-to-SQL expert. Convert the following natural language "
    "query into a SQL statement based on the schema."
)
DDL_PATH = "data/fixtures/omop_cdm_v53_ddl.sql"
DATASET_PATH = "data/260914/auto_confirmed_val_260914.jsonl"
CUSTOM_QUERIES_PATH = "data/custom_eval_queries.jsonl"
OUTPUT_PATH = "eval_results.csv"

CODE_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}")
SQL_START_RE = re.compile(r"^\s*(SELECT|WITH|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)

CSV_FIELDNAMES = [
    "자연어 질의",
    "모델 답변 쿼리문",
    "정답 쿼리문",
    "SQL문법 결과",
    "SQL문법 에러 사유",
    "omop-cdm 스키마 오류 여부",
    "omop-cdm 스키마 에러 사유",
    "응답 속도",
    "비고",
]


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_schema(ddl_path: str) -> dict[str, set[str]]:
    """DDL의 CREATE TABLE 문에서 테이블명 -> 컬럼명 집합을 뽑는다 (모두 소문자)."""
    ddl = Path(ddl_path).read_text(encoding="utf-8")
    schema: dict[str, set[str]] = {}
    for stmt in sqlglot.parse(ddl, read="postgres"):
        if not isinstance(stmt, exp.Create):
            continue
        table_schema = stmt.this
        table_name = table_schema.this.name.lower()
        columns = {
            col.this.name.lower()
            for col in table_schema.expressions
            if isinstance(col, exp.ColumnDef)
        }
        schema[table_name] = columns
    return schema


def select_scenario_cases(dataset_path: str) -> list[dict]:
    """시나리오당 증강된 paraphrase(수백 개)는 건너뛰고, 시나리오별 고유 질의
    (is_original=True — 1012건 중 68건)만 뽑는다. 같은 시나리오 안에서도
    포함기준/노출군/비교군/결과/추적기간 등 항목(item)마다 SQL이 다르므로
    시나리오명 하나당 1건이 아니라, 시나리오 안의 고유 질의 전부를 포함한다."""
    rows = [r for r in load_jsonl(dataset_path) if r.get("is_original")]
    cases = []
    for r in rows:
        cases.append({
            "id": r["id"],
            "text": r["text"],
            "gold_query": r.get("query", ""),
            "note": f"[데이터셋] 시나리오: {r['scenario_name']} | 항목: {r['item']} | 유형: {r['query_type']} | 난이도: {r['difficulty']}",
        })
    return cases


def load_custom_cases(path: str) -> list[dict]:
    rows = load_jsonl(path)
    cases = []
    for r in rows:
        note = r.get("note", "")
        cases.append({
            "id": r["id"],
            "text": r["text"],
            "gold_query": r.get("query", ""),
            "note": f"[신규 작성 질의] {note}" if note else "[신규 작성 질의]",
        })
    return cases


def call_model(text: str, api_url: str, model: str, timeout: float, max_tokens: int) -> tuple[str | None, float, str | None]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    start = time.perf_counter()
    try:
        resp = requests.post(api_url, json=payload, timeout=timeout)
        elapsed = time.perf_counter() - start
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content, elapsed, None
    except Exception as exc:  # noqa: BLE001 - API 오류는 결과 행에 그대로 기록
        elapsed = time.perf_counter() - start
        return None, elapsed, str(exc)


def extract_sql(raw_response: str) -> tuple[str, bool]:
    """모델 응답에서 SQL을 뽑아내고, SQL 형식으로 답했는지 여부를 함께 반환한다."""
    text = raw_response.strip()
    fenced = CODE_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    text = re.sub(r"^(sql|answer)\s*[:\-]\s*", "", text, flags=re.IGNORECASE).strip()
    is_sql_format = bool(SQL_START_RE.match(text))
    return text, is_sql_format


def check_syntax(sql: str) -> tuple[bool, str]:
    substituted = PLACEHOLDER_RE.sub("0", sql)
    try:
        parsed = sqlglot.parse_one(substituted, read="postgres", error_level=sqlglot.ErrorLevel.RAISE)
        if parsed is None:
            return False, "빈 SQL"
        return True, ""
    except Exception as exc:  # noqa: BLE001 - sqlglot 예외를 그대로 사유로 기록
        return False, str(exc)


def check_schema(sql: str, schema: dict[str, set[str]]) -> tuple[bool, str]:
    substituted = PLACEHOLDER_RE.sub("0", sql)
    try:
        parsed = sqlglot.parse_one(substituted, read="postgres")
    except Exception:
        return False, "구문 오류로 스키마 검증 불가"

    cte_names = {cte.alias_or_name.lower() for cte in parsed.find_all(exp.CTE)}

    errors: list[str] = []
    alias_to_table: dict[str, str] = {}
    real_table_names: list[str] = []
    for t in parsed.find_all(exp.Table):
        name = t.name.lower()
        if name in cte_names:
            continue  # CTE 참조 - 실제 테이블 아님
        real_table_names.append(name)
        if name not in schema:
            errors.append(f"알 수 없는 테이블: {t.name}")
        alias_to_table[t.alias_or_name.lower()] = name

    sole_table = real_table_names[0] if len(set(real_table_names)) == 1 else None

    reported_cols: set[tuple[str, str]] = set()
    for c in parsed.find_all(exp.Column):
        col_name = c.name.lower()
        qualifier = c.table.lower() if c.table else None
        if qualifier:
            resolved_table = alias_to_table.get(qualifier)
            if resolved_table is None:
                continue  # CTE/서브쿼리 별칭 등 - 스키마 매칭 대상 아님
        elif sole_table:
            resolved_table = sole_table
        else:
            continue  # 테이블이 여러 개인데 별칭이 없어 어느 테이블인지 판별 불가 - 스킵

        if resolved_table not in schema:
            continue  # 이미 "알 수 없는 테이블"로 보고됨
        key = (resolved_table, col_name)
        if col_name not in schema[resolved_table] and key not in reported_cols:
            reported_cols.add(key)
            errors.append(f"{resolved_table}.{col_name} 컬럼 없음")

    return len(errors) == 0, "; ".join(errors)


def evaluate_case(case: dict, schema: dict[str, set[str]], api_url: str, model: str, timeout: float, max_tokens: int) -> dict:
    raw_response, elapsed, api_error = call_model(case["text"], api_url, model, timeout, max_tokens)

    if api_error is not None:
        return {
            "자연어 질의": case["text"],
            "모델 답변 쿼리문": "",
            "정답 쿼리문": case["gold_query"],
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "",
            "응답 속도": f"{elapsed:.2f}",
            "비고": f"{case['note']} | API 호출 실패: {api_error}",
        }

    sql, is_sql_format = extract_sql(raw_response)

    if not is_sql_format:
        return {
            "자연어 질의": case["text"],
            "모델 답변 쿼리문": raw_response.strip(),
            "정답 쿼리문": case["gold_query"],
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "응답 속도": f"{elapsed:.2f}",
            "비고": case["note"],
        }

    syntax_ok, syntax_reason = check_syntax(sql)
    if syntax_ok:
        schema_ok, schema_reason = check_schema(sql, schema)
    else:
        schema_ok, schema_reason = False, "구문 오류로 스키마 검증 불가"

    note = case["note"]
    if PLACEHOLDER_RE.search(sql):
        note += " | {{}} 플레이스홀더 포함 (검사 시 0으로 치환)"

    return {
        "자연어 질의": case["text"],
        "모델 답변 쿼리문": sql,
        "정답 쿼리문": case["gold_query"],
        "SQL문법 결과": "pass" if syntax_ok else "fail",
        "SQL문법 에러 사유": "" if syntax_ok else syntax_reason,
        "omop-cdm 스키마 오류 여부": "pass" if schema_ok else "fail",
        "omop-cdm 스키마 에러 사유": "" if schema_ok else schema_reason,
        "응답 속도": f"{elapsed:.2f}",
        "비고": note,
    }


def print_summary(rows: list[dict]) -> None:
    n = len(rows)
    if n == 0:
        print("평가할 케이스가 없습니다.")
        return

    format_fail = sum(1 for r in rows if "Format 이탈" in r["SQL문법 에러 사유"])
    syntax_pass = sum(1 for r in rows if r["SQL문법 결과"] == "pass")
    schema_pass = sum(1 for r in rows if r["omop-cdm 스키마 오류 여부"] == "pass")
    speeds = [float(r["응답 속도"]) for r in rows]

    print(f"\n총 {n}건 평가")
    print(f"  Syntactic Validity : {syntax_pass}/{n} ({syntax_pass / n:.1%})")
    print(f"  Format 이탈율       : {format_fail}/{n} ({format_fail / n:.1%})")
    print(f"  스키마 참조 정확도  : {schema_pass}/{n} ({schema_pass / n:.1%})")
    print(f"  응답 속도(평균/최대) : {sum(speeds) / n:.2f}s / {max(speeds):.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="파인튜닝 Text-to-SQL 모델 API 성능 자동 평가")
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--dataset", default=DATASET_PATH, help="시나리오 원본 검증셋 (is_original 항목만 사용)")
    parser.add_argument("--custom-queries", default=CUSTOM_QUERIES_PATH)
    parser.add_argument("--ddl", default=DDL_PATH)
    parser.add_argument("--output", default=OUTPUT_PATH)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--max-tokens", type=int, default=256,
        help="응답 max_tokens. HARD 난이도 등 긴 쿼리가 잘려서 SQL문법 fail로 잡히면 512 이상으로 올릴 것",
    )
    parser.add_argument("--limit", type=int, default=None, help="앞 N건만 실행 (스모크 테스트용)")
    parser.add_argument("--skip-dataset", action="store_true", help="데이터셋 시나리오 없이 --custom-queries만 실행")
    parser.add_argument("--skip-custom", action="store_true", help="신규 작성 질의 없이 데이터셋만 실행")
    args = parser.parse_args()

    schema = load_schema(args.ddl)
    print(f"OMOP CDM 스키마 로드: 테이블 {len(schema)}개 ({args.ddl})")

    cases: list[dict] = []
    if not args.skip_dataset:
        cases += select_scenario_cases(args.dataset)
    if not args.skip_custom:
        cases += load_custom_cases(args.custom_queries)
    if args.limit:
        cases = cases[: args.limit]

    print(f"평가 케이스 {len(cases)}건 (데이터셋 시나리오 원본 + 신규 작성 질의)\n")

    rows = []
    for i, case in enumerate(cases, 1):
        row = evaluate_case(case, schema, args.api_url, args.model, args.timeout, args.max_tokens)
        rows.append(row)
        print(f"[{i}/{len(cases)}] {case['id']}: 문법={row['SQL문법 결과']} 스키마={row['omop-cdm 스키마 오류 여부']} ({row['응답 속도']}s)")

    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n결과 저장: {args.output}")

    print_summary(rows)


if __name__ == "__main__":
    main()
