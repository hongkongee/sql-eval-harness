"""갈린 질의 10개의 답 원문 비교 → answers_compare.md

- 답마다 모델 응답 원문(responses*.jsonl 의 sql, 고친 것 없음)을 그대로 싣는다.
- 답 이름은 summarize.py 와 같다(순차 1회차 답 = A, 이후 처음 나온 순서).
- A와 다른 부분은 토큰 단위로 [- 빠진 것 -] [+ 들어간 것 +] 로 표시한다.
- 실행 결과·EX 는 샌드박스에서 확인한 값을 아래 EXEC 에 적어 둔 것이다(이 스크립트는 DB를 부르지 않음).
실행: python3 compare_answers.py
"""
import collections, difflib, json, re
from common import ROOT, RESPONSES, REQUESTS, read_jsonl

EXEC = {  # (qid, 답): (실행 결과, 정답 일치)
    ("val_441", "A"): ("1,120행", "pass"), ("val_441", "B"): ("1,120행 (A와 같음)", "pass"),
    ("val_441", "C"): ("**13,041행**", "fail"),
    ("val_445", "A"): ("18,573행", "fail"), ("val_445", "B"): ("18,573행 (A와 같음)", "fail"),
    ("val_261", "A"): ("9,103행", "fail"), ("val_261", "B"): ('**문법 오류** (`syntax error at or near ")"`)', "fail"),
    ("val_420", "A"): ("**시간 초과** (샌드박스 30초 제한, 다시 실행해도 같음)", "fail"),
    ("val_420", "B"): ("645행", "fail"),
    ("val_720", "A"): ("6,421행", "pass"), ("val_720", "B"): ("6,421행 (A와 같음)", "pass"),
    ("val_468", "A"): ("1,278,608행", "fail"), ("val_468", "B"): ("1,278,608행, **반환 컬럼 다름**", "fail"),
    ("seed_598_test_concept", "A"): ("53,832행", "fail"), ("seed_598_test_concept", "B"): ("**71,615행**", "fail"),
    ("seed_747_test_paraphrase", "A"): ("79,941행", "pass"), ("seed_747_test_paraphrase", "B"): ("79,941행 (A와 같음)", "pass"),
    ("seed_690_test_restructure", "A"): ("66,454행", "pass"), ("seed_690_test_restructure", "B"): ("66,454행 (A와 같음)", "pass"),
    ("seed_690_test_restructure", "C"): ("66,454행 (A와 같음)", "pass"),
    ("seed_547_test_restructure", "A"): ("0행", "pass"), ("seed_547_test_restructure", "B"): ("0행 (A와 같음)", "pass"),
}
NOTE = {
    "val_441": "B는 A 끝에 `HAVING COUNT(*) >= 1`만 붙임(결과 같음). C는 발사르탄 단일제 `1308842`를 OR로 추가해 결과가 12배 가까이 늘어남. `/rag` 후보 2순위 `1308842`의 한글명이 복합제 제품명이라 생긴 갈림.",
    "val_445": "심부전 조건을 `MIN(CASE WHEN …)`과 `HAVING`으로 거르느냐(A), `WHERE`로 먼저 거르느냐(B)의 차이. 결과 같음. 둘 다 '입원'(visit)을 빠뜨려 정답과 다름.",
    "val_261": "B는 맨 끝에 닫는 괄호 `)`가 하나 더 있어 실행되지 않음. 둘 다 후보 5개를 모두 넣어 정답(`46221581`)과 다름.",
    "val_420": "B는 유방암 진단이 기준일(시술일) 이전이어야 한다는 조건 `co.condition_start_date <= po.procedure_date`가 빠짐. 정답에는 이 조건이 있음. A는 후보 5개를 모두 넣어 샌드박스에서 시간 초과(정답은 개념 1개로 0초, 224행).",
    "val_720": "B는 같은 내용을 `WITH outcome_events` CTE로 씀(정답과 같은 모양). 결과 같음.",
    "val_468": "A는 `range_low, range_high`, B는 `unit_source_value`를 덧붙임. 정답은 `unit_concept_id`. 둘 다 상위개념 `80180`(골관절염)을 골라 정답 `4079749`(고관절 골관절염)와 다름.",
    "seed_598_test_concept": "A는 합병증 동반 당뇨 `442793` 환자를 `EXCEPT`로 뺌. B는 빼지 않음. 둘 다 후보 1~4를 모두 넣어 정답(`4008576` 하나)과 다름.",
    "seed_747_test_paraphrase": "B는 사망 테이블 조인 조건의 `d.death_date <= DATE '2026-11-18'`이 빠짐. 미래 사망일이 없어 결과 같음.",
    "seed_690_test_restructure": "A는 `procedure_occurrence`에서 바로, B·C는 `person`에서 `EXISTS`로 고름. B와 C는 괄호 안 공백 하나만 다름. 결과 같음.",
    "seed_547_test_restructure": "첫 CTE의 `select / min / as / from / where / group by`가 A는 소문자, B는 대문자. 나머지 같음.",
}
TOK = re.compile(r"\w+|'[^']*'|\s+|[^\w\s]")


