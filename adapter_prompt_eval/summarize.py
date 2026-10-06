"""run_eval.py가 만든 결과 CSV들을 보고서와 같은 기준으로 집계해 표로 출력한다.

summary JSON은 Format 이탈(자연어 답변) 문항을 분모에서 빼서 점수가 부풀려지므로,
보고서 수치는 이 스크립트로 전체 문항 기준으로 다시 계산한다.

    # 학습셋·val: 모델 여러 개를 한 표로
    python summarize.py --model ft1_trainsys --model base_sysprompt_v2 \\
        --testset proposed_input_train=../test_set/proposed_input_train.jsonl \\
        --testset proposed_input_val=../test_set/proposed_input_val.jsonl

    # 변형 테스트셋: 같은 시드의 원본 결과(학습셋·val)와 짝지어 비교
    python summarize.py --model ft1_trainsys --pair-original \\
        --testset variant_concept=../test_set/eval_ready/concept.jsonl

집계 기준:
- base+시스템 프롬프트의 few-shot 문항(id 또는 seed_id가 290·535·721·447·299)은
  모든 모델에서 뺀다 (--exclude-seeds ""로 끌 수 있음).
- 분모는 전체 문항이다. 자연어로 답한 문항은 실패로 센다.
- concept_id 핵심 지표는 정답 SQL이 실제로 쓰는 코드(필요한 코드)와 쓰지 않는 코드
  (불필요한 코드)를 나눠 코드 단위로 센다.
  - 올바른 반영률: 필요한 코드가 해당 항목의 조건 안에 있고, 하위 전개 형식이며,
    SQL이 실행검증을 통과한 비율
  - 필요한 코드 반영률: 필요한 코드가 해당 항목의 조건 안에 있는 비율 (형식 무관)
  - 불필요한 코드 사용률: 불필요한 코드가 조건 안에 들어간 비율 (낮을수록 좋음)

결과 CSV는 ../results/ 바로 아래와 ../results/adapter_eval/{train,val,variant}/ 를
모두 찾는다.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import adherence as ad
from run_eval import parse_labeled_path, prepare_case

RESULTS = Path(__file__).resolve().parent.parent / "results"
FEWSHOT_SEEDS = "290,535,721,447,299"
ORIGINAL_TESTSETS = {"train": "proposed_input_train", "val": "proposed_input_val"}


def find_csv(model: str, testset: str) -> Path | None:
    name = f"adapter_eval_{model}_{testset}.csv"
    for p in [RESULTS / name, *(RESULTS / "adapter_eval" / sub / name for sub in ("train", "val", "variant"))]:
        if p.exists():
            return p
    return None


def load_rows(model: str, testset: str) -> dict[str, dict] | None:
    path = find_csv(model, testset)
    if path is None:
        return None
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def load_cases(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        raw = [json.loads(line) for line in f if line.strip()]
    return {str(r["id"]): r for r in raw}


def seed_of(case: dict) -> str:
    return str(case.get("seed_id", case["id"]))


def score(rows: dict[str, dict], cases: dict[str, dict], ids: list[str]) -> dict:
    n = len(ids)
    pct = lambda k: 100 * k / n if n else 0.0
    c: Counter = Counter()
    sub_sum, sub_n = 0.0, 0
    for i in ids:
        r, case = rows[i], prepare_case(cases[i])
        fmt_fail = r["비고"].startswith("Format")
        sql = "" if fmt_fail else r["모델 답변 쿼리문"]
        valid = r["샌드박스 DB 실행검증 결과"] == "pass"
        c["format"] += fmt_fail
        c["api"] += r["비고"].startswith("API")
        c["syntax"] += r["SQL문법 결과"] == "pass"
        c["sandbox"] += valid
        c["em"] += r["EM 결과"] == "pass"
        c["ex"] += r["EX 결과"] == "pass"
        if case["anchors"]:
            v = r["쿼리문 하위 전개 반영도"]
            sub_sum += 0.0 if v in ("N/A", "") else float(v)
            sub_n += 1
        for a in case["anchors"]:
            s = ad.score_anchor(sql, a)
            if ad.score_anchor(case["gold_query"], a)["correctness"]:
                c["need"] += 1
                c["need_ok"] += s["correctness"]
                c["correct"] += s["correctness"] and s["subexpansion"] and valid
            else:
                c["extra"] += 1
                c["extra_used"] += s["correctness"]
    return {
        "n": n, "format": c["format"], "api": c["api"],
        "syntax": pct(c["syntax"]), "sandbox": pct(c["sandbox"]),
        "subexp": 100 * sub_sum / sub_n if sub_n else 0.0,
        "correct": 100 * c["correct"] / c["need"] if c["need"] else 0.0,
        "need": 100 * c["need_ok"] / c["need"] if c["need"] else 0.0,
        "extra": 100 * c["extra_used"] / c["extra"] if c["extra"] else 0.0, "extra_n": c["extra"],
        "em": pct(c["em"]), "ex": pct(c["ex"]), "ex_count": c["ex"],
    }


def pair_with_original(model: str, rows: dict[str, dict], cases: dict[str, dict], ids: list[str]) -> dict | None:
    originals: dict[str, dict] = {}
    for testset in ORIGINAL_TESTSETS.values():
        orig = load_rows(model, testset)
        if orig is None:
            return None
        originals.update(orig)
    c: Counter = Counter()
    for i in ids:
        o = originals.get(seed_of(cases[i]))
        if o is None:
            continue
        a, b = o["EX 결과"] == "pass", rows[i]["EX 결과"] == "pass"
        c["n"] += 1
        c["orig"] += a
        c["lost"] += a and not b
        c["gain"] += b and not a
    return {"orig_ex": 100 * c["orig"] / c["n"] if c["n"] else 0.0, "lost": c["lost"], "gain": c["gain"], "paired": c["n"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", action="append", required=True, help="결과 CSV의 모델 라벨 (run_eval.py --adapter LABEL=...의 LABEL)")
    parser.add_argument("--testset", action="append", required=True, metavar="LABEL=PATH")
    parser.add_argument("--exclude-seeds", default=FEWSHOT_SEEDS, help=f"집계에서 뺄 id/seed_id (기본: few-shot {FEWSHOT_SEEDS})")
    parser.add_argument("--pair-original", action="store_true", help="변형 테스트셋을 같은 모델의 학습셋·val 원본 결과와 짝지어 비교")
    args = parser.parse_args()

    exclude = {s.strip() for s in args.exclude_seeds.split(",") if s.strip()}
    for testset, path in map(parse_labeled_path, args.testset):
        cases = load_cases(path)
        ids_all = [i for i in cases if seed_of(cases[i]) not in exclude]
        print(f"\n### {testset} (집계 {len(ids_all)}건, 제외 {len(cases) - len(ids_all)}건)\n")
        header = "| 모델 | 문항 | 자연어 답변 | API 실패 | 문법 | 실행검증 | 하위 전개 | 올바른 반영률 | 필요한 코드 | 불필요한 코드 ↓ | EM | EX |"
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        if args.pair_original:
            header += " 원본 EX | 변화 | 원본 맞힘→틀림 | 원본 틀림→맞힘 |"
            sep += "---:|---:|---:|---:|"
        print(header)
        print(sep)
        for model in args.model:
            rows = load_rows(model, testset)
            if rows is None:
                print(f"| {model} | (결과 CSV 없음) |")
                continue
            ids = [i for i in ids_all if i in rows]
            s = score(rows, cases, ids)
            line = (
                f"| {model} | {s['n']} | {s['format']} | {s['api']} | {s['syntax']:.2f}% | {s['sandbox']:.2f}% | "
                f"{s['subexp']:.2f}% | {s['correct']:.1f}% | {s['need']:.1f}% | {s['extra']:.1f}% ({s['extra_n']}) | "
                f"{s['em']:.2f}% | {s['ex']:.2f}% ({s['ex_count']}) |"
            )
            if args.pair_original:
                p = pair_with_original(model, rows, cases, ids)
                line += (
                    f" {p['orig_ex']:.2f}% | {s['ex'] - p['orig_ex']:+.1f}%p | {p['lost']} | {p['gain']} |"
                    if p else " (원본 결과 없음) | | | |"
                )
            if len(ids) < len(ids_all):
                line += f" ⚠️ {len(ids_all) - len(ids)}건 미완료"
            print(line)


if __name__ == "__main__":
    main()
