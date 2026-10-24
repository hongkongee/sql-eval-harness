"""사전 보강 후보 수집: ref(Qwen)는 뽑았는데 base(API)의 schema_keywords에는 없는 단어를 모은다.

    python -m eval.candidates --data ../test_set/paraphrase.jsonl --base eval/outputs/api.jsonl --ref eval/outputs/qwen.jsonl

제외: 이미 사전에 있는 표면형 / 질의 안에서 base의 concept span과 겹치는 단어.
사전에 자동으로 넣지 않는다 - candidates.csv를 사람이 검토해서 schema_keywords.yaml에 추가한다.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from eval.common import load_datasets, load_dotenv, read_jsonl
from eval.keyword_map import KeywordTableMap
from eval.score import RUNS_DIR
from eval.sql_tables import TARGET_TABLES, TableCache


def occurrences(text: str, word: str) -> list[tuple[int, int]]:
    out, i = [], text.find(word)
    while i != -1:
        out.append((i, i + len(word)))
        i = text.find(word, i + 1)
    return out


def overlaps_concept(text: str, word: str, concept_spans: list[dict]) -> bool:
    spans = []
    for s in concept_spans:
        if "start" in s and "end" in s:
            spans.append((s["start"], s["end"]))
        else:  # 위치 정보가 없는 결과 파일이면 텍스트로 위치를 찾는다
            spans.extend(occurrences(text, s["text"]))
    return any(a < ce and b > cs for a, b in occurrences(text, word) for cs, ce in spans)


def collect(records: list[dict], base: dict, ref: dict, kmap: KeywordTableMap, cache: TableCache,
            concept_min_score: float = 0.0) -> list[dict]:
    count = Counter()
    gold_dist = defaultdict(Counter)
    ref_tables = defaultdict(Counter)
    examples = defaultdict(list)
    excluded = Counter()
    for rec in records:
        b, r = base.get(rec["id"]), ref.get(rec["id"])
        if b is None or r is None:
            continue
        base_kw = set(b.get("schema_keywords", []))
        guessed = {p["text"]: p.get("table") for p in r.get("keyword_tables", [])}
        g = cache.get(rec["sql"]).get("tables", []) if rec["sql"] else []
        for w in r.get("schema_keywords", []):
            if w in base_kw:
                continue
            if kmap.is_dict_surface(w):
                excluded["already_in_dict"] += 1
                continue
            concepts = [s for s in b.get("concept_spans", [])
                        if s.get("score") is None or s["score"] >= concept_min_score]
            if overlaps_concept(rec["text"], w, concepts):
                excluded["overlaps_concept"] += 1
                continue
            count[w] += 1
            for t in g:
                gold_dist[w][t] += 1
            if guessed.get(w):
                ref_tables[w][guessed[w]] += 1
            if len(examples[w]) < 3:
                examples[w].append(f"[{rec['id']}] {rec['text']}")
    rows = []
    for w, c in count.most_common():
        contained = kmap.contained_groups(w)
        rows.append({
            "candidate": w,
            "count": c,
            "gold_tables": "; ".join(f"{t}:{n}" for t, n in sorted(gold_dist[w].items(),
                                                                    key=lambda x: (-x[1], TARGET_TABLES.index(x[0])))),
            "ref_tables": "; ".join(f"{t}:{n}" for t, n in ref_tables[w].most_common()),
            "contains_dict_group": ",".join(contained),
            "example_1": examples[w][0] if len(examples[w]) > 0 else "",
            "example_2": examples[w][1] if len(examples[w]) > 1 else "",
            "example_3": examples[w][2] if len(examples[w]) > 2 else "",
        })
    print(f"후보 {len(rows)}개 (제외: 사전에 이미 있음 {excluded['already_in_dict']}회, "
          f"concept span과 겹침 {excluded['overlaps_concept']}회)")
    return rows


def run(args) -> int:
    records = load_datasets(args.data)
    base = {r["id"]: r for r in read_jsonl(args.base)}
    ref = {r["id"]: r for r in read_jsonl(args.ref)}
    common = sum(1 for rec in records if rec["id"] in base and rec["id"] in ref)
    if not common:
        print("[error] base와 ref에 공통으로 있는 질의가 없습니다 (같은 --data로 추출했는지 확인)", file=sys.stderr)
        return 2
    print(f"공통 질의 {common}건 (데이터 {len(records)}건)")
    kmap = KeywordTableMap(dict_file=args.dict)
    cache = TableCache()
    rows = collect(records, base, ref, kmap, cache, args.concept_min_score)
    cache.save()
    out = Path(args.out) if args.out else RUNS_DIR / datetime.now().strftime("%Y%m%d-%H%M%S") / "candidates.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["candidate", "count", "gold_tables", "ref_tables", "contains_dict_group", "example_1", "example_2", "example_3"]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"→ {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, action="append")
    ap.add_argument("--base", required=True, help="기준 결과 (API)")
    ap.add_argument("--ref", required=True, help="비교 결과 (Qwen)")
    ap.add_argument("--dict", default=None)
    ap.add_argument("--concept-min-score", type=float, default=0.0,
                    help="이 score 미만 concept span은 겹침 제외 판정에 안 씀 (API threshold가 낮아 '이력' 같은 "
                         "일반 단어가 concept로 잡히면 후보에서 빠지는 것을 막을 때)")
    ap.add_argument("--out", default=None, help="기본: eval/runs/<타임스탬프>/candidates.csv")
    load_dotenv()
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
