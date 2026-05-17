from __future__ import annotations

import re
from typing import Any

from .models import A2AMessage, AgentProfile, BusinessIntent, MCPTool, OrchestrationResult, TaskStep
from .simulator import NetworkSimulator


class AgentRegistry:
    def __init__(self) -> None:
        self._agents = [
            AgentProfile(name="Intent Agent", role="意图识别", capabilities=["自然语言解析", "SLA 抽取", "业务分类"]),
            AgentProfile(name="Planner Agent", role="任务规划", capabilities=["任务拆解", "Agent 编排", "闭环流程生成"]),
            AgentProfile(name="Topology Agent", role="拓扑感知", capabilities=["跨域拓扑查询", "服务发现", "路径候选生成"]),
            AgentProfile(name="Telemetry Agent", role="遥测采集", capabilities=["链路状态采集", "拥塞识别", "故障识别"]),
            AgentProfile(name="Policy Agent", role="策略生成", capabilities=["QoS", "ACL", "路由策略", "配置预览"]),
            AgentProfile(name="Verification Agent", role="闭环验证", capabilities=["SLA 验证", "冲突检测", "连通性验证"]),
            AgentProfile(name="Healing Agent", role="自愈重构", capabilities=["故障绕行", "拥塞避让", "策略重规划"]),
        ]

    def list_agents(self) -> list[AgentProfile]:
        return self._agents

    def list_mcp_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="mcp.topology.query",
                description="查询跨域网络拓扑、节点域信息和链路基线状态。",
                input_schema={"type": "object", "properties": {"domain": {"type": "string"}}},
                output_schema={"type": "object", "properties": {"nodes": {"type": "array"}, "links": {"type": "array"}}},
            ),
            MCPTool(
                name="mcp.telemetry.snapshot",
                description="采集链路时延、丢包、利用率和健康状态。",
                input_schema={"type": "object", "properties": {"link_id": {"type": "string"}}},
                output_schema={"type": "array", "items": {"type": "object"}},
            ),
            MCPTool(
                name="mcp.policy.generate",
                description="根据结构化意图和遥测状态生成网络策略。",
                input_schema={"type": "object", "properties": {"intent": {"type": "object"}, "avoid_degraded": {"type": "boolean"}}},
                output_schema={"type": "object", "properties": {"policy_id": {"type": "string"}, "selected_links": {"type": "array"}}},
            ),
            MCPTool(
                name="mcp.verification.verify",
                description="验证策略是否满足 SLA、连通性和冲突约束。",
                input_schema={"type": "object", "properties": {"intent": {"type": "object"}, "policy": {"type": "object"}}},
                output_schema={"type": "object", "properties": {"passed": {"type": "boolean"}, "issues": {"type": "array"}}},
            ),
        ]


class IntentAgent:
    def parse(self, text: str) -> BusinessIntent:
        max_latency = self._extract_number(text, r"(\d+)\s*ms|时延[^\d]*(\d+)", default=50)
        max_loss = float(self._extract_number(text, r"丢包率?[^\d]*(\d+(?:\.\d+)?)\s*%", default=1))
        bandwidth = self._extract_number(text, r"(\d+)\s*(?:Mbps|mbps|M|兆)", default=100)
        service = self._detect_service(text)
        source = "北京园区" if "北京" in text else "源业务域"
        destination = "上海云服务" if "上海" in text else "目标业务域"
        constraints: list[str] = []
        if "避开拥塞" in text or "拥塞" in text:
            constraints.append("avoid_congestion")
        if "安全" in text or "隔离" in text:
            constraints.append("security_first")
        if "低时延" in text or "时延" in text:
            constraints.append("low_latency")
        return BusinessIntent(
            source=source,
            destination=destination,
            service=service,
            max_latency_ms=max_latency,
            max_loss_percent=max_loss,
            min_bandwidth_mbps=bandwidth,
            priority="critical" if service in {"视频会议", "语音", "实时业务"} else "high",
            constraints=constraints,
            raw_text=text,
        )

    def _extract_number(self, text: str, pattern: str, default: int) -> int:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return default
        value = next(group for group in match.groups() if group is not None)
        return int(float(value))

    def _detect_service(self, text: str) -> str:
        if "视频" in text or "会议" in text:
            return "视频会议"
        if "语音" in text:
            return "语音"
        if "核心" in text:
            return "核心业务"
        if "灾备" in text:
            return "灾备同步"
        return "通用业务"


