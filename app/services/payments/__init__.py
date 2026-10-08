# ============================================================================
# Payment providers package — registry of online-payment integrations.
# ----------------------------------------------------------------------------
# get_provider() resolves a provider name ("stripe", ...) to its stateless
# singleton; unknown names raise KeyError (routes turn that into a 400).
# enabled_providers() reads the settings table once and returns the
# providers that are both enabled and configured — the public pay page
# renders one button per entry.
#
# Same registry shape as app/services/state_tax.
# ============================================================================

from sqlalchemy.orm import Session

from app.models.settings import Settings
from app.services.payments.base import CheckoutSession, PaymentProvider, PaymentResult
from app.services.payments.paypal import PayPalProvider
from app.services.payments.square import SquareProvider
from app.services.payments.stripe import StripeProvider

__all__ = [
    "CheckoutSession",
    "PaymentProvider",
    "PaymentResult",
    "StripeProvider",
    "PayPalProvider",
    "SquareProvider",
    "get_provider",
    "provider_settings",
    "enabled_providers",
]

_REGISTRY: dict[str, PaymentProvider] = {
    "stripe": StripeProvider(),
    "paypal": PayPalProvider(),
    "square": SquareProvider(),
}


def get_provider(name: str) -> PaymentProvider:
    """Resolve a provider by name. Raises KeyError for unknown names."""
    return _REGISTRY[name]


def all_providers() -> list[PaymentProvider]:
    return list(_REGISTRY.values())


def provider_settings(db: Session, provider: PaymentProvider) -> dict:
    """Load this provider's settings rows as a plain dict ('' when unset)."""
    keys = list(provider.settings_keys)
    from app.services.settings_service import _maybe_decrypt

    rows = db.query(Settings).filter(Settings.key.in_(keys)).all()
    result = {k: "" for k in keys}
    for r in rows:
        result[r.key] = _maybe_decrypt(r.key, r.value)
    return result


def enabled_providers(db: Session) -> list[PaymentProvider]:
    """Providers that are both enabled and configured, registry order."""
    result = []
    for provider in _REGISTRY.values():
        settings = provider_settings(db, provider)
        if provider.is_enabled(settings) and provider.is_configured(settings):
            result.append(provider)
    return result
