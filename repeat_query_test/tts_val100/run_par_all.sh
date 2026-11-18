#!/usr/bin/env bash
# 병렬 시험: 순차 시험(run_all.sh)이 끝난 뒤 실행. /rag 는 다시 부르지 않고 같은 requests.json 을 쓴다.
#   nohup caffeinate -i ./run_par_all.sh > run_par.log 2>&1 &
#   tail -f run_par.log
# 옵션(환경변수): CONC=4 REPS=5 MODE=both|mixed|same IDLE_WAIT=120
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-../../.venv/bin/python3}"; [ -x "$PY" ] || PY=python3
[ -f requests.json ] || { echo "requests.json 이 없습니다. 먼저 run_all.sh(또는 prepare.py)를 실행하세요."; exit 1; }
echo "== $(date '+%F %T') 병렬 요청 (동시 ${CONC:-4}개, 모드 ${MODE:-both})"
"$PY" -u run_par.py --mode "${MODE:-both}" --conc "${CONC:-4}" --reps "${REPS:-5}" --idle-wait "${IDLE_WAIT:-120}"
echo "== $(date '+%F %T') 정리"
"$PY" -u analyze_par.py
echo "== $(date '+%F %T') 끝 — report_par.md 확인"
