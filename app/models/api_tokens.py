# ============================================================================
# API tokens — non-human principals (agents, integrations, the receipt
# service). A token wears a role exactly like a user does; the RBAC
# middleware can't tell the difference, which is the point.
#
# Storage: SHA-256 of the secret (tokens are 256-bit random — deterministic
# hashing enables indexed lookup and offline brute force is meaningless).
# The full secret is shown exactly once at creation. No DELETE — tokens
# deactivate, so their label stays meaningful in the audit trail forever.
# ============================================================================

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


TOKEN_PREFIX = "sbp_"


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String(100), unique=True, nullable=False)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    # First characters of the secret ("sbp_ab12…") so the operator can
    # match a token in a config file to a row here without exposing it.
    token_hint = Column(String(12), nullable=False)
    role = Column(String(20), nullable=False)  # same values as users.role
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(100), nullable=False, default="")
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
