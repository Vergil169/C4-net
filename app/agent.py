from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .agents import A2ABus, AgentRegistry, Orchestrator, PlannerAgent
from .llm import create_deepseek_chat_model
from .models import A2AMessage, OrchestrationResult, TaskStep
from .simulator import NetworkSimulator
from .tools import NetworkToolContext, NetworkToolKit
from .utils import load_active_result, persist_runtime_state


SYSTEM_PROMPT = """你是意图驱动网络自治系统智能体。
你需要自动理解用户自然语言网络意图，自动选择工具并多轮调用，完成意图解析、拓扑查询、遥测采集、路径规划、策略生成、SLA 验证和必要时的自愈重规划。
工作顺序必须遵循：解析意图 -> 查询拓扑和遥测 -> 路径规划 -> 策略生成 -> SLA 验证 -> 如果验证失败或链路退化则自愈重规划。
最多进行 8 轮工具调用；如果已经拿到完整结果，必须停止调用工具。
最终只输出一个 JSON 对象，字段必须与原系统 OrchestrationResult 兼容，不要输出 Markdown 或解释文字。
"""


class ReactOrchestrator:
    def __init__(self, simulator: NetworkSimulator, registry: AgentRegistry) -> None:
        self.simulator = simulator
        self.registry = registry
        self.planner_agent = PlannerAgent()
        self.fallback = Orchestrator(simulator=simulator, registry=registry)
        self.active_result: OrchestrationResult | None = load_active_result()
        self.fallback.active_result = self.active_result

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
        context = NetworkToolContext()
        toolkit = NetworkToolKit(self.simulator, context)
        tools = toolkit.create_tools()
        tool_map = {item.name: item for item in tools}

        try:
            model = create_deepseek_chat_model()
            # LangGraph 1.x recommends create_agent, but this project intentionally
            # uses create_react_agent now to satisfy the ReAct upgrade requirement.
            graph = create_react_agent(model, tools, prompt=SYSTEM_PROMPT)
            graph.invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                f"用户网络意图：{text}\n"
                                f"是否为自愈重规划：{healing}\n"
                                "请按系统提示调用工具并最终输出原系统兼容 JSON。"
                            )
                        )
                    ]
                },
                config={"recursion_limit": 16},
            )
            result = self._result_from_context(text, healing, context, tool_map, graph_backend="LangGraph ReAct")
        except Exception as exc:
            result = self._fallback_result(text, healing, exc)

        self.active_result = result
        self.fallback.active_result = result
        persist_runtime_state(self.simulator, result)
        return result

    def _result_from_context(
        self,
        text: str,
        healing: bool,
        context: NetworkToolContext,
        tool_map: dict[str, Any],
        graph_backend: str,
    ) -> OrchestrationResult:
        if context.intent is None:
            tool_map["parse_business_intent"].invoke({"text": text})
        if context.topology is None:
            tool_map["query_network_topology"].invoke({})
        if context.telemetry is None:
            tool_map["collect_telemetry_snapshot"].invoke({})
        if context.path_plan is None:
            tool_map["plan_candidate_path"].invoke({"intent": context.intent.model_dump(mode="json")})
        if context.policy is None:
            tool_map["generate_network_policy"].invoke({"intent": context.intent.model_dump(mode="json")})
        if healing:
            tool_map["heal_and_replan_policy"].invoke(
                {
                    "intent": context.intent.model_dump(mode="json"),
                    "reason": "SLA violation or degraded link detected",
                }
            )
        if context.verification is None:
            tool_map["verify_sla_compliance"].invoke(
                {
                    "intent": context.intent.model_dump(mode="json"),
                    "policy": context.policy.model_dump(mode="json"),
                }
            )

        assert context.intent is not None

        nodes, links = self.simulator.topology()
        telemetry = self.simulator.telemetry()
        healing_trace = []
        auto_healing = False
        if healing:
            base_result = self.active_result
            original_policy = base_result.policy if base_result is not None else self.simulator.generate_policy(context.intent, avoid_degraded=True)
            original_verification = base_result.verification if base_result is not None else self.simulator.verify(context.intent, original_policy)
            healed_policy, healed_verification, attempts = self.simulator.heal_policy(context.intent)
            context.policy = healed_policy
            context.verification = healed_verification
            context.healing_attempts = attempts
            healing_trace = self.simulator.build_healing_trace(context.intent, original_policy, original_verification, healed_policy, healed_verification, attempts)
        else:
            original_policy = self.simulator.generate_policy(context.intent, avoid_degraded=True)
            original_verification = self.simulator.verify(context.intent, original_policy)
            if original_verification.passed:
                context.policy = original_policy
                context.verification = original_verification
            else:
                context.policy = original_policy
                context.verification = original_verification
                original_policy = context.policy
                original_verification = context.verification
                healed_policy, healed_verification, attempts = self.simulator.heal_policy(context.intent)
                context.policy = healed_policy
                context.verification = healed_verification
                context.healing_attempts = attempts
                healing_trace = self.simulator.build_healing_trace(context.intent, original_policy, original_verification, healed_policy, healed_verification, attempts)
                auto_healing = True

        tasks = self._tasks(healing or auto_healing, context.verification, context.healing_attempts)
        messages = self._messages(text, context, graph_backend, healing or auto_healing)
        verification = context.verification
        return OrchestrationResult(
            intent=context.intent,
            tasks=tasks,
            messages=messages,
            nodes=nodes,
            links=links,
            telemetry=telemetry,
            policy=context.policy,
            verification=verification,
            status=verification.status,
            healed=(healing or auto_healing) and verification.passed,
            healing_trace=healing_trace,
        )

    def _fallback_result(self, text: str, healing: bool, exc: Exception) -> OrchestrationResult:
        result = self.fallback._run(text=text, healing=healing)
        note = result.intent.parse_note
        result.intent.parse_note = f"{note} ReAct 智能体不可用，已保留演示降级。原因：{exc}"
        return result

    def _tasks(self, healing: bool, verification: Any | None = None, healing_attempts: int = 0) -> list[TaskStep]:
        tasks = self.planner_agent.build_tasks()
        if healing:
            passed = bool(verification and verification.passed)
            detail = "根据异常遥测避开退化链路并重规划"
            if verification is not None and not passed:
                detail = f"已重试 {healing_attempts} 次，仍无可行路径"
            tasks.append(TaskStep(id="T6", agent="Healing Agent", action="replan", status="done" if passed else "blocked", detail=detail))
        return tasks

    def _messages(self, text: str, context: NetworkToolContext, graph_backend: str, healing: bool) -> list[A2AMessage]:
        bus = A2ABus()
        bus.send("GUI", "LangGraph ReAct Agent", "request", {"text": text, "healing": healing})
        if context.intent is not None:
            bus.send("LangGraph ReAct Agent", "Intent Tool", "call", {"tool": "parse_business_intent"})
            bus.send("Intent Tool", "LangGraph ReAct Agent", "observation", {"intent": context.intent.model_dump(mode="json"), "graph_backend": graph_backend})
        bus.send("LangGraph ReAct Agent", "Topology Tool", "call", {"tool": "query_network_topology"})
        bus.send("LangGraph ReAct Agent", "Telemetry Tool", "call", {"tool": "collect_telemetry_snapshot"})
        if context.path_plan is not None:
            bus.send("Path Tool", "Policy Tool", "inform", context.path_plan)
        if context.policy is not None:
            bus.send("Policy Tool", "Verification Tool", "request", {"policy_id": context.policy.policy_id, "path": context.policy.path})
        if healing:
            bus.send("Telemetry Tool", "Healing Tool", "alert", {"reason": context.healing_reason or "SLA violation or degraded link detected"})
            bus.send("Healing Tool", "Verification Tool", "inform", {"attempts": context.healing_attempts, "passed": bool(context.verification and context.verification.passed)})
        if context.verification is not None:
            bus.send("Verification Tool", "GUI", "inform", context.verification.model_dump(mode="json"))
        return bus.messages
