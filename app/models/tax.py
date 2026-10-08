# ============================================================================
# Tax Category Mappings — map accounts to IRS Schedule C lines
# Feature 19: Tax Report Export — Schedule C
# ============================================================================

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class TaxCategoryMapping(Base):
    __tablename__ = "tax_category_mappings"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True)
    tax_line = Column(String(100), nullable=False)  # e.g. "Schedule C, Line 1"

    account = relationship("Account", backref="tax_mapping")
