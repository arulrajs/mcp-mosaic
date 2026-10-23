"""Local-only hackathon POC for round-trip network-data mosaicing."""
import json
import secrets
import urllib.error
import urllib.request

from flask import Flask, jsonify, render_template, request, session as browser_session

from mcp_mosaic.proxy import MosaicProxy
from mcp_mosaic.session import MosaicSessionManager


OLLAMA_URL = "http://127.0.0.1:11434"
DEMO_INTENT = "Update the lobby demo AP to use the management gateway it reports."
DEMO_DATA = {
    "device_id": "f7aa56c8-060e-4f34-a6fb-0d87f2b45d10",
    "site_id": "b94b45a2-8c73-4d84-91ae-c0d5170fca12",
    "name": "ap-lobby-demo",
    "management_ip": "192.0.2.42",
    "mac": "02:00:00:00:00:42",
    "management_gateway": "192.0.2.1",
    "ssid": "HPE-HACKATHON-DEMO",
    "psk": "demo-only-psk-not-a-real-secret",
}
SENSITIVE_SAMPLE_VALUES = {
    "device_id": DEMO_DATA["device_id"],
    "site_id": DEMO_DATA["site_id"],
    "management_ip": DEMO_DATA["management_ip"],
    "mac": DEMO_DATA["mac"],
    "management_gateway": DEMO_DATA["management_gateway"],
    "psk": DEMO_DATA["psk"],
}
SYSTEM_PROMPT = """You are a network automation planner. The user message contains a synthetic API response and a task. Return one JSON object with an `analysis` string and a `tool_call` object. The tool_call must contain exactly these fields: `operation` set to `mist.update_ap`, `device_id`, `site_id`, and `management_gateway`. Copy the exact opaque token values from the API response. Do not invent or transform identifiers. Do not include prose outside the JSON object."""


def query_ollama(model: str, messages: list[dict[str, str]]) -> str:
    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["message"]["content"]


def available_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
        return [
            model["name"]
            for model in result.get("models", [])
            if "embed" not in model["name"].lower()
        ]
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    sessions = MosaicSessionManager(ttl_minutes=60)

    def get_mosaic_session():
        session_id = browser_session.get("mosaic_session_id")
        if session_id is None:
            session_id = secrets.token_urlsafe(24)
            browser_session["mosaic_session_id"] = session_id
        return sessions.get_or_create(session_id)

    def model_context(proxy):
        safe_payload = proxy.mosaic_value(DEMO_DATA)
        safe_intent = proxy.mosaic_value(DEMO_INTENT)
        user_content = json.dumps(
            {"intent": safe_intent, "api_response": safe_payload}, indent=2
        )
        messages = [
            {"role": "system", "content": MosaicProxy.augment_system_prompt(SYSTEM_PROMPT)},
            {"role": "user", "content": user_content},
        ]
        serialized = json.dumps(messages)
        leaked_fields = [
            field for field, value in SENSITIVE_SAMPLE_VALUES.items() if value in serialized
        ]
        if leaked_fields:
            raise RuntimeError("Privacy preflight failed: sensitive values remain in model context")
        return safe_payload, messages, leaked_fields

    @app.get("/")
    def index():
        return render_template("demo.html")

    @app.get("/api/status")
    def status():
        models = available_models()
        return jsonify({"connected": bool(models), "models": models})

    @app.get("/api/preview")
    def preview():
        proxy = get_mosaic_session().proxy
        safe_payload, messages, leaked_fields = model_context(proxy)
        return jsonify(
            {
                "raw_api_response": DEMO_DATA,
                "model_context": messages,
                "safe_api_response": safe_payload,
                "intent": DEMO_INTENT,
                "privacy": {
                    "leaked_fields": len(leaked_fields),
                    "tokens_created": get_mosaic_session().vault.stats()["tokens_minted"],
                },
            }
        )

    @app.post("/api/run")
    def run_demo():
        body = request.get_json(silent=True) or {}
        model = body.get("model")
        models = available_models()
        if not models:
            return jsonify({"error": "Ollama is not responding on 127.0.0.1:11434."}), 503
        if not isinstance(model, str) or model not in models:
            return jsonify({"error": "Choose an installed local Ollama model."}), 400

        mosaic_session = get_mosaic_session()
        proxy = mosaic_session.proxy
        try:
            safe_payload, messages, leaked_fields = model_context(proxy)
            model_output = query_ollama(model, messages)
            result = json.loads(model_output)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, RuntimeError) as exc:
            app.logger.warning("Local Mosaic POC request failed: %s", type(exc).__name__)
            return jsonify({"error": "The local model response could not be used. No action was executed."}), 502

        tool_call = result.get("tool_call") if isinstance(result, dict) else None
        expected = {
            "operation": "mist.update_ap",
            "device_id": safe_payload["device_id"],
            "site_id": safe_payload["site_id"],
            "management_gateway": safe_payload["management_gateway"],
        }
        if not isinstance(tool_call, dict) or tool_call != expected:
            return jsonify(
                {
                    "error": "The model did not return the exact known tokens. No action was executed.",
                    "model_context": messages,
                    "privacy": {"leaked_fields": len(leaked_fields)},
                }
            ), 422

        return jsonify(
            {
                "analysis": result.get("analysis", ""),
                "model_output": result,
                "model_context": messages,
                "restored_action": proxy.demosaic_value(tool_call),
                "privacy": {
                    "leaked_fields": len(leaked_fields),
                    "tokens_created": mosaic_session.vault.stats()["tokens_minted"],
                },
                "dry_run": True,
            }
        )

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8765, debug=False)