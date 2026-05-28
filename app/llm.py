from __future__ import annotations

import os

from .settings import DEFAULT_BASE_URL, DEFAULT_MODEL, LLMSettings, load_llm_settings


DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def normalize_deepseek_base_url(base_url: str | None) -> str:
    value = (base_url or DEFAULT_DEEPSEEK_BASE_URL).strip().rstrip("/")
    if value.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
    if not value:
        return DEFAULT_DEEPSEEK_BASE_URL
    return value


def load_deepseek_runtime_settings() -> LLMSettings:
    settings = load_llm_settings()
    env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    api_key = env_key or settings.api_key.strip()
    base_url = normalize_deepseek_base_url(settings.base_url or DEFAULT_BASE_URL)
    return LLMSettings(
        provider=settings.provider,
        api_key=api_key,
        model=settings.model.strip() or DEFAULT_MODEL,
        base_url=base_url,
        timeout=settings.timeout,
    )


def create_deepseek_chat_model():
    settings = load_deepseek_runtime_settings()
    if not settings.api_key:
        raise RuntimeError("DeepSeek API Key 未配置，请设置 DEEPSEEK_API_KEY 或在设置页保存 API Key")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError("缺少 langchain-openai 依赖，请先执行 pip install -r requirements.txt") from exc

    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout,
        temperature=0.1,
    )
