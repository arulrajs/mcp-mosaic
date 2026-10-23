import json

from mcp_mosaic import demo_app
from mcp_mosaic.session import MosaicSession


def test_nested_credential_fields_are_mosaiced_and_restored():
    session = MosaicSession("credential-test")
    raw = {"psk": "demo-psk-value", "auth": {"client_secret": "demo-secret-value"}}

    safe = session.proxy.mosaic_value(raw)

    assert "demo-psk-value" not in repr(safe)
    assert "demo-secret-value" not in repr(safe)
    assert session.proxy.demosaic_value(safe) == raw


def test_demo_sends_only_tokens_and_restores_a_dry_run(monkeypatch):
    captured = {}
    monkeypatch.setattr(demo_app, "available_models", lambda: ["mistral:latest"])

    def fake_query_ollama(model, messages):
        assert model == "mistral:latest"
        captured["context"] = json.dumps(messages)
        user_data = json.loads(messages[1]["content"])
        safe = user_data["api_response"]
        return json.dumps(
            {
                "analysis": "Use the gateway token reported by the AP.",
                "tool_call": {
                    "operation": "mist.update_ap",
                    "device_id": safe["device_id"],
                    "site_id": safe["site_id"],
                    "management_gateway": safe["management_gateway"],
                },
            }
        )

    monkeypatch.setattr(demo_app, "query_ollama", fake_query_ollama)
    client = demo_app.create_app().test_client()

    response = client.post("/api/run", json={"model": "mistral:latest"})

    assert response.status_code == 200
    result = response.get_json()
    assert result["dry_run"] is True
    assert result["privacy"]["leaked_fields"] == 0
    assert result["restored_action"]["device_id"] == demo_app.DEMO_DATA["device_id"]
    assert result["restored_action"]["management_gateway"] == demo_app.DEMO_DATA["management_gateway"]
    assert all(value not in captured["context"] for value in demo_app.SENSITIVE_SAMPLE_VALUES.values())