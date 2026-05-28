from fastapi.testclient import TestClient

from app.main import STATIC_DIR, app


DEMO_INTENT = "北京园区到上海云服务的视频会议业务，需要低时延路径，50ms 内，丢包小于1%，带宽至少100M，优先避开拥塞链路。"


def test_llm_settings_api_does_not_return_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    client = TestClient(app)

    save_response = client.post(
        "/api/settings/llm",
        json={
            "api_key": "secret-key",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/chat/completions",
            "timeout": 12,
        },
    )
    assert save_response.status_code == 200
    assert save_response.json()["configured"] is True
    assert "api_key" not in save_response.json()

    get_response = client.get("/api/settings/llm")
    assert get_response.status_code == 200
    assert get_response.json()["configured"] is True
    assert "secret-key" not in get_response.text


def test_static_home_removes_demo_flow_language():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert "演示流程" not in html
    assert "推荐演示输入" not in html
    assert "输入参考" in html


def test_intents_api_returns_orchestration_result(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = TestClient(app)

    response = client.post("/api/intents", json={"text": DEMO_INTENT})

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent_id"].startswith("INT-")
    assert payload["intent"]["raw_text"] == DEMO_INTENT
    assert payload["policy"]["selected_links"]
    assert "verification" in payload
    assert "messages" in payload


def test_agent_intents_api_returns_orchestration_result(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = TestClient(app)

    response = client.post("/api/agent/intents", json={"text": DEMO_INTENT})

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent_id"].startswith("INT-")
    assert payload["intent"]["raw_text"] == DEMO_INTENT
    assert payload["policy"]["selected_links"]
    assert "verification" in payload


def test_heal_api_returns_orchestration_result(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = TestClient(app)
    client.post("/api/intents", json={"text": DEMO_INTENT})
    client.post("/api/simulate", json={"action": "congest", "link_id": "lnk-tianjin-jinan"})

    response = client.post("/api/heal")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent_id"].startswith("INT-")
    assert payload["healed"] is True
    assert "lnk-tianjin-jinan" not in payload["policy"]["selected_links"]
    assert "verification" in payload


def test_simulate_unknown_link_returns_404(monkeypatch, tmp_path):
    monkeypatch.setenv("C4_SETTINGS_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post("/api/simulate", json={"action": "congest", "link_id": "missing-link"})

    assert response.status_code == 404
