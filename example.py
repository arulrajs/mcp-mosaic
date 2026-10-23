"""
Usage example: wiring MosaicProxy into the existing MistOrchestrator.

Before (data leaks to LLM):
    client = MistAPIClient()
    response = client.get_device(device_id)
    # response contains real IPs, MACs, org UUIDs → sent verbatim to Ollama/external LLM

After (round-trip mosaiced):
    session = manager.get_or_create(session_id="user-abc-123")
    client = MosaicMistClient(MistAPIClient(), session)
    response = client.get_device(device_id)
    # response contains [IP:a3f2], [MAC:7b1c], [UID:d9e3] → LLM sees only tokens
    # when LLM emits tool call params with those tokens, demosaic restores real values
"""
import json

from mcp_mosaic import MosaicMistClient, MosaicSessionManager, MosaicProxy

manager = MosaicSessionManager(ttl_minutes=60)


def demo_round_trip():
    session = manager.get_or_create("demo-session-001")
    proxy = session.proxy

    # Simulate a Mist API response with sensitive network data
    raw_api_response = {
        "id": "a1b2c3d4-0000-0000-0000-aabbccddeeff",
        "name": "ap-lobby-01",
        "ip": "10.10.5.42",
        "mac": "a4:e3:1e:01:23:45",
        "org_id": "deadbeef-dead-beef-dead-beefdeadbeef",
        "site_id": "cafecafe-cafe-cafe-cafe-cafecafecafe",
        "config": {
            "ssid": "corp-wifi",
            "psk": "s3cr3tP@ssw0rd",
        },
        "upstream": "10.10.5.1",
    }

    # ── INGRESS: mosaic before entering LLM context ──────────────────────────
    safe = proxy.mosaic_value(raw_api_response)
    print("Safe payload sent to LLM:")
    print(json.dumps(safe, indent=2))

    # ── LLM reasons with mosaiced tokens (simulated LLM output) ─────────────
    llm_tool_call = {
        "action": "configure_device",
        "device_id": safe["id"],           # LLM passes token back verbatim
        "site_id": safe["site_id"],
        "upstream_ip": safe["upstream"],
    }
    print("\nLLM tool call (with tokens):")
    print(json.dumps(llm_tool_call, indent=2))

    # ── EGRESS: de-mosaic before real API execution ──────────────────────────
    real_params = proxy.demosaic_value(llm_tool_call)
    print("\nResolved params sent to Mist API:")
    print(json.dumps(real_params, indent=2))

    # ── Verify round-trip fidelity ───────────────────────────────────────────
    assert real_params["device_id"] == raw_api_response["id"]
    assert real_params["site_id"] == raw_api_response["site_id"]
    assert real_params["upstream_ip"] == raw_api_response["upstream"]
    print("\nRound-trip OK — no real values leaked to LLM context.")

    # ── Vault stats ──────────────────────────────────────────────────────────
    print("\nVault stats:", session.vault.stats())

    # ── System prompt augmentation ───────────────────────────────────────────
    base_prompt = "You are a network automation assistant for Mist Cloud."
    augmented = MosaicProxy.augment_system_prompt(base_prompt)
    print("\nAugmented system prompt:\n", augmented)


if __name__ == "__main__":
    demo_round_trip()
