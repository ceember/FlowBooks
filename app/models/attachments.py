# ============================================================================
# Attachments — file uploads linked to any entity (invoices, bills, etc.)
# Phase 10: Quick Wins + Medium Effort Features
# Tier 3: doubles as the per-employee HR document vault via employee_id.
# ============================================================================

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.database import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    filename = Column(String(255), nullable=False)
    # "stored_files/<id>": the file is that row of this company's database.
    # Before 2.18.0 it was a path under the uploads folder every company
    # shared; the upgrade copied each one in (stored_files.legacy_path).
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    stored_file_id = Column(
        Integer,
        ForeignKey("stored_files.id", name="fk_attachments_stored_file_id"),
        nullable=True,
        index=True,
    )
    # Joined, and the bytes are deferred on StoredFile: a list shows each
    # file's flags without an extra query per row and without its content.
    stored_file = relationship("StoredFile", lazy="joined")

    # Per-employee HR document vault (Tier 3). When set, the attachment is an
    # employee document; doc_category classifies it (w4, i9, offer_letter...).
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    doc_category = Column(String(50), nullable=True)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def from_shared_folder(self) -> bool:
        """Copied in by the upgrade from the folder earlier versions shared
        between companies: it may be another company's file."""
        return bool(
            self.stored_file is not None and self.stored_file.from_shared_folder
        )

    @property
    def missing(self) -> bool:
        """There are no bytes to give back: the shared-folder file this row
        pointed at was not there when the books were upgraded."""
        return self.stored_file is None or bool(self.stored_file.missing)
