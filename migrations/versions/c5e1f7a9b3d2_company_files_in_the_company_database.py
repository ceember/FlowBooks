"""company files in the company's own database

Every company on a desktop install wrote its uploads into one shared
folder: the logo as uploads/company_logo.<ext>, attachments as
uploads/attachments/<type>/<record id>/<name>, employee documents as
uploads/attachments/employee/<employee id>/<name>. The paths said nothing
about the company, so company B's logo became company A's, B's invoice 1
"receipt.pdf" replaced A's, B's employee #1 W-4 opened from A's employee #1,
and an updated W-4.pdf replaced the original even within one company
(2.18.0 gate: skytech, and macbase1 NEW-14 for the logo). Backups were the
database alone, so a restored company had none of its files.

From here each company keeps its files in its own database: stored_files,
one row per upload, and attachments.stored_file_id pointing at it (the logo
is the stored file its company_logo_path setting names, as
/api/uploads/logo/<id>).

The upgrade copies each file the company's rows point at from the shared
folder into its database, once, here. Why a migration step and not a task
on first open: alembic's revision stamp is already the per-company "done"
marker; it runs when a company is opened on this version (the desktop
launcher migrates before serving, Docker's entrypoint before uvicorn starts,
a restored older backup is migrated on restore), in one process before any
request can race it, on SQLite and PostgreSQL alike. It only READS the
shared folder: nothing there says which company wrote a file, another
company may point at the same one, and every company copies its own.

- The shared folder is SLOWBOOKS_DATA_DIR (the launcher, a restore and the
  server set it), else the data folder a desktop company file lives in
  (<data dir>/companies/<file>.db: the repair tool migrates with only a
  database URL), else app/static (a server install).
- Paths written on Windows ("uploads\\attachments\\...") are read with
  either separator.
- A path in the database is never trusted to leave the uploads folder.
- A file that is not there is recorded as missing (a row with no bytes),
  not an error: the attachment stays listed and says so.
- Every copy is flagged from_shared_folder: it may be another company's
  file (the last one written to that path), and the app says so beside it.
- Only rows with no stored file yet are copied, so a second run copies
  nothing twice.

Downgrade puts the old paths back for what came from the shared folder and
drops the table. Files uploaded after this upgrade exist only in the
database and do not survive a downgrade.

Revision ID: c5e1f7a9b3d2
Revises: d3d40d716684
Create Date: 2026-09-27

"""

import hashlib
import os
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5e1f7a9b3d2"
down_revision: Union[str, None] = "d3d40d716684"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The logo's type came from its extension, which the upload route derived
# from the verified content type.
_LOGO_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}
_LOGO_URL_PREFIX = "/api/uploads/logo/"

_attachments = sa.table(
    "attachments",
    sa.column("id", sa.Integer),
    sa.column("entity_type", sa.String),
    sa.column("employee_id", sa.Integer),
    sa.column("filename", sa.String),
    sa.column("file_path", sa.String),
    sa.column("mime_type", sa.String),
    sa.column("stored_file_id", sa.Integer),
)
_settings = sa.table(
    "settings", sa.column("key", sa.String), sa.column("value", sa.Text)
)


def _shared_folder(bind) -> Path:
    """Where releases before this one kept every company's uploads, which
    stored paths are relative to (storage.files_root() as they had it).

    SLOWBOOKS_DATA_DIR when it is set (the desktop launcher, a restore, the
    server and the tests all set it). Otherwise a desktop company file says
    where it is: <data dir>/companies/<file>.db, and the uploads were in
    <data dir>. The repair tool (--_repair-schema) migrates with nothing but
    a database URL, and must not find every file "missing". Otherwise
    app/static, a server install's folder."""
    override = os.environ.get("SLOWBOOKS_DATA_DIR")
    if override:
        return Path(override)
    database = bind.engine.url.database if bind.dialect.name == "sqlite" else None
    if database and database != ":memory:":
        company_file = Path(database).resolve()
        if company_file.parent.name == "companies":
            return company_file.parent.parent
    return Path(__file__).resolve().parents[2] / "app" / "static"


def _normalised(stored: str | None) -> str:
    """A stored relative path with forward slashes, whichever OS wrote it."""
    return "/".join(p for p in (stored or "").replace("\\", "/").split("/") if p)


def _read_shared_file(root: Path, relative: str) -> bytes | None:
    """The bytes at ``relative`` in the shared folder, or None when there is
    no such file — or it would be outside the uploads folder."""
    if not relative:
        return None
    try:
        uploads = (root / "uploads").resolve()
        candidate = root.joinpath(*relative.split("/")).resolve()
        candidate.relative_to(uploads)
        if not candidate.is_file():
            return None
        return candidate.read_bytes()
    except (OSError, ValueError, RuntimeError):
        return None


def _keep(bind, stored_files, root, kind, name, content_type, relative, read=True):
    """Copy one shared-folder file into this company's stored files: a row
    with no bytes, marked missing, when the file is not there (or ``read``
    is False: not a file this kind can be). Returns (id, missing)."""
    data = _read_shared_file(root, relative) if read else None
    result = bind.execute(
        stored_files.insert().values(
            kind=kind,
            original_name=(name or relative.rsplit("/", 1)[-1] or "file")[:255],
            content_type=content_type,
            size=len(data) if data is not None else 0,
            sha256=hashlib.sha256(data).hexdigest() if data is not None else None,
            data=data,
            legacy_path=relative[:500],
            from_shared_folder=True,
            missing=data is None,
        )
    )
    return result.inserted_primary_key[0], data is None


