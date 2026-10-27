"""GLiNER `/extract`(zero-shot)의 "방문 유형"/"성별" 라벨 평가.

정답은 정답 SQL에서 만든다. SQL이 visit_concept_id/gender_concept_id로 거르는 개념이 있으면,
그 개념을 가리키는 질의 문장 속 표현(예: 9201 → "입원", 8532 → "여성")을 정답 span으로 삼는다.
SQL이 거르지 않는 문장은 전부 음성이라, 그 문장에서 나온 두 라벨 예측은 모두 오탐이다.

추출은 낮은 threshold(기본 0.05)로 한 번만 돌려 점수를 같이 저장하고, threshold별 점수는
채점 단계에서 거른다. GLiNER는 점수 높은 span부터 겹치는 span을 지우므로, 낮은 threshold
결과를 t 이상만 남기면 threshold=t로 돌린 결과와 같다.

    python -m eval.visit_gender_eval extract --data ../test_set/slot.jsonl --out eval/outputs/vg_6.jsonl
    python -m eval.visit_gender_eval score --pred eval/outputs/vg_6.jsonl --data ... --out-dir eval/runs/vg
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from eval.common import append_jsonl, load_datasets, read_jsonl, write_json
from eval.httpclient import RequestFailed, post_json

VISIT, GENDER = "방문 유형", "성별"
MED_LABELS = ["진단명 또는 질병명", "약물명", "검사명 또는 측정 항목", "시술명 또는 수술명"]
ALL_LABELS = MED_LABELS + [VISIT, GENDER]
TARGETS = (VISIT, GENDER)
THRESHOLDS = [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

# 개념 → 문장 속 표현. 앞에 있는 것부터 찾아서(262 "응급실 입원 방문"이 9201 "입원"보다 먼저) 겹치지 않게 잡는다.
SURFACE = {
    ("visit_concept_id", 262): (VISIT, r"응급실\s*입원(?:\s*방문)?"),
    ("visit_concept_id", 9201): (VISIT, r"입원(?:\s*방문)?"),
    ("visit_concept_id", 9202): (VISIT, r"외래(?:\s*방문)?"),
    ("visit_concept_id", 9203): (VISIT, r"응급실?(?:\s*방문)?"),
    ("gender_concept_id", 8532): (GENDER, r"여성|여자"),
    ("gender_concept_id", 8507): (GENDER, r"남성|남자"),
}
# SQL에 개념이 없는데 문장에 나오면 "어려운 음성"으로 따로 본다 (예: "만성 외래 복막투석")
LEXICON = re.compile(r"입원|외래|응급|여성|여자|남성|남자")

_ID_RE = r"{col}\s*(?:=\s*(\d+)|IN\s*\(\s*(?:SELECT\s+descendant_concept_id\s+FROM\s+concept_ancestor\s+WHERE\s+ancestor_concept_id\s+IN\s*\()?([\d,\s]+)\))"


def sql_concepts(sql: str) -> set[tuple[str, int]]:
    out = set()
    for col in ("visit_concept_id", "gender_concept_id"):
        for m in re.finditer(_ID_RE.format(col=col), sql, re.I):
            for x in (m.group(1) or m.group(2)).split(","):
                if x.strip():
                    out.add((col, int(x)))
    return out


def build_gold(text: str, sql: str) -> tuple[list[dict], list[str]]:
    """(정답 span 목록, 문장에서 표현을 못 찾은 개념) 를 돌려준다."""
    concepts = sql_concepts(sql)
    gold, taken, missing = [], [], []
    for key, (label, pat) in SURFACE.items():
        if key not in concepts:
            continue
        found = False
        for m in re.finditer(pat, text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            gold.append({"start": m.start(), "end": m.end(), "text": m.group(), "label": label, "concept": key[1]})
            found = True
        if not found:
            missing.append(f"{key[0]}={key[1]}")
    unknown = [f"{c}={i}" for c, i in concepts if (c, i) not in SURFACE]
    return sorted(gold, key=lambda g: g["start"]), missing + unknown


# ---------------------------------------------------------------- extract


def cmd_extract(args) -> int:
    records = load_datasets(args.data)
    if args.limit:
        records = records[: args.limit]
    out = Path(args.out)
    meta = {"url": args.url, "labels": args.labels, "threshold": args.threshold}
    meta_path = out.with_suffix(".meta.json")
    if out.exists() and meta_path.exists() and json.loads(meta_path.read_text())["config"] != meta and not args.overwrite:
        print(f"{out}: 설정이 다른 기존 결과가 있습니다. --overwrite로 새로 시작하세요.", file=sys.stderr)
        return 2
    if args.overwrite and out.exists():
        out.unlink()
    done = {r["id"] for r in read_jsonl(out)} if out.exists() else set()
    todo = [r for r in records if r["id"] not in done]
    print(f"{len(records)}건 중 {len(done)}건 완료, {len(todo)}건 추출", file=sys.stderr)
    write_json(meta_path, {"config": meta, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")})

    def one(rec):
        payload = {"text": rec["text"], "labels": args.labels, "threshold": args.threshold}
        try:
            r = post_json(args.url, payload, timeout=args.timeout, max_retries=3)
            return {"id": rec["id"], "text": rec["text"], "entities": r.body, "latency_ms": round(r.latency_ms, 1)}
        except RequestFailed as e:
            return {"id": rec["id"], "error": str(e)}

    fails = 0
    t0 = time.time()
    with ThreadPoolExecutor(args.concurrency) as pool:
        for i, row in enumerate(pool.map(one, todo), 1):
            if "error" in row:
                fails += 1
                append_jsonl(out.with_suffix(".failed.jsonl"), row)
            else:
                append_jsonl(out, row)
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} ({time.time() - t0:.0f}s)", file=sys.stderr)
    print(f"완료: 실패 {fails}건", file=sys.stderr)
    return 1 if fails else 0


# ---------------------------------------------------------------- score


def overlaps(a, b) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def prf(tp_pred, n_pred, tp_gold, n_gold):
    p = tp_pred / n_pred if n_pred else None
    r = tp_gold / n_gold if n_gold else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if n_pred or n_gold else None)
    return {"n_pred": n_pred, "tp_pred": tp_pred, "n_gold": n_gold, "tp_gold": tp_gold,
            "precision": p, "recall": r, "f1": f1}


def score_label(items, label, th, exact=False):
    """span 단위. 예측은 같은 라벨 정답과 겹치면 TP, 정답은 같은 라벨 예측과 하나라도 겹치면 맞힘."""
    hit = (lambda p, g: p["start"] == g["start"] and p["end"] == g["end"]) if exact else overlaps
    n_pred = tp_pred = n_gold = tp_gold = 0
    q = Counter()  # 문장 단위: 정답 있는 문장 중 하나라도 맞힘 / 정답 없는 문장 중 오탐 있음
    for it in items:
        preds = [p for p in it["pred"] if p["label"] == label and p["score"] >= th]
        gold = [g for g in it["gold"] if g["label"] == label]
        n_pred += len(preds)
        tp_pred += sum(any(hit(p, g) for g in gold) for p in preds)
        n_gold += len(gold)
        tp_gold += sum(any(hit(p, g) for p in preds) for g in gold)
        if gold:
            q["pos"] += 1
            q["pos_all_hit"] += all(any(hit(p, g) for p in preds) for g in gold)
        else:
            q["neg"] += 1
            q["neg_fp"] += bool(preds)
    m = prf(tp_pred, n_pred, tp_gold, n_gold)
    m["query"] = {"pos": q["pos"], "pos_all_hit": q["pos_all_hit"], "neg": q["neg"], "neg_with_fp": q["neg_fp"]}
    return m


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}"


def cmd_score(args) -> int:
    records = {r["id"]: r for r in load_datasets(args.data)}
    preds = {r["id"]: r for r in read_jsonl(args.pred)}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items, gold_issues = [], []
    for rid, rec in records.items():
        if rid not in preds:
            continue
        gold, missing = build_gold(rec["text"], rec["sql"])
        if missing:
            gold_issues.append({"id": rid, "text": rec["text"], "missing": ";".join(missing)})
        items.append({"id": rid, "text": rec["text"], "gold": gold, "pred": preds[rid]["entities"],
                      "hard_neg": not gold and bool(LEXICON.search(rec["text"]))})
    if len(items) < len(records):
        print(f"[warn] 예측 없는 질의 {len(records) - len(items)}건은 빼고 채점", file=sys.stderr)

    uniq = {}
    for it in items:
        uniq.setdefault(it["text"], it)
    scopes = {"all": items, "dedup": list(uniq.values())}
    result = {"pred": args.pred, "n": len(items), "n_dedup": len(uniq), "gold_issues": len(gold_issues),
              "gold_counts": {lab: Counter(g["text"] for it in items for g in it["gold"] if g["label"] == lab)
                              for lab in TARGETS},
              "sweep": {}}
    for scope, its in scopes.items():
        for lab in TARGETS:
            for th in THRESHOLDS:
                result["sweep"][f"{scope}|{lab}|{th}"] = {
                    "overlap": score_label(its, lab, th), "exact": score_label(its, lab, th, exact=True)}
    write_json(out / "visit_gender_scores.json", result)

    # 오탐/미탐 상세 (지정 threshold)
    th = args.threshold
    fp_rows, fn_rows = [], []
    fp_text = {lab: Counter() for lab in TARGETS}
    fn_conf = {lab: Counter() for lab in TARGETS}  # 놓친 정답 span이 다른 라벨로 잡혔는지
    for it in items:
        for lab in TARGETS:
            gold = [g for g in it["gold"] if g["label"] == lab]
            for p in it["pred"]:
                if p["label"] == lab and p["score"] >= th and not any(overlaps(p, g) for g in gold):
                    fp_text[lab][p["text"]] += 1
                    fp_rows.append({"id": it["id"], "label": lab, "pred": p["text"], "score": round(p["score"], 3),
                                    "hard_neg": it["hard_neg"], "text": it["text"]})
            for g in gold:
                if any(p["label"] == lab and p["score"] >= th and overlaps(p, g) for p in it["pred"]):
                    continue
                other = sorted({p["label"] for p in it["pred"] if p["score"] >= th and overlaps(p, g)})
                best = max((p["score"] for p in it["pred"] if p["label"] == lab and overlaps(p, g)), default=None)
                fn_conf[lab]["/".join(other) or "(아무 라벨로도 안 잡힘)"] += 1
                fn_rows.append({"id": it["id"], "label": lab, "gold": g["text"], "best_score_same_label":
                                None if best is None else round(best, 3), "other_labels": "/".join(other),
                                "text": it["text"]})
    for name, rows in (("fp", fp_rows), ("fn", fn_rows), ("gold_issues", gold_issues)):
        path = out / f"visit_gender_{name}.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

    # 콘솔 요약
    print(f"질의 {len(items)}건 (중복 제거 {len(uniq)}건), 정답 표현을 못 찾은 질의 {len(gold_issues)}건")
    for lab in TARGETS:
        print(f"\n[{lab}] 정답 {dict(result['gold_counts'][lab])}")
        print("  th    P(ovl)  R(ovl)  F1     P(ex)  R(ex)  | 정답문장 전부맞힘  음성문장 오탐")
        for t in THRESHOLDS:
            s = result["sweep"][f"all|{lab}|{t}"]
            o, e, q = s["overlap"], s["exact"], s["overlap"]["query"]
            print(f"  {t:<5} {pct(o['precision']):>6} {pct(o['recall']):>6} {pct(o['f1']):>6} "
                  f"{pct(e['precision']):>6} {pct(e['recall']):>6}  | {q['pos_all_hit']}/{q['pos']}"
                  f"            {q['neg_with_fp']}/{q['neg']}  (예측 {o['n_pred']})")
        print(f"  th={th} 오탐 상위: {fp_text[lab].most_common(12)}")
        print(f"  th={th} 미탐 시 다른 라벨: {dict(fn_conf[lab])}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--data", action="append", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--url", default="http://localhost:8002/extract")
    e.add_argument("--labels", type=lambda s: s.split(","), default=ALL_LABELS, help="콤마 구분")
    e.add_argument("--threshold", type=float, default=0.05)
    e.add_argument("--timeout", type=float, default=60)
    e.add_argument("--concurrency", type=int, default=1)
    e.add_argument("--limit", type=int)
    e.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("--data", action="append", required=True)
    s.add_argument("--pred", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--threshold", type=float, default=0.5, help="오탐/미탐 상세를 뽑을 threshold")
    args = ap.parse_args(argv)
    return cmd_extract(args) if args.cmd == "extract" else cmd_score(args)


if __name__ == "__main__":
    sys.exit(main())
