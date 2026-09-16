"""RAG가 만들어준 프롬프트(개념명 -> concept_id 매핑, 관련 테이블/컬럼 스키마, 조인
관계가 이미 합쳐진 프롬프트)를 파인튜닝 모델에 직접 넣어서 테스트한다.

``eval_api_model.py``는 모델에 "자연어 질문"만 던지고, 모델이 IN절 자리에
``{{개념명}}`` 플레이스홀더를 남기는 것까지가 정상 동작이었다 (그 뒤 RAG가
문자열 치환으로 concept_id를 채워넣는 파이프라인을 전제로 함). 이 스크립트는
다른 파이프라인을 테스트한다: RAG API가 미리 개념명 -> concept_id 매핑과
관련 스키마를 계산해 하나의 프롬프트로 합쳐주면, 그 프롬프트를 그대로 모델에
넣어 "완성된"(실제 concept_id가 채워진) SQL을 한 번에 받아보는 실험이다.

RAG는 아직 완성 단계는 아니지만 API로 나온다는 전제 하에, 이 스크립트는 RAG
서버를 직접 호출하지 않는다 (엔드포인트/요청 스펙이 아직 정해지지 않았으므로).
대신 RAG 출력들을 모아둔 JSONL 파일을 입력으로 받는다 — 각 줄은 최소한
"text"(원본 자연어 질문)와 "prompt"(모델에 그대로 넣을 최종 프롬프트) 필드를
가져야 한다:

  {"text": "당뇨 환자의 사망일", "prompt": "[질의]\\n...\\n[재료]\\n...", "concepts": [...], ...}

(예시 1건이 data/rag_outputs_sample.jsonl에 있음 — 실제 RAG API를 이 형태로
호출해 여러 줄을 모은 파일을 --rag-outputs로 넘기면 됨. 기존 88건과 동일한
자연어로 비교하려면 auto_confirmed_val_260914.jsonl/custom_eval_queries.jsonl의
"text"를 그대로 RAG에 넣어서 만들면 된다.)

RAG 출력의 "text"가 기존 88건(데이터셋 원본 68 + custom_eval_queries.jsonl 20)의
질의와 일치하면 그 문항의 정답 SQL을 같이 채점하고(EM/EX), 없으면 정답 없이
(포맷/스키마/실행검증만) 채점한다.

이 모드에서는 모델이 실제 concept_id를 받았으므로 ``{{}}`` 플레이스홀더가 더 이상
정상이 아니다 — 여전히 플레이스홀더가 남아있으면 "RAG 컨텍스트를 무시함"이라는
뜻이므로 별도 컬럼(플레이스홀더 잔존 여부)으로 표시한다.

사용법:
  export SANDBOX_DB_HOST=10.10.30.32   # (선택) 설정하면 실행검증/EM/EX도 실행
  ...

  python scripts/eval_api_model_rag.py \\
      --rag-outputs data/rag_outputs_sample.jsonl \\
      --output eval_results_rag.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_api_model as base  # noqa: E402 - 기존 체크 로직/유틸 재사용

SYSTEM_PROMPT_RAG = (
    "당신은 OMOP CDM 기반 Text-to-SQL 전문가입니다. [질의]는 사용자의 자연어 질문이고, "
    "[재료]에는 질의에 필요한 개념(concept) ID 매핑, 사용 가능한 테이블/컬럼 스키마, "
    "테이블 간 조인 관계가 이미 정리되어 있습니다.\n\n"
    "다음을 반드시 지키세요:\n"
    "1. [재료]에 주어진 개념 값 조건의 concept_id 목록을 SQL의 IN (...) 절에 그대로 사용하세요 "
    "(개념명을 텍스트나 {{}} 플레이스홀더로 남기지 마세요).\n"
    "2. [재료]에 나열된 테이블/컬럼만 사용하세요. 나열되지 않은 테이블/컬럼을 추측해서 만들지 마세요.\n"
    "3. [재료]의 조인 관계를 그대로 사용하세요.\n"
    "4. 다른 설명 없이 SQL 쿼리 하나만 답하세요."
)

RESULT_FIELDNAMES = [
    "자연어 질의",
    "RAG 프롬프트",
    "모델 답변 쿼리문",
    "정답 쿼리문",
    "SQL문법 결과",
    "SQL문법 에러 사유",
    "omop-cdm 스키마 오류 여부",
    "omop-cdm 스키마 에러 사유",
    "플레이스홀더 잔존 여부",
    "샌드박스 DB 실행검증 결과",
    "샌드박스 DB 실행검증 에러 사유",
    "EM 결과",
    "EX 결과",
    "EX 참고사항",
    "응답 속도",
    "비고",
]


def load_gold_lookup() -> dict[str, str]:
    """기존 88건(데이터셋 원본 68 + custom 20)의 text -> 정답 SQL 매핑."""
    lookup: dict[str, str] = {}
    for c in base.select_scenario_cases(base.DATASET_PATH):
        lookup[c["text"]] = c["gold_query"]
    for c in base.load_custom_cases(base.CUSTOM_QUERIES_PATH):
        if c["gold_query"]:
            lookup[c["text"]] = c["gold_query"]
    return lookup


def evaluate_rag_case(
    item: dict,
    gold_query: str,
    schema: dict[str, set[str]],
    api_url: str,
    model: str,
    timeout: float,
    max_tokens: int,
    sandbox_conn,
) -> dict:
    text = item["text"]
    rag_prompt = item["prompt"]

    raw_response, elapsed, api_error = base.call_model(
        rag_prompt, api_url, model, timeout, max_tokens, system_prompt=SYSTEM_PROMPT_RAG
    )

    if api_error is not None:
        return {
            "자연어 질의": text,
            "RAG 프롬프트": rag_prompt,
            "모델 답변 쿼리문": "",
            "정답 쿼리문": gold_query,
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "",
            "플레이스홀더 잔존 여부": "N/A",
            "샌드박스 DB 실행검증 결과": "skip",
            "샌드박스 DB 실행검증 에러 사유": "",
            "EM 결과": "N/A",
            "EX 결과": "skip",
            "EX 참고사항": "",
            "응답 속도": f"{elapsed:.2f}",
            "비고": f"[RAG 프롬프트 입력] API 호출 실패: {api_error}",
        }

    sql, is_sql_format = base.extract_sql(raw_response)

    if not is_sql_format:
        return {
            "자연어 질의": text,
            "RAG 프롬프트": rag_prompt,
            "모델 답변 쿼리문": raw_response.strip(),
            "정답 쿼리문": gold_query,
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "omop-cdm 스키마 오류 여부": "fail",
            "omop-cdm 스키마 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "플레이스홀더 잔존 여부": "N/A",
            "샌드박스 DB 실행검증 결과": "fail" if sandbox_conn is not None else "skip",
            "샌드박스 DB 실행검증 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)" if sandbox_conn is not None else "",
            "EM 결과": base.check_em("", gold_query),
            "EX 결과": "fail" if (sandbox_conn is not None and gold_query) else ("N/A" if not gold_query else "skip"),
            "EX 참고사항": "",
            "응답 속도": f"{elapsed:.2f}",
            "비고": "[RAG 프롬프트 입력]",
        }

    has_placeholder = bool(base.PLACEHOLDER_RE.search(sql))

    syntax_ok, syntax_reason = base.check_syntax(sql)
    if syntax_ok:
        schema_ok, schema_reason = base.check_schema(sql, schema)
    else:
        schema_ok, schema_reason = False, "구문 오류로 스키마 검증 불가"

    sandbox_result, sandbox_reason = base.check_sandbox_validity(sandbox_conn, sql)
    em_result = base.check_em(sql, gold_query)
    ex_result, ex_note = base.check_ex(sandbox_conn, sql, gold_query)

    note = "[RAG 프롬프트 입력]"
    if not gold_query:
        note += " | 정답 SQL 없음 (기존 88건 목록에 없는 신규 질의)"

    return {
        "자연어 질의": text,
        "RAG 프롬프트": rag_prompt,
        "모델 답변 쿼리문": sql,
        "정답 쿼리문": gold_query,
        "SQL문법 결과": "pass" if syntax_ok else "fail",
        "SQL문법 에러 사유": "" if syntax_ok else syntax_reason,
        "omop-cdm 스키마 오류 여부": "pass" if schema_ok else "fail",
        "omop-cdm 스키마 에러 사유": "" if schema_ok else schema_reason,
        "플레이스홀더 잔존 여부": "있음 (RAG 컨텍스트 무시 - 회귀 의심)" if has_placeholder else "없음",
        "샌드박스 DB 실행검증 결과": sandbox_result,
        "샌드박스 DB 실행검증 에러 사유": sandbox_reason,
        "EM 결과": em_result,
        "EX 결과": ex_result,
        "EX 참고사항": ex_note,
        "응답 속도": f"{elapsed:.2f}",
        "비고": note,
    }


def print_summary(rows: list[dict]) -> None:
    n = len(rows)
    if n == 0:
        print("평가할 케이스가 없습니다.")
        return

    syntax_pass = sum(1 for r in rows if r["SQL문법 결과"] == "pass")
    schema_pass = sum(1 for r in rows if r["omop-cdm 스키마 오류 여부"] == "pass")
    placeholder_left = sum(1 for r in rows if r["플레이스홀더 잔존 여부"].startswith("있음"))
    speeds = [float(r["응답 속도"]) for r in rows]

    print(f"\n총 {n}건 평가 (RAG 프롬프트 입력)")
    print(f"  Syntactic Validity  : {syntax_pass}/{n} ({syntax_pass / n:.1%})")
    print(f"  스키마 참조 정확도   : {schema_pass}/{n} ({schema_pass / n:.1%})")
    print(f"  {{}} 플레이스홀더 잔존   : {placeholder_left}/{n} ({placeholder_left / n:.1%}) — RAG concept_id를 무시하고 예전처럼 답한 비율")
    print(f"  응답 속도(평균/최대)  : {sum(speeds) / n:.2f}s / {max(speeds):.2f}s")

    sandbox_checked = [r for r in rows if r["샌드박스 DB 실행검증 결과"] in ("pass", "fail")]
    if sandbox_checked:
        sb_pass = sum(1 for r in sandbox_checked if r["샌드박스 DB 실행검증 결과"] == "pass")
        m = len(sandbox_checked)
        print(f"  샌드박스 DB 실행검증 : {sb_pass}/{m} ({sb_pass / m:.1%})")
    else:
        print("  샌드박스 DB 실행검증 : SANDBOX_DB_HOST 미설정으로 건너뜀")

    em_checked = [r for r in rows if r["EM 결과"] in ("pass", "fail")]
    if em_checked:
        em_pass = sum(1 for r in em_checked if r["EM 결과"] == "pass")
        m = len(em_checked)
        print(f"  EM (정답 있는 {m}건)  : {em_pass}/{m} ({em_pass / m:.1%})")

    ex_checked = [r for r in rows if r["EX 결과"] in ("pass", "fail")]
    if ex_checked:
        ex_pass = sum(1 for r in ex_checked if r["EX 결과"] == "pass")
        m = len(ex_checked)
        print(f"  EX (정답 있는 {m}건)  : {ex_pass}/{m} ({ex_pass / m:.1%})")
        print("    주의: 샌드박스 DB에 임상 데이터가 비어있으면 EX는 사실상 항상 pass가 되므로 로직 정확성의 증거로 해석하지 말 것")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 결과 프롬프트를 파인튜닝 모델에 직접 넣어 테스트")
    parser.add_argument("--rag-outputs", required=True, help="RAG API 출력을 모아둔 JSONL (text/prompt 필드 필수)")
    parser.add_argument("--api-url", default=base.API_URL)
    parser.add_argument("--model", default=base.MODEL_NAME)
    parser.add_argument("--ddl", default=base.DDL_PATH)
    parser.add_argument("--output", default="eval_results_rag.csv")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--limit", type=int, default=None, help="앞 N건만 실행 (스모크 테스트용)")
    args = parser.parse_args()

    schema = base.load_schema(args.ddl)
    print(f"OMOP CDM 스키마 로드: 테이블 {len(schema)}개 ({args.ddl})")

    sandbox_conn = base.get_sandbox_connection()
    if sandbox_conn is not None:
        print("샌드박스 DB 연결 성공 — 실행검증/EM/EX도 함께 실행합니다.")
    else:
        print("SANDBOX_DB_HOST 미설정 — 실행검증/EM/EX는 건너뜁니다 (정적 분석만 실행).")

    gold_lookup = load_gold_lookup()
    rag_items = base.load_jsonl(args.rag_outputs)
    for item in rag_items:
        if "text" not in item or "prompt" not in item:
            raise ValueError(f"RAG 출력에 text/prompt 필드가 없습니다: {item}")
    if args.limit:
        rag_items = rag_items[: args.limit]

    print(f"RAG 출력 {len(rag_items)}건 평가 (시스템 프롬프트: RAG 컨텍스트 활용형)\n")

    rows = []
    try:
        for i, item in enumerate(rag_items, 1):
            gold_query = gold_lookup.get(item["text"], "")
            row = evaluate_rag_case(
                item, gold_query, schema, args.api_url, args.model, args.timeout, args.max_tokens, sandbox_conn
            )
            rows.append(row)
            preview = item["text"][:30]
            print(
                f"[{i}/{len(rag_items)}] {preview}: 문법={row['SQL문법 결과']} 스키마={row['omop-cdm 스키마 오류 여부']} "
                f"플레이스홀더={row['플레이스홀더 잔존 여부']} EM={row['EM 결과']} EX={row['EX 결과']} ({row['응답 속도']}s)"
            )
    finally:
        if sandbox_conn is not None:
            sandbox_conn.close()

    with open(args.output, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n결과 저장: {args.output}")

    print_summary(rows)


if __name__ == "__main__":
    main()
