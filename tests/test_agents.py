from app.agents import AgentRegistry, Orchestrator
from app.simulator import NetworkSimulator


DEMO_INTENT = "请保障北京园区到上海云服务的视频会议业务，要求时延低于50ms，丢包率低于1%，优先避开拥塞链路。"


def test_submit_intent_generates_policy_and_passes_sla():
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())

    result = orchestrator.submit_intent(DEMO_INTENT)

    assert result.intent.service == "视频会议"
    assert result.intent.max_latency_ms == 50
    assert result.policy.selected_links
    assert result.verification.passed
    assert result.status == "achieved"


def test_healing_avoids_degraded_primary_link():
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())
    orchestrator.submit_intent(DEMO_INTENT)
    simulator.apply_simulation("congest", "lnk-tianjin-jinan")

    result = orchestrator.heal()

    assert result.healed
    assert "lnk-tianjin-jinan" not in result.policy.selected_links
    assert result.verification.passed


def test_failure_is_reported_when_no_path_can_satisfy_sla():
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())
    simulator.apply_simulation("fail", "lnk-tianjin-jinan")
    simulator.apply_simulation("fail", "lnk-tianjin-guangzhou")

    result = orchestrator.submit_intent(DEMO_INTENT)

    assert not result.verification.passed
    assert result.status == "partial"
