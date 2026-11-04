"""NL2SQL 패러프레이즈 셋(test_set/paraphrase.jsonl)에서 키워드 추출 정답 CSV를 만든다.

사람이 단 정답이 아니라 NL2SQL 평가용 데이터에서 결정론적으로 끌어낸 정답이다. 그래서 일부 지표만 믿을 수 있다.
- gold_concept_gliner: 재료(input)의 "개념 값 조건" 중 진단/약물/시술/검사 컬럼 → 라벨
- gold_concept_dict: 같은 조건 중 visit_concept_id(방문 유형), gender_concept_id(성별)
- gold_tables: 정답 SQL이 쓰는 테이블. observation_period(구조용)는 빼고, person은 성별/나이 컬럼을 쓸 때만 넣는다
- gold_schema_keywords, gold_derived_schema: 만들 수 없어 비운다 (스키마 키워드 F1은 이 셋으로 재지 않는다)
- 원문에 키워드가 그대로 없는 개념 값 조건, 재료 오류(KNOWN_BAD)는 빼고 note에 남긴다

    python -m eval.paraphrase_gold --src ../test_set/paraphrase.jsonl --out ../test_set/keyword_ext/paraphrase573/paraphrase_573_gold.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re

COLUMN_TO_LABEL = {
    ("condition_occurrence", "condition_concept_id"): "진단명 또는 질병명",
    ("drug_exposure", "drug_concept_id"): "약물명",
    ("procedure_occurrence", "procedure_concept_id"): "시술명 또는 수술명",
    ("measurement", "measurement_concept_id"): "검사명 또는 측정 항목",
}
COLUMN_TO_DOMAIN = {("visit_occurrence", "visit_concept_id"): "Visit", ("person", "gender_concept_id"): "Gender"}
TABLES = ["person", "visit_occurrence", "condition_occurrence", "drug_exposure", "procedure_occurrence",
          "measurement", "observation", "death", "device_exposure", "visit_detail", "specimen"]
PERSON_COLS = re.compile(r"\b(gender_concept_id|year_of_birth|birth_datetime|month_of_birth|day_of_birth)\b")
COND_LINE = re.compile(r'- "(.+?)" → (\w+)\.(\w+)')
# 재료의 개념 값 조건이 잘못 연결된 것 (사람이 검토해 확인). 정답에서 빼고 note에 남긴다.
# 예: "측정값" → condition_occurrence, "PCI"(시술) → condition_occurrence, "pH"(검사) → drug_exposure
KNOWN_BAD = {
    ("측정값", "condition_occurrence"), ("측정값", "procedure_occurrence"),
    ("PCI", "condition_occurrence"), ("TKA", "condition_occurrence"), ("EVT", "condition_occurrence"),
    ("위약", "condition_occurrence"), ("같은 약", "condition_occurrence"), ("사쿠비트릴", "condition_occurrence"),
    ("인결합제", "condition_occurrence"), ("인결합제", "procedure_occurrence"),
    ("치료 실행가능성", "drug_exposure"), ("pH", "drug_exposure"), ("젖산", "drug_exposure"),
    ("PJI", "drug_exposure"), ("PJI", "procedure_occurrence"), ("HbA1c", "procedure_occurrence"),
}


def build(row: dict) -> dict:
    m = re.search(r"개념 값 조건:\n(.*?)\n테이블", row["input"], re.S)
    gliner, cdict, notes = [], [], []
    for kw, table, col in COND_LINE.findall(m.group(1)) if m else []:
        if kw not in row["text"]:
            notes.append(f"원문에 없음:{kw}")
            continue
        if (kw, table) in KNOWN_BAD:
            notes.append(f"재료 오류:{kw}→{table}")
            continue
        if any(ch in kw for ch in ":|"):
            notes.append(f"구분자 포함:{kw}")
            continue
        if (table, col) in COLUMN_TO_LABEL:
            gliner.append(f"{kw}:{COLUMN_TO_LABEL[table, col]}")
        elif (table, col) in COLUMN_TO_DOMAIN:
            cdict.append(f"{kw}:{COLUMN_TO_DOMAIN[table, col]}:{kw}")
        else:
            notes.append(f"기타 컬럼:{kw}→{table}.{col}")
    q = row["query"]
    tables = [t for t in TABLES if re.search(rf"\b{t}\b", q) and (t != "person" or PERSON_COLS.search(q))]
    return {"id": row["id"], "query": row["text"], "gold_schema_keywords": "", "gold_concept_gliner": "|".join(gliner),
            "gold_concept_dict": "|".join(cdict), "gold_derived_schema": "", "gold_tables": "|".join(tables),
            "case_type": row.get("query_type", ""), "note": "; ".join(notes)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rows = [build(json.loads(line)) for line in open(args.src, encoding="utf-8") if line.strip()]
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = lambda k: sum(len([x for x in r[k].split("|") if x]) for r in rows)  # noqa: E731
    print(f"{len(rows)}문항, concept {n('gold_concept_gliner')}, 방문/성별 {n('gold_concept_dict')}, "
          f"note 있음 {sum(1 for r in rows if r['note'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
