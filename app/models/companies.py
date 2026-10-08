# ============================================================================
# Multi-Company — support multiple company databases
# Feature 16: Master DB stores company list, switching = changing connection
# ============================================================================

from sqlalchemy import Column, Integer, String, DateTime, Boolean, func

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    database_name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    last_accessed = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
