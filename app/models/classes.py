# ============================================================================
# Classes — QuickBooks-style tracking dimension (department / location /
# line of business). In QuickBooks a class was a flat list entry that
# tagged transactions for the "Profit & Loss by Class" report and nothing
# else.
# Same here: one nullable dimension on posted transactions and their
# source documents, aggregated by the by-class reports.
#
# One row is the system default ("Uncategorized", is_system_default=True):
# it can't be renamed, archived, or deleted, so by-class reports always
# have a bucket for untagged activity. Archived classes stay on historical
# rows but disappear from entry-form dropdowns.
# ============================================================================

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.database import Base

# Nonprofit mode: a class is a fund. Restriction follows ASU 2016-14 —
# temporarily and permanently restricted both report as "with donor
# restrictions"; the three-way label is kept because treasurers still
# think in it. Function is the Form 990 Part IX column an expense in this
# fund defaults to.
RESTRICTIONS = ("unrestricted", "temporarily_restricted", "permanently_restricted")
FUNCTIONS = ("program", "management", "fundraising")


def is_restricted(restriction: str | None) -> bool:
    return restriction in ("temporarily_restricted", "permanently_restricted")


class TxnClass(Base):
    __tablename__ = "classes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    is_system_default = Column(Boolean, default=False, nullable=False)
    # Fund accounting (nonprofit mode); harmless defaults for a business.
    restriction = Column(String(30), nullable=False, default="unrestricted")
    default_function = Column(String(20), nullable=True)
    donor_name = Column(String(200), nullable=True)
    purpose = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
