"""EM / EX / SQL Validity 채점기. 어떤 시스템(베이스 모델, RAG, 파인튜닝 모델 등)이
만든 예측이든 predictions.jsonl 스키마만 맞으면 동일하게 채점한다.

사용법:
  python -m eval_harness.score \\
      --testset data/testset.jsonl \\
      --predictions predictions.jsonl \\
      [--report report.json]

predictions.jsonl 스키마 (평가 대상 시스템이 생성):
  {"id": "nlsql_001", "predicted_sql": "SELECT ..."}
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from eval_harness.db import get_connection
from eval_harness.exact_match import is_exact_match
from eval_harness.execution import is_execution_match
from eval_harness.validity import is_valid_sql


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="NL-to-SQL EM/EX/Validity 채점기")
    parser.add_argument("--testset", default="data/testset.jsonl")
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--report", default=None, help="집계 결과를 JSON으로 저장할 경로")
    args = parser.parse_args()

    testset = {row["id"]: row for row in load_jsonl(args.testset)}
    predictions = {row["id"]: row["predicted_sql"] for row in load_jsonl(args.predictions)}

    missing = sorted(set(testset) - set(predictions))
    if missing:
        print(
            f"[경고] 예측이 없는 문항 {len(missing)}개는 채점에서 제외됩니다: {missing[:5]}"
            + (" ..." if len(missing) > 5 else ""),
            file=sys.stderr,
        )

    connections: dict[str, object] = {}
    results = []

    try:
        for qid, gold in testset.items():
            if qid not in predictions:
                continue
            db_id = gold["db_id"]
            if db_id not in connections:
                connections[db_id] = get_connection(db_id)
            conn = connections[db_id]

            pred_sql = predictions[qid]
            results.append({
                "id": qid,
                "difficulty": gold.get("difficulty"),
                "valid": is_valid_sql(conn, pred_sql),
                "em": is_exact_match(pred_sql, gold["query"]),
                "ex": is_execution_match(conn, pred_sql, gold["query"]),
            })
    finally:
        for conn in connections.values():
            conn.close()

    n = len(results)
    if n == 0:
        print("채점할 문항이 없습니다 (testset과 predictions의 id가 겹치지 않음).", file=sys.stderr)
        sys.exit(1)

    validity_rate = sum(r["valid"] for r in results) / n
    em_rate = sum(r["em"] for r in results) / n
    ex_rate = sum(r["ex"] for r in results) / n

    print(f"채점 문항 수: {n}")
    print(f"SQL Validity : {validity_rate:.1%}")
    print(f"EM           : {em_rate:.1%}")
    print(f"EX           : {ex_rate:.1%}")

    by_difficulty = defaultdict(list)
    for r in results:
        by_difficulty[r["difficulty"]].append(r)
    if len(by_difficulty) > 1:
        print("\n난이도별:")
        for diff, rows in sorted(by_difficulty.items(), key=lambda kv: str(kv[0])):
            m = len(rows)
            print(
                f"  {str(diff):8s} (n={m:2d}): "
                f"valid={sum(r['valid'] for r in rows) / m:.1%}  "
                f"em={sum(r['em'] for r in rows) / m:.1%}  "
                f"ex={sum(r['ex'] for r in rows) / m:.1%}"
            )

    if args.report:
        Path(args.report).write_text(
            json.dumps(
                {
                    "n": n,
                    "validity_rate": validity_rate,
                    "em_rate": em_rate,
                    "ex_rate": ex_rate,
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n상세 리포트 저장: {args.report}")


if __name__ == "__main__":
    main()
