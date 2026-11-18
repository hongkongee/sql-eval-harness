"""질의 100개 고르기 → candidates.json
- proposed_input_val.jsonl 68개 전부
- test_set/eval_ready 에서 32개: 이미 고른 질의들과 '형태'가 최대한 겹치지 않게 욕심쟁이(greedy) 방식으로 고름
  · val 과 같은 seed·같은 시나리오·같은 문장은 제외, seed·시나리오당 1개
  · 유형 = 섹션·질의유형·난이도 + 정답 SQL 구조(쓰는 테이블, WITH/GROUP BY/MIN/NOT EXISTS/INTERVAL/LEFT JOIN …)
  · val 68개에 없는 유형이면서 val 과 문장 틀도 다른 문항만 후보. 섹션×난이도 칸을 번갈아 돌며, 칸 안에서는 흔한 유형(문항 많은)부터 유형당 1개
  · 같은 유형 안에서는 증강 방식(concept/paraphrase/restructure/slot)이 고르게 되도록 고름
- 그 뒤에 예비 후보(같은 방식으로 계속 고른 순서)를 붙인다. prepare.py 가 /rag 실패 시 예비로 채움.
실행: python3 select_queries.py
"""
import json, pathlib, re, collections
ROOT = pathlib.Path(__file__).resolve().parent
TS = ROOT.parent.parent / "test_set"
TABLES = ["person", "condition_occurrence", "drug_exposure", "procedure_occurrence", "measurement", "observation",
          "visit_occurrence", "observation_period", "death", "device_exposure", "drug_era", "condition_era",
          "specimen", "note", "payer_plan_period", "cost", "visit_detail", "concept_ancestor", "concept"]
CONSTRUCTS = {
    "WITH": r"\bWITH\b", "GROUP BY": r"\bGROUP BY\b", "HAVING": r"\bHAVING\b", "COUNT": r"\bCOUNT\s*\(",
    "MIN": r"\bMIN\s*\(", "MAX": r"\bMAX\s*\(", "AVG": r"\bAVG\s*\(", "NOT EXISTS": r"\bNOT EXISTS\b",
    "EXISTS": r"(?<!NOT )\bEXISTS\b", "LEFT JOIN": r"\bLEFT JOIN\b", "JOIN": r"(?<!LEFT )\bJOIN\b", "UNION": r"\bUNION\b",
    "CASE": r"\bCASE\b", "INTERVAL": r"\bINTERVAL\b", "LEAST": r"\bLEAST\s*\(", "GREATEST": r"\bGREATEST\s*\(",
    "OVER": r"\bOVER\s*\(", "DISTINCT ON": r"\bDISTINCT ON\b", "BETWEEN": r"\bBETWEEN\b", " OR ": r"\bOR\b",
    "NOT IN": r"\bNOT IN\b", "EXTRACT/AGE": r"\b(EXTRACT|AGE|DATE_PART)\s*\(", "value_as_number": r"value_as_number",
    "gender": r"gender_concept_id", "visit_concept": r"visit_concept_id", "status_concept": r"condition_status_concept_id",
    "birth": r"(birth_datetime|year_of_birth)", "COALESCE": r"\bCOALESCE\s*\(", "date literal": r"DATE\s*'\d{4}",
    "CURRENT_DATE": r"CURRENT_DATE", "ORDER BY": r"\bORDER BY\b", "LIMIT": r"\bLIMIT\b",
}


def surfaces(inp):
    return re.findall(r'"([^"]+)"\s*→', inp or "")


def template(text, inp):
    t = text
    for s in sorted(surfaces(inp), key=len, reverse=True):
        t = t.replace(s, "○")
    t = re.sub(r"\d{4}-\d{2}-\d{2}", "D", t); t = re.sub(r"\d+(\.\d+)?", "N", t)
    t = re.sub(r"(정의|설정|규정|확인|조회|추출|산출|집계)(함|한다|하라|해 주세요|해줘)?\.?$", "V", t)   # 끝 동사만 다른 것은 같은 틀
    t = re.sub(r"(시행일|처방일|진단일|시술일)", "○일", t)
    t = re.sub(r"(노출군|비교군|대조군)", "G", t); t = re.sub(r"(기준 시점|기준시점|기준일|index date)", "기준", t)
    return re.sub(r"\s+", " ", t).strip()


def features(r):
    sql = r["query"]; up = sql.upper()
    f = {f"tbl:{t}" for t in TABLES if re.search(rf"\b{t}\b", sql, re.I)}
    f |= {f"sql:{k}" for k, p in CONSTRUCTS.items() if re.search(p, up if k.isupper() else sql, re.I if not k.isupper() else 0)}
    f |= {f"section:{r['section']}", f"item:{r['item']}", f"type:{r['query_type']}", f"diff:{r['difficulty']}",
          f"sec×diff:{r['section']}×{r['difficulty']}", f"tpl:{template(r['text'], r.get('input'))}"}
    nsql = len(sql)
    f.add("len:" + ("<300" if nsql < 300 else "<700" if nsql < 700 else "<1200" if nsql < 1200 else "1200+"))
    return f


