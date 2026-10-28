"""키워드 추출 정답 CSV(test_set/keyword_ext/keyword_eval_samples_50.csv)로 API를 채점한다.

CSV 열: id, query, gold_schema_keywords("a|b"), gold_concept_gliner("텍스트:라벨|..."),
gold_concept_dict("텍스트:도메인:값|..."), gold_derived_schema("묶음|..."), gold_tables, case_type, note

경로별로 따로 잰다.
- schema: API schema span 텍스트 vs gold_schema_keywords (표면형 그대로 비교)
- concept(GLiNER): API concept span vs gold_concept_gliner. 위치가 겹치고 라벨까지 같으면 TP.
  겹치기만 하고 라벨이 다르면 "라벨 오류"로 따로 센다 (채점상 FN+FP).
- concept(사전): gold_concept_dict vs API의 방문 유형/성별 concept span (API v2부터, score 없음).
  위치가 겹치고 도메인(Visit=방문 유형, Gender=성별)이 같으면 TP. 응답에 값(입원/여성 등)이
  없어 값 정규화는 채점하지 않는다. v1처럼 경로가 없으면 전부 FN.
- derived: concept 라벨 → 대체 스키마 묶음(약물명 → 처방, 방문 유형 → 방문 등). API는 이걸 내지
  않으므로, API concept 라벨에서 결정론적으로 만들어 본 값(모의)이다.
- tables: (a) schema 키워드만, (b) schema + derived 모의 로 가리킨 테이블 vs gold_tables

    python -m eval.csv_keyword_eval extract --csv ../test_set/keyword_ext/keyword_eval_samples_50.csv --out eval/outputs/kw50_api.jsonl
    python -m eval.csv_keyword_eval extract --system prod-llm --csv ... --out eval/outputs/kw50_prod_llm.jsonl  # 운영 LLM 기준선
    python -m eval.csv_keyword_eval score --csv ... --pred eval/outputs/kw50_api.jsonl --out-dir eval/runs/kw50
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from pathlib import Path

from eval.common import append_jsonl, load_dotenv, read_jsonl, write_json
from eval.extractors import ExtractError, PreflightError
from eval.extractors.prod_llm import ProdLLMExtractor, mock_chat_post
from eval.httpclient import RequestFailed, post_json
from eval.keyword_map import KeywordTableMap

LABEL_TO_GROUP = {"약물명": "처방", "진단명 또는 질병명": "진단", "검사명 또는 측정 항목": "측정",
                  "시술명 또는 수술명": "시술"}
# API의 사전 concept category → 정답 CSV의 도메인, 대체 스키마 묶음
DICT_CATEGORY_TO_DOMAIN = {"방문 유형": "Visit", "성별": "Gender"}
DOMAIN_TO_GROUP = {"Visit": "방문", "Gender": "성별"}
# 대체 묶음 → 테이블은 사전 묶음 표(schema_keyword_table_map.yaml)를 그대로 쓴다


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


def _make_extractor(args):
    """→ (질의 하나를 받아 {spans, latency_ms, …}를 돌려주는 함수, 이어하기 판정용 설정)."""
    if args.system == "api":
        def call(text):
            resp = post_json(args.url, {"text": text}, timeout=args.timeout, max_retries=3)
            return {"spans": resp.body["spans"], "latency_ms": round(resp.latency_ms, 1)}
        return call, {"system": "api", "url": args.url}
    ex = ProdLLMExtractor(post=mock_chat_post if args.mock else None)
    if args.mock:
        ex.base_url, ex.model = ex.base_url or "mock://llm", ex.model or "mock"
        ex.system_prompt = ex.system_prompt or "(mock)"
    ex.preflight()
    return ex.extract, {**ex.config(), "mock": args.mock}


def cmd_extract(args) -> int:
    load_dotenv()
    rows = load_csv(args.csv)
    out = Path(args.out)
    meta_path = out.with_suffix(".meta.json")
    try:
        call, config = _make_extractor(args)
    except PreflightError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2
    if out.exists() and not args.overwrite:
        old = json.loads(meta_path.read_text(encoding="utf-8")).get("config") if meta_path.exists() else None
        if old is not None and old != config:
            print(f"{out}: 설정이 다른 기존 결과가 있습니다 (모델/프롬프트/URL 등). 새 파일로 저장하거나 --overwrite",
                  file=sys.stderr)
            return 2
        done = {r["id"] for r in read_jsonl(out)}
    else:
        out.unlink(missing_ok=True)
        done = set()
    failed_path = out.with_suffix(".failed.jsonl")
    failed_path.unlink(missing_ok=True)
    todo = [r for r in rows if r["id"] not in done]

    def one(r):
        try:
            return {"id": r["id"], "text": r["query"], **call(r["query"])}
        except (RequestFailed, ExtractError) as e:
            return {"id": r["id"], "text": r["query"], "error": str(e), "raw": getattr(e, "raw", None)}

    fails = 0
    with ThreadPoolExecutor(max(1, args.concurrency)) as pool:
        for row in pool.map(one, todo):
            if "error" in row:
                fails += 1
                append_jsonl(failed_path, row)
                print(f"[fail] {row['id']}: {row['error']}", file=sys.stderr)
            else:
                append_jsonl(out, row)
    write_json(meta_path, {"config": config, "csv": str(args.csv),
                           "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print(f"완료: {len(rows)}건 중 {len(todo)}건 추출, 실패 {fails}건"
          + (f" (실패 목록 {failed_path})" if fails else ""), file=sys.stderr)
    return 1 if fails else 0


# ---------------------------------------------------------------- score


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if tp else (0.0 if fp + fn else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1}


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def score_row(g, pred, km: KeywordTableMap, min_score: float, ignore_label: bool = False, llm_table: bool = False):
    spans = pred["spans"]
    schema_spans = [s for s in spans if s["type"] == "schema"]
    schema_pred = [s["text"] for s in schema_spans]
    concepts = [s for s in spans if s["type"] == "concept" and s["category"] not in DICT_CATEGORY_TO_DOMAIN
                and (s.get("score") is None or s["score"] >= min_score)]
    dict_concepts = [s for s in spans if s["type"] == "concept" and s["category"] in DICT_CATEGORY_TO_DOMAIN]
    res = {"id": g["id"], "case_type": g["case_type"]}

    # schema: 표면형 집합 비교
    gs, ps = set(g["schema"]), set(schema_pred)
    res["schema"] = {"tp": sorted(gs & ps), "fn": sorted(gs - ps), "fp": sorted(ps - gs)}
    # schema(겹침): 정답 표현이 나오는 위치와 예측 span이 겹치면 맞힘. LLM은 "처방 이력"처럼 구 단위로 내서
    # 표면형 집합 비교로는 정답 "처방"과 다르게 계산되므로 참고 지표로 같이 본다.
    occ = {k: [(i, i + len(k)) for i in range(len(g["query"])) if g["query"].startswith(k, i)] for k in gs}
    hit = lambda sp, k: any(overlaps((sp["start"], sp["end"]), o) for o in occ[k])  # noqa: E731
    res["schema_overlap"] = {"tp": sorted(k for k in gs if any(hit(sp, k) for sp in schema_spans)),
                             "fn": sorted(k for k in gs if not any(hit(sp, k) for sp in schema_spans)),
                             "fp": sorted({sp["text"] for sp in schema_spans if not any(hit(sp, k) for k in gs)})}

    # concept(GLiNER): 위치 겹침 + 라벨 (ignore_label이면 위치만)
    lab_ok = lambda p, c: ignore_label or p["category"] == c["label"]  # noqa: E731
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
        same = [p for p in concepts if overlaps((p["start"], p["end"]), c["loc"]) and lab_ok(p, c)]
        other = [p for p in concepts if overlaps((p["start"], p["end"]), c["loc"]) and not lab_ok(p, c)]
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
        if any(c["loc"] and overlaps(loc, c["loc"]) and lab_ok(p, c) for c in gold):
            continue
        hits_dict = any(d and overlaps(loc, d) for d in dict_locs)
        fp.append({"text": p["text"], "category": p["category"], "score": round(p.get("score", 0), 3),
                   "on_gold": any(c["loc"] and overlaps(loc, c["loc"]) for c in gold), "on_dict_gold": hits_dict})
    res["concept"] = {"tp": tp, "fn": fn, "fp": fp, "label_err": label_err, "n_gold": len(gold)}

    # concept(사전): API에 경로 없음 → 전부 FN
    used = []
    dgold = [{**d, "loc": locate(g["query"], d["text"], used)} for d in g["dict"]]
    dtp, dfn, dfp, dlab = [], [], [], []
    for d in dgold:
        hit = [p for p in dict_concepts if d["loc"] and overlaps((p["start"], p["end"]), d["loc"])]
        if any(DICT_CATEGORY_TO_DOMAIN[p["category"]] == d["domain"] for p in hit):
            dtp.append(f"{d['text']}:{d['domain']}")
        else:
            dfn.append(f"{d['text']}:{d['domain']}")
            if hit:
                dlab.append(f"{d['text']}→{hit[0]['category']}")
    for p in dict_concepts:
        if not any(d["loc"] and overlaps((p["start"], p["end"]), d["loc"])
                   and DICT_CATEGORY_TO_DOMAIN[p["category"]] == d["domain"] for d in dgold):
            dfp.append(f"{p['text']}:{p['category']}")
    res["concept_dict"] = {"tp": dtp, "fn": dfn, "fp": dfp, "label_err": dlab, "n_gold": len(g["dict"])}

    # derived(모의): API concept 라벨 → 묶음
    dp = {LABEL_TO_GROUP[p["category"]] for p in concepts if p["category"] in LABEL_TO_GROUP}
    dp |= {DOMAIN_TO_GROUP[DICT_CATEGORY_TO_DOMAIN[p["category"]]] for p in dict_concepts}
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
    variants = [("schema", set(t_schema)), ("schema+derived", set(t_both))]
    if llm_table:  # 운영 LLM이 schema 키워드마다 직접 지정한 table
        t_llm = {sp["table"] for sp in schema_spans if sp.get("table")}
        t_llm_both = t_llm | {t for grp in dp for t in km.group_to_tables.get(grp, [])}
        variants += [("llm_table", t_llm), ("llm_table+derived", t_llm_both)]
    for name, pt in variants:
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
    llm_table = any("table" in sp for p in preds.values() for sp in p["spans"])
    results = [score_row(g, preds[g["id"]], km, args.min_score, args.ignore_concept_label, llm_table)
               for g in gold if g["id"] in preds]
    variants = list(results[0]["tables"]) if results else []
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    summary = {"n": len(results), "min_score": args.min_score, "ignore_concept_label": args.ignore_concept_label,
               "schema": agg(results, "schema"), "schema_overlap": agg(results, "schema_overlap"),
               "concept": agg(results, "concept"),
               "derived_sim": agg(results, "derived"),
               "concept_dict": agg(results, "concept_dict"),
               "tables": {k: agg(results, "tables", k) for k in variants},
               "coverage": {k: sum(r["tables"][k]["covered"] for r in results) / len(results) for k in variants},
               "concept_exact_tp": sum(t["exact"] for r in results for t in r["concept"]["tp"]),
               "concept_label_err": sum(len(r["concept"]["label_err"]) for r in results)}
    # 테이블 person 제외
    np_ = defaultdict(lambda: [0, 0, 0])
    for r in results:
        for k in variants:
            t = r["tables"][k]
            np_[k][0] += sum(x != "person" for x in t["tp"])
            np_[k][1] += sum(x != "person" for x in t["fp"])
            np_[k][2] += sum(x != "person" for x in t["fn"])
    summary["tables_no_person"] = {k: prf(*v) for k, v in np_.items()}
    # 테이블별
    per_table = defaultdict(lambda: Counter())
    for r in results:
        for k in variants:
            for kind in ("tp", "fp", "fn"):
                for t in r["tables"][k][kind]:
                    per_table[(k, t)][kind] += 1
    summary["per_table"] = {f"{k}|{t}": prf(c["tp"], c["fp"], c["fn"]) for (k, t), c in per_table.items()}
    # case_type별
    by_case = defaultdict(list)
    for r in results:
        by_case[r["case_type"]].append(r)
    summary["by_case"] = {c: {"n": len(rs), "schema": agg(rs, "schema"), "concept": agg(rs, "concept"),
                              "concept_dict": agg(rs, "concept_dict"),
                              "coverage_schema": sum(r["tables"]["schema"]["covered"] for r in rs) / len(rs),
                              "coverage_both": sum(r["tables"]["schema+derived"]["covered"] for r in rs) / len(rs)}
                          for c, rs in by_case.items()}
    write_json(out / "kw50_scores.json", summary)

    # 문장별 상세 CSV
    with open(out / "kw50_per_query.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "case_type", "query", "schema_FN", "schema_FP", "concept_FN", "concept_label_err",
                    "concept_FP", "concept_dict_FN", "concept_dict_FP", "tables_gold", "tables_pred(schema)", "tables_FN(schema)",
                    "tables_FP(schema)", "tables_FN(schema+derived)", "note"])
        gi = {g["id"]: g for g in gold}
        for r in results:
            g = gi[r["id"]]
            w.writerow([r["id"], r["case_type"], g["query"], "|".join(r["schema"]["fn"]), "|".join(r["schema"]["fp"]),
                        "|".join(r["concept"]["fn"]), "|".join(r["concept"]["label_err"]),
                        "|".join(f"{p['text']}:{p['category']}({p['score']})" for p in r["concept"]["fp"]),
                        "|".join(r["concept_dict"]["fn"]), "|".join(r["concept_dict"]["fp"]), "|".join(g["tables"]),
                        "|".join(r["tables"]["schema"]["pred"]), "|".join(r["tables"]["schema"]["fn"]),
                        "|".join(r["tables"]["schema"]["fp"]), "|".join(r["tables"]["schema+derived"]["fn"]), g["note"]])
    write_json(out / "kw50_per_query.json", results)

    s = summary
    print(f"문장 {s['n']}건 (concept score ≥ {args.min_score})")
    for k in ("schema", "schema_overlap", "concept", "concept_dict", "derived_sim"):
        m = s[k]
        print(f"  {k:<14} P {pct(m['precision'])} R {pct(m['recall'])} F1 {pct(m['f1'])}  (TP {m['tp']} FP {m['fp']} FN {m['fn']})")
    print(f"  concept 경계 정확 TP {s['concept_exact_tp']}, 라벨 오류 {s['concept_label_err']}")
    for k in variants:
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
    e.add_argument("--system", choices=["api", "prod-llm"], default="api",
                   help="api: 키워드 추출 API / prod-llm: 운영 프롬프트 LLM (설정은 .env의 PROD_LLM_*)")
    e.add_argument("--url", default="http://localhost:8001/keyword-extraction", help="--system api일 때")
    e.add_argument("--timeout", type=float, default=60, help="--system api일 때 (LLM은 PROD_LLM_TIMEOUT)")
    e.add_argument("--concurrency", type=int, default=1)
    e.add_argument("--mock", action="store_true", help="prod-llm: 서버 없이 가짜 응답으로 흐름 확인")
    e.add_argument("--overwrite", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("--csv", required=True)
    s.add_argument("--pred", required=True)
    s.add_argument("--out-dir", required=True)
    s.add_argument("--min-score", type=float, default=0.0, help="concept span 점수 하한 (API threshold 위로만 의미 있음)")
    s.add_argument("--ignore-concept-label", action="store_true",
                   help="concept는 위치만 맞으면 TP (라벨을 안 주거나 다른 체계를 쓰는 LLM 비교용, 참고 지표)")
    args = ap.parse_args(argv)
    return cmd_extract(args) if args.cmd == "extract" else cmd_score(args)


if __name__ == "__main__":
    sys.exit(main())
