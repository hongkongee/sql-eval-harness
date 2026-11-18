#!/usr/bin/env bash
# 퇴근 후 실행용: 1) /rag 로 프롬프트 고정(질의당 1번) → 2) LLM 순차 반복 → 3) 정리
# 사용법 (tts_val100 폴더에서):
#   export TTS_API_KEY='...'                     # 키는 환경변수로만 (파일에 쓰지 않음)
#   nohup ./run_all.sh > run_all.log 2>&1 &      # 터미널 닫아도 계속 돎
#   tail -f run_all.log                          # 진행 상황
# 옵션(환경변수): N=100 REPS=5 SOURCE=file|tts|testset DELAY=3 IDLE_WAIT=120 TTS_URL=http://10.1.1.69:8080
#                 EXCLUDE_RAG=<다른 시험의 rag 폴더>  (그 질의들은 빼고 고름)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PY:-../../.venv/bin/python3}"; [ -x "$PY" ] || PY=python3
: "${TTS_API_KEY:?TTS_API_KEY 환경변수를 먼저 export 하세요}"
echo "== $(date '+%F %T') 1) 프롬프트 고정 (/rag, 질의당 1번)"
EXCL=(); [ -n "${EXCLUDE_RAG:-}" ] && EXCL=(--exclude-rag "$EXCLUDE_RAG")
"$PY" -u prepare.py --n "${N:-100}" --source "${SOURCE:-file}" --delay "${DELAY:-3}" "${EXCL[@]+"${EXCL[@]}"}"
echo "== $(date '+%F %T') 2) LLM 순차 반복"
"$PY" -u run_seq.py --reps "${REPS:-5}" --idle-wait "${IDLE_WAIT:-120}"
echo "== $(date '+%F %T') 3) 정리"
"$PY" -u analyze.py
echo "== $(date '+%F %T') 끝 — report.md 확인"
