#!/usr/bin/env bash
# LoRA 병합 시험: 3차(tts_val100)와 같은 requests.json 으로 순차 → 병렬 반복.
# /rag 는 부르지 않는다(prepare.py 생략) → 프롬프트가 3차와 글자까지 같다.
#   nohup caffeinate -i ./run_merge.sh > run_merge.log 2>&1 &
#   tail -f run_merge.log
# 옵션(환경변수): REPS=5 CONC=4 IDLE_WAIT=120
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-../../.venv/bin/python3}"; [ -x "$PY" ] || PY=python3
echo "== $(date '+%F %T') 1) LLM 순차 반복"
"$PY" -u run_seq.py --reps "${REPS:-5}" --idle-wait "${IDLE_WAIT:-120}"
"$PY" -u analyze.py
echo "== $(date '+%F %T') 2) 병렬"
"$PY" -u run_par.py --mode both --conc "${CONC:-4}" --reps "${REPS:-5}" --idle-wait "${IDLE_WAIT:-120}"
"$PY" -u analyze_par.py
echo "== $(date '+%F %T') 3) 요약"
"$PY" -u summarize.py
echo "== $(date '+%F %T') 끝"
