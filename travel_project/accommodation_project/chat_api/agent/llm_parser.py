from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from threading import Lock
from typing import Any

from .parser_fallback import normalize_rule_result
from .prompt_builder import build_messages, build_plain_prompt
from .schema_normalizer import normalize_parsed_result

logger = logging.getLogger(__name__)


class LLMParserError(RuntimeError):
    pass


@dataclass(frozen=True)
class HFParserConfig:
    model_name: str = os.getenv("CHAT_API_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    fallback_model_name: str | None = os.getenv("CHAT_API_FALLBACK_MODEL") or os.getenv(
        "CHAT_API_LIGHT_MODEL",
        "Qwen/Qwen2.5-0.5B-Instruct",
    )
    strong_model_name: str | None = os.getenv("CHAT_API_STRONG_MODEL") or None
    device: str = os.getenv("CHAT_API_DEVICE", "auto")
    max_new_tokens: int = int(os.getenv("CHAT_API_MAX_NEW_TOKENS", "256"))
    temperature: float = float(os.getenv("CHAT_API_TEMPERATURE", "0.1"))
    top_p: float = float(os.getenv("CHAT_API_TOP_P", "0.9"))
    do_sample: bool = os.getenv("CHAT_API_DO_SAMPLE", "false").strip().lower() in {"1", "true", "yes"}
    timeout_seconds: float = float(os.getenv("CHAT_API_TIMEOUT_SECONDS", "25"))


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    if start == -1:
        raise LLMParserError("LLM output did not contain a JSON object.")

    depth = 0
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start:index + 1]
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise LLMParserError("LLM JSON object is malformed.") from exc
                if not isinstance(payload, dict):
                    raise LLMParserError("LLM JSON payload must be an object.")
                return payload

    raise LLMParserError("LLM JSON object was not closed.")


class HFSlotParser:
    def __init__(self, config: HFParserConfig | None = None):
        self.config = config or HFParserConfig()
        self._pipeline = None
        self._tokenizer = None
        self._loaded_model_name: str | None = None
        self._lock = Lock()

    def parse(
        self,
        text: str,
        *,
        locale: str = "vi",
        context_slots: dict[str, Any] | None = None,
        fallback_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            generated = self._generate(text, locale=locale, context_slots=context_slots)
            payload = _extract_json_object(generated)
            return normalize_parsed_result(
                payload,
                raw_text=text,
                locale=locale,
                context_slots=context_slots,
                fallback_result=fallback_result,
                parser_mode=f"hf_transformers:{self._loaded_model_name or self.config.model_name}",
            )
        except Exception as exc:
            logger.warning("chat_api hf slot parser fallback: %s", exc)
            return normalize_rule_result(
                text,
                locale=locale,
                context_slots=context_slots,
                fallback_result=fallback_result,
            )

    def _generate(self, text: str, *, locale: str, context_slots: dict[str, Any] | None) -> str:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._generate_sync, text, locale, context_slots)
        try:
            return future.result(timeout=self.config.timeout_seconds)
        except TimeoutError as exc:
            future.cancel()
            raise LLMParserError("HF parser generation timed out.") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _generate_sync(self, text: str, locale: str, context_slots: dict[str, Any] | None) -> str:
        pipe = self._ensure_pipeline()
        prompt = self._build_prompt(text, locale=locale, context_slots=context_slots)
        outputs = pipe(
            prompt,
            max_new_tokens=self.config.max_new_tokens,
            do_sample=self.config.do_sample,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            return_full_text=False,
        )
        if isinstance(outputs, list) and outputs:
            generated = outputs[0].get("generated_text") if isinstance(outputs[0], dict) else outputs[0]
            if isinstance(generated, str):
                return generated
        raise LLMParserError("HF parser returned an empty generation.")

    def _build_prompt(self, text: str, *, locale: str, context_slots: dict[str, Any] | None) -> str:
        messages = build_messages(text, locale=locale, context_slots=context_slots)
        tokenizer = self._tokenizer
        if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
            try:
                return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                logger.debug("tokenizer chat template unavailable; using plain prompt", exc_info=True)
        return build_plain_prompt(text, locale=locale, context_slots=context_slots)

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        with self._lock:
            if self._pipeline is not None:
                return self._pipeline

            load_errors: list[str] = []
            for model_name in [self.config.model_name, self.config.fallback_model_name]:
                if not model_name:
                    continue
                try:
                    self._pipeline = self._load_pipeline(model_name)
                    self._loaded_model_name = model_name
                    return self._pipeline
                except Exception as exc:
                    load_errors.append(f"{model_name}: {exc}")

            raise LLMParserError("; ".join(load_errors) or "No HF model configured.")

    def _load_pipeline(self, model_name: str):
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        model_kwargs: dict[str, Any] = {"trust_remote_code": True}
        pipe_kwargs: dict[str, Any] = {}

        if self.config.device == "auto":
            model_kwargs["device_map"] = "auto"
            model_kwargs["torch_dtype"] = "auto"
        elif self.config.device == "cpu":
            pipe_kwargs["device"] = -1
        elif self.config.device.startswith("cuda"):
            pipe_kwargs["device"] = 0

        model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
        self._tokenizer = tokenizer
        return pipeline("text-generation", model=model, tokenizer=tokenizer, **pipe_kwargs)


_parser: HFSlotParser | None = None
_parser_lock = Lock()


def get_hf_slot_parser() -> HFSlotParser:
    global _parser
    if _parser is None:
        with _parser_lock:
            if _parser is None:
                _parser = HFSlotParser()
    return _parser
