"""파인튜닝 GLiNER를 라벨 목록을 바꿔 가며 호출해 llm-compat 형식 결과를 만든다 (라벨 분리 실험용).

`gliner-entity-router`의 `service/app.py` `POST /extract`(라벨·threshold를 요청마다 받음)를 호출하고,
변환은 서비스 코드(`app.core.llm_compat.spans_to_llm_compat`: 겹침 처리 + 라벨 매핑)를 그대로 불러 쓴다.
→ 운영 /keyword-extraction/llm-compat과 같은 경로이고, 평가 도구 안에 변환 로직을 복제하지 않는다.

    --mode joint : 19개(중복 제거 18개) 라벨을 한 번에 → /llm-compat 응답과 같아야 한다 (검증용)
    --mode split : A 의료 4라벨 / B 스키마 13 + 방문 유형 + 성별, 두 번 호출해 합침

실행에는 Python 3.10+, pydantic, pyyaml이 필요하고 gliner-entity-router 레포가 PYTHONPATH에 있어야 한다.
    PYTHONPATH=.:<gliner-entity-router> python -m eval.gliner_label_split --url http://<서버>:8000/extract \\
        --csv <정답 CSV> --mode split --threshold 0.3 --out eval/outputs/<셋>/<이름>.jsonl
"""
import argparse
import json
import random
import time
from pathlib import Path

from app.config.settings import get_settings
from app.core.llm_compat import _get_map, spans_to_llm_compat
from app.models.schemas import Span

from eval.csv_keyword_eval import load_csv
from eval.extractors.prod_llm import load_category_map, parse_obj, to_spans
from eval.httpclient import post_json

MEDICAL = ["진단명 또는 질병명", "약물명", "검사명 또는 측정 항목", "시술명 또는 수술명"]


def label_groups(mode):
    m = _get_map(get_settings().llm_compat_map_path)
    schema, concept = list(m["schema"]), list(m["concept"])
    if mode == "joint":
        return [list(dict.fromkeys(schema + concept))], set(schema)
    rest = [c for c in concept if c not in MEDICAL]
    return [MEDICAL, list(dict.fromkeys(schema + rest))], set(schema)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["joint", "split"], required=True)
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--order-seed", type=int, help="각 묶음 안의 라벨 순서를 이 seed로 섞는다 (GLiNER는 라벨 순서에도 결과가 흔들린다)")
    a = ap.parse_args()
    groups, schema_labels = label_groups(a.mode)
    if a.order_seed is not None:
        rng = random.Random(a.order_seed)
        groups = [rng.sample(g, len(g)) for g in groups]
    cmap = load_category_map()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = load_csv(a.csv)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            text, raw, lat = r["query"], [], []
            for labels in groups:
                t0 = time.perf_counter()
                resp = post_json(a.url, {"text": text, "labels": labels, "threshold": a.threshold},
                                 timeout=a.timeout, max_retries=3)
                lat.append(round((time.perf_counter() - t0) * 1000, 1))
                raw.append(resp.body)
            spans = [Span(type="schema" if e["label"] in schema_labels else "concept", text=e["text"],
                          start=e["start"], end=e["end"], category=e["label"], score=e["score"])
                     for ents in raw for e in ents]
            items = [i.model_dump() for i in spans_to_llm_compat(spans)]
            ev_spans, dropped = to_spans(parse_obj(items), text, cmap)
            f.write(json.dumps({"id": r["id"], "text": text, "spans": ev_spans, "dropped": dropped, "raw": items,
                                "gliner_raw": raw, "latency_ms": round(sum(lat), 1), "latency_parts_ms": lat},
                               ensure_ascii=False) + "\n")
    out.with_suffix(".meta.json").write_text(json.dumps(
        {"config": {"system": "gliner-extract", "url": a.url, "mode": a.mode, "threshold": a.threshold,
                    "order_seed": a.order_seed, "label_groups": groups}, "csv": a.csv}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out, len(rows))


if __name__ == "__main__":
    main()
