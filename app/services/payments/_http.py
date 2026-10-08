# ============================================================================
# Shared HTTP plumbing for payment providers that speak plain REST
# (PayPal, Square). No provider SDKs — request builders are pure
# functions returning httpx-ready dicts so unit tests can assert the
# exact URL/headers/body without mocking the network (same pattern as
# app/services/ai_service.build_request).
# ============================================================================

import httpx

DEFAULT_TIMEOUT = 20.0


def hardened_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.Client:
    """httpx.Client with explicit security defaults (mirrors ai_service):

    * ``verify=True``            — TLS cert validation on; no downgrade
    * ``follow_redirects=False`` — a compromised upstream can't 302 us
      into a different host/scheme
    * explicit timeout           — no hang forever on a dead provider
    * minimal User-Agent         — don't leak version strings
    """
    return httpx.Client(
        verify=True,
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": "slowbooks-payments"},
        trust_env=False,
    )


def send(request: dict, timeout: float = DEFAULT_TIMEOUT) -> httpx.Response:
    """Execute a request dict produced by a provider's build_* function."""
    with hardened_client(timeout) as client:
        return client.request(
            request["method"],
            request["url"],
            headers=request.get("headers"),
            json=request.get("json"),
            data=request.get("data"),
            auth=request.get("auth"),
        )
