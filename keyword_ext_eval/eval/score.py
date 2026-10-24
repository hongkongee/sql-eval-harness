"""채점: 추출 결과 파일(들)을 정답 SQL의 테이블과 대조해 테이블 단위 커버리지를 낸다.

    python -m eval.score --data ../test_set/paraphrase.jsonl --pred eval/outputs/api.jsonl [--pred ...] [--concept]

판정: 정답 SQL이 쓰는 대상 테이블(8개)마다, 그 테이블을 가리키는 키워드가 하나 이상 있으면 덮인 것.
시스템 이름은 pred 파일 이름(확장자 제외)이다. 한 pred 파일에서 여러 "변형(variant)"이 나온다:
  <name>          schema_keywords(표면형 → 사전 묶음 → 테이블)
  <name>_label    schema_labels가 있으면(gliner) 라벨 → 테이블
  <name>_concept  --concept이고 concept span에 label이 있으면 schema + concept 라벨 → 테이블
출력: eval/runs/<타임스탬프>/ (README 참고)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from eval.common import EVAL_DIR, load_datasets, load_dotenv, read_jsonl, write_json
from eval.keyword_map import MAPS_DIR, KeywordTableMap, LabelTableMap
from eval.sql_tables import TARGET_TABLES, TableCache

RUNS_DIR = EVAL_DIR / "runs"
ALL = "__all__"

# ── 템플릿 중복 제거 ────────────────────────────────────────────────────

_INPUT_CONCEPT_RE = re.compile(r'^\s*-\s*"(.+?)"\s*→', re.M)
_DATE_RE = re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{4}년\s*\d{1,2}월(\s*\d{1,2}일)?")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def concept_strings(record: dict, fallback_spans: list | None) -> list[str]:
    """마스킹할 concept 문자열. 데이터의 input([재료] 개념 값 조건)에 있으면 그걸 쓰고 - 시스템과
    무관하게 같은 기준이 되도록 - 없으면 기준 pred(API)의 concept span 텍스트를 쓴다."""
    found = _INPUT_CONCEPT_RE.findall(record["row"].get("input") or "")
    if not found and fallback_spans:
        found = [s["text"] for s in fallback_spans]
    return sorted({c for c in found if c and c in record["text"]}, key=len, reverse=True)


def template_key(record: dict, fallback_spans: list | None) -> str:
    text = record["text"]
    for c in concept_strings(record, fallback_spans):
        text = text.replace(c, "<C>")
    text = _DATE_RE.sub("<D>", text)
    text = _NUM_RE.sub("<N>", text)
    return re.sub(r"\s+", " ", text).strip()


# ── 변형별 예측 테이블 ──────────────────────────────────────────────────

class Variant:
    def __init__(self, name: str, source: str, kind: str, preds: dict, kmap: KeywordTableMap,
                 label_map: LabelTableMap | None = None):
        self.name, self.source, self.kind = name, source, kind
        self.preds, self.kmap, self.label_map = preds, kmap, label_map

    def predict(self, row: dict) -> dict:
        """→ {tables: set, signals: [(word, tables, how)], unmapped: [word]}"""
        signals = []
        if self.kind == "label":
            for item in row.get("schema_labels", []):
                signals.append((f"{item['text']}[{item['label']}]", self.label_map.tables(item["label"]), "label"))
        else:
            for w in row.get("schema_keywords", []):
                r = self.kmap.resolve(w)
                signals.append((w, r.tables, r.how))
            if self.kind == "concept":
                for s in row.get("concept_spans", []):
                    signals.append((f"{s['text']}[{s.get('label')}]", self.label_map.tables(s.get("label")), "concept"))
        tables = {t for _, ts, _ in signals for t in ts}
        unmapped = [w for w, _, how in signals if how == "unmapped"]
        return {"tables": tables, "signals": signals, "unmapped": unmapped}


def build_variants(pred_paths: list[str], kmap: KeywordTableMap, concept: bool) -> tuple[list[Variant], list[str], dict]:
    variants, warnings, metas = [], [], {}
    gliner_labels = LabelTableMap(MAPS_DIR / "gliner_schema_label_table_map.yaml")
    concept_labels = LabelTableMap(MAPS_DIR / "concept_label_table_map.yaml")
    for p in pred_paths:
        path = Path(p)
        name = path.stem
        rows = read_jsonl(path)
        preds = {r["id"]: r for r in rows}
        mp = path.with_name(path.stem + ".meta.json")
        metas[name] = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else None
        variants.append(Variant(name, str(path), "schema", preds, kmap))
        if any("schema_labels" in r for r in rows):
            variants.append(Variant(f"{name}_label", str(path), "label", preds, kmap, gliner_labels))
        if concept:
            spans = [s for r in rows for s in r.get("concept_spans", [])]
            if not spans:
                warnings.append(f"{name}: concept span이 없어 --concept 집계를 건너뜀")
            elif not any(s.get("label") for s in spans):
                warnings.append(f"{name}: concept span에 label이 없어(라벨 없음으로 계산 불가) "
                                "스키마 커버리지만 출력합니다. API에 label 필드가 추가되면 자동으로 계산됩니다.")
            else:
                n_nolabel = sum(1 for s in spans if not s.get("label"))
                if n_nolabel:
                    warnings.append(f"{name}: concept span {n_nolabel}/{len(spans)}개에 label이 없음 (그 span은 무시)")
                variants.append(Variant(f"{name}_concept", str(path), "concept", preds, kmap, concept_labels))
    return variants, warnings, metas


# ── 지표 ────────────────────────────────────────────────────────────────

def p95(values: list[float]) -> float | None:
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]


def compute(items: list[dict]) -> dict:
    """items: 평가 대상 질의별 {gold, pred, noise, unmapped, latency}."""
    n = len(items)
    covered = sum(1 for it in items if it["gold"] <= it["pred"])
    per_table = {}
    for t in TARGET_TABLES:
        g = [it for it in items if t in it["gold"]]
        hit = sum(1 for it in g if t in it["pred"])
        per_table[t] = {"gold": len(g), "hit": hit, "recall": hit / len(g) if g else None}
    noise = sum(len(it["noise"]) for it in items)
    lat = [it["latency"] for it in items if it["latency"] is not None]
    return {
        "n": n,
        "covered": covered,
        "coverage": covered / n if n else None,
        "per_table": per_table,
        "noise_keywords": noise,
        "noise_per_query": noise / n if n else None,
        "unmapped_keywords": sum(len(it["unmapped"]) for it in items),
        "latency_ms_mean": sum(lat) / len(lat) if lat else None,
        "latency_ms_p95": p95(lat),
    }


def dedup(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        if it["template"] not in seen:
            seen.add(it["template"])
            out.append(it)
    return out


def evaluate(variant: Variant, records: list[dict], gold: dict, templates: dict) -> tuple[dict, list[dict], Counter]:
    items, unmapped = [], Counter()
    missing_pred = 0
    for rec in records:
        g = gold[rec["id"]]
        if g is None or not g:
            continue  # 파싱 실패 / 대상 테이블 없음 - 전체 집계에서 따로 보고
        row = variant.preds.get(rec["id"])
        if row is None:
            missing_pred += 1
            continue
        pr = variant.predict(row)
        noise = [w for w, ts, _ in pr["signals"] if ts and not (set(ts) & g)]
        unmapped.update(pr["unmapped"])
        items.append({
            "id": rec["id"], "dataset": rec["dataset"], "text": rec["text"], "template": templates[rec["id"]],
            "gold": g, "pred": pr["tables"], "noise": noise, "unmapped": pr["unmapped"],
            "keywords": row.get("schema_keywords", []), "signals": pr["signals"],
            "latency": row.get("latency_ms"),
        })
    scopes = {}
    datasets = []
    for rec in records:
        if rec["dataset"] not in datasets:
            datasets.append(rec["dataset"])
    for scope in [ALL] + datasets:
        sel = items if scope == ALL else [it for it in items if it["dataset"] == scope]
        scopes[scope] = {"all": compute(sel), "dedup": compute(dedup(sel))}
    n_missing_by_ds = Counter()
    for rec in records:
        if gold[rec["id"]] and rec["id"] not in variant.preds:
            n_missing_by_ds[rec["dataset"]] += 1
    return {"source": variant.source, "kind": variant.kind, "missing_pred": missing_pred,
            "missing_pred_by_dataset": dict(n_missing_by_ds), "scopes": scopes}, items, unmapped


# ── 출력 ────────────────────────────────────────────────────────────────

def fmt_pct(x) -> str:
    return "–" if x is None else f"{x * 100:.1f}%"


def fmt_num(x, nd=1) -> str:
    return "–" if x is None else f"{x:.{nd}f}"


def write_misses(path: Path, items: list[dict]) -> int:
    rows = []
    order = {t: i for i, t in enumerate(TARGET_TABLES)}
    for idx, it in enumerate(items):
        missing = [t for t in TARGET_TABLES if t in it["gold"] and t not in it["pred"]]
        for t in missing:
            rows.append((order[t], idx, {
                "missing_table": t, "id": it["id"], "dataset": it["dataset"], "text": it["text"],
                "gold_tables": ",".join(t2 for t2 in TARGET_TABLES if t2 in it["gold"]),
                "schema_keywords": ", ".join(it["keywords"]),
                "pred_tables": ",".join(t2 for t2 in TARGET_TABLES if t2 in it["pred"]),
                "missing_tables": ",".join(missing),
            }))
    rows.sort(key=lambda r: (r[0], r[1]))
    fields = ["missing_table", "id", "dataset", "text", "gold_tables", "schema_keywords", "pred_tables", "missing_tables"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for _, _, r in rows:
            w.writerow(r)
    return len(rows)


def write_per_query(path: Path, items: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps({
                "id": it["id"], "covered": it["gold"] <= it["pred"],
                "gold": sorted(it["gold"]), "pred": sorted(it["pred"]),
                "missing": sorted(it["gold"] - it["pred"]), "keywords": it["keywords"],
            }, ensure_ascii=False) + "\n")


def find_prev_run(run_dir: Path, variant: str) -> Path | None:
    """run_dir와 같은 폴더(기본 eval/runs/) 안에서 이름(타임스탬프)이 더 앞선 run 중 같은 시스템이 있는 마지막 것."""
    candidates = sorted(p for p in run_dir.parent.iterdir() if p.is_dir() and p.name < run_dir.name
                        and (p / f"per_query_{variant}.jsonl").exists())
    return candidates[-1] if candidates else None


def write_diff(run_dir: Path, variant: str, items: list[dict]) -> str:
    out = run_dir / f"diff_prev_{variant}.md"
    prev = find_prev_run(run_dir, variant)
    lines = [f"# {variant}: 직전 run 대비 변화", ""]
    if prev is None:
        lines.append("같은 시스템의 직전 run이 없습니다 (이번이 첫 run).")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "직전 run 없음"
    before = {r["id"]: r for r in read_jsonl(prev / f"per_query_{variant}.jsonl")}
    now = {it["id"]: it for it in items}
    common = [i for i in now if i in before]
    fixed = [i for i in common if not before[i]["covered"] and now[i]["gold"] <= now[i]["pred"]]
    broken = [i for i in common if before[i]["covered"] and not now[i]["gold"] <= now[i]["pred"]]
    lines += [f"- 직전 run: `{prev.name}`", f"- 공통 질의 {len(common)}건, "
              f"이번에만 있음 {len(set(now) - set(before))}건, 직전에만 있음 {len(set(before) - set(now))}건",
              f"- **새로 덮인 질의 {len(fixed)}건 / 새로 깨진 질의(회귀) {len(broken)}건**", ""]
    for title, ids in (("새로 깨진 질의 (회귀)", broken), ("새로 덮인 질의", fixed)):
        lines += [f"## {title} ({len(ids)})", ""]
        if ids:
            lines += ["| id | text | 직전 키워드 | 이번 키워드 | 이번 누락 테이블 |", "|---|---|---|---|---|"]
            for i in ids:
                it = now[i]
                lines.append(f"| {i} | {it['text']} | {', '.join(before[i]['keywords'])} | {', '.join(it['keywords'])} | "
                             f"{', '.join(sorted(it['gold'] - it['pred'])) or '–'} |")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return f"직전 `{prev.name}` 대비 새로 덮임 {len(fixed)} / 회귀 {len(broken)}"


def meta_summary(meta: dict | None) -> str:
    if not meta:
        return "meta 없음"
    c = meta.get("config", {})
    keys = ["api_url", "dict_check", "dict_sha256_api", "gliner_model", "gliner_threshold", "concept_labels",
            "extract_url", "labels", "threshold", "base_url", "model", "mock", "prompt_sha256"]
    parts = []
    for k in keys:
        if k in c and c[k] is not None:
            v = c[k]
            if isinstance(v, str) and len(v) == 64 and k.endswith(("sha256", "sha256_api")):
                v = v[:12]
            parts.append(f"{k}={v}")
    sess = meta.get("sessions", [])
    return f"{meta.get('updated_at')} · " + ", ".join(parts) + (f" · sessions={len(sess)}" if sess else "")


def write_md(path: Path, ctx: dict) -> None:
    res = ctx["results"]
    L = [f"# 키워드 추출 커버리지 비교 — {ctx['run']}", ""]
    L += [f"- 데이터: {', '.join(f'`{d}`' for d in ctx['data'])}",
          f"- 질의 {ctx['n_records']}건 · 정답 SQL 파싱 실패 {len(ctx['parse_failures'])}건 · "
          f"대상 테이블 없는 질의 {ctx['n_gold_empty']}건 (둘 다 평가 제외)",
          "- 커버리지 = 정답 테이블이 **모두** 키워드로 덮인 질의 비율. 중복 제거 = 숫자·날짜·concept를 가린 문장 기준 첫 질의만",
          "- 잡음 = 정답에 없는 테이블만 가리키는 키워드 수(오류 아님, 참고치). 속도 = 추출 시 측정한 latency_ms", ""]
    for w in ctx["warnings"]:
        L.append(f"> ⚠️ {w}")
    if ctx["warnings"]:
        L.append("")
    L += ["## 전체", "", "| 시스템 | 평가 질의 | 커버리지 | 커버리지(중복 제거) | 잡음 키워드 (질의당) | 미매핑 단어 | latency 평균 / p95 (ms) | pred 없음 |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in res.items():
        a, d = r["scopes"][ALL]["all"], r["scopes"][ALL]["dedup"]
        L.append(f"| {name} | {a['n']} | {fmt_pct(a['coverage'])} | {fmt_pct(d['coverage'])} (n={d['n']}) | "
                 f"{a['noise_keywords']} ({fmt_num(a['noise_per_query'], 2)}) | {a['unmapped_keywords']} | "
                 f"{fmt_num(a['latency_ms_mean'])} / {fmt_num(a['latency_ms_p95'])} | {r['missing_pred']} |")
    L += ["", "## 테이블별 재현율 (전체, 중복 제거 전)", ""]
    first = next(iter(res.values()), None)
    if first:
        pt = first["scopes"][ALL]["all"]["per_table"]
        L.append("| 시스템 | " + " | ".join(f"{t} (n={pt[t]['gold']})" for t in TARGET_TABLES) + " |")
        L.append("|---|" + "---:|" * len(TARGET_TABLES))
        for name, r in res.items():
            p = r["scopes"][ALL]["all"]["per_table"]
            L.append(f"| {name} | " + " | ".join(fmt_pct(p[t]["recall"]) for t in TARGET_TABLES) + " |")
    L += ["", "## 데이터 파일별 커버리지 (전체 / 중복 제거)", ""]
    ds = ctx["datasets"]
    L.append("| 시스템 | " + " | ".join(ds) + " |")
    L.append("|---|" + "---:|" * len(ds))
    for name, r in res.items():
        cells = []
        for d in ds:
            s = r["scopes"].get(d)
            cells.append(f"{fmt_pct(s['all']['coverage'])} / {fmt_pct(s['dedup']['coverage'])}" if s else "–")
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    L += ["", "## 미매핑 단어 (상위 15, 전체 목록은 unmapped_<시스템>.csv)", ""]
    any_unmapped = False
    for name, cnt in ctx["unmapped"].items():
        if cnt:
            any_unmapped = True
            L.append(f"- **{name}**: " + ", ".join(f"{w}({c})" for w, c in cnt.most_common(15)))
    if not any_unmapped:
        L.append("- 없음")
    L += ["", "## 직전 run 대비", ""]
    for name, s in ctx["diffs"].items():
        L.append(f"- **{name}**: {s} (`diff_prev_{name}.md`)")
    L += ["", "## 실행 메타데이터", ""]
    for name, meta in ctx["metas"].items():
        L.append(f"- **{name}**: {meta_summary(meta)}")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def run(args) -> int:
    pred_paths = [p for p in args.pred if not p.endswith(".failed.jsonl")]
    if not pred_paths:
        print("[error] 채점할 pred 파일이 없습니다", file=sys.stderr)
        return 2
    records = load_datasets(args.data)
    kmap = KeywordTableMap(dict_file=args.dict)
    cache = TableCache()
    gold, parse_failures = {}, []
    for rec in records:
        r = cache.get(rec["sql"]) if rec["sql"] else {"error": "정답 SQL 없음"}
        if "error" in r:
            gold[rec["id"]] = None
            parse_failures.append({"id": rec["id"], "error": r["error"], "sql": rec["sql"][:300]})
        else:
            gold[rec["id"]] = set(r["tables"])
    cache.save()
    n_gold_empty = sum(1 for v in gold.values() if v is not None and not v)

    variants, warnings, metas = build_variants(pred_paths, kmap, args.concept)
    # 중복 제거용 concept 마스킹: 데이터 input이 없을 때 기준(api 계열) pred의 concept span 사용
    base_preds = next((v.preds for v in variants if any(r.get("concept_spans") for r in v.preds.values())), {})
    templates = {rec["id"]: template_key(rec, (base_preds.get(rec["id"]) or {}).get("concept_spans"))
                 for rec in records}

    run_dir = Path(args.run_dir) if args.run_dir else RUNS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    results, unmapped_all, diffs = {}, {}, {}
    for v in variants:
        res, items, unmapped = evaluate(v, records, gold, templates)
        results[v.name] = res
        unmapped_all[v.name] = unmapped
        res["n_miss_rows"] = write_misses(run_dir / f"misses_{v.name}.csv", items)
        write_per_query(run_dir / f"per_query_{v.name}.jsonl", items)
        diffs[v.name] = write_diff(run_dir, v.name, items)
        with open(run_dir / f"unmapped_{v.name}.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["word", "count"])
            w.writerows(unmapped.most_common())
        if res["missing_pred"]:
            warnings.append(f"{v.name}: 데이터에 있는데 pred에 없는 질의 {res['missing_pred']}건 (평가 제외)")

    if parse_failures:
        with open(run_dir / "sql_parse_failures.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "error", "sql"])
            w.writeheader()
            w.writerows(parse_failures)
        print(f"[warn] 정답 SQL 파싱 실패 {len(parse_failures)}건 → {run_dir / 'sql_parse_failures.csv'}")

    datasets = []
    for rec in records:
        if rec["dataset"] not in datasets:
            datasets.append(rec["dataset"])
    ctx = {"run": run_dir.name, "data": args.data, "n_records": len(records), "parse_failures": parse_failures,
           "n_gold_empty": n_gold_empty, "warnings": warnings, "results": results, "datasets": datasets,
           "unmapped": unmapped_all, "diffs": diffs, "metas": metas}
    write_json(run_dir / "scores.json", {
        "run": run_dir.name, "data": args.data, "n_records": len(records), "n_gold_empty": n_gold_empty,
        "parse_failures": parse_failures, "warnings": warnings, "dict_file": str(kmap.dict_file),
        "dict_groups_without_table_map": kmap.unmapped_groups,
        "results": results, "unmapped": {k: dict(v.most_common()) for k, v in unmapped_all.items()},
        "diff_prev": diffs, "meta": metas,
    })
    write_md(run_dir / "scores.md", ctx)
    for w in warnings:
        print(f"[warn] {w}")
    print(f"→ {run_dir / 'scores.md'}")
    for name, r in results.items():
        a = r["scopes"][ALL]["all"]
        print(f"  {name:20s} 커버리지 {fmt_pct(a['coverage'])} (n={a['n']})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, action="append")
    ap.add_argument("--pred", required=True, action="append")
    ap.add_argument("--concept", action="store_true", help="스키마 + concept 라벨 커버리지도 계산")
    ap.add_argument("--dict", default=None, help="사전 파일 (기본: $SCHEMA_KEYWORDS_PATH 또는 서비스 레포 경로)")
    ap.add_argument("--run-dir", default=None, help="출력 폴더 (기본: eval/runs/<타임스탬프>)")
    load_dotenv()
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
