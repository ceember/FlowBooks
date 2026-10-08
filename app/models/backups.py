# ============================================================================
# Backups — database backup and restore metadata
# Feature 11: Backup/Restore from UI
# ============================================================================

from sqlalchemy import Column, Integer, String, DateTime, Text, func

from app.database import Base


class Backup(Base):
    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)
    backup_type = Column(String(20), default="manual")  # manual, auto
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
