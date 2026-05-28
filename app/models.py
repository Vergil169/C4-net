from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


IntentStatus = Literal["pending", "achieved", "partial", "conflict", "failed", "healing"]
LinkHealth = Literal["normal", "congested", "failed"]
SimulationAction = Literal["congest", "fail", "recover"]


class BusinessIntent(BaseModel):
    source: str
    destination: str
    service: str
    max_latency_ms: int
    max_loss_percent: float
    min_bandwidth_mbps: int
    priority: Literal["low", "medium", "high", "critical"]
    constraints: list[str] = Field(default_factory=list)
    raw_text: str
    parse_source: Literal["deepseek", "rule_fallback"] = "rule_fallback"
    confidence: float = 0.65
    parse_note: str = ""


class AgentProfile(BaseModel):
    name: str
    role: str
    capabilities: list[str]
    protocol: str = "A2A/MCP"


class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class A2AMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sender: str
    receiver: str
    performative: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskStep(BaseModel):
    id: str
    agent: str
    action: str
    status: Literal["pending", "running", "done", "blocked"] = "pending"
    detail: str


class Link(BaseModel):
    id: str
    source: str
    target: str
    domain: str
    latency_ms: int
    loss_percent: float
    capacity_mbps: int
    utilization_percent: int
    health: LinkHealth = "normal"


class Node(BaseModel):
    id: str
    label: str
    domain: str
    kind: Literal["campus", "backbone", "cloud", "edge", "dr"]


class TelemetrySnapshot(BaseModel):
    link_id: str
    latency_ms: int
    loss_percent: float
    utilization_percent: int
    health: LinkHealth


class NetworkPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: f"POL-{uuid4().hex[:8].upper()}")
    path: list[str]
    selected_links: list[str]
    qos_class: str
    bandwidth_reservation_mbps: int
    acl_rules: list[str]
    route_rules: list[str]
    config_preview: list[str]
    dry_run: bool = True


class VerificationResult(BaseModel):
    status: IntentStatus
    passed: bool
    latency_ms: int
    loss_percent: float
    bottleneck_utilization_percent: int
    issues: list[str] = Field(default_factory=list)
    recommendation: str


class OrchestrationResult(BaseModel):
    intent_id: str = Field(default_factory=lambda: f"INT-{uuid4().hex[:8].upper()}")
    intent: BusinessIntent
    tasks: list[TaskStep]
    messages: list[A2AMessage]
    nodes: list[Node]
    links: list[Link]
    telemetry: list[TelemetrySnapshot]
    policy: NetworkPolicy
    verification: VerificationResult
    status: IntentStatus
    healed: bool = False


class SimulationRequest(BaseModel):
    action: SimulationAction
    link_id: str = "lnk-tianjin-jinan"


class SimulationResult(BaseModel):
    action: SimulationAction
    link: Link
    telemetry: list[TelemetrySnapshot]


class StateResponse(BaseModel):
    agents: list[AgentProfile]
    nodes: list[Node]
    links: list[Link]
    telemetry: list[TelemetrySnapshot]
    active_result: OrchestrationResult | None = None
    recent_intents: list[dict[str, Any]] = Field(default_factory=list)
