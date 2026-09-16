"""RAG API가 실시간으로 만들어준 프롬프트(개념명 -> concept_id 매핑, 관련
테이블/컬럼 스키마, 조인 관계가 이미 합쳐진 프롬프트)를 파인튜닝 모델에 직접
넣어서 테스트한다.

``eval_api_model.py``는 모델에 "자연어 질문"만 던지고, 모델이 IN절 자리에
``{{개념명}}`` 플레이스홀더를 남기는 것까지가 정상 동작이었다 (그 뒤 RAG가
문자열 치환으로 concept_id를 채워넣는 파이프라인을 전제로 함). 이 스크립트는
다른 파이프라인을 테스트한다: 자연어 질문을 RAG API(``RAG_API_URL``)에 먼저
보내 concept_id 매핑 + 관련 스키마가 합쳐진 프롬프트를 받고, 그 프롬프트를
그대로 모델에 넣어 "완성된"(실제 concept_id가 채워진) SQL을 한 번에 받아보는
실험이다.

RAG API 계약: ``POST {RAG_API_URL}`` body ``{"text": "<자연어 질의>"}`` ->
``{"text", "concepts", "tables", "joins", "prompt"}`` JSON. "prompt" 필드를
그대로 LLM의 user 메시지로 쓴다 (직접 호출해 구조 확인 완료).

정답 SQL을 알 수 없는 전제의 테스트이므로 EM/EX(정답과의 비교)는 하지 않는다.
대신 실제로 실행해서 오류 없이 결과가 나오는지(EX 컬럼 = 실행 성공 여부, 정답과의
일치가 아니라 "실행 가능한가")만 본다.

설정은 모두 ``.env``에서 읽는다 (``.env.example`` 참고, 없으면 ``cp .env.example .env``):
  LLM_API_URL, LLM_MODEL_NAME       — 파인튜닝 모델 추론 API
  RAG_API_URL                       — RAG 프롬프트 조립 API
  RAG_LLM_SYSTEM_PROMPT             — 위 RAG 프롬프트를 넣을 때 쓸 시스템 프롬프트
  SANDBOX_DB_*                      — 샌드박스 PostgreSQL (미설정 시 실행검증/EX 건너뜀)

사용법:
  python scripts/eval_api_model_rag.py --output eval_results_rag.csv

  # 앞부분만 빠르게 스모크 테스트
  python scripts/eval_api_model_rag.py --limit 5 --output smoke.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path

import psycopg
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_api_model as base  # noqa: E402 - .env 로딩 + 기존 체크 로직/유틸 재사용

RAG_API_URL = os.environ.get("RAG_API_URL", "http://10.1.1.106:8080/materials")
SYSTEM_PROMPT_RAG = os.environ.get(
    "RAG_LLM_SYSTEM_PROMPT",
    "당신은 OMOP CDM 기반 Text-to-SQL 전문가입니다. [질의]는 사용자의 자연어 질문이고, "
    "[재료]에는 질의에 필요한 개념(concept) ID 매핑, 사용 가능한 테이블/컬럼 스키마, "
    "테이블 간 조인 관계가 이미 정리되어 있습니다.\n\n"
    "다음을 반드시 지키세요:\n"
    "1. [재료]에 주어진 개념 값 조건의 concept_id 목록을 SQL의 IN (...) 절에 그대로 사용하세요 "
    "(개념명을 텍스트나 {{}} 플레이스홀더로 남기지 마세요).\n"
    "2. [재료]에 나열된 테이블/컬럼만 사용하세요. 나열되지 않은 테이블/컬럼을 추측해서 만들지 마세요.\n"
    "3. [재료]의 조인 관계를 그대로 사용하세요.\n"
    "4. 다른 설명 없이 SQL 쿼리 하나만 답하세요.",
)

RESULT_FIELDNAMES = [
    "자연어 질의",
    "모델 답변 쿼리문",
    "SQL문법 결과",
    "SQL문법 에러 사유",
    "omop-cdm 스키마 오류 여부",
    "omop-cdm 스키마 에러 사유",
    "샌드박스 DB 실행검증 결과",
    "샌드박스 DB 실행검증 에러 사유",
    "EX 결과",
    "응답 속도",
    "비고",
]


def collect_texts(dataset_path: str, custom_path: str, skip_dataset: bool, skip_custom: bool) -> list[str]:
    texts: list[str] = []
    if not skip_dataset:
        texts += [c["text"] for c in base.select_scenario_cases(dataset_path)]
    if not skip_custom:
        texts += [c["text"] for c in base.load_custom_cases(custom_path)]
    return texts


def call_rag(text: str, rag_api_url: str, timeout: float) -> tuple[dict | None, str | None]:
    try:
        resp = requests.post(rag_api_url, json={"text": text}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if "prompt" not in data:
            return None, f"RAG 응답에 prompt 필드 없음: {data}"
        return data, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def check_actual_execution(conn: psycopg.Connection | None, sql: str) -> tuple[str, str]:
    """EXPLAIN(계획만)이 아니라 실제로 SQL을 실행해서 오류 없이 끝나는지 확인.
    정답이 없으니 결과 일치가 아니라 '실행 가능한가'만 본다."""
    if conn is None:
        return "skip", ""
    substituted = base.PLACEHOLDER_RE.sub("0", sql).strip().rstrip(";").strip()
    if not substituted:
        return "fail", "빈 SQL"
    try:
        rows = conn.execute(substituted).fetchall()
        return "pass", f"{len(rows)}행 반환"
    except psycopg.Error as exc:
        return "fail", str(exc).strip()


def evaluate_case(
    text: str,
    rag_api_url: str,
    llm_api_url: str,
    model: str,
    system_prompt: str,
    timeout: float,
    max_tokens: int,
    schema: dict[str, set[str]],
    sandbox_conn: psycopg.Connection | None,
) -> dict:
    rag_start = time.perf_counter()
    rag_item, rag_error = call_rag(text, rag_api_url, timeout)
    rag_elapsed = time.perf_counter() - rag_start

    if rag_error is not None:
        return {
            "자연어 질의": text,
            "모델 답변 쿼리문": "",
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "",
            "샌드박스 DB 실행검증 결과": "skip",
            "샌드박스 DB 실행검증 에러 사유": "",
            "EX 결과": "skip",
            "응답 속도": f"{rag_elapsed:.2f}",
            "비고": f"RAG API 호출 실패: {rag_error}",
        }

    rag_prompt = rag_item["prompt"]
    raw_response, llm_elapsed, api_error = base.call_model(
        rag_prompt, llm_api_url, model, timeout, max_tokens, system_prompt=system_prompt
    )
    total_elapsed = rag_elapsed + llm_elapsed

    if api_error is not None:
        return {
            "자연어 질의": text,
            "모델 답변 쿼리문": "",
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "",
            "샌드박스 DB 실행검증 결과": "skip",
            "샌드박스 DB 실행검증 에러 사유": "",
            "EX 결과": "skip",
            "응답 속도": f"{total_elapsed:.2f}",
            "비고": f"LLM API 호출 실패: {api_error}",
        }

    sql, is_sql_format = base.extract_sql(raw_response)

    if not is_sql_format:
        return {
            "자연어 질의": text,
            "모델 답변 쿼리문": raw_response.strip(),
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "샌드박스 DB 실행검증 결과": "fail" if sandbox_conn is not None else "skip",
            "샌드박스 DB 실행검증 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)" if sandbox_conn is not None else "",
            "EX 결과": "fail" if sandbox_conn is not None else "skip",
            "응답 속도": f"{total_elapsed:.2f}",
            "비고": "SQL이 아닌 자연어로 응답 (Format 이탈)",
        }

    syntax_ok, syntax_reason = base.check_syntax(sql)
    if syntax_ok:
        schema_ok, schema_reason = base.check_schema(sql, schema)
    else:
        schema_ok, schema_reason = False, "구문 오류로 스키마 검증 불가"

    sandbox_result, sandbox_reason = base.check_sandbox_validity(sandbox_conn, sql)
    ex_result, ex_note = check_actual_execution(sandbox_conn, sql)

    note_parts = []
    if base.PLACEHOLDER_RE.search(sql):
        note_parts.append("⚠ {{}} 플레이스홀더 잔존 (RAG concept_id를 무시하고 예전처럼 답함)")
    if rag_item.get("concepts"):
        concept_names = ", ".join(c["surface"] for c in rag_item["concepts"])
        note_parts.append(f"RAG 인식 개념: {concept_names}")
    if ex_result == "fail" and ex_note:
        note_parts.append(f"EX 실패 사유: {ex_note}")
    elif ex_result == "pass" and ex_note:
        note_parts.append(ex_note)

    return {
        "자연어 질의": text,
        "모델 답변 쿼리문": sql,
        "SQL문법 결과": "pass" if syntax_ok else "fail",
        "SQL문법 에러 사유": "" if syntax_ok else syntax_reason,
        "omop-cdm 스키마 오류 여부": "pass" if schema_ok else "fail",
        "omop-cdm 스키마 에러 사유": "" if schema_ok else schema_reason,
        "샌드박스 DB 실행검증 결과": sandbox_result,
        "샌드박스 DB 실행검증 에러 사유": sandbox_reason,
        "EX 결과": ex_result,
        "응답 속도": f"{total_elapsed:.2f}",
        "비고": " | ".join(note_parts),
    }


def print_summary(rows: list[dict]) -> None:
    n = len(rows)
    if n == 0:
        print("평가할 케이스가 없습니다.")
        return

    syntax_pass = sum(1 for r in rows if r["SQL문법 결과"] == "pass")
    schema_pass = sum(1 for r in rows if r["omop-cdm 스키마 오류 여부"] == "pass")
    placeholder_left = sum(1 for r in rows if "플레이스홀더 잔존" in r["비고"])
    speeds = [float(r["응답 속도"]) for r in rows]

    print(f"\n총 {n}건 평가 (RAG 프롬프트 실시간 조립 -> LLM 입력)")
    print(f"  Syntactic Validity    : {syntax_pass}/{n} ({syntax_pass / n:.1%})")
    print(f"  스키마 참조 정확도     : {schema_pass}/{n} ({schema_pass / n:.1%})")
    print(f"  {{}} 플레이스홀더 잔존   : {placeholder_left}/{n} ({placeholder_left / n:.1%})")
    print(f"  응답 속도(평균/최대)   : {sum(speeds) / n:.2f}s / {max(speeds):.2f}s  (RAG 호출 + LLM 호출 합산)")

    sandbox_checked = [r for r in rows if r["샌드박스 DB 실행검증 결과"] in ("pass", "fail")]
    if sandbox_checked:
        sb_pass = sum(1 for r in sandbox_checked if r["샌드박스 DB 실행검증 결과"] == "pass")
        m = len(sandbox_checked)
        print(f"  샌드박스 DB 실행검증   : {sb_pass}/{m} ({sb_pass / m:.1%})")
    else:
        print("  샌드박스 DB 실행검증   : SANDBOX_DB_HOST 미설정으로 건너뜀")

    ex_checked = [r for r in rows if r["EX 결과"] in ("pass", "fail")]
    if ex_checked:
        ex_pass = sum(1 for r in ex_checked if r["EX 결과"] == "pass")
        m = len(ex_checked)
        print(f"  EX (실제 실행 성공률)  : {ex_pass}/{m} ({ex_pass / m:.1%}) — 정답과의 일치가 아니라 오류 없이 실행됐는지")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG API가 조립한 프롬프트를 파인튜닝 모델에 실시간으로 넣어 테스트")
    parser.add_argument("--rag-api-url", default=RAG_API_URL)
    parser.add_argument("--llm-api-url", default=base.API_URL)
    parser.add_argument("--model", default=base.MODEL_NAME)
    parser.add_argument("--system-prompt", default=SYSTEM_PROMPT_RAG)
    parser.add_argument("--dataset", default=base.DATASET_PATH)
    parser.add_argument("--custom-queries", default=base.CUSTOM_QUERIES_PATH)
    parser.add_argument("--ddl", default=base.DDL_PATH)
    parser.add_argument("--output", default="eval_results_rag.csv")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--limit", type=int, default=None, help="앞 N건만 실행 (스모크 테스트용)")
    parser.add_argument("--skip-dataset", action="store_true")
    parser.add_argument("--skip-custom", action="store_true")
    args = parser.parse_args()

    schema = base.load_schema(args.ddl)
    print(f"OMOP CDM 스키마 로드: 테이블 {len(schema)}개 ({args.ddl})")

    sandbox_conn = base.get_sandbox_connection()
    if sandbox_conn is not None:
        print("샌드박스 DB 연결 성공 — 실행검증/EX도 함께 실행합니다.")
    else:
        print("SANDBOX_DB_HOST 미설정 — 실행검증/EX는 건너뜁니다 (정적 분석만 실행).")

    texts = collect_texts(args.dataset, args.custom_queries, args.skip_dataset, args.skip_custom)
    if args.limit:
        texts = texts[: args.limit]

    print(f"RAG API: {args.rag_api_url}")
    print(f"평가 케이스 {len(texts)}건 (자연어 질의 -> RAG 프롬프트 조립 -> LLM 호출)\n")

    # 문항 수가 많고(RAG+LLM 호출 합산이라 문항당 수 초~십수 초) 이 프로세스와
    # 무관한 이유(시스템 메모리 부족 등)로 중간에 죽는 경우에도 그때까지의
    # 결과는 남도록, 끝에 한 번에 쓰지 않고 문항마다 바로 파일에 쓰고 flush한다.
    rows = []
    out_f = open(args.output, "w", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(out_f, fieldnames=RESULT_FIELDNAMES)
    writer.writeheader()
    try:
        for i, text in enumerate(texts, 1):
            row = evaluate_case(
                text, args.rag_api_url, args.llm_api_url, args.model, args.system_prompt,
                args.timeout, args.max_tokens, schema, sandbox_conn,
            )
            rows.append(row)
            writer.writerow(row)
            out_f.flush()
            preview = text[:30]
            print(
                f"[{i}/{len(texts)}] {preview}: 문법={row['SQL문법 결과']} 스키마={row['omop-cdm 스키마 오류 여부']} "
                f"샌드박스={row['샌드박스 DB 실행검증 결과']} EX={row['EX 결과']} ({row['응답 속도']}s)"
            )
    finally:
        out_f.close()
        if sandbox_conn is not None:
            sandbox_conn.close()

    print(f"\n결과 저장: {args.output}")

    print_summary(rows)


if __name__ == "__main__":
    main()