def main():
    val = [json.loads(l) for l in open(TS / "proposed_input_val.jsonl", encoding="utf-8") if l.strip()]
    ev = [dict(json.loads(l), _aug=f.stem) for f in sorted((TS / "eval_ready").glob("*.jsonl"))
          for l in open(f, encoding="utf-8") if l.strip()]
    vseeds = {v["id"] for v in val}; vscen = {v["scenario_name"] for v in val}; vtext = {v["text"] for v in val}
    pool = [e for e in ev if e["seed_id"] not in vseeds and e["scenario_name"] not in vscen and e["text"] not in vtext]
    covered = collections.Counter()
    for v in val:
        covered.update(features(v))
    # 유형 = 섹션·질의유형·난이도 + SQL 구조 특징(테이블·구문). 문장 틀(tpl)과 길이 구간은 빼고 본다.
    def kind(r, fs=None):
        fs = fs if fs is not None else features(r)
        return tuple(sorted(x for x in fs if x.startswith(("tbl:", "sql:")))) + (r["section"], r["query_type"], r["difficulty"])
    val_kinds = {kind(v) for v in val}
    val_tpls = {template(v["text"], v["input"]) for v in val}       # val 과 문장 틀이 같은 질의도 뺌
    feats = {e["id"]: features(e) for e in pool}
    groups = collections.defaultdict(list)                       # 유형 → 문항들
    for e in pool:
        k = kind(e, feats[e["id"]])
        if k not in val_kinds and template(e["text"], e["input"]) not in val_tpls:
            groups[k].append(e)
    # 섹션×난이도 칸마다 유형 목록(문항 많은 = 흔한 유형 먼저), 칸을 번갈아 하나씩
    cells = collections.defaultdict(list)
    for k, es in groups.items():
        cells[(k[-3], k[-1])].append(k)
    for c in cells:
        cells[c].sort(key=lambda k: (-len(groups[k]), k))
    order = sorted(cells, key=lambda c: (-len(cells[c]), c))
    picked, used_seed, used_scen, aug_n = [], set(), set(), collections.Counter()
    while any(cells[c] for c in order):
        for c in order:
            while cells[c]:
                k = cells[c].pop(0)
                es = [e for e in groups[k] if e["seed_id"] not in used_seed and e["scenario_name"] not in used_scen
                      and template(e["text"], e["input"]) not in val_tpls]
                if not es:
                    continue
                es.sort(key=lambda e: (aug_n[e["_aug"]], abs(len(e["query"]) - 500), e["id"]))  # 증강 방식 고르게
                best = es[0]
                picked.append((best, len(groups[k])))
                val_tpls.add(template(best["text"], best["input"]))      # 고른 것끼리도 문장 틀 중복 없게
                used_seed.add(best["seed_id"]); used_scen.add(best["scenario_name"]); aug_n[best["_aug"]] += 1
                break
    out = [{"qid": f"val_{v['id']}", "set": "val", "text": v["text"], "gold": v["query"], "input": v["input"],
            "section": v["section"], "query_type": v["query_type"], "difficulty": v["difficulty"],
            "template": template(v["text"], v["input"])} for v in val]
    for i, (e, new) in enumerate(picked):
        out.append({"qid": e["id"], "set": "eval_ready" if i < 32 else "eval_ready_spare", "text": e["text"],
                    "gold": e["query"], "input": e["input"], "section": e["section"], "query_type": e["query_type"],
                    "difficulty": e["difficulty"], "aug": e["_aug"], "kind_size": new,
                    "template": template(e["text"], e["input"])})
    json.dump(out, open(ROOT / "candidates.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sel = out[:100]
    print(f"후보 {len(out)}개 저장 (val 68 + eval_ready 32 + 예비 {len(out) - 100})")
    print("문장 틀 종류(100개 중):", len({o['template'] for o in sel}))
    for k in ("section", "query_type", "difficulty"):
        print(k, collections.Counter(o[k] for o in sel).most_common())
    print("eval_ready 증강 방식:", collections.Counter(o["aug"] for o in sel if o["set"] == "eval_ready"))
    for o in out[68:100]:
        print(f"{o['qid']:30} {o['section']:8} {o['difficulty']:6} {o['query_type']:24} 같은유형={o['kind_size']:3} | {o['text'][:70]}")


if __name__ == "__main__":
    main()
