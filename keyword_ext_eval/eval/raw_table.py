"""정답과 모델 응답을 문장별로 나란히 놓은 원본 표 (사람이 읽는 용도). 채점은 하지 않는다.

    python -m eval.raw_table --csv <정답 CSV> --pred eval/outputs/<x>.jsonl --name <모델 이름> --out-dir <폴더>
      → <폴더>/raw.md, <폴더>/raw.csv

열: 정답/답변 스키마, 정답/답변 의료 컨셉, 정답/답변 방문·성별
- 답변 스키마: type=schema span. 표기 "텍스트(테이블)"
- 답변 의료 컨셉: type=concept span. 표기 "텍스트(라벨 앞 2글자)"
- 답변 방문·성별: llm-compat 응답에는 방문·성별 칸이 따로 없다. 정답 방문·성별 위치와 겹치는 span(종류 무관)을
  "텍스트(종류/테이블)"로 적는다. 그 span이 정답 스키마와도 겹치지 않으면 스키마 열에서는 뺀다
- 그 밖의 span(OPERATOR, TIME, VALUE 등)은 '기타' 열에 적는다
"""
import argparse
import csv
import json
import os

from eval.csv_keyword_eval import load_csv, locate

SHORT_TABLE = {"condition_occurrence": "condition", "drug_exposure": "drug", "procedure_occurrence": "procedure",
               "visit_occurrence": "visit", "observation_period": "obs_period"}
SHORT_LABEL = {"진단명 또는 질병명": "진단", "약물명": "약물", "시술명 또는 수술명": "시술", "검사명 또는 측정 항목": "검사"}


def _ov(a, b):
    return a[0] < b[1] and b[0] < a[1]


def _t(t):
    return SHORT_TABLE.get(t, t) if t else "-"


def rows_for(gold, preds):
    out = []
    for g in gold:
        q = g["query"]
        used = []
        sch_loc = [locate(q, s, used) for s in g["schema"]]
        used2 = []
        vg_loc = [locate(q, d["text"], used2) for d in g["dict"]]
        p = preds.get(g["id"], {"spans": [], "latency_ms": None})
        a_sch, a_con, a_vg, a_etc = [], [], [], []
        for s in p["spans"]:
            loc = (s["start"], s["end"])
            on_vg = any(v and _ov(loc, v) for v in vg_loc)
            on_sch = any(v and _ov(loc, v) for v in sch_loc)
            if on_vg:
                a_vg.append(f"{s['text']}({s.get('category')}/{_t(s.get('table'))})")
            if s["type"] == "schema" and (on_sch or not on_vg):
                a_sch.append(f"{s['text']}({_t(s.get('table'))})")
            elif s["type"] == "concept" and not on_vg:
                a_con.append(f"{s['text']}({SHORT_LABEL.get(s.get('category'), s.get('category'))})")
            elif s["type"] not in ("schema", "concept") and not on_vg:
                a_etc.append(f"{s['text']}({s.get('category')})")
        out.append({
            "id": g["id"], "문장": q,
            "정답 스키마": ", ".join(g["schema"]), "답변 스키마": ", ".join(a_sch),
            "정답 의료": ", ".join(f"{c['text']}({SHORT_LABEL.get(c['label'], c['label'])})" for c in g["gliner"]),
            "답변 의료": ", ".join(a_con),
            "정답 방문·성별": ", ".join(f"{d['text']}({d['value']})" for d in g["dict"]),
            "답변 방문·성별": ", ".join(a_vg),
            "답변 기타": ", ".join(a_etc),
            "지연(ms)": "" if p.get("latency_ms") is None else f"{p['latency_ms']:.0f}",
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    gold = load_csv(a.csv)
    preds = {}
    with open(a.pred, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                preds[r["id"]] = r
    rows = rows_for(gold, preds)
    os.makedirs(a.out_dir, exist_ok=True)
    cols = list(rows[0])
    with open(os.path.join(a.out_dir, "raw.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    esc = lambda s: s.replace("|", "\\|")  # noqa: E731
    md = [f"# 원본 결과 — {a.name}", "",
          f"- 정답: `{os.path.basename(a.csv)}` / 응답: `{os.path.basename(a.pred)}` / {len(rows)}문장",
          "- 스키마 표기: 텍스트(테이블). 의료 컨셉 표기: 텍스트(라벨). 정답 방문·성별 표기: 텍스트(값)",
          "- 답변 방문·성별: 응답에 방문·성별 칸이 따로 없어, 정답 방문·성별 위치와 겹치는 span을 텍스트(종류/테이블)로 적음",
          "- 답변 기타: 스키마·컨셉이 아닌 span(OPERATOR, TIME, VALUE 등). 채점에는 쓰지 않음", "",
          "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(esc(r[c]) for c in cols) + " |" for r in rows]
    with open(os.path.join(a.out_dir, "raw.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(os.path.join(a.out_dir, "raw.md"), len(rows))


if __name__ == "__main__":
    main()
