"""이미 만들어진 결과 CSV의 스키마 Adherence 컬럼(Presence/Correctness/Usage/상세)만
현재 adherence.py 기준으로 다시 채점한다. 모델을 다시 호출하지 않고 CSV에 저장된
"모델 답변 쿼리문"을 그대로 쓰므로, 채점 로직만 바뀌었을 때 기존 결과를 갱신하는 용도.

    python rescore_schema.py --testset proposed_input_train=../test_set/proposed_input_train.jsonl \\
        ../results/adapter_eval_*_proposed_input_train.csv

CSV의 "테스트셋" 컬럼 값으로 --testset LABEL을 찾아 재료(스키마/조인)를 다시 읽는다.
Format 이탈(SQL이 아닌 응답) 행은 원래대로 N/A로 둔다. 파일은 제자리에서 덮어쓴다.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import adherence as ad
from run_eval import CSV_FIELDNAMES, _fmt, parse_labeled_path, prepare_case


def load_cases(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        cases = [prepare_case(json.loads(line)) for line in f if line.strip()]
    return {str(c["id"]): c for c in cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--testset", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("csv_files", nargs="+", type=Path)
    args = parser.parse_args()

    testsets = {label: load_cases(path) for label, path in map(parse_labeled_path, args.testset)}

    for csv_path in args.csv_files:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != CSV_FIELDNAMES:
                raise SystemExit(f"[오류] {csv_path}의 컬럼 구성이 지금 스크립트와 다릅니다.")
            rows = list(reader)

        before, after = Counter(), Counter()
        for row in rows:
            before[row["스키마 Usage"]] += 1
            if row["비고"].startswith("Format 이탈") or row["비고"].startswith("API 호출 실패"):
                after[row["스키마 Usage"]] += 1
                continue
            cases = testsets.get(row["테스트셋"])
            if cases is None:
                raise SystemExit(f"[오류] {csv_path}: 테스트셋 '{row['테스트셋']}'에 해당하는 --testset이 없습니다.")
            case = cases[row["id"]]
            score = ad.score_schema_adherence(row["모델 답변 쿼리문"], case["schema"], case["joins"])
            row["스키마 Presence"] = _fmt(score["presence"])
            row["스키마 Correctness"] = _fmt(score["correctness"])
            row["스키마 Usage"] = _fmt(score["usage"])
            row["스키마 상세"] = score["detail"]
            after[row["스키마 Usage"]] += 1

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        print(f"{csv_path.name}: 스키마 Usage {dict(before)} -> {dict(after)}")


if __name__ == "__main__":
    main()
