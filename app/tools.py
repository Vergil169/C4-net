from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from .agents import IntentAgent
from .models import BusinessIntent, NetworkPolicy, VerificationResult
from .simulator import CandidatePath, NetworkSimulator


class IntentTextInput(BaseModel):
    text: str = Field(description="用户输入的自然语言网络业务意图，例如北京到上海的视频会议低时延保障。")


class OptionalLinkInput(BaseModel):
    link_id: str | None = Field(default=None, description="可选链路 ID。为空时返回全部链路遥测。")


class IntentPayloadInput(BaseModel):
    intent: dict[str, Any] | None = Field(default=None, description="结构化业务意图 JSON。为空时使用最近一次解析出的意图。")
    avoid_degraded: bool = Field(default=True, description="是否避开故障、拥塞或高利用率链路。")


class PolicyVerifyInput(BaseModel):
    intent: dict[str, Any] | None = Field(default=None, description="结构化业务意图 JSON。为空时使用最近一次解析出的意图。")
    policy: dict[str, Any] | None = Field(default=None, description="待验证的网络策略 JSON。为空时使用最近一次生成的策略。")


class HealingInput(BaseModel):
    intent: dict[str, Any] | None = Field(default=None, description="需要自愈重规划的结构化业务意图 JSON。为空时使用最近一次解析出的意图。")
    reason: str = Field(default="SLA violation or degraded link detected", description="触发自愈的原因，例如链路拥塞、链路故障或 SLA 未达成。")


class NetworkToolContext:
    def __init__(self) -> None:
        self.intent: BusinessIntent | None = None
        self.topology: dict[str, Any] | None = None
        self.telemetry: list[dict[str, Any]] | None = None
        self.path_plan: dict[str, Any] | None = None
        self.policy: NetworkPolicy | None = None
        self.verification: VerificationResult | None = None
        self.healing_reason: str | None = None


