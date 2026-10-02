"""어댑터 기반(RAG API 미연동) nl2sql 모델 단독 평가.

[질의]/[재료] 프롬프트를 입력으로 받도록 학습된 모델(프롬프트 반영 + concept
랜덤화 방식으로 학습한 "새 방식" 모델)의 체크포인트 여러 개를, 사용자가
지정한 테스트셋 파일 여러 개에 대해 한 번에 돌려서 다음을 측정한다:

  1. SQL Validity        — 문법(sqlglot) + 샌드박스 DB 실행검증(EXPLAIN)
  2. 쿼리문 하위 전개 반영도 — 개념 값 조건을 concept_ancestor 서브쿼리로
                             하위 개념까지 확장했는가
  3. 프롬프트 반영도       — 스키마 Adherence / concept-id Adherence 각각
                             Presence·Correctness·Usage 3개 지표로 채점
                             (automl-llm/scripts/compute_adherence.py와
                             동일한 정의 — 체크포인트 선택 기준과 이 평가가
                             같은 잣대를 쓰도록 맞춤)
  4. EM / EX              — 테스트 케이스에 정답 SQL(query 필드)이 있을 때만
  5. 응답 속도

모델은 로컬에서 로드하지 않는다 — automl-llm/scripts/serve_vllm.sh가 베이스
모델 + 체크포인트들을 원격 vLLM 서버에 `--enable-lora`로 이미 동시에 띄워둔
전제로, OpenAI 호환 `/v1/chat/completions`에 `model` 필드만 체크포인트별
서빙 이름(예: `by-loss`/`final-step`/`by-adherence`)으로 바꿔가며 요청한다.
`--adapter`를 하나도 안 주면 `.env`의 `CHECKPOINT_EVAL_LOSS`/`CHECKPOINT_CONCEPT_ID`/
`CHECKPOINT_FINAL_STEP`(설정된 것만) 기본값을 쓰고, `--no-base`를 안 주면
베이스 모델(`.env`의 `BASE_MODEL_NAME`, 파인튜닝 전)도 자동으로 같이 비교한다
— "체크포인트 3개 vs 베이스 모델"까지 한 번에 보고 싶을 때를 위함.

RAG는 붙이지 않는다 — 테스트셋 파일은 automl-llm의 학습 데이터셋과 동일한
물리 필드("text"=자연어 질의, "input"=재료, "query"=정답 SQL)로 주면 되고,
이 스크립트가 그 둘을 합쳐 모델이 실제로 받을 "[질의]/[재료]" 프롬프트를
조립한다(학습 데이터 재현 테스트/MPX 독립 테스트셋/LLM 생성 테스트셋 전부
동일 스키마). 이미 조립된 프롬프트를 담고 있으면("prompt" 필드) 그걸 그대로
쓴다 — 자세한 스키마는 README.md 참고.

테스트셋 JSONL 스키마 (한 줄에 한 케이스, 둘 중 하나):
  {"id": "...", "text": "자연어 질의", "input": "[재료]\\n...", "query": "<정답 SQL, 모르면 \"\">"}
  {"id": "...", "prompt": "[질의]\\n...\\n\\n[재료]\\n...", "query": "<정답 SQL, 모르면 \"\">"}  # 이미 조립된 경우

사용법 (.env에 VLLM_HOST/VLLM_PORT/CHECKPOINT_*/BASE_MODEL_NAME을 채워뒀다면
--adapter/--api-url 없이 테스트셋만 줘도 체크포인트 전부 + 베이스 모델까지
자동으로 비교한다):
  python run_eval.py \\
      --testset train_repro=/path/to/train_subset.jsonl \\
      --testset independent=/path/to/mpx_testset.jsonl \\
      --testset llm_generated=/path/to/llm_generated_testset.jsonl

  # 명시적으로 지정하고 싶으면 (.env 설정을 덮어씀)
  python run_eval.py \\
      --api-url http://<vLLM 서버>:<포트>/v1/chat/completions \\
      --adapter eval_loss=by-loss \\
      --adapter concept_id=by-adherence \\
      --adapter final_step=final-step \\
      --testset independent=/path/to/mpx_testset.jsonl

  # 스모크 테스트 (한 테스트셋 앞 5건만, 체크포인트 1개만, 베이스 모델 비교는 끔)
  python run_eval.py --adapter final_step=final-step --no-base --testset smoke=/path/... --limit 5
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import os
import sys
import time
from pathlib import Path

import adherence as ad
from inference import call_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import eval_api_model as base  # noqa: E402 - 공용 .env 로딩 + syntax/sandbox/EM/EX 유틸 재사용

# adapter_prompt_eval 전용 설정은 공용 .env(scripts/eval_api_model.py가 쓰는
# LLM_API_URL 등)와 분리된 별도 .env에 둔다 — 이 도구가 말 거는 원격 서버는
# serve_vllm.sh로 체크포인트 여러 개를 동시에 올려둔 평가용 vLLM이라, 운영
# 서빙 엔드포인트(LLM_API_URL)와는 보통 다른 서버이기 때문.
base._load_dotenv(Path(__file__).resolve().parent / ".env")

_VLLM_HOST = os.environ.get("VLLM_HOST", "").strip()
_VLLM_PORT = os.environ.get("VLLM_PORT", "").strip()
DEFAULT_API_URL = f"http://{_VLLM_HOST}:{_VLLM_PORT}/v1/chat/completions" if _VLLM_HOST and _VLLM_PORT else None

DEFAULT_CHECKPOINTS = [
    (label, value)
    for label, value in (
        ("eval_loss", os.environ.get("CHECKPOINT_EVAL_LOSS", "").strip()),
        ("concept_id", os.environ.get("CHECKPOINT_CONCEPT_ID", "").strip()),
        ("final_step", os.environ.get("CHECKPOINT_FINAL_STEP", "").strip()),
    )
    if value
]
DEFAULT_BASE_MODEL_NAME = os.environ.get("BASE_MODEL_NAME", "").strip() or None

CSV_FIELDNAMES = [
    "id",
    "체크포인트",
    "테스트셋",
    "자연어 질의",
    "모델 답변 쿼리문",
    "SQL문법 결과",
    "SQL문법 에러 사유",
    "샌드박스 DB 실행검증 결과",
    "샌드박스 DB 실행검증 에러 사유",
    "쿼리문 하위 전개 반영도",
    "concept_id Presence",
    "concept_id Correctness",
    "concept_id Usage",
    "concept_id 상세",
    "스키마 Presence",
    "스키마 Correctness",
    "스키마 Usage",
    "스키마 상세",
    "EM 결과",
    "EX 결과",
    "EX 참고사항",
    "응답 속도",
    "비고",
]


def parse_labeled_value(spec: str) -> tuple[str, str]:
    """"LABEL=값" 또는 "값"(이 경우 값 자체가 라벨)을 (라벨, 값) 튜플로."""
    if "=" in spec:
        label, _, value = spec.partition("=")
        return label.strip(), value.strip()
    return spec.strip(), spec.strip()


def parse_labeled_path(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        label, _, path = spec.partition("=")
        return label.strip(), Path(path.strip())
    p = Path(spec)
    return p.stem, p


def _fmt(v: bool | float | None) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, bool):
        return "pass" if v else "fail"
    return f"{v:.2f}"


def prepare_case(case: dict) -> dict:
    prompt = ad.build_prompt(case)
    nl, material = ad.split_prompt(prompt)
    return {
        "id": case["id"],
        "prompt": prompt,
        "nl_query": nl,
        "gold_query": ad.resolve_gold_query(case),
        "anchors": ad.parse_anchors(material),
        "schema": ad.parse_schema_section(material),
        "joins": ad.parse_joins_section(material),
    }


def evaluate_one(
    case: dict,
    checkpoint_label: str,
    model_name: str,
    testset_label: str,
    api_url: str,
    system_prompt: str | None,
    max_tokens: int,
    timeout: float,
    sandbox_conn,
) -> dict:
    raw, elapsed, api_error = call_model(case["prompt"], api_url, model_name, timeout, max_tokens, system_prompt)

    if api_error is not None:
        return {
            "id": case["id"],
            "체크포인트": checkpoint_label,
            "테스트셋": testset_label,
            "자연어 질의": case["nl_query"],
            "모델 답변 쿼리문": "",
            "응답 속도": f"{elapsed:.2f}",
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "",
            "샌드박스 DB 실행검증 결과": "skip",
            "샌드박스 DB 실행검증 에러 사유": "",
            "쿼리문 하위 전개 반영도": "N/A",
            "concept_id Presence": "N/A", "concept_id Correctness": "N/A", "concept_id Usage": "N/A",
            "concept_id 상세": "",
            "스키마 Presence": "N/A", "스키마 Correctness": "N/A", "스키마 Usage": "N/A",
            "스키마 상세": "",
            "EM 결과": "N/A", "EX 결과": "skip", "EX 참고사항": "",
            "비고": f"API 호출 실패: {api_error}",
        }

    sql, is_sql_format = base.extract_sql(raw)

    row = {
        "id": case["id"],
        "체크포인트": checkpoint_label,
        "테스트셋": testset_label,
        "자연어 질의": case["nl_query"],
        "모델 답변 쿼리문": sql if is_sql_format else raw.strip(),
        "응답 속도": f"{elapsed:.2f}",
    }

    if not is_sql_format:
        row.update({
            "SQL문법 결과": "fail",
            "SQL문법 에러 사유": "SQL이 아닌 자연어로 응답 (Format 이탈)",
            "샌드박스 DB 실행검증 결과": "skip",
            "샌드박스 DB 실행검증 에러 사유": "",
            "쿼리문 하위 전개 반영도": "N/A",
            "concept_id Presence": "N/A", "concept_id Correctness": "N/A", "concept_id Usage": "N/A",
            "concept_id 상세": "",
            "스키마 Presence": "N/A", "스키마 Correctness": "N/A", "스키마 Usage": "N/A",
            "스키마 상세": "",
            "EM 결과": "N/A", "EX 결과": "skip", "EX 참고사항": "",
            "비고": "Format 이탈로 나머지 채점 생략",
        })
        return row

    syntax_ok, syntax_reason = base.check_syntax(sql)
    sandbox_result, sandbox_reason = base.check_sandbox_validity(sandbox_conn, sql)
    concept = ad.score_concept_adherence(sql, case["anchors"])
    schema_score = ad.score_schema_adherence(sql, case["schema"], case["joins"])
    em_result = base.check_em(sql, case["gold_query"])
    ex_result, ex_note = base.check_ex(sandbox_conn, sql, case["gold_query"])

    row.update({
        "SQL문법 결과": "pass" if syntax_ok else "fail",
        "SQL문법 에러 사유": "" if syntax_ok else syntax_reason,
        "샌드박스 DB 실행검증 결과": sandbox_result,
        "샌드박스 DB 실행검증 에러 사유": sandbox_reason,
        "쿼리문 하위 전개 반영도": _fmt(concept["subexpansion_rate"]),
        "concept_id Presence": _fmt(concept["presence_rate"]),
        "concept_id Correctness": _fmt(concept["correctness_rate"]),
        "concept_id Usage": _fmt(concept["usage_rate"]),
        "concept_id 상세": concept["detail"],
        "스키마 Presence": _fmt(schema_score["presence"]),
        "스키마 Correctness": _fmt(schema_score["correctness"]),
        "스키마 Usage": _fmt(schema_score["usage"]),
        "스키마 상세": schema_score["detail"],
        "EM 결과": em_result,
        "EX 결과": ex_result,
        "EX 참고사항": ex_note,
        "비고": "",
    })
    return row


def load_existing_rows(out_path: Path) -> list[dict]:
    """--resume용: 기존 결과 CSV를 읽어온다. 컬럼 구성이 지금 버전과 다르면
    (예: 옛 버전 스크립트로 만든 파일) 이어쓰다 망가뜨리지 않도록 바로 에러를 낸다."""
    with open(out_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != CSV_FIELDNAMES:
            raise SystemExit(
                f"[오류] {out_path}의 컬럼 구성이 지금 스크립트와 달라 --resume으로 이어쓸 수 "
                "없습니다. 파일을 지우거나 다른 이름으로 옮긴 뒤 다시 실행하세요."
            )
        return list(reader)


def _rate(values: list, predicate=lambda v: v) -> tuple[float | None, int]:
    known = [v for v in values if v is not None and v not in ("N/A", "skip")]
    if not known:
        return None, 0
    hits = sum(1 for v in known if predicate(v))
    return hits / len(known), len(known)


def summarize(rows: list[dict]) -> dict:
    n = len(rows)

    def col_rate(name: str) -> tuple[float | None, int]:
        return _rate([r[name] for r in rows], predicate=lambda v: v == "pass")

    syntax_rate, syntax_n = col_rate("SQL문법 결과")
    sandbox_rate, sandbox_n = col_rate("샌드박스 DB 실행검증 결과")
    em_rate, em_n = col_rate("EM 결과")
    ex_rate, ex_n = col_rate("EX 결과")

    def avg_float_col(name: str) -> tuple[float | None, int]:
        known = [float(r[name]) for r in rows if r[name] not in ("N/A",)]
        if not known:
            return None, 0
        return sum(known) / len(known), len(known)

    subexp_rate, subexp_n = avg_float_col("쿼리문 하위 전개 반영도")
    concept_presence, concept_presence_n = avg_float_col("concept_id Presence")
    concept_correctness, _ = avg_float_col("concept_id Correctness")
    concept_usage, _ = avg_float_col("concept_id Usage")
    # 스키마 Presence/Correctness/Usage는 (concept_id 지표와 달리) 케이스당
    # 앵커 여러 개의 평균 비율이 아니라 SQL 1건에 대한 단일 pass/fail/N/A
    # 판정이라 _fmt()가 "pass"/"fail" 문자열로 적어둔다 — 숫자 평균이 아니라
    # col_rate(파싱된 "pass" 비율)로 집계해야 한다.
    schema_presence, schema_presence_n = col_rate("스키마 Presence")
    schema_correctness, _ = col_rate("스키마 Correctness")
    schema_usage, _ = col_rate("스키마 Usage")

    speeds = [float(r["응답 속도"]) for r in rows]

    return {
        "n": n,
        "sql_syntax_valid_rate": syntax_rate, "sql_syntax_n": syntax_n,
        "sql_sandbox_valid_rate": sandbox_rate, "sql_sandbox_n": sandbox_n,
        "subexpansion_rate": subexp_rate, "subexpansion_n": subexp_n,
        "concept_presence_rate": concept_presence, "concept_presence_n": concept_presence_n,
        "concept_correctness_rate": concept_correctness,
        "concept_usage_rate": concept_usage,
        "schema_presence_rate": schema_presence, "schema_presence_n": schema_presence_n,
        "schema_correctness_rate": schema_correctness,
        "schema_usage_rate": schema_usage,
        "em_rate": em_rate, "em_n": em_n,
        "ex_rate": ex_rate, "ex_n": ex_n,
        "avg_latency_sec": sum(speeds) / n if n else None,
        "max_latency_sec": max(speeds) if n else None,
    }


def print_summary(label: str, summary: dict) -> None:
    def fmt_rate(v: float | None, n: int) -> str:
        return f"{v:.1%} (n={n})" if v is not None else f"N/A (n={n})"

    def pct(key: str, n_key: str) -> str:
        return fmt_rate(summary[key], summary[n_key])

    concept_n = summary["concept_presence_n"]
    schema_n = summary["schema_presence_n"]

    print(f"\n[{label}] 총 {summary['n']}건")
    print(f"  SQL Validity (문법)        : {pct('sql_syntax_valid_rate', 'sql_syntax_n')}")
    print(f"  SQL Validity (샌드박스)     : {pct('sql_sandbox_valid_rate', 'sql_sandbox_n')}")
    print(f"  쿼리문 하위 전개 반영도      : {pct('subexpansion_rate', 'subexpansion_n')}")
    print(f"  concept-id Presence        : {fmt_rate(summary['concept_presence_rate'], concept_n)}")
    print(f"  concept-id Correctness     : {fmt_rate(summary['concept_correctness_rate'], concept_n)}")
    print(f"  concept-id Usage           : {fmt_rate(summary['concept_usage_rate'], concept_n)}")
    print(f"  스키마 Presence             : {fmt_rate(summary['schema_presence_rate'], schema_n)}")
    print(f"  스키마 Correctness          : {fmt_rate(summary['schema_correctness_rate'], schema_n)}")
    print(f"  스키마 Usage                : {fmt_rate(summary['schema_usage_rate'], schema_n)}")
    print(f"  EM                         : {pct('em_rate', 'em_n')}")
    print(f"  EX                         : {pct('ex_rate', 'ex_n')}")
    print(f"  응답 속도(평균/최대)         : {summary['avg_latency_sec']:.2f}s / {summary['max_latency_sec']:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="어댑터 단독(RAG 미연동) [질의]/[재료] nl2sql 모델 평가 — 원격 vLLM API 호출")
    parser.add_argument(
        "--adapter", action="append", default=None, metavar="LABEL=MODEL_NAME",
        help=(
            "원격 vLLM 서버에 등록된 체크포인트 모델 이름 (예: eval_loss=by-loss, "
            "concept_id=by-adherence, final_step=final-step — automl-llm/scripts/serve_vllm.sh가 "
            "등록하는 이름). 여러 번 지정 가능. 생략하면 .env의 CHECKPOINT_EVAL_LOSS/"
            "CHECKPOINT_CONCEPT_ID/CHECKPOINT_FINAL_STEP 중 설정된 것만 기본값으로 쓴다."
        ),
    )
    parser.add_argument(
        "--base-model-name", default=DEFAULT_BASE_MODEL_NAME, metavar="MODEL_NAME",
        help=(
            "베이스 모델(파인튜닝 전) 자체도 같이 비교하려면 그 served model 이름 "
            "(serve_vllm.sh가 --served-model-name으로 등록한 {STUDY_NAME}). "
            "미지정 시 .env의 BASE_MODEL_NAME이 기본값."
        ),
    )
    parser.add_argument(
        "--no-base", action="store_true",
        help="베이스 모델 이름이 있어도(--base-model-name/.env BASE_MODEL_NAME) 베이스 모델 비교를 끈다.",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=".env의 VLLM_HOST/VLLM_PORT로 조립한 URL이 기본값")
    parser.add_argument(
        "--testset", action="append", required=True, metavar="LABEL=PATH",
        help="평가할 테스트셋 JSONL 파일 (예: independent=/path/to/mpx.jsonl). 여러 번 지정 가능.",
    )
    parser.add_argument("--system-prompt", default=None, help="미지정 시 system 메시지 없이 prompt 필드만 user로 전송")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="체크포인트 1개당 동시에 처리할 문항 수 (vLLM이 continuous batching을 지원하면 5~10 권장)",
    )
    parser.add_argument("--limit", type=int, default=None, help="각 테스트셋 앞 N건만 실행 (스모크 테스트용)")
    parser.add_argument(
        "--resume", action="store_true",
        help=(
            "체크포인트×테스트셋 조합마다 기존 결과 CSV가 있으면 거기 담긴 id는 다시 "
            "호출하지 않고 이어서 나머지만 돌린다 (API 에러/중단 등으로 일부만 끝난 뒤 "
            "재실행할 때 사용). 기본값은 매번 새로 덮어쓰기."
        ),
    )
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parent.parent / "results"))
    args = parser.parse_args()

    adapters = [parse_labeled_value(a) for a in args.adapter] if args.adapter else list(DEFAULT_CHECKPOINTS)
    if not args.no_base:
        if args.base_model_name:
            adapters.append(("base", args.base_model_name))
        else:
            print("[안내] 베이스 모델 이름이 없어(--base-model-name 또는 .env BASE_MODEL_NAME) 베이스 모델 비교는 건너뜁니다.")
    if not adapters:
        raise SystemExit(
            "[오류] 테스트할 체크포인트가 하나도 없습니다. --adapter를 지정하거나 "
            ".env의 CHECKPOINT_EVAL_LOSS/CHECKPOINT_CONCEPT_ID/CHECKPOINT_FINAL_STEP 중 "
            "하나 이상을 설정하세요 (베이스 모델만 보려면 --base-model-name만 줘도 됨)."
        )
    if not args.api_url:
        raise SystemExit(
            "[오류] --api-url이 없고 .env의 VLLM_HOST/VLLM_PORT도 설정되지 않았습니다. "
            "adapter_prompt_eval/.env.example을 참고해 .env를 채우거나 --api-url을 직접 지정하세요."
        )
    testsets = [parse_labeled_path(t) for t in args.testset]

    print(f"API: {args.api_url}")
    print("체크포인트: " + ", ".join(f"{label}={model_name}" for label, model_name in adapters))

    pool = base.SandboxConnectionPool()
    if pool.get() is not None:
        print("샌드박스 DB 연결 성공 — 실행검증/EX도 함께 실행합니다.")
    else:
        print("SANDBOX_DB_HOST 미설정 — 실행검증/EX는 건너뜁니다 (정적 분석만 실행).")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_summaries: dict[str, dict] = {}

    try:
        for testset_label, testset_path in testsets:
            cases = [prepare_case(c) for c in base.load_jsonl(str(testset_path))]
            if args.limit:
                cases = cases[: args.limit]
            print(f"\n=== 테스트셋 '{testset_label}' ({testset_path}) — {len(cases)}건 ===")
            if not cases:
                print(f"[경고] '{testset_label}' 테스트셋에 케이스가 없어 건너뜁니다.")
                continue

            for checkpoint_label, model_name in adapters:
                out_path = output_dir / f"adapter_eval_{checkpoint_label}_{testset_label}.csv"

                rows: list[dict] = []
                pending_cases = cases
                append_mode = False
                if args.resume and out_path.exists() and out_path.stat().st_size > 0:
                    rows = load_existing_rows(out_path)
                    done_ids = {r["id"] for r in rows}
                    pending_cases = [c for c in cases if str(c["id"]) not in done_ids]
                    append_mode = True
                    print(
                        f"[이어하기] '{checkpoint_label}/{testset_label}': 기존 {len(rows)}건 "
                        f"중 {len(cases) - len(pending_cases)}건 재사용, 남은 {len(pending_cases)}건 실행"
                    )

                if not pending_cases:
                    print(f"[이어하기] '{checkpoint_label}/{testset_label}': 이미 전부 완료되어 건너뜁니다.")
                else:
                    def run_one(case: dict) -> dict:
                        return evaluate_one(
                            case, checkpoint_label, model_name, testset_label,
                            args.api_url, args.system_prompt, args.max_tokens, args.timeout, pool.get(),
                        )

                    with open(out_path, "a" if append_mode else "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                        if not append_mode:
                            writer.writeheader()
                        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                            # 제출은 한 번에 다 해서 동시에 돌아가게 하되, 진행 로그/CSV 기록은
                            # 원래 문항 순서대로 남긴다 (동시성이 출력 순서에 영향 안 주도록).
                            futures = [executor.submit(run_one, case) for case in pending_cases]
                            for i, (case, future) in enumerate(zip(pending_cases, futures), 1):
                                row = future.result()
                                rows.append(row)
                                writer.writerow(row)
                                f.flush()
                                print(
                                    f"  [{checkpoint_label}][{i}/{len(pending_cases)}] {case['id']}: "
                                    f"문법={row['SQL문법 결과']} 전개={row['쿼리문 하위 전개 반영도']} "
                                    f"concept_correctness={row['concept_id Correctness']} "
                                    f"EM={row['EM 결과']} EX={row['EX 결과']} ({row['응답 속도']}s)"
                                )

                summary = summarize(rows)
                all_summaries[f"{testset_label}/{checkpoint_label}"] = summary
                print(f"결과 저장: {out_path}")
                print_summary(f"{testset_label} / {checkpoint_label}", summary)
    finally:
        pool.close_all()

    summary_path = output_dir / f"adapter_eval_summary_{time.strftime('%y%m%d_%H%M%S')}.json"
    summary_path.write_text(
        json.dumps(
            {
                "api_url": args.api_url,
                "adapters": dict(adapters),
                "testsets": {label: str(path) for label, path in testsets},
                "results": all_summaries,
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n전체 요약 저장: {summary_path}")


if __name__ == "__main__":
    main()
