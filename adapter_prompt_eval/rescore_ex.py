"""샌드박스 DB 인프라 문제(공유 메모리 부족, statement timeout)로 실행검증/EX가
제대로 판정되지 못한 행만 골라, CSV에 저장된 "모델 답변 쿼리문"으로 다시 실행한다.
모델은 다시 호출하지 않는다. DB 설정을 고친 뒤 기존 결과를 갱신하는 용도.

    python rescore_ex.py --testset proposed_input_train=../test_set/proposed_input_train.jsonl \\
        ../results/adapter_eval_*_proposed_input_train.csv

대상 행: EX 결과가 ERROR이거나, EX 참고사항/샌드박스 실행검증 에러 사유에
공유 메모리 부족·statement timeout이 기록된 행. 그 행의 샌드박스 실행검증과 EX만
다시 판정하고 나머지 컬럼은 그대로 둔다. 파일은 제자리에서 덮어쓴다.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from rescore_schema import load_cases
from run_eval import CSV_FIELDNAMES, base, parse_labeled_path

_INFRA_MARKERS = ("could not resize shared memory segment", "canceling statement due to statement timeout")


def _is_infra(text: str) -> bool:
    return any(m in text for m in _INFRA_MARKERS)


def needs_recheck(row: dict) -> bool:
    if row["비고"].startswith(("Format 이탈", "API 호출 실패")):
        return False
    return (
        row["EX 결과"] == "ERROR"
        or _is_infra(row["EX 참고사항"])
        or _is_infra(row["샌드박스 DB 실행검증 에러 사유"])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--testset", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("csv_files", nargs="+", type=Path)
    args = parser.parse_args()

    testsets = {label: load_cases(path) for label, path in map(parse_labeled_path, args.testset)}
    pool = base.SandboxConnectionPool()
    conn = pool.get()
    if conn is None:
        raise SystemExit("[오류] 샌드박스 DB에 연결할 수 없습니다 (../.env의 SANDBOX_DB_* 확인).")

    try:
        for csv_path in args.csv_files:
            with open(csv_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != CSV_FIELDNAMES:
                    raise SystemExit(f"[오류] {csv_path}의 컬럼 구성이 지금 스크립트와 다릅니다.")
                rows = list(reader)

            targets = [r for r in rows if needs_recheck(r)]
            transitions: Counter = Counter()
            for row in targets:
                case = testsets[row["테스트셋"]][row["id"]]
                sql = row["모델 답변 쿼리문"]
                before = row["EX 결과"]
                sandbox_result, sandbox_reason = base.check_sandbox_validity(conn, sql)
                ex_result, ex_note = base.check_ex(conn, sql, case["gold_query"])
                row["샌드박스 DB 실행검증 결과"] = sandbox_result
                row["샌드박스 DB 실행검증 에러 사유"] = sandbox_reason
                row["EX 결과"] = ex_result
                row["EX 참고사항"] = ex_note
                transitions[(before, ex_result)] += 1
                still = " (여전히 인프라 오류)" if _is_infra(ex_note) or _is_infra(sandbox_reason) else ""
                print(f"  {csv_path.name} id={row['id']}: EX {before} -> {ex_result}{still}")

            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
                writer.writeheader()
                writer.writerows(rows)
            summary = ", ".join(f"{a}->{b}: {n}" for (a, b), n in sorted(transitions.items()))
            print(f"{csv_path.name}: 재검증 {len(targets)}건 ({summary or '대상 없음'})")
    finally:
        pool.close_all()


if __name__ == "__main__":
    main()
