# 키워드 추출 커버리지 평가 - 사용법은 eval/README.md
#   make extract-api       API(:8001)가 떠 있으면 지금 실행 가능
#   make extract-gliner    entity-router(/extract, :8000) 컨테이너로 지금 실행 가능 (CPU)
#   make extract-qwen      개발서버 Qwen 접근 시 (.env의 QWEN_BASE_URL, QWEN_MODEL)
#   make score             eval/outputs/의 결과를 모두 채점 → eval/runs/<타임스탬프>/
#   make candidates        Qwen 결과가 있을 때 사전 보강 후보
#   make loop              사전 수정 후 재실행 (extract-api → score → candidates)
# 변수 예: make extract-api DATA="../test_set/slot.jsonl" EXTRA="--limit 10"
# 서버 주소·모델·시스템 프롬프트 등은 .env에서 읽는다 (cp .env.example .env)

PY ?= $(if $(wildcard ../.venv/bin/python),../.venv/bin/python,python3)
TEST_SET ?= ../test_set
DATA ?= $(TEST_SET)/proposed_input_train.jsonl $(TEST_SET)/proposed_input_val.jsonl \
        $(TEST_SET)/paraphrase.jsonl $(TEST_SET)/restructure.jsonl \
        $(TEST_SET)/concept.jsonl $(TEST_SET)/slot.jsonl
DATA_ARGS = $(foreach d,$(DATA),--data $(d))
OUT ?= eval/outputs
SERVICE_DIR ?= ../../../gliner-entity-router
# 모델이 바뀌면 결과를 따로 두려고 바꾸는 값 (예: QWEN_OUT=eval/outputs/qwen_next.jsonl)
QWEN_OUT ?= $(OUT)/qwen.jsonl
RUN_ID := $(shell date +%Y%m%d-%H%M%S)
RUN_DIR ?= eval/runs/$(RUN_ID)
EXTRA ?=

.PHONY: help extract-api extract-gliner extract-qwen extract-qwen-mock score candidates loop test

help:
	@sed -n '2,8p' Makefile

extract-api:
	$(PY) -m eval.extract --system api $(DATA_ARGS) --out $(OUT)/api.jsonl $(EXTRA)

extract-gliner:
	$(PY) -m eval.extract --system gliner $(DATA_ARGS) --out $(OUT)/gliner.jsonl $(EXTRA)

extract-qwen:
	$(PY) -m eval.extract --system qwen $(DATA_ARGS) --out $(QWEN_OUT) $(EXTRA)

# 서버 없이 흐름 확인용 (결과는 qwen_mock.jsonl - 실제 qwen.jsonl과 섞이지 않게)
extract-qwen-mock:
	$(PY) -m eval.extract --system qwen --mock $(DATA_ARGS) --out $(OUT)/qwen_mock.jsonl $(EXTRA)

score:
	@test -n "$(filter-out %.failed.jsonl,$(wildcard $(OUT)/*.jsonl))" || { echo "[error] $(OUT)/에 결과 파일이 없습니다 - 먼저 make extract-*"; exit 1; }
	$(PY) -m eval.score $(DATA_ARGS) $(foreach p,$(filter-out %.failed.jsonl,$(wildcard $(OUT)/*.jsonl)),--pred $(p)) --concept --run-dir $(RUN_DIR)

candidates:
	@test -f $(QWEN_OUT) || { echo "[skip] $(QWEN_OUT)이 없습니다 - Qwen 서버 접근 후 make extract-qwen"; exit 0; }; \
	$(PY) -m eval.candidates $(DATA_ARGS) --base $(OUT)/api.jsonl --ref $(QWEN_OUT) --out $(RUN_DIR)/candidates.csv

loop:
	@echo "=================================================================="
	@echo " 사전 수정 후 재실행 루프"
	@echo " API는 사전을 프로세스에 캐시하고, 사전 파일이 Docker 이미지에 들어 있으므로"
	@echo " 사전을 고쳤다면 재시작이 아니라 '재빌드'해야 반영됩니다:"
	@echo "     cd $(SERVICE_DIR) && docker compose up -d --build keyword-extraction"
	@echo " (API 사전 해시가 현재 파일과 다르면 아래 extract-api가 중단됩니다)"
	@echo "=================================================================="
	$(MAKE) extract-api EXTRA="--overwrite --strict-dict $(EXTRA)"
	$(MAKE) score RUN_DIR=$(RUN_DIR)
	$(MAKE) candidates RUN_DIR=$(RUN_DIR)
	@echo "→ 검토: $(RUN_DIR)/scores.md, misses_api.csv, diff_prev_api.md, candidates.csv"

test:
	$(PY) -m pytest