class NetworkToolKit:
    def __init__(self, simulator: NetworkSimulator, context: NetworkToolContext | None = None) -> None:
        self.simulator = simulator
        self.context = context or NetworkToolContext()
        self.intent_agent = IntentAgent()

    def create_tools(self) -> list[BaseTool]:
        simulator = self.simulator
        context = self.context
        intent_agent = self.intent_agent

        @tool(
            "parse_business_intent",
            args_schema=IntentTextInput,
            description=(
                "意图解析工具。功能：把用户自然语言网络诉求解析为结构化业务意图。"
                "输入：text 自然语言意图。输出：BusinessIntent JSON，包含源、目的、业务类型、SLA、优先级、约束、置信度。"
                "适用场景：所有新意图处理的第一步，必须先调用本工具获得标准意图对象。"
            ),
        )
        def parse_business_intent(text: str) -> dict[str, Any]:
            intent = intent_agent.parse(text)
            context.intent = intent
            return intent.model_dump(mode="json")

        @tool(
            "query_network_topology",
            description=(
                "拓扑查询工具。功能：查询当前跨域网络节点和链路状态。"
                "输入：无。输出：nodes 与 links 两个数组，字段与原系统 Node/Link JSON 一致。"
                "适用场景：路径规划、策略生成、自愈前需要了解全网拓扑时调用。"
            ),
        )
        def query_network_topology() -> dict[str, Any]:
            nodes, links = simulator.topology()
            payload = {
                "nodes": [node.model_dump(mode="json") for node in nodes],
                "links": [link.model_dump(mode="json") for link in links],
            }
            context.topology = payload
            return payload

        @tool(
            "collect_telemetry_snapshot",
            args_schema=OptionalLinkInput,
            description=(
                "遥测采集工具。功能：采集链路时延、丢包率、利用率和健康状态。"
                "输入：可选 link_id；为空返回全部链路，指定时只返回该链路。输出：TelemetrySnapshot JSON 数组。"
                "适用场景：策略生成、SLA 验证和自愈判断前必须获取当前链路健康状态。"
            ),
        )
        def collect_telemetry_snapshot(link_id: str | None = None) -> list[dict[str, Any]]:
            telemetry = [item.model_dump(mode="json") for item in simulator.telemetry()]
            if link_id:
                telemetry = [item for item in telemetry if item["link_id"] == link_id]
            context.telemetry = telemetry
            return telemetry

        @tool(
            "plan_candidate_path",
            args_schema=IntentPayloadInput,
            description=(
                "路径规划工具。功能：根据结构化意图和当前遥测选择候选路径。"
                "输入：intent 结构化意图，可选 avoid_degraded 是否避开退化链路。"
                "输出：path 节点 ID、selected_links 链路 ID、总时延、总丢包、瓶颈带宽、瓶颈利用率。"
                "适用场景：生成策略前需要先判断可用路径和链路质量。"
            ),
        )
        def plan_candidate_path(intent: dict[str, Any] | None = None, avoid_degraded: bool = True) -> dict[str, Any]:
            parsed_intent = _resolve_intent(context, intent)
            candidate = simulator._select_path(parsed_intent, avoid_degraded)
            payload = _path_payload(simulator, candidate)
            context.intent = parsed_intent
            context.path_plan = payload
            return payload

        @tool(
            "generate_network_policy",
            args_schema=IntentPayloadInput,
            description=(
                "策略生成工具。功能：根据业务意图、路径规划和遥测状态生成网络执行策略。"
                "输入：intent 结构化意图，可选 avoid_degraded。输出：NetworkPolicy JSON，包含路径、QoS、带宽预留、ACL、路由规则和配置预览。"
                "适用场景：意图已解析且已查询拓扑/遥测后，生成可演示的网络策略。"
            ),
        )
        def generate_network_policy(intent: dict[str, Any] | None = None, avoid_degraded: bool = True) -> dict[str, Any]:
            parsed_intent = _resolve_intent(context, intent)
            policy = simulator.generate_policy(parsed_intent, avoid_degraded=avoid_degraded)
            context.intent = parsed_intent
            context.policy = policy
            return policy.model_dump(mode="json")

        @tool(
            "verify_sla_compliance",
            args_schema=PolicyVerifyInput,
            description=(
                "SLA 验证工具。功能：验证策略是否满足连通性、链路健康、时延、丢包率和带宽约束。"
                "输入：intent 结构化意图与 policy 网络策略；为空时使用最近一次上下文。"
                "输出：VerificationResult JSON，包含 passed、status、指标、issues 和 recommendation。"
                "适用场景：策略生成后必须调用，用于决定是否达成意图或触发自愈。"
            ),
        )
        def verify_sla_compliance(intent: dict[str, Any] | None = None, policy: dict[str, Any] | None = None) -> dict[str, Any]:
            parsed_intent = _resolve_intent(context, intent)
            parsed_policy = _resolve_policy(context, policy)
            verification = simulator.verify(parsed_intent, parsed_policy)
            context.intent = parsed_intent
            context.policy = parsed_policy
            context.verification = verification
            return verification.model_dump(mode="json")

        @tool(
            "heal_and_replan_policy",
            args_schema=HealingInput,
            description=(
                "自愈重规划工具。功能：当链路拥塞、故障或 SLA 未达成时，避开退化链路重新规划并生成新策略。"
                "输入：intent 结构化意图和 reason 自愈原因。输出：新的 path_plan、policy、verification 组合 JSON。"
                "适用场景：验证结果 failed、partial，或遥测显示 congested/failed 链路影响当前路径时调用。"
            ),
        )
        def heal_and_replan_policy(intent: dict[str, Any] | None = None, reason: str = "SLA violation or degraded link detected") -> dict[str, Any]:
            parsed_intent = _resolve_intent(context, intent)
            candidate = simulator._select_path(parsed_intent, avoid_degraded=True)
            path_plan = _path_payload(simulator, candidate)
            policy = simulator.generate_policy(parsed_intent, avoid_degraded=True)
            verification = simulator.verify(parsed_intent, policy)
            context.intent = parsed_intent
            context.path_plan = path_plan
            context.policy = policy
            context.verification = verification
            context.healing_reason = reason
            return {
                "reason": reason,
                "path_plan": path_plan,
                "policy": policy.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
            }

        return [
            parse_business_intent,
            query_network_topology,
            collect_telemetry_snapshot,
            plan_candidate_path,
            generate_network_policy,
            verify_sla_compliance,
            heal_and_replan_policy,
        ]


def _resolve_intent(context: NetworkToolContext, payload: dict[str, Any] | None) -> BusinessIntent:
    if payload is None:
        if context.intent is None:
            raise ValueError("缺少结构化意图，请先调用 parse_business_intent")
        return context.intent
    intent = BusinessIntent.model_validate(payload)
    context.intent = intent
    return intent


def _resolve_policy(context: NetworkToolContext, payload: dict[str, Any] | None) -> NetworkPolicy:
    if payload is None:
        if context.policy is None:
            raise ValueError("缺少网络策略，请先调用 generate_network_policy")
        return context.policy
    policy = NetworkPolicy.model_validate(payload)
    context.policy = policy
    return policy


def _path_payload(simulator: NetworkSimulator, candidate: CandidatePath) -> dict[str, Any]:
    links = [simulator.links[link_id] for link_id in candidate.links]
    return {
        "path": candidate.nodes,
        "selected_links": candidate.links,
        "latency_ms": sum(link.latency_ms for link in links),
        "loss_percent": round(sum(link.loss_percent for link in links), 2),
        "bottleneck_capacity_mbps": min(link.capacity_mbps for link in links),
        "bottleneck_utilization_percent": max(link.utilization_percent for link in links),
    }
