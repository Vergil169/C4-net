from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import OrchestrationResult
from .settings import settings_path

if TYPE_CHECKING:
    from .simulator import NetworkSimulator


MAX_RECENT_INTENTS = 10


def state_path() -> Path:
    override = os.getenv("C4_STATE_FILE")
    if override:
        return Path(override).resolve()
    return settings_path().parent / "state.local.json"


def load_runtime_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_runtime_state(payload: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def restore_simulator_state(simulator: "NetworkSimulator") -> None:
    payload = load_runtime_state()
    links = payload.get("links")
    if not isinstance(links, dict):
        return
    for link_id, saved in links.items():
        if link_id not in simulator.links or not isinstance(saved, dict):
            continue
        link = simulator.links[link_id]
        for field in ("latency_ms", "loss_percent", "utilization_percent", "health"):
            if field in saved:
                setattr(link, field, saved[field])


def persist_runtime_state(simulator: "NetworkSimulator", active_result: OrchestrationResult | None = None) -> None:
    current = load_runtime_state()
    payload: dict[str, Any] = {
        "links": {
            link_id: {
                "latency_ms": link.latency_ms,
                "loss_percent": link.loss_percent,
                "utilization_percent": link.utilization_percent,
                "health": link.health,
            }
            for link_id, link in simulator.links.items()
        },
        "recent_intents": current.get("recent_intents", []),
    }
    if active_result is not None:
        result_payload = active_result.model_dump(mode="json")
        payload["active_result"] = result_payload
        payload["recent_intents"] = _append_recent_intent(current.get("recent_intents", []), active_result)
    elif "active_result" in current:
        payload["active_result"] = current["active_result"]
    save_runtime_state(payload)


def load_active_result() -> OrchestrationResult | None:
    active = load_runtime_state().get("active_result")
    if not isinstance(active, dict):
        return None
    try:
        return OrchestrationResult.model_validate(active)
    except Exception:
        return None


def recent_intents() -> list[dict[str, Any]]:
    value = load_runtime_state().get("recent_intents", [])
    return value if isinstance(value, list) else []


def _append_recent_intent(history: Any, result: OrchestrationResult) -> list[dict[str, Any]]:
    items = history if isinstance(history, list) else []
    summary = {
        "intent_id": result.intent_id,
        "raw_text": result.intent.raw_text,
        "service": result.intent.service,
        "source": result.intent.source,
        "destination": result.intent.destination,
        "status": result.status,
        "healed": result.healed,
    }
    deduped = [item for item in items if isinstance(item, dict) and item.get("intent_id") != result.intent_id]
    return ([summary] + deduped)[:MAX_RECENT_INTENTS]