def copy_shared_folder_files(bind, stored_files) -> dict:
    """Bring this company's files in from the shared folder. Idempotent:
    only rows that have no stored file yet are copied. Returns counts."""
    root = _shared_folder(bind)
    copied = missing = 0
    rows = bind.execute(
        sa.select(
            _attachments.c.id,
            _attachments.c.entity_type,
            _attachments.c.employee_id,
            _attachments.c.filename,
            _attachments.c.file_path,
            _attachments.c.mime_type,
        )
        .where(_attachments.c.stored_file_id.is_(None))
        .order_by(_attachments.c.id)
    ).fetchall()
    for row in rows:
        relative = _normalised(row.file_path)
        is_document = row.employee_id is not None or row.entity_type == "employee"
        new_id, was_missing = _keep(
            bind,
            stored_files,
            root,
            "employee_document" if is_document else "attachment",
            row.filename,
            row.mime_type,
            relative,
        )
        bind.execute(
            _attachments.update()
            .where(_attachments.c.id == row.id)
            .where(_attachments.c.stored_file_id.is_(None))
            .values(stored_file_id=new_id, file_path=f"stored_files/{new_id}")
        )
        missing += was_missing
        copied += not was_missing

    logo = bind.execute(
        sa.select(_settings.c.value).where(_settings.c.key == "company_logo_path")
    ).scalar()
    relative = _normalised(logo)
    if relative.startswith("static/"):
        relative = relative[len("static/") :]
    # "/static/uploads/company_logo.png" is a shared-folder logo; "" is none,
    # and "/api/uploads/logo/<id>" is one already kept here.
    if relative.startswith("uploads/") and not (logo or "").startswith(
        _LOGO_URL_PREFIX
    ):
        ext = relative.rsplit(".", 1)[-1].lower() if "." in relative else ""
        content_type = _LOGO_TYPES.get(ext)
        # Not an image type a logo can be: recorded, never read.
        new_id, was_missing = _keep(
            bind,
            stored_files,
            root,
            "logo",
            f"company_logo.{ext}" if content_type else None,
            content_type,
            relative,
            read=content_type is not None,
        )
        missing += was_missing
        copied += not was_missing
        bind.execute(
            _settings.update()
            .where(_settings.c.key == "company_logo_path")
            .values(value=f"{_LOGO_URL_PREFIX}{new_id}")
        )
    return {"copied": copied, "missing": missing}


def upgrade() -> None:
    stored_files = op.create_table(
        "stored_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        sa.Column("token", sa.String(length=32), nullable=True),
        sa.Column("legacy_path", sa.String(length=500), nullable=True),
        sa.Column(
            "from_shared_folder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("missing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
        # ids are never reused: a logo's address is its id (PostgreSQL's
        # sequence never reuses one; SQLite needs AUTOINCREMENT for that)
        sqlite_autoincrement=True,
    )
    op.create_index("ix_stored_files_id", "stored_files", ["id"])
    op.create_index("ix_stored_files_kind", "stored_files", ["kind"])

    with op.batch_alter_table("attachments") as batch:
        batch.add_column(sa.Column("stored_file_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_attachments_stored_file_id",
            "stored_files",
            ["stored_file_id"],
            ["id"],
        )
        batch.create_index("ix_attachments_stored_file_id", ["stored_file_id"])

    copy_shared_folder_files(op.get_bind(), stored_files)


def downgrade() -> None:
    bind = op.get_bind()
    stored_files = sa.Table("stored_files", sa.MetaData(), autoload_with=bind)
    # What came from the shared folder points there again; a file uploaded
    # after the upgrade has nowhere to point and goes with the table.
    rows = bind.execute(
        sa.select(
            _attachments.c.id.label("attachment_id"),
            stored_files.c.legacy_path,
        ).select_from(
            _attachments.join(
                stored_files, stored_files.c.id == _attachments.c.stored_file_id
            )
        )
    ).fetchall()
    for row in rows:
        if row.legacy_path:
            bind.execute(
                _attachments.update()
                .where(_attachments.c.id == row.attachment_id)
                .values(file_path=row.legacy_path)
            )
    logo = bind.execute(
        sa.select(_settings.c.value).where(_settings.c.key == "company_logo_path")
    ).scalar()
    if (logo or "").startswith(_LOGO_URL_PREFIX):
        tail = logo[len(_LOGO_URL_PREFIX) :]
        legacy = None
        if tail.isdigit():
            legacy = bind.execute(
                sa.select(stored_files.c.legacy_path).where(
                    stored_files.c.id == int(tail)
                )
            ).scalar()
        bind.execute(
            _settings.update()
            .where(_settings.c.key == "company_logo_path")
            .values(value=f"/static/{legacy}" if legacy else "")
        )

    with op.batch_alter_table("attachments") as batch:
        batch.drop_index("ix_attachments_stored_file_id")
        batch.drop_constraint("fk_attachments_stored_file_id", type_="foreignkey")
        batch.drop_column("stored_file_id")
    op.drop_index("ix_stored_files_kind", table_name="stored_files")
    op.drop_index("ix_stored_files_id", table_name="stored_files")
    op.drop_table("stored_files")