def mark_diff(a, b):
    """A → b 차이를 b 기준으로 표시. 같은 부분이 길면 앞뒤 일부만 남긴다."""
    ta, tb = TOK.findall(a), TOK.findall(b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if op == "equal":
            seg = "".join(ta[i1:i2])
            out.append(seg if len(seg) <= 80 else seg[:35] + " … " + seg[-35:])
        else:
            if i2 > i1: out.append("[-" + "".join(ta[i1:i2]) + "-]")
            if j2 > j1: out.append("[+" + "".join(tb[j1:j2]) + "+]")
    return "".join(out)


reqs = json.load(open(REQUESTS, encoding="utf-8"))
seq = list(read_jsonl(RESPONSES)); par = list(read_jsonl(ROOT / "responses_par.jsonl"))
L = ["# 갈린 질의 10개: 답 원문 비교 (3차, 2026-11-18)", "",
     "`report_summary.md`에서 답이 갈린 10개 질의의 **모델 응답 원문**을 그대로 옮겼습니다. "
     "응답은 한 줄이라 코드 블록이 옆으로 깁니다. 원본은 `responses.jsonl`(순차), `responses_par.jsonl`(병렬)의 `sql` 필드입니다. "
     "자리표시자 복원 전후(`sql`, `sql_restored`)가 1,400건 모두 같아서 원문 하나만 싣습니다.", "",
     "- 답 이름: 순차 1회차 답을 A로 하고, 이후 처음 나온 순서대로 B, C를 붙였습니다.",
     "- 나온 곳: `순차 n` = 순차 n회차, `mixed n`/`same n` = 병렬 n회차. (x)는 외부 요청과 겹친 응답, 표시가 없으면 우리 요청만 처리된 응답입니다.",
     "- A와 다른 부분: A 원문을 기준으로 `[-빠진 것-]`, `[+들어간 것+]`로 표시했습니다. 같은 부분이 길면 ` … `로 줄였습니다.",
     "- 실행 결과와 정답 일치(EX)는 샌드박스 DB에서 확인한 값입니다.", "",
     "| # | 질의 | 답 종류 | 순차 | mixed | same | 실행 결과 달라짐 | concept_id 갈림 |", "|---|---|---|---|---|---|---|---|"]
body = []
n = 0
for q, meta in reqs.items():
    s_rows = sorted([r for r in seq if r["qid"] == q], key=lambda r: r["rep"])
    p_rows = sorted([r for r in par if r["qid"] == q], key=lambda r: (r["mode"], r["rep"]))
    order = list(dict.fromkeys(r["sql"] for r in s_rows + p_rows))
    if len(order) < 2:
        continue
    n += 1
    lab = {s: chr(65 + i) for i, s in enumerate(order)}
    mixed = [r for r in p_rows if r["mode"] == "mixed"]; same = [r for r in p_rows if r["mode"] == "same"]
    fmt = lambda rows: "".join(lab[r["sql"]] for r in rows)
    res_diff = len({EXEC[(q, lab[s])][0].split(" (A와")[0].replace("**", "") for s in order}) > 1
    cid = len({tuple(sorted(set(re.findall(r"\b\d{4,}\b", re.sub(r"'[^']*'", "", s))))) for s in order}) > 1
    short = q.split("_test_")[0]
    L.append(f"| {n} | [{short}](#{n}-{short.replace('_', '_')}) {meta['text'][:30]} | {len(order)} | {fmt(s_rows)} | {fmt(mixed)} | {fmt(same)} | "
             f"{'**예**' if res_diff else '아니오'} | {'**예**' if cid else '아니오'} |")
    body += ["", f"## {n}. {short}", "", f"**질의:** {meta['text']}  ",
             f"**출처·섹션·난이도:** {meta.get('set')} · {meta.get('section')} · {meta.get('difficulty')}", "",
             "| 순차 | mixed | same |", "|---|---|---|",
             f"| {fmt(s_rows)} | {fmt(mixed)} | {fmt(same)} |", "", f"**차이 요약:** {NOTE[q]}", ""]
    cnt = collections.Counter(r["sql"] for r in s_rows + p_rows)
    for s in order:
        where = [f"순차 {r['rep']}" for r in s_rows if r["sql"] == s]
        where += [f"{r['mode']} {r['rep']}" + ("" if r.get("only_ours") else " (x)") for r in p_rows if r["sql"] == s]
        toks = sorted({r["completion_tokens"] for r in s_rows + p_rows if r["sql"] == s})
        ex = EXEC[(q, lab[s])]
        body += [f"### {short} — 답 {lab[s]} ({cnt[s]}번)", "",
                 f"- 나온 곳: {', '.join(where)}",
                 f"- 생성 토큰 수: {', '.join(map(str, toks))}",
                 f"- 실행 결과: {ex[0]} / 정답 일치: {ex[1]}", "", "```sql", s, "```", ""]
        if lab[s] != "A":
            body += ["A와 다른 부분:", "", "```diff", mark_diff(order[0], s), "```", ""]
    body += [f"### {short} — 정답 SQL", "", "```sql", meta["gold"], "```"]
L.append("")
L += body
open(ROOT / "answers_compare.md", "w", encoding="utf-8").write("\n".join(L) + "\n")
print(f"{n}개 질의 → answers_compare.md")
