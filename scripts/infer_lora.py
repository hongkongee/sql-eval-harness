"""LoRA adapter로 파인튜닝한 모델을 로드해 테스트셋 질문에 대한 SQL을 생성하고
predictions.jsonl로 저장한다 (eval_harness.score에 바로 넣을 수 있는 스키마).

automl-llm이 LLaMA Factory로 학습한 산출물(예: output/<study>/best_model/)은
adapter_config.json + adapter_model.safetensors만 있는 PEFT LoRA adapter이지
병합된 모델이 아니므로, 베이스 모델 위에 adapter를 얹어서 로드한다.

사용법:
  python scripts/infer_lora.py \\
      --adapter /path/to/best_model \\
      --testset data/testset.jsonl \\
      --output predictions.jsonl \\
      --limit 5   # 스모크 테스트로 앞 5문항만 빠르게 확인하고 싶을 때
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

CODE_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def resolve_base_model(adapter_dir: Path, override: str | None) -> str:
    if override:
        return override
    config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    base_model = config.get("base_model_name_or_path")
    if not base_model:
        raise RuntimeError(
            f"{adapter_dir}/adapter_config.json에 base_model_name_or_path가 없습니다. "
            "--base-model로 직접 지정하세요."
        )
    return base_model


def build_prompt(tokenizer, question: str) -> str:
    messages = [{"role": "user", "content": question}]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def extract_sql(generated_text: str) -> str:
    text = generated_text.strip()
    fenced = CODE_FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    text = re.sub(r"^(sql|answer)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="LoRA adapter로 predictions.jsonl 생성 (스모크 테스트용)")
    parser.add_argument("--adapter", required=True, help="LoRA adapter 디렉토리 (adapter_config.json이 있는 곳)")
    parser.add_argument("--base-model", default=None, help="베이스 모델 이름/경로 (미지정 시 adapter_config.json에서 읽음)")
    parser.add_argument("--testset", default="data/testset.jsonl")
    parser.add_argument("--output", default="predictions.jsonl")
    parser.add_argument("--limit", type=int, default=None, help="앞 N문항만 실행 (스모크 테스트용)")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    args = parser.parse_args()

    adapter_dir = Path(args.adapter)
    base_model_name = resolve_base_model(adapter_dir, args.base_model)

    print(f"베이스 모델: {base_model_name}")
    print(f"어댑터: {adapter_dir}")

    # LLaMA Factory가 내보낸 tokenizer_config.json의 extra_special_tokens가
    # (신형 transformers가 기대하는 dict가 아니라) 구형 리스트 형태라 최신
    # transformers에서 바로 로드하면 AttributeError('list' object has no
    # attribute 'keys')가 난다. 빈 dict로 덮어써서 우회한다 — 실제 special
    # token들은 tokenizer.json에 이미 다 들어있어서 기능상 손실은 없다.
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir, extra_special_tokens={})
    base_model = AutoModelForCausalLM.from_pretrained(base_model_name, dtype="auto", device_map="auto")
    model = PeftModel.from_pretrained(base_model, adapter_dir)
    model.eval()

    testset = load_jsonl(args.testset)
    if args.limit:
        testset = testset[: args.limit]

    results = []
    for row in testset:
        prompt = build_prompt(tokenizer, row["text"])
        inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )
        generated = tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )
        predicted_sql = extract_sql(generated)
        print(f"[{row['id']}] {row['text']}\n  -> {predicted_sql}")
        results.append({"id": row["id"], "predicted_sql": predicted_sql})

    with open(args.output, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n{len(results)}건 저장: {args.output}")


if __name__ == "__main__":
    main()
