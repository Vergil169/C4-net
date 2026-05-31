from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import ReactOrchestrator
from .agents import AgentRegistry
from .models import OrchestrationResult, SimulationRequest, SimulationResult, StateResponse
from .settings import (
    LLMSettingsStatus,
    LLMSettingsUpdate,
    LLMTestResult,
    deepseek_chat_completion,
    llm_settings_status,
    load_llm_settings,
    save_llm_settings,
    test_llm_connection,
)
from .simulator import NetworkSimulator
from .utils import recent_intents


class IntentRequest(BaseModel):
    text: str = Field(min_length=3)


class PromptOptimizeResponse(BaseModel):
    optimized_text: str
    source: str
    note: str


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="意图驱动跨域网络自治系统", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

registry = AgentRegistry()
simulator = NetworkSimulator()
orchestrator = ReactOrchestrator(simulator=simulator, registry=registry)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/agents")
def list_agents():
    return registry.list_agents()


@app.get("/api/mcp/tools")
def list_mcp_tools():
    return registry.list_mcp_tools()


@app.get("/api/a2a/messages")
def list_a2a_messages():
    return [] if orchestrator.active_result is None else orchestrator.active_result.messages


@app.get("/api/settings/llm", response_model=LLMSettingsStatus)
def get_llm_settings() -> LLMSettingsStatus:
    return llm_settings_status()


@app.post("/api/settings/llm", response_model=LLMSettingsStatus)
def update_llm_settings(request: LLMSettingsUpdate) -> LLMSettingsStatus:
    return save_llm_settings(request)


@app.post("/api/settings/llm/test", response_model=LLMTestResult)
def test_llm_settings() -> LLMTestResult:
    return test_llm_connection()


@app.get("/api/state", response_model=StateResponse)
def get_state() -> StateResponse:
    nodes, links = simulator.topology()
    return StateResponse(
        agents=registry.list_agents(),
        nodes=nodes,
        links=links,
        telemetry=simulator.telemetry(),
        active_result=orchestrator.active_result,
        recent_intents=recent_intents(),
    )


@app.post("/api/intents", response_model=OrchestrationResult)
def submit_intent(request: IntentRequest) -> OrchestrationResult:
    return orchestrator.submit_intent(request.text)


@app.post("/api/intents/optimize", response_model=PromptOptimizeResponse)
def optimize_intent_prompt(request: IntentRequest) -> PromptOptimizeResponse:
    fallback = _fallback_optimized_prompt(request.text)
    settings = load_llm_settings()
    if not settings.api_key:
        return PromptOptimizeResponse(optimized_text=fallback, source="rule_fallback", note="DeepSeek 未配置，已使用本地模板优化。")
    try:
        response = deepseek_chat_completion(
            settings,
            [
                {"role": "system", "content": "你是网络意图输入优化助手。只输出 JSON，字段为 optimized_text 和 note。保留用户真实诉求，补齐源站点、目标站点、业务场景、SLA、带宽、优先级、避让约束。"},
                {"role": "user", "content": request.text},
            ],
            temperature=0.2,
        )
        content = response["choices"][0]["message"]["content"]
        payload = json.loads(content)
        optimized = str(payload.get("optimized_text") or fallback)
        note = str(payload.get("note") or "DeepSeek 已完成提示词优化。")
        return PromptOptimizeResponse(optimized_text=optimized, source="deepseek", note=note)
    except Exception as exc:
        return PromptOptimizeResponse(optimized_text=fallback, source="rule_fallback", note=f"DeepSeek 优化不可用，已使用本地模板。原因：{exc}")


@app.post("/api/agent/intents", response_model=OrchestrationResult)
def submit_agent_intent(request: IntentRequest) -> OrchestrationResult:
    return orchestrator.submit_intent(request.text)


@app.post("/api/simulate", response_model=SimulationResult)
def simulate(request: SimulationRequest) -> SimulationResult:
    if request.link_id not in simulator.links:
        raise HTTPException(status_code=404, detail="Unknown link_id")
    link = simulator.apply_simulation(request.action, request.link_id)
    active_result = orchestrator.active_result
    healing_triggered = False
    if active_result is not None:
        current_verification = simulator.verify(active_result.intent, active_result.policy)
        if not current_verification.passed:
            active_result = orchestrator.heal()
            healing_triggered = True
    return SimulationResult(
        action=request.action,
        link=link,
        telemetry=simulator.telemetry(),
        healing_triggered=healing_triggered,
        active_result=active_result,
    )


@app.post("/api/heal", response_model=OrchestrationResult)
def heal() -> OrchestrationResult:
    return orchestrator.heal()


def _fallback_optimized_prompt(text: str) -> str:
    normalized = " ".join(text.split())
    if all(keyword in normalized for keyword in ["北京", "上海"]):
        return (
            f"{normalized}。请按关键业务保障处理：源站点北京园区，目标站点上海云服务；"
            "优先选择低时延路径，链路拥塞或故障时自动切换到备用专线；"
            "要求明确输出时延、丢包、带宽、优先级和避让约束。"
        )
    return f"{normalized}。请补齐源站点、目标站点、业务场景、SLA 时延/丢包/带宽、优先级和故障/拥塞避让要求。"