class PlannerAgent:
    def __init__(self) -> None:
        self.graph_backend = self._detect_graph_backend()

    def build_tasks(self) -> list[TaskStep]:
        return [
            TaskStep(id="T1", agent="Intent Agent", action="parse_intent", status="done", detail="解析自然语言意图与 SLA 约束"),
            TaskStep(id="T2", agent="Topology Agent", action="query_topology", status="done", detail="查询跨域拓扑、节点和链路状态"),
            TaskStep(id="T3", agent="Telemetry Agent", action="collect_metrics", status="done", detail="采集链路时延、丢包、利用率和健康状态"),
            TaskStep(id="T4", agent="Policy Agent", action="generate_policy", status="done", detail="生成 QoS、ACL、路径和配置预览"),
            TaskStep(id="T5", agent="Verification Agent", action="verify_sla", status="done", detail="验证 SLA、连通性和策略冲突"),
        ]

    def _detect_graph_backend(self) -> str:
        try:
            import langgraph  # noqa: F401

            return "LangGraph"
        except Exception:
            return "DeterministicGraph"


class A2ABus:
    def __init__(self) -> None:
        self.messages: list[A2AMessage] = []

    def send(self, sender: str, receiver: str, performative: str, payload: dict[str, Any]) -> None:
        self.messages.append(A2AMessage(sender=sender, receiver=receiver, performative=performative, payload=payload))


class Orchestrator:
    def __init__(self, simulator: NetworkSimulator, registry: AgentRegistry) -> None:
        self.simulator = simulator
        self.registry = registry
        self.intent_agent = IntentAgent()
        self.planner_agent = PlannerAgent()
        self.active_result: OrchestrationResult | None = None

    def submit_intent(self, text: str) -> OrchestrationResult:
        return self._run(text=text, healing=False)

    def heal(self) -> OrchestrationResult:
        if self.active_result is None:
            return self._run(
                text="请保障北京园区到上海云服务的视频会议业务，要求时延低于50ms，丢包率低于1%，优先避开拥塞链路。",
                healing=True,
            )
        return self._run(text=self.active_result.intent.raw_text, healing=True)

    def _run(self, text: str, healing: bool) -> OrchestrationResult:
        bus = A2ABus()
        bus.send("GUI", "Intent Agent", "request", {"text": text})
        intent = self.intent_agent.parse(text)
        bus.send("Intent Agent", "Planner Agent", "inform", {"intent": intent.model_dump(), "graph_backend": self.planner_agent.graph_backend})

        tasks = self.planner_agent.build_tasks()
        if healing:
            tasks.append(TaskStep(id="T6", agent="Healing Agent", action="replan", status="done", detail="根据异常遥测避开退化链路并重规划"))
            bus.send("Telemetry Agent", "Healing Agent", "alert", {"reason": "SLA violation or degraded link detected"})
            bus.send("Healing Agent", "Planner Agent", "request", {"action": "replan_with_degraded_links_avoided"})

        nodes, links = self.simulator.topology()
        telemetry = self.simulator.telemetry()
        bus.send("Planner Agent", "Topology Agent", "request", {"tool": "mcp.topology.query"})
        bus.send("Topology Agent", "Policy Agent", "inform", {"nodes": len(nodes), "links": len(links)})
        bus.send("Planner Agent", "Telemetry Agent", "request", {"tool": "mcp.telemetry.snapshot"})
        bus.send("Telemetry Agent", "Policy Agent", "inform", {"snapshots": [item.model_dump() for item in telemetry]})

        policy = self.simulator.generate_policy(intent, avoid_degraded=True)
        bus.send("Policy Agent", "Verification Agent", "request", {"policy_id": policy.policy_id, "path": policy.path})
        verification = self.simulator.verify(intent, policy)
        bus.send("Verification Agent", "GUI", "inform", verification.model_dump())

        result = OrchestrationResult(
            intent=intent,
            tasks=tasks,
            messages=bus.messages,
            nodes=nodes,
            links=links,
            telemetry=telemetry,
            policy=policy,
            verification=verification,
            status=verification.status if not healing or verification.passed else "healing",
            healed=healing and verification.passed,
        )
        self.active_result = result
        return result
