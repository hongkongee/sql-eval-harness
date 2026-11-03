"""두 추출 결과의 스키마 키워드 일치도 (정답이 없는 셋용, 정확도가 아니다).

기준(--ref, 예: 운영 LLM) span 대비 비교(--pred) span을 본다.
- 위치 일치: span이 겹치면 일치. 기준 기준 재현율 / 비교 기준 정밀도 / F1
- 위치+테이블 일치: 겹치고 table까지 같으면 일치
- 불일치 문장 목록을 CSV로 남겨 사람이 볼 곳을 고른다

    python -m eval.schema_agreement --ref eval/outputs/pp573_prod_llm.jsonl --pred eval/outputs/pp573_ft-gliner_compat.jsonl --out eval/runs/pp573_agreement
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from eval.common import read_jsonl


def ov(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


def prf(tp_p, n_p, tp_r, n_r):
    p = tp_p / n_p if n_p else 0.0
    r = tp_r / n_r if n_r else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    ref = {r["id"]: r for r in read_jsonl(args.ref) if "error" not in r}
    pred = {r["id"]: r for r in read_jsonl(args.pred) if "error" not in r}
    ids = [i for i in ref if i in pred]
    c = {k: 0 for k in ("n_ref", "n_pred", "r_loc", "p_loc", "r_tab", "p_tab", "same_rows")}
    diff_rows = []
    for i in ids:
        rs = [s for s in ref[i]["spans"] if s["type"] == "schema"]
        ps = [s for s in pred[i]["spans"] if s["type"] == "schema"]
        c["n_ref"] += len(rs)
        c["n_pred"] += len(ps)
        same_tab = lambda a, b: ov(a, b) and a.get("table") == b.get("table")  # noqa: E731
        c["r_loc"] += sum(any(ov(r, p) for p in ps) for r in rs)
        c["p_loc"] += sum(any(ov(p, r) for r in rs) for p in ps)
        c["r_tab"] += sum(any(same_tab(r, p) for p in ps) for r in rs)
        c["p_tab"] += sum(any(same_tab(p, r) for r in rs) for p in ps)
        only_ref = [f"{r['text']}→{r.get('table')}" for r in rs if not any(same_tab(r, p) for p in ps)]
        only_pred = [f"{p['text']}→{p.get('table')}" for p in ps if not any(same_tab(p, r) for r in rs)]
        if only_ref or only_pred:
            diff_rows.append([i, ref[i]["text"], "|".join(only_ref), "|".join(only_pred)])
        else:
            c["same_rows"] += 1
    loc = prf(c["p_loc"], c["n_pred"], c["r_loc"], c["n_ref"])
    tab = prf(c["p_tab"], c["n_pred"], c["r_tab"], c["n_ref"])
    summary = {"ref": args.ref, "pred": args.pred, "n_rows": len(ids), **c,
               "loc": dict(zip(("p", "r", "f1"), loc)), "loc_table": dict(zip(("p", "r", "f1"), tab)),
               "identical_rows_rate": c["same_rows"] / len(ids) if ids else 0.0}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(out / "diff_rows.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "query", "ref에만", "pred에만"])
        w.writerows(diff_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
