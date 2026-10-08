#!/usr/bin/env python3
"""Bring a company file or database to the current migration head, including
one that a server half-upgraded (issue #132).

    python3 scripts/repair-schema.py --database-url sqlite:////path/to/company.db
    python3 scripts/repair-schema.py --database-url "$DATABASE_URL" --dry-run

`alembic upgrade head` is the right tool for an ordinary old file and cannot
recover a half-upgraded one: a server started against a database behind head
runs `create_all()`, which creates the tables a pending revision would add
without altering the ones it would change and without moving the revision
stamp. The upgrade then fails on `table <x> already exists`.

This runs the upgrade and, when a table blocks it, drops that table **only if
it is empty** before trying again. `create_all()` only ever creates, so
anything it left behind carries no rows; a table with data was made by
something else and this refuses to touch it.

Take a copy first. This edits the database it is pointed at.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.schema_repair import repair  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", required=True, help="SQLAlchemy URL")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="say what would happen without changing anything",
    )
    args = ap.parse_args()

    result = repair(args.database_url, dry_run=args.dry_run)
    print(f"revision before : {result.started_at}")
    print(f"revision now    : {result.now_at}")
    if result.dropped:
        print(f"dropped (empty) : {', '.join(result.dropped)}")
    print(f"result          : {'OK' if result.ok else 'FAILED'} — {result.message}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
