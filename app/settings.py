from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_TIMEOUT = 12.0


class LLMSettings(BaseModel):
    provider: str = DEFAULT_PROVIDER
    api_key: str = ""
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT


class LLMSettingsStatus(BaseModel):
    provider: str
    configured: bool
    model: str
    base_url: str
    timeout: float


class LLMSettingsUpdate(BaseModel):
    api_key: str = ""
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout: float = Field(default=DEFAULT_TIMEOUT, ge=1, le=60)


class LLMTestResult(BaseModel):
    ok: bool
    message: str


def settings_path() -> Path:
    override = os.getenv("C4_SETTINGS_DIR")
    if override:
        root = Path(override).resolve()
    else:
        config_home = os.getenv("APPDATA") or os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        root = Path(config_home).resolve() / "C4NetAutonomy"
    return root / "settings.local.json"


def load_llm_settings() -> LLMSettings:
    path = settings_path()
    if not path.exists():
        return LLMSettings(api_key=os.getenv("DEEPSEEK_API_KEY", ""))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    settings = LLMSettings(**payload)
    if not settings.api_key:
        settings.api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return settings


def save_llm_settings(update: LLMSettingsUpdate) -> LLMSettingsStatus:
    settings = LLMSettings(
        provider=DEFAULT_PROVIDER,
        api_key=update.api_key.strip(),
        model=update.model.strip() or DEFAULT_MODEL,
        base_url=update.base_url.strip() or DEFAULT_BASE_URL,
        timeout=update.timeout,
    )
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return llm_settings_status(settings)


def llm_settings_status(settings: LLMSettings | None = None) -> LLMSettingsStatus:
    settings = settings or load_llm_settings()
    return LLMSettingsStatus(
        provider=settings.provider,
        configured=bool(settings.api_key),
        model=settings.model,
        base_url=settings.base_url,
        timeout=settings.timeout,
    )


def deepseek_chat_completion(settings: LLMSettings, messages: list[dict[str, str]], *, temperature: float = 0.1) -> dict[str, Any]:
    if not settings.api_key:
        raise RuntimeError("DeepSeek API Key 未配置")
    payload = {
        "model": settings.model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        settings.base_url or DEFAULT_BASE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DeepSeek 请求失败: {exc}") from exc


def test_llm_connection() -> LLMTestResult:
    settings = load_llm_settings()
    if not settings.api_key:
        return LLMTestResult(ok=False, message="请先输入 DeepSeek API Key")
    try:
        deepseek_chat_completion(
            settings,
            [
                {"role": "system", "content": "请只输出 JSON。"},
                {"role": "user", "content": '输出 {"ok": true}'},
            ],
            temperature=0,
        )
    except RuntimeError as exc:
        return LLMTestResult(ok=False, message=str(exc))
    return LLMTestResult(ok=True, message="DeepSeek 连接测试成功")
