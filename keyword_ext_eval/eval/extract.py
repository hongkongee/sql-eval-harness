"""추출기 실행: 데이터 파일의 질의를 시스템(api/gliner/qwen)에 넣고 공통 형식 JSONL로 저장한다.

    python -m eval.extract --system api --data ../test_set/paraphrase.jsonl --out eval/outputs/api.jsonl

- 결과: <out>.jsonl (질의당 한 줄), 실행 메타데이터: <out>.meta.json, 실패: <out>.failed.jsonl
- 이어하기: <out>.jsonl에 이미 있는 id는 건너뛴다. 실패한 id는 결과에 안 쓰므로 다음 실행 때 다시 시도된다.
  설정(사전 해시·모델·라벨·threshold·프롬프트)이 기존 meta와 다르면 섞이지 않도록 멈춘다 → --overwrite.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from eval.common import append_jsonl, hardware_info, load_datasets, load_dotenv, read_jsonl, write_json
from eval.extractors import ExtractError, PreflightError

# 이어하기 때 이 값이 바뀌면 결과가 섞인다 - 같아야 이어서 돌린다
FINGERPRINT_KEYS = {
    "api": ("dict_sha256", "gliner_model", "gliner_threshold", "concept_labels"),
    "gliner": ("gliner_model", "labels", "threshold"),
    "qwen": ("model", "messages_sha256", "mock", "max_tokens", "extra_body"),
}


def meta_path(out: Path) -> Path:
    return out.with_name(out.stem + ".meta.json")


def failed_path(out: Path) -> Path:
    return out.with_name(out.stem + ".failed.jsonl")


def fingerprint(system: str, cfg: dict) -> dict:
    cfg = dict(cfg)
    if system == "api":
        # API가 실제로 쓰는 사전 해시를 우선, 못 읽었으면 로컬 파일 해시
        cfg["dict_sha256"] = cfg.get("dict_sha256_api") or cfg.get("dict_sha256_local")
    return {k: cfg.get(k) for k in FINGERPRINT_KEYS[system]}


def build_extractor(args):
    if args.system == "api":
        from eval.extractors.api import ApiExtractor
        return ApiExtractor(url=args.api_url, timeout=args.timeout or 60.0, dict_override=args.dict,
                            strict_dict=args.strict_dict)
    if args.system == "gliner":
        from eval.extractors.gliner import DEFAULT_LABELS, GlinerExtractor
        labels = [x.strip() for x in args.labels.split(",")] if args.labels else DEFAULT_LABELS
        return GlinerExtractor(url=args.gliner_url, labels=labels, threshold=args.threshold,
                               timeout=args.timeout or 120.0)
    from eval.extractors.qwen import QwenExtractor
    return QwenExtractor(prompt_path=args.prompt, timeout=args.timeout, max_retries=args.max_retries,
                         mock=args.mock)


def run(args) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        extractor = build_extractor(args)
        extractor.preflight()
        cfg = extractor.config()
        extractor.check_config(cfg)
    except PreflightError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    records = load_datasets(args.data)
    if args.limit:
        records = records[: args.limit]

    if args.overwrite:
        for p in (out, meta_path(out), failed_path(out)):
            if p.exists():
                p.unlink()

    fp = fingerprint(args.system, cfg)
    meta = {}
    if meta_path(out).exists():
        meta = json.loads(meta_path(out).read_text(encoding="utf-8"))
        if out.exists() and meta.get("fingerprint") != fp:
            print(
                f"[error] {out}에 다른 설정으로 만든 결과가 있습니다.\n"
                f"  기존: {meta.get('fingerprint')}\n  현재: {fp}\n"
                "  결과가 섞이지 않도록 멈춥니다. 새로 돌리려면 --overwrite, 따로 두려면 --out을 바꾸세요\n"
                "  (예: 모델을 바꿨다면 make extract-qwen QWEN_OUT=eval/outputs/qwen_<모델>.jsonl).",
                file=sys.stderr,
            )
            return 2

    done = {r["id"] for r in read_jsonl(out)} if out.exists() else set()
    todo = [r for r in records if r["id"] not in done]
    print(f"[{args.system}] 전체 {len(records)}건 / 완료 {len(records) - len(todo)}건 / 이번에 처리 {len(todo)}건")

    if failed_path(out).exists():
        failed_path(out).unlink()  # 실패 목록은 이번 실행 기준으로 새로 쓴다

    started = datetime.now().isoformat(timespec="seconds")
    n_ok = n_fail = 0
    concurrency = args.concurrency or (int(os.environ.get("QWEN_CONCURRENCY") or 4) if args.system == "qwen" else 1)
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(extractor.extract, r): r for r in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            rec = futures[fut]
            try:
                result = fut.result()
            except ExtractError as exc:
                n_fail += 1
                append_jsonl(failed_path(out), {"id": rec["id"], "system": args.system, "error": str(exc),
                                                "attempts": exc.attempts, "raw": exc.raw})
            else:
                n_ok += 1
                append_jsonl(out, {"id": rec["id"], "dataset": rec["dataset"], "system": args.system, **result})
            if i % 50 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} (성공 {n_ok}, 실패 {n_fail})")

    sessions = meta.get("sessions", [])
    sessions.append({"started_at": started, "finished_at": datetime.now().isoformat(timespec="seconds"),
                     "processed": len(todo), "ok": n_ok, "failed": n_fail})
    write_json(meta_path(out), {
        "system": args.system,
        "output": str(out),
        "data": [str(Path(d)) for d in args.data],
        "created_at": meta.get("created_at", started),
        "updated_at": sessions[-1]["finished_at"],
        "hardware": hardware_info(),
        "config": cfg,
        "fingerprint": fp,
        "sessions": sessions,
    })
    if n_fail:
        print(f"[warn] 실패 {n_fail}건 → {failed_path(out)} (다시 실행하면 실패한 id만 재시도)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True, choices=["api", "gliner", "qwen"])
    ap.add_argument("--data", required=True, action="append", help="평가 데이터 JSONL (여러 번 지정 가능)")
    ap.add_argument("--out", required=True, help="결과 JSONL 경로 (예: eval/outputs/api.jsonl)")
    ap.add_argument("--limit", type=int, default=0, help="앞에서부터 N건만 (스모크 테스트용)")
    ap.add_argument("--overwrite", action="store_true", help="기존 결과를 지우고 처음부터")
    ap.add_argument("--concurrency", type=int, default=None,
                    help="동시 요청 수 (기본: qwen은 $QWEN_CONCURRENCY 또는 4, 나머지 1)")
    ap.add_argument("--timeout", type=float, default=None, help="요청 타임아웃(초). qwen 기본: $QWEN_TIMEOUT 또는 60")
    # api
    ap.add_argument("--api-url", default=None, help="기본: $KEYWORD_API_URL 또는 http://localhost:8001")
    ap.add_argument("--dict", default=None, help="사전 파일 (기본: $SCHEMA_KEYWORDS_PATH 또는 서비스 레포 경로)")
    ap.add_argument("--strict-dict", action="store_true", help="API 사전 해시가 파일과 다르면 경고 대신 중단")
    # gliner
    ap.add_argument("--gliner-url", default=None, help="기본: $GLINER_EXTRACT_URL 또는 http://localhost:8000")
    ap.add_argument("--labels", default=None, help="GLiNER 라벨 (콤마 구분)")
    ap.add_argument("--threshold", type=float, default=0.3)
    # qwen
    ap.add_argument("--prompt", default=None, help="작업 프롬프트. 기본: $QWEN_PROMPT_FILE 또는 eval/prompts/qwen_schema_keywords.txt")
    ap.add_argument("--max-retries", type=int, default=None, help="기본: $QWEN_MAX_RETRIES 또는 4")
    ap.add_argument("--mock", action="store_true", help="qwen: 서버 없이 가짜 응답으로 실행")
    load_dotenv()
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
