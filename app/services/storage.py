# ============================================================================
# Storage roots — where files live on disk.
#
# Backups: server installs keep the historical location (<repo>/backups) so
# existing deployments and volume mounts are untouched. Desktop installs set
# SLOWBOOKS_DATA_DIR (launcher-managed, per-user, e.g.
# %LOCALAPPDATA%\SlowBooksPro\data) because the install dir (Program Files)
# is read-only at runtime — everything writable is redirected under the data
# dir.
#
# Uploads: since 2.18.0 a company's files (logo, attachments, employee
# documents, scanned receipts) are kept in its own database —
# app/services/file_store.py. files_root()/uploads_root() name the folder
# earlier releases wrote EVERY company's uploads to (app/static/uploads on
# a server, <data dir>/uploads on a desktop). Nothing writes there any more
# and it is not served; the upgrade migration (c5e1f7a9b3d2) reads it, once
# per company, to copy in the files that company's rows point at.
# ============================================================================

import os
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent  # app/


def files_root() -> Path:
    """Where releases before 2.18.0 kept every company's uploads (the
    stored attachment paths were relative to this)."""
    override = os.environ.get("SLOWBOOKS_DATA_DIR")
    if override:
        return Path(override)
    return _APP_DIR / "static"


def uploads_root() -> Path:
    return files_root() / "uploads"


def backups_root() -> Path:
    """Root for database backup files."""
    override = os.environ.get("SLOWBOOKS_DATA_DIR")
    if override:
        return Path(override) / "backups"
    return _APP_DIR.parent / "backups"
