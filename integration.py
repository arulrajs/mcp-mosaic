"""
Drop-in wrappers for the existing Mist orchestrator stack.

MosaicMistClient  — wraps MistAPIClient: mosaics API responses before they
                    reach the LLM, de-mosaics parameters before API calls.

MosaicAgentMixin  — mixin for BaseDeviceAgent subclasses: intercepts
                    generate_config_from_intent so the LLM prompt never
                    contains real network values.

Existing code requires zero changes; swap in these wrappers at init time.
"""
from typing import Any, Dict, Optional

from mcp_mosaic.session import MosaicSession


class MosaicMistClient:
    """
    Wraps api.mist_client.MistAPIClient with bidirectional mosaicing.

    Mosaic boundary:
      real API response  →  [mosaic]  →  LLM context
      LLM tool params    →  [demosaic]  →  real API call
    """

    def __init__(self, real_client, session: MosaicSession):
        self._client = real_client
        self._session = session

    def __getattr__(self, name: str):
        """Proxy all attributes to the real client."""
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def _wrapped(*args, **kwargs):
            # De-mosaic any token references in outbound params
            clean_args = [self._session.proxy.demosaic_value(a) for a in args]
            clean_kwargs = {k: self._session.proxy.demosaic_value(v) for k, v in kwargs.items()}

            result = attr(*clean_args, **clean_kwargs)

            # Mosaic the API response before it enters LLM context
            return self._session.proxy.mosaic_value(result)

        return _wrapped


class MosaicAgentMixin:
    """
    Mixin for BaseDeviceAgent subclasses.

    Overrides generate_config_from_intent to:
      1. Mosaic the RAG template and parameters before building the LLM prompt.
      2. De-mosaic the LLM's JSON response before returning to the caller.

    Requires self._mosaic_session: MosaicSession to be set after super().__init__().
    """

    _mosaic_session: Optional[MosaicSession] = None

    def generate_config_from_intent(
        self, intent: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self._mosaic_session is None:
            # Fall back to base implementation if session not injected
            return super().generate_config_from_intent(intent, parameters)  # type: ignore[misc]

        proxy = self._mosaic_session.proxy

        # Mosaic parameters heading into the LLM prompt
        safe_parameters = proxy.mosaic_value(parameters)

        result = super().generate_config_from_intent(intent, safe_parameters)  # type: ignore[misc]

        # De-mosaic LLM output before it's used for real API calls
        return proxy.demosaic_value(result)
