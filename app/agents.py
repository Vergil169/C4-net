from __future__ import annotations

import json
import re
from typing import Any

from .models import A2AMessage, AgentProfile, BusinessIntent, MCPTool, OrchestrationResult, TaskStep
from .settings import deepseek_chat_completion, load_llm_settings
from .simulator import NetworkSimulator


class AgentRegistry:
    def __init__(self) -> None:
        self._agents = [
            AgentProfile(name="Intent Agent", role="意图识别", capabilities=["自然语言解析", "SLA 提取", "业务分类"]),
            AgentProfile(name="Planner Agent", role="任务规划", capabilities=["任务拆解", "Agent 编排", "闭环流程生成"]),
            AgentProfile(name="Topology Agent", role="拓扑感知", capabilities=["跨域拓扑查询", "服务发现", "候选路径生成"]),
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
    SYSTEM_PROMPT = """你是网络意图解析专家。必须严格输出 JSON，不要输出 Markdown、解释文字或多余字段。
从用户输入中提取：业务类型、源站点、目标站点、SLA 参数（时延/丢包/带宽）、优先级和约束。
如果表达模糊，请基于网络工程常识补全合理默认值，并在 parse_note 中说明依据。
输出格式：
{
  "service": "视频会议/语音/核心交易/灾备同步/通用业务",
  "source": "源域或源站点",
  "destination": "目的域或目的站点",
  "max_latency_ms": 50,
  "max_loss_percent": 1.0,
  "min_bandwidth_mbps": 100,
  "priority": "low|medium|high|critical",
  "constraints": ["avoid_congestion", "low_latency", "high_bandwidth", "security_first"],
  "confidence": 0.0,
  "parse_note": "简短说明"
}
"""

    def parse(self, text: str) -> BusinessIntent:
        try:
            return self._parse_with_deepseek(text)
        except Exception as exc:
            return self._parse_with_rules(text, note=f"模型解析不可用，已使用本地规则解析。原因：{exc}")

    def _parse_with_deepseek(self, text: str) -> BusinessIntent:
        settings = load_llm_settings()
        response = deepseek_chat_completion(
            settings,
            [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
        )
        content = response["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return self._intent_from_payload(parsed, text, parse_source="deepseek")

    def _parse_with_rules(self, text: str, note: str = "已使用本地规则解析。") -> BusinessIntent:
        max_latency = self._extract_number(text, r"(\d+)\s*ms|(\d+)\s*毫秒|时延[^\d]*(\d+)|延迟[^\d]*(\d+)", default=50)
        max_loss = float(self._extract_number(text, r"丢包率?[^\d]*(\d+(?:\.\d+)?)\s*%|loss[^\d]*(\d+(?:\.\d+)?)\s*%", default=1))
        bandwidth = self._extract_number(text, r"(\d+)\s*(?:Gbps|gbps|G|吉)", default=0) * 1000
        if bandwidth == 0:
            bandwidth = self._extract_number(text, r"(\d+)\s*(?:Mbps|mbps|M|兆)|带宽[^\d]*(\d+)", default=100)

        service = self._detect_service(text)
        source = self._detect_domain(text, default="源业务域", source=True)
        destination = self._detect_domain(text, default="目标业务域", source=False)
        constraints: list[str] = []
        if any(word in text for word in ["避开拥塞", "拥塞", "绕行"]):
            constraints.append("avoid_congestion")
        if any(word in text for word in ["安全", "隔离"]):
            constraints.append("security_first")
        if any(word in text for word in ["低时延", "时延", "延迟", "实时", "低抖动"]):
            constraints.append("low_latency")
        if any(word in text for word in ["大带宽", "高吞吐"]) or bandwidth >= 500:
            constraints.append("high_bandwidth")

        return BusinessIntent(
            source=source,
            destination=destination,
            service=service,
            max_latency_ms=max_latency,
            max_loss_percent=max_loss,
            min_bandwidth_mbps=bandwidth,
            priority=self._detect_priority(text, service),
            constraints=constraints,
            raw_text=text,
            parse_source="rule_fallback",
            confidence=0.7 if source != "源业务域" and destination != "目标业务域" else 0.55,
            parse_note=note,
        )

    def _intent_from_payload(self, payload: dict[str, Any], raw_text: str, parse_source: str) -> BusinessIntent:
        required = ["service", "source", "destination", "max_latency_ms", "max_loss_percent", "min_bandwidth_mbps", "priority"]
        if not all(key in payload for key in required):
            raise ValueError("模型响应缺少必要字段")
        priority = str(payload["priority"]).lower()
        if priority not in {"low", "medium", "high", "critical"}:
            priority = "high"
        constraints = payload.get("constraints") or []
        if not isinstance(constraints, list):
            constraints = []
        return BusinessIntent(
            source=str(payload["source"] or "源业务域"),
            destination=str(payload["destination"] or "目标业务域"),
            service=str(payload["service"] or "通用业务"),
            max_latency_ms=max(1, int(float(payload["max_latency_ms"]))),
            max_loss_percent=max(0.0, float(payload["max_loss_percent"])),
            min_bandwidth_mbps=max(1, int(float(payload["min_bandwidth_mbps"]))),
            priority=priority,  # type: ignore[arg-type]
            constraints=[str(item) for item in constraints],
            raw_text=raw_text,
            parse_source=parse_source,  # type: ignore[arg-type]
            confidence=min(1.0, max(0.0, float(payload.get("confidence", 0.85)))),
            parse_note=str(payload.get("parse_note", "DeepSeek 结构化解析成功。")),
        )

    def _extract_number(self, text: str, pattern: str, default: int) -> int:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return default
        value = next(group for group in match.groups() if group is not None)
        return int(float(value))

    def _detect_service(self, text: str) -> str:
        if "视频" in text or "会议" in text or "VC" in text.upper():
            return "视频会议"
        if "语音" in text or "VoIP" in text or "SIP" in text.upper():
            return "语音"
        if "交易" in text or "支付" in text or "核心" in text:
            return "核心交易"
        if "灾备" in text or "备份" in text or "同步" in text:
            return "灾备同步"
        if "实时" in text or "低抖动" in text:
            return "实时业务"
        return "通用业务"

    def _detect_domain(self, text: str, default: str, source: bool) -> str:
        domains = ["北京园区", "上海云服务", "天津骨干", "济南骨干", "广州灾备", "华北接入域", "华东云域", "华南灾备域"]
        matches = [domain for domain in domains if domain[:2] in text or domain in text]
        if not matches:
            return default
        return matches[0] if source else matches[-1]

    def _detect_priority(self, text: str, service: str) -> str:
        if "最高" in text or "关键" in text or "P0" in text.upper() or service in {"视频会议", "语音", "实时业务"}:
            return "critical"
        if "普通" in text or "一般" in text:
            return "medium"
        if "低优先" in text:
            return "low"
        return "high"


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

        if healing:
            policy, verification, healing_attempts = self.simulator.heal_policy(intent)
        else:
            policy = self.simulator.generate_policy(intent, avoid_degraded=True)
            verification = self.simulator.verify(intent, policy)
            healing_attempts = 0
        bus.send("Policy Agent", "Verification Agent", "request", {"policy_id": policy.policy_id, "path": policy.path})
        if healing:
            bus.send("Healing Agent", "Verification Agent", "inform", {"attempts": healing_attempts, "passed": verification.passed})
            tasks[-1].status = "done" if verification.passed else "blocked"
            if not verification.passed:
                tasks[-1].detail = f"已重试 {healing_attempts} 次，仍无可行路径"
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
            status=verification.status,
            healed=healing and verification.passed,
        )
        self.active_result = result
        return result
