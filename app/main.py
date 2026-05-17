from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import AgentRegistry, Orchestrator
from .models import SimulationRequest, SimulationResult, StateResponse
from .simulator import NetworkSimulator


class IntentRequest(BaseModel):
    text: str = Field(min_length=3)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="意图驱动跨域网络自治系统", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

registry = AgentRegistry()
simulator = NetworkSimulator()
orchestrator = Orchestrator(simulator=simulator, registry=registry)


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


@app.get("/api/state", response_model=StateResponse)
def get_state() -> StateResponse:
    nodes, links = simulator.topology()
    return StateResponse(
        agents=registry.list_agents(),
        nodes=nodes,
        links=links,
        telemetry=simulator.telemetry(),
        active_result=orchestrator.active_result,
    )


@app.post("/api/intents")
def submit_intent(request: IntentRequest):
    return orchestrator.submit_intent(request.text)


@app.post("/api/simulate", response_model=SimulationResult)
def simulate(request: SimulationRequest) -> SimulationResult:
    if request.link_id not in simulator.links:
        raise HTTPException(status_code=404, detail="Unknown link_id")
    link = simulator.apply_simulation(request.action, request.link_id)
    return SimulationResult(action=request.action, link=link, telemetry=simulator.telemetry())


@app.post("/api/heal")
def heal():
    return orchestrator.heal()
