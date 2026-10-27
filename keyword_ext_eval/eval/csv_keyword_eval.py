"""키워드 추출 정답 CSV(test_set/keyword_ext/keyword_eval_samples_50.csv)로 API를 채점한다.

CSV 열: id, query, gold_schema_keywords("a|b"), gold_concept_gliner("텍스트:라벨|..."),
gold_concept_dict("텍스트:도메인:값|..."), gold_derived_schema("묶음|..."), gold_tables, case_type, note

경로별로 따로 잰다.
- schema: API schema span 텍스트 vs gold_schema_keywords (표면형 그대로 비교)
- concept(GLiNER): API concept span vs gold_concept_gliner. 위치가 겹치고 라벨까지 같으면 TP.
  겹치기만 하고 라벨이 다르면 "라벨 오류"로 따로 센다 (채점상 FN+FP).
- concept(사전): gold_concept_dict. 지금 API에는 이 경로가 없어 전부 FN이다.
- derived: concept 라벨 → 대체 스키마 묶음(약물명 → 처방 등). API는 이걸 내지 않으므로,
  API concept 라벨에서 결정론적으로 만들어 본 값(모의)이다.
- tables: (a) schema 키워드만, (b) schema + derived 모의 로 가리킨 테이블 vs gold_tables

    python -m eval.csv_keyword_eval extract --csv ../test_set/keyword_ext/keyword_eval_samples_50.csv --out eval/outputs/kw50_api.jsonl
    python -m eval.csv_keyword_eval score --csv ... --pred eval/outputs/kw50_api.jsonl --out-dir eval/runs/kw50
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from eval.common import append_jsonl, read_jsonl, write_json
from eval.httpclient import RequestFailed, post_json
from eval.keyword_map import KeywordTableMap

LABEL_TO_GROUP = {"약물명": "처방", "진단명 또는 질병명": "진단", "검사명 또는 측정 항목": "측정",
                  "시술명 또는 수술명": "시술"}
DOMAIN_TO_GROUP = {"Visit": "방문", "Gender": "성별"}
GROUP_TABLES_EXTRA = {}  # 대체 묶음 → 테이블은 사전 묶음 표(schema_keyword_table_map.yaml)를 그대로 쓴다


def load_csv(path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    split = lambda s: [x.strip() for x in (s or "").split("|") if x.strip()]  # noqa: E731
    out = []
    for r in rows:
        gliner = []
        for item in split(r["gold_concept_gliner"]):
            text, label = item.rsplit(":", 1)
            gliner.append({"text": text, "label": label})
        cdict = []
        for item in split(r["gold_concept_dict"]):
            text, domain, value = item.split(":")
            cdict.append({"text": text, "domain": domain, "value": value})
        out.append({"id": r["id"], "query": r["query"], "schema": split(r["gold_schema_keywords"]),
                    "gliner": gliner, "dict": cdict, "derived": split(r["gold_derived_schema"]),
                    "tables": split(r["gold_tables"]), "case_type": r["case_type"], "note": r["note"]})
    return out


def locate(query: str, text: str, used: list) -> tuple[int, int] | None:
    """정답 텍스트의 위치. 이미 잡은 정답과 겹치지 않는 첫 위치 ("고혈압 … 혈압"의 혈압이 고혈압 안을 가리키지 않게)."""
    start = query.find(text)
    while start != -1 and any(overlaps((start, start + len(text)), u) for u in used):
        start = query.find(text, start + 1)
    if start == -1:
        return None
    used.append((start, start + len(text)))
    return start, start + len(text)


# ---------------------------------------------------------------- extract


def cmd_extract(args) -> int:
    rows = load_csv(args.csv)
    out = Path(args.out)
    if out.exists() and not args.overwrite:
        done = {r["id"] for r in read_jsonl(out)}
    else:
        out.unlink(missing_ok=True)
        done = set()
    fails = 0
    for r in rows:
        if r["id"] in done:
            continue
        try:
            resp = post_json(args.url, {"text": r["query"]}, timeout=args.timeout, max_retries=3)
            append_jsonl(out, {"id": r["id"], "text": r["query"], "spans": resp.body["spans"],
                               "latency_ms": round(resp.latency_ms, 1)})
        except RequestFailed as e:
            fails += 1
            print(f"[fail] {r['id']}: {e}", file=sys.stderr)
    write_json(out.with_suffix(".meta.json"), {"url": args.url, "csv": str(args.csv),
                                               "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print(f"완료: {len(rows)}건, 실패 {fails}건", file=sys.stderr)
    return 1 if fails else 0


# ---------------------------------------------------------------- score


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if tp else (0.0 if fp + fn else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def score_row(g, pred, km: KeywordTableMap, min_score: float):
    spans = pred["spans"]
    schema_pred = [s["text"] for s in spans if s["type"] == "schema"]
    concepts = [s for s in spans if s["type"] == "concept" and s.get("score", 1) >= min_score]
    res = {"id": g["id"], "case_type": g["case_type"]}

    # schema: 표면형 집합 비교
    gs, ps = set(g["schema"]), set(schema_pred)
    res["schema"] = {"tp": sorted(gs & ps), "fn": sorted(gs - ps), "fp": sorted(ps - gs)}

    # concept(GLiNER): 위치 겹침 + 라벨
    used = []
    gold = []
    for c in g["gliner"]:
        loc = locate(g["query"], c["text"], used)
        gold.append({**c, "loc": loc})
    dict_locs = [locate(g["query"], d["text"], []) for d in g["dict"]]
    tp, fn, label_err = [], [], []
    for c in gold:
        if c["loc"] is None:
            fn.append(f"{c['text']}(원문에 없음)")
            continue
        same = [p for p in concepts if overlaps((p["start"], p["end"]), c["loc"]) and p["category"] == c["label"]]
        other = [p for p in concepts if overlaps((p["start"], p["end"]), c["loc"]) and p["category"] != c["label"]]
        if same:
            exact = any(p["start"] == c["loc"][0] and p["end"] == c["loc"][1] for p in same)
            tp.append({"gold": c["text"], "pred": same[0]["text"], "exact": exact})
        else:
            fn.append(c["text"])
            if other:
                label_err.append(f"{c['text']}→{other[0]['category']}")
    fp = []
    for p in concepts:
        loc = (p["start"], p["end"])
        if any(c["loc"] and overlaps(loc, c["loc"]) and p["category"] == c["label"] for c in gold):
            continue
        hits_dict = any(d and overlaps(loc, d) for d in dict_locs)
        fp.append({"text": p["text"], "category": p["category"], "score": round(p.get("score", 0), 3),
                   "on_gold": any(c["loc"] and overlaps(loc, c["loc"]) for c in gold), "on_dict_gold": hits_dict})
    res["concept"] = {"tp": tp, "fn": fn, "fp": fp, "label_err": label_err, "n_gold": len(gold)}

    # concept(사전): API에 경로 없음 → 전부 FN
    res["concept_dict"] = {"n_gold": len(g["dict"]), "fn": [f"{d['text']}:{d['domain']}" for d in g["dict"]]}

    # derived(모의): API concept 라벨 → 묶음
    dp = {LABEL_TO_GROUP[p["category"]] for p in concepts if p["category"] in LABEL_TO_GROUP}
    dg = set(g["derived"])
    res["derived"] = {"tp": sorted(dg & dp), "fn": sorted(dg - dp), "fp": sorted(dp - dg)}

    # tables
    t_schema = []
    for w in schema_pred:
        for t in km.resolve(w).tables:
            if t not in t_schema:
                t_schema.append(t)
    t_both = list(t_schema)
    for grp in dp:
        for t in km.group_to_tables.get(grp, []):
            if t not in t_both:
                t_both.append(t)
    gt = set(g["tables"])
    res["tables"] = {}
    for name, pt in (("schema", set(t_schema)), ("schema+derived", set(t_both))):
        res["tables"][name] = {"pred": sorted(pt), "tp": sorted(gt & pt), "fn": sorted(gt - pt), "fp": sorted(pt - gt),
                               "covered": gt <= pt}
    return res


def agg(results, key, sub=None):
    tp = fp = fn = 0
    for r in results:
        x = r[key] if sub is None else r[key][sub]
        tp += len(x["tp"]); fp += len(x["fp"]); fn += len(x["fn"])
    return prf(tp, fp, fn)


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}"


def cmd_score(args) -> int:
    gold = load_csv(args.csv)
    preds = {r["id"]: r for r in read_jsonl(args.pred)}
    km = KeywordTableMap(warn=False)
    results = [score_row(g, preds[g["id"]], km, args.min_score) for g in gold if g["id"] in preds]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    summary = {"n": len(results), "min_score": args.min_score,
               "schema": agg(results, "schema"), "concept": agg(results, "concept"),
               "derived_sim": agg(results, "derived"),
               "concept_dict": {"n_gold": sum(r["concept_dict"]["n_gold"] for r in results), "recall": 0.0},
               "tables": {k: agg(results, "tables", k) for k in ("schema", "schema+derived")},
               "coverage": {k: sum(r["tables"][k]["covered"] for r in results) / len(results)
                            for k in ("schema", "schema+derived")},
               "concept_exact_tp": sum(t["exact"] for r in results for t in r["concept"]["tp"]),
               "concept_label_err": sum(len(r["concept"]["label_err"]) for r in results)}
    # 테이블 person 제외
    np_ = defaultdict(lambda: [0, 0, 0])
    for r in results:
        for k in ("schema", "schema+derived"):
            t = r["tables"][k]
            np_[k][0] += sum(x != "person" for x in t["tp"])
            np_[k][1] += sum(x != "person" for x in t["fp"])
            np_[k][2] += sum(x != "person" for x in t["fn"])
    summary["tables_no_person"] = {k: prf(*v) for k, v in np_.items()}
    # 테이블별
    per_table = defaultdict(lambda: Counter())
    for r in results:
        for k in ("schema", "schema+derived"):
            for kind in ("tp", "fp", "fn"):
                for t in r["tables"][k][kind]:
                    per_table[(k, t)][kind] += 1
    summary["per_table"] = {f"{k}|{t}": prf(c["tp"], c["fp"], c["fn"]) for (k, t), c in per_table.items()}
    # case_type별
    by_case = defaultdict(list)
    for r in results:
        by_case[r["case_type"]].append(r)
    summary["by_case"] = {c: {"n": len(rs), "schema": agg(rs, "schema"), "concept": agg(rs, "concept"),
                              "coverage_schema": sum(r["tables"]["schema"]["covered"] for r in rs) / len(rs),
                              "coverage_both": sum(r["tables"]["schema+derived"]["covered"] for r in rs) / len(rs)}
                          for c, rs in by_case.items()}
    write_json(out / "kw50_scores.json", summary)

    # 문장별 상세 CSV
    with open(out / "kw50_per_query.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "case_type", "query", "schema_FN", "schema_FP", "concept_FN", "concept_label_err",
                    "concept_FP", "concept_dict_FN", "tables_gold", "tables_pred(schema)", "tables_FN(schema)",
                    "tables_FP(schema)", "tables_FN(schema+derived)", "note"])
        gi = {g["id"]: g for g in gold}
        for r in results:
            g = gi[r["id"]]
            w.writerow([r["id"], r["case_type"], g["query"], "|".join(r["schema"]["fn"]), "|".join(r["schema"]["fp"]),
                        "|".join(r["concept"]["fn"]), "|".join(r["concept"]["label_err"]),
                        "|".join(f"{p['text']}:{p['category']}({p['score']})" for p in r["concept"]["fp"]),
                        "|".join(r["concept_dict"]["fn"]), "|".join(g["tables"]),
                        "|".join(r["tables"]["schema"]["pred"]), "|".join(r["tables"]["schema"]["fn"]),
                        "|".join(r["tables"]["schema"]["fp"]), "|".join(r["tables"]["schema+derived"]["fn"]), g["note"]])
    write_json(out / "kw50_per_query.json", results)

    s = summary
    print(f"문장 {s['n']}건 (concept score ≥ {args.min_score})")
    for k in ("schema", "concept", "derived_sim"):
        m = s[k]
        print(f"  {k:<12} P {pct(m['precision'])} R {pct(m['recall'])} F1 {pct(m['f1'])}  (TP {m['tp']} FP {m['fp']} FN {m['fn']})")
    print(f"  concept 경계 정확 TP {s['concept_exact_tp']}, 라벨 오류 {s['concept_label_err']}, 사전 concept 정답 {s['concept_dict']['n_gold']}개 전부 FN")
    for k in ("schema", "schema+derived"):
        m, mn = s["tables"][k], s["tables_no_person"][k]
        print(f"  tables[{k}] P {pct(m['precision'])} R {pct(m['recall'])} F1 {pct(m['f1'])} 커버리지 {pct(s['coverage'][k])}"
              f" | person 제외 P {pct(mn['precision'])} R {pct(mn['recall'])}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--csv", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--url", default="http://localhost:8001/keyword-extraction")
    e.add_argument("--timeout", type=float, default=60)
    e.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("--csv", required=True)
    s.add_argument("--pred", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--min-score", type=float, default=0.0, help="concept span 점수 하한 (API threshold 위로만 의미 있음)")
    args = ap.parse_args(argv)
    return cmd_extract(args) if args.cmd == "extract" else cmd_score(args)


if __name__ == "__main__":
    sys.exit(main())
