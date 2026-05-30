import json
from pathlib import Path

from app.agents import AgentRegistry, Orchestrator
from app.models import BusinessIntent
from app.settings import LLMSettingsUpdate, llm_settings_status, save_llm_settings, settings_path
from app.simulator import NetworkSimulator
from app.tools import NetworkToolKit
from app.utils import load_active_result, persist_runtime_state, recent_intents
from app.llm import load_deepseek_runtime_settings, normalize_deepseek_base_url


DEMO_INTENT = "请保障北京园区到上海云服务的视频会议业务，要求时延低于50ms，丢包率低于1%，优先避开拥塞链路。"


def test_submit_intent_generates_policy_and_passes_sla(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())

    result = orchestrator.submit_intent(DEMO_INTENT)

    assert result.intent.service == "视频会议"
    assert result.intent.max_latency_ms == 50
    assert result.intent.parse_source == "rule_fallback"
    assert result.policy.selected_links
    assert "lnk-tianjin-jinan" in result.policy.selected_links
    assert "lnk-tianjin-nanjing" not in result.policy.selected_links
    assert result.verification.passed
    assert result.status == "achieved"


def test_healing_avoids_degraded_primary_link(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())
    orchestrator.submit_intent(DEMO_INTENT)
    simulator.apply_simulation("congest", "lnk-tianjin-jinan")

    result = orchestrator.heal()

    assert result.healed
    assert "lnk-tianjin-jinan" not in result.policy.selected_links
    assert result.verification.passed
    assert "lnk-tianjin-nanjing" in result.policy.selected_links


def test_failure_is_reported_when_no_path_can_satisfy_sla(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())
    simulator.apply_simulation("fail", "lnk-tianjin-jinan")
    simulator.apply_simulation("fail", "lnk-tianjin-guangzhou")
    simulator.apply_simulation("fail", "lnk-tianjin-nanjing")

    result = orchestrator.submit_intent(DEMO_INTENT)

    assert not result.verification.passed
    assert result.status == "failed"
    assert any("No feasible candidate path" in issue for issue in result.verification.issues)


def test_healing_reports_failed_after_max_retries(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())
    orchestrator.submit_intent(DEMO_INTENT)
    simulator.apply_simulation("fail", "lnk-tianjin-jinan")
    simulator.apply_simulation("fail", "lnk-tianjin-guangzhou")
    simulator.apply_simulation("fail", "lnk-tianjin-nanjing")

    result = orchestrator.heal()

    assert not result.healed
    assert result.status == "failed"
    assert result.tasks[-1].status == "blocked"
    assert any("retried 3 times" in issue for issue in result.verification.issues)


def test_deepseek_parser_is_used_when_configured(monkeypatch, tmp_path):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            content = {
                "service": "核心交易",
                "source": "北京园区",
                "destination": "上海云服务",
                "max_latency_ms": 30,
                "max_loss_percent": 0.2,
                "min_bandwidth_mbps": 500,
                "priority": "critical",
                "constraints": ["low_latency", "security_first"],
                "confidence": 0.93,
                "parse_note": "识别为核心交易专线保障。",
            }
            return json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode("utf-8")

    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setattr("app.settings.urllib.request.urlopen", lambda request, timeout: FakeResponse())
    save_llm_settings(LLMSettingsUpdate(api_key="test-key"))
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())

    result = orchestrator.submit_intent("北京到上海的核心交易专线要低时延、强隔离，30ms 内，丢包不超过0.2%，带宽500M。")

    assert result.intent.parse_source == "deepseek"
    assert result.intent.service == "核心交易"
    assert result.intent.max_latency_ms == 30
    assert result.intent.min_bandwidth_mbps == 500
    assert result.intent.confidence == 0.93


def test_settings_status_does_not_expose_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))

    status = save_llm_settings(LLMSettingsUpdate(api_key="secret-key"))

    assert status.configured
    assert not hasattr(status, "api_key")
    assert "secret-key" in settings_path().read_text(encoding="utf-8")
    assert llm_settings_status().configured


def test_deepseek_env_key_has_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    save_llm_settings(LLMSettingsUpdate(api_key="settings-key", base_url="https://api.deepseek.com/chat/completions"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    settings = load_deepseek_runtime_settings()

    assert settings.api_key == "env-key"
    assert settings.base_url == "https://api.deepseek.com"
    assert normalize_deepseek_base_url("https://api.deepseek.com/chat/completions") == "https://api.deepseek.com"


def test_default_settings_path_uses_user_config_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("C4_SETTINGS_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    project_dist_settings = Path.cwd() / "dist" / "settings.local.json"
    before = project_dist_settings.read_text(encoding="utf-8") if project_dist_settings.exists() else None

    status = save_llm_settings(LLMSettingsUpdate(api_key="default-path-key"))

    assert status.configured
    assert settings_path() == tmp_path / "appdata" / "C4NetAutonomy" / "settings.local.json"
    assert settings_path().exists()
    after = project_dist_settings.read_text(encoding="utf-8") if project_dist_settings.exists() else None
    assert after == before


def test_policy_reports_insufficient_bandwidth(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    simulator = NetworkSimulator()
    intent = BusinessIntent(
        source="beijing-campus",
        destination="shanghai-cloud",
        service="video",
        max_latency_ms=80,
        max_loss_percent=2.0,
        min_bandwidth_mbps=1200,
        priority="high",
        raw_text="need 1200Mbps",
    )

    policy = simulator.generate_policy(intent)
    verification = simulator.verify(intent, policy)

    assert not verification.passed
    assert verification.status == "failed"
    assert any("Insufficient path bandwidth" in issue for issue in verification.issues)


def test_langchain_tools_return_valid_json(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    simulator = NetworkSimulator()
    tools = {item.name: item for item in NetworkToolKit(simulator).create_tools()}

    intent = tools["parse_business_intent"].invoke({"text": DEMO_INTENT})
    topology = tools["query_network_topology"].invoke({})
    telemetry = tools["collect_telemetry_snapshot"].invoke({})
    path = tools["plan_candidate_path"].invoke({"intent": intent})
    policy = tools["generate_network_policy"].invoke({"intent": intent})
    verification = tools["verify_sla_compliance"].invoke({"intent": intent, "policy": policy})

    assert BusinessIntent.model_validate(intent).service == "视频会议"
    assert topology["nodes"] and topology["links"]
    assert telemetry
    assert path["selected_links"]
    assert policy["selected_links"]
    assert verification["status"] in {"achieved", "partial", "failed"}


def test_simulator_state_is_restored_after_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    simulator = NetworkSimulator()
    simulator.apply_simulation("congest", "lnk-tianjin-jinan")

    restarted = NetworkSimulator()

    assert restarted.links["lnk-tianjin-jinan"].health == "congested"
    assert restarted.links["lnk-tianjin-jinan"].utilization_percent == 94


def test_recent_intents_keep_latest_ten(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    simulator = NetworkSimulator()
    orchestrator = Orchestrator(simulator=simulator, registry=AgentRegistry())

    for index in range(12):
        result = orchestrator.submit_intent(f"北京园区到上海云服务的视频会议业务 {index}，时延低于50ms，丢包率低于1%。")
        persist_runtime_state(simulator, result)

    history = recent_intents()
    assert len(history) == 10
    assert history[0]["raw_text"].startswith("北京园区到上海云服务的视频会议业务 11")
    assert load_active_result() is not None
