"""
Bidirectional mosaic proxy.

Ingress (tool response → LLM context):  mosaic_value()   — replace sensitive data with tokens
Egress  (LLM output  → tool execution): demosaic_value() — restore real values before API calls

This round-trip coherence is the core capability absent from one-way redaction tools.
"""
import json
import re
from typing import Any

from mcp_mosaic.detectors import DETECTORS
from mcp_mosaic.vault import TokenVault


class MosaicProxy:
    """
    Wraps any dict/list/str payload flowing between MCP tools and an LLM.

    Usage:
        proxy = MosaicProxy(vault)

        # Before tool response enters LLM context:
        safe_payload = proxy.mosaic_value(raw_tool_response)

        # Before LLM-generated params reach a real API call:
        real_params = proxy.demosaic_value(llm_tool_call_params)
    """

    def __init__(self, vault: TokenVault):
        self._vault = vault

    _SENSITIVE_FIELD = re.compile(
        r"^(?:password|passwd|secret|token|api[-_]?key|auth|psk|passphrase|"
        r"private[-_]?key|client[-_]?secret)$",
        re.IGNORECASE,
    )

    # ------------------------------------------------------------------ ingress

    def mosaic_value(self, value: Any) -> Any:
        """Recursively replace sensitive data with LLM-semantic tokens."""
        if isinstance(value, str):
            return self._mosaic_text(value)
        if isinstance(value, dict):
            return {
                key: self._mosaic_sensitive_field(item)
                if isinstance(key, str) and self._SENSITIVE_FIELD.fullmatch(key)
                else self.mosaic_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.mosaic_value(item) for item in value]
        return value

    def _mosaic_sensitive_field(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._vault.tokenize(value, "CRED")
        return self.mosaic_value(value)

    def _mosaic_text(self, text: str) -> str:
        for det in DETECTORS:
            if det.group == 0:
                text = det.pattern.sub(
                    lambda m, lbl=det.label: self._vault.tokenize(m.group(0), lbl),
                    text,
                )
            else:
                # Replace only the nth capture group; keep surrounding text intact.
                text = det.pattern.sub(
                    lambda m, lbl=det.label, g=det.group: m.group(0).replace(
                        m.group(g), self._vault.tokenize(m.group(g), lbl)
                    ),
                    text,
                )
        return text

    # ----------------------------------------------------------------- egress

    def demosaic_value(self, value: Any) -> Any:
        """Recursively restore real values from tokens in LLM-generated output."""
        if isinstance(value, str):
            return self._vault.detokenize_text(value)
        if isinstance(value, dict):
            return {k: self.demosaic_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.demosaic_value(item) for item in value]
        return value

    # ---------------------------------------------------------- LLM guidance

    SYSTEM_ADDENDUM = (
        "SECURITY CONTEXT: Some values in tool responses are replaced with "
        "opaque reference tokens of the form [TYPE:xxxx] (e.g. [IP:a3f2], "
        "[UID:7b1c]). Treat each token as an exact opaque identifier. "
        "Pass tokens back verbatim when supplying parameters to tool calls — "
        "do not alter, guess, or expand them. "
        "You may reason about type (IP, MAC, UID, HOST) without knowing the "
        "actual value."
    )

    @staticmethod
    def augment_system_prompt(original: str) -> str:
        """Append the token guidance block to an existing system prompt."""
        return f"{original}\n\n{MosaicProxy.SYSTEM_ADDENDUM}"
