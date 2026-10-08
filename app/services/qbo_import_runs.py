"""Latest-only, durable QBO import log and background runner.

The private sidecar database is separate from the accounting database so
polling and progress writes stay available during long SQLite imports.
Threads in one server process share a store; Server Edition runs several
worker processes (APP_WORKERS), each with its own connection to the same
file, so a run's owner beats a heartbeat while it works and another
process calls the run interrupted only once that heartbeat has stopped.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import sqlite3
from threading import Event, RLock, Thread
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.services import qbo_progress, storage
from app.services.safe_errors import safe_message

logger = logging.getLogger(__name__)
ENTITY_ORDER = (
    "accounts",
    "customers",
    "vendors",
    "items",
    "invoices",
    "payments",
    "sales_receipts",
    "journal_entries",
    "ledger",
)
ACTIVE = {"queued", "running"}
_BOOT_ID = uuid4().hex
_stores = {}
_stores_lock = RLock()
# A working run's process writes its heartbeat this often; a run whose
# owner has not beaten for STALE_SECONDS is taken to have died with it.
HEARTBEAT_SECONDS = 5
STALE_SECONDS = 20
_clock = time.time


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ImportStore:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = RLock()
        self.connection = sqlite3.connect(path, timeout=5, check_same_thread=False)
        path.chmod(0o600)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            "CREATE TABLE IF NOT EXISTS latest (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS owners (boot_id TEXT PRIMARY KEY, heartbeat REAL NOT NULL);"
        )

    def _write_lock(self):
        """Take the file's write lock before reading what will be written:
        another worker process must not change the run in between."""
        self.connection.execute("BEGIN IMMEDIATE")

    def _beat(self):
        self.connection.execute(
            "INSERT OR REPLACE INTO owners VALUES (?, ?)", (_BOOT_ID, _clock())
        )

    def beat(self):
        """This process is still working on its run."""
        with self.lock, self.connection:
            self._beat()

    def _owner_alive(self, owner):
        if owner == _BOOT_ID:
            return True
        row = self.connection.execute(
            "SELECT heartbeat FROM owners WHERE boot_id = ?", (owner,)
        ).fetchone()
        return bool(row) and _clock() - row[0] < STALE_SECONDS

    def _abandoned(self, state):
        return bool(
            state
            and state["status"] in ACTIVE
            and not self._owner_alive(state.get("owner"))
        )

    def _read(self):
        row = self.connection.execute(
            "SELECT payload FROM latest WHERE id=1"
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _save(self, state):
        self.connection.execute(
            "INSERT OR REPLACE INTO latest VALUES (1, ?)", (json.dumps(state),)
        )

    def _append(self, state, action, message, **fields):
        now = _now()
        state["last_sequence"] += 1
        state["last_progress_at"] = now
        row = {
            "sequence": state["last_sequence"],
            "timestamp": now,
            "level": "info",
            "code": "",
            "entity": state.get("entity", ""),
            "item_id": "",
            "item_label": "",
            "action": action,
            "message": message,
            **fields,
        }
        self.connection.execute(
            "INSERT INTO events VALUES (?, ?)", (row["sequence"], json.dumps(row))
        )
        self._save(state)

    def _recover(self, state):
        if self._abandoned(state):
            state.update(
                status="interrupted",
                finished_at=_now(),
                current_step="Import interrupted",
            )
            state["counters"]["errors"] += 1
            state["counters"]["pending"] = 0
            self._append(
                state,
                "interrupt",
                "Server restarted; unfinished work was not resumed",
                level="error",
                code="IMPORT_INTERRUPTED",
            )

    def reserve(self, entities, actor):
        with self.lock, self.connection:
            self._write_lock()
            state = self._read()
            self._recover(state)
            if state and state["status"] in ACTIVE:
                raise HTTPException(
                    409,
                    {
                        "message": "A QBO import is already running",
                        "run_id": state["run_id"],
                    },
                )
            state = {
                "run_id": uuid4().hex,
                "owner": _BOOT_ID,
                "status": "queued",
                "started_at": _now(),
                "finished_at": None,
                "started_by": actor,
                "entities": list(entities),
                "entity": "",
                "current_step": "Queued",
                "last_progress_at": _now(),
                "last_sequence": 0,
                "counters": {
                    key: 0
                    for key in (
                        "fetched",
                        "processed",
                        "imported",
                        "skipped",
                        "errors",
                        "pending",
                    )
                },
                "result": {**{entity: 0 for entity in ENTITY_ORDER}, "errors": []},
            }
            self.connection.execute("DELETE FROM events")
            self._beat()
            self._append(state, "start", f"Import accepted: {', '.join(entities)}")
            return state

    def publish(self, state, action, message, **fields):
        with self.lock, self.connection:
            self._write_lock()
            current = self._read()
            if current and current["run_id"] == state["run_id"]:
                # Continue after any row another process added to this run.
                state["last_sequence"] = max(
                    state["last_sequence"], current["last_sequence"]
                )
                self._append(state, action, message, **fields)

    def latest(self, after=0):
        with self.lock, self.connection:
            state = self._read()
            if self._abandoned(state):
                self._write_lock()
                state = self._read()
                self._recover(state)
            if not state:
                return {
                    "run": None,
                    "events": [],
                    "has_more": False,
                    "server_time": _now(),
                }
            events = [
                json.loads(row[0])
                for row in self.connection.execute(
                    "SELECT payload FROM events WHERE sequence > ? ORDER BY sequence LIMIT 500",
                    (after,),
                )
            ]
            return {
                "run": {key: value for key, value in state.items() if key != "owner"},
                "events": events,
                "has_more": bool(
                    events and events[-1]["sequence"] < state["last_sequence"]
                ),
                "server_time": _now(),
            }


def store_for(db):
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    identity = engine.url.render_as_string(hide_password=True)
    key = sha256(identity.encode()).hexdigest()
    root = storage.backups_root() / ".qbo-import"
    cache_key = (str(root), key)
    with _stores_lock:
        if cache_key not in _stores:
            _stores[cache_key] = ImportStore(root / key / "latest.sqlite3")
        return _stores[cache_key]


class Reporter:
    def __init__(self, store, state):
        self.store, self.state = store, state
        self.item_id = self.item_label = self.error_code = ""
        self.item_labels = {}
        self.phase = ""
        self.resolved = True
        self.pending = {}
        self.checkpoints = {}
        self.reported_errors = set()
        self.kept = set()

    def emit(self, action, message, item_id=None, **fields):
        self.state["counters"]["fetched"] += fields.pop("fetched", 0)
        item_id = self.item_id if item_id is None else str(item_id)
        if action == "query":
            self.phase = "query"
        elif action in {"validate", "create", "map"}:
            self.phase = "item"
        if action not in {"skip", "error", "map", "note"}:
            self.state["current_step"] = message
        self.store.publish(
            self.state,
            action,
            message,
            item_id=item_id,
            item_label=self.item_labels.get(
                item_id, self.item_label if item_id == self.item_id else ""
            ),
            **fields,
        )

    def finish_item(self):
        if self.item_id and not self.resolved:
            self.skip(
                "No new record; matched existing data or source item is incomplete"
            )

    def begin_entity(self, entity):
        self.finish_item()
        self.item_id = self.item_label = self.error_code = ""
        self.item_labels = {}
        self.resolved = True
        self.state["entity"] = entity
        self.entity_pending_before = self.pending.get(entity, 0)
        self.entity_imported_before = self.state["result"][entity]
        self.state["status"] = "running"
        self.emit("entity", f"Importing {entity.replace('_', ' ')}")

    def end_entity(self, result):
        self.finish_item()
        entity = self.state["entity"]
        for error in result.get("errors", []):
            self.error(error)
        committed = self.state["result"][entity] - self.entity_imported_before
        expected = max(
            0, self.entity_pending_before + result.get("imported", 0) - committed
        )
        if self.pending.get(entity, 0) > expected:
            self.pending[entity] = expected
            self.emit(
                "rollback",
                "Pending item writes were rolled back",
                level="warning",
                code="IMPORT_ROLLED_BACK",
                item_id="",
            )
        else:
            self.pending[entity] = expected
        self.state["counters"]["pending"] = sum(self.pending.values())
        self.emit(
            "summary",
            f"{entity.replace('_', ' ')}: {result.get('imported', 0)} new items; {expected} pending commit; {len(result.get('errors', []))} errors",
            item_id="",
        )

    def begin_item(self, item_id, label):
        self.finish_item()
        self.item_id, self.item_label = item_id, label
        self.item_labels[item_id] = label
        self.error_code = ""
        self.resolved = False
        self.state["counters"]["processed"] += 1
        self.emit("validate", "Inspecting source item")

    def matches(self, entity, qbo_id):
        return (
            entity
            == {
                "accounts": "account",
                "customers": "customer",
                "vendors": "vendor",
                "items": "item",
                "invoices": "invoice",
                "payments": "payment",
                "sales_receipts": "sales_receipt",
                "journal_entries": "journal_entry",
                "ledger": "ledger",
            }.get(self.state["entity"])
            and str(qbo_id) == self.item_id
        )

    def created(self, item_id=None):
        entity = self.state["entity"]
        self.pending[entity] = self.pending.get(entity, 0) + 1
        self.state["counters"]["pending"] = sum(self.pending.values())
        if item_id is None or item_id == self.item_id:
            self.resolved = True
        self.emit("create", "Created local item; pending commit", item_id=item_id)

    def skip(self, message="Existing mapping; no duplicate created"):
        if self.resolved:
            return
        self.resolved = True
        self.state["counters"]["skipped"] += 1
        self.emit("skip", message, code="IMPORT_SKIPPED")

    def keep(self, key, message=None):
        """A transaction changed in FlowBooks and kept as it is here:
        counted once in finish()'s line for the run, however many steps
        keep it; `message` is its own line, which only the first run to
        keep it gives (qbo_common.kept_here)."""
        self.kept.add(key)
        if message:
            self.skip(message)
        elif not self.resolved:
            self.resolved = True
            self.state["counters"]["skipped"] += 1

    def error(self, error):
        item_id = str(error.get("qbo_id", self.item_id) or "")
        label = error.get("document_number") or self.item_labels.get(item_id, "")
        if label:
            self.item_labels[item_id] = label
        message = error.get("message") or "Import failed"
        if item_id and f"#{item_id}" not in message:
            message = (
                f"{error.get('entity', self.state['entity'])} QBO #{item_id}"
                + (f" (document {label})" if label else "")
                + f": {message}"
            )
        error = {
            **error,
            "qbo_id": item_id,
            "document_number": label,
            "message": message,
        }
        key = (
            error.get("entity", self.state["entity"]),
            error.get("qbo_id", ""),
            error.get("message", ""),
        )
        if key in self.reported_errors:
            return
        self.reported_errors.add(key)
        self.resolved = True
        self.state["counters"]["errors"] += 1
        code = error.get("code") or self.error_code or "IMPORT_VALIDATION"
        self.state["result"]["errors"].append({**error, "code": code})
        self.emit(
            "error",
            error.get("message") or "Import failed",
            level="error",
            code=code,
            item_id=error.get("qbo_id", self.item_id),
        )

    def transaction_created(self, session, transaction):
        if transaction.nested:
            self.checkpoints[transaction] = dict(self.pending)

    def committed(self, session):
        if not session.in_nested_transaction():
            count = sum(self.pending.values())
            self.state["counters"]["imported"] += count
            for entity, imported in self.pending.items():
                self.state["result"][entity] += imported
            self.pending.clear()
            self.state["counters"]["pending"] = 0
            self.emit(
                "commit", f"Transaction committed; {count} new items saved", item_id=""
            )

    def rolled_back(self, session, transaction):
        if transaction.nested:
            self.pending = self.checkpoints.pop(transaction, {})
        elif transaction.parent is None:
            self.pending.clear()
        else:
            return
        self.state["counters"]["pending"] = sum(self.pending.values())
        self.emit(
            "rollback",
            "Current transaction rolled back; pending writes were not saved",
            level="warning",
            code="IMPORT_ROLLED_BACK",
            item_id="",
        )

    def finish(self, status):
        self.finish_item()
        self.state["entity"] = ""
        if self.kept:
            count = len(self.kept)
            self.emit(
                "summary",
                (
                    "1 transaction changed in FlowBooks was kept as it is here"
                    if count == 1
                    else f"{count} transactions changed in FlowBooks were kept "
                    "as they are here"
                ),
                item_id="",
            )
        self.state.update(status=status, finished_at=_now(), entity="")
        self.emit("finish", status.replace("_", " ").capitalize(), item_id="")


@contextmanager
def _heartbeat(store):
    """Beat for as long as this process works on its run."""
    stop = Event()

    def beat():
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                store.beat()
            except Exception:
                logger.warning("Could not record the QBO import heartbeat")

    thread = Thread(target=beat, name="qbo-import-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=HEARTBEAT_SECONDS)


@contextmanager
def _run_context(db, store, state):
    reporter = Reporter(store, state)
    listeners = [
        ("after_transaction_create", reporter.transaction_created),
        ("after_commit", reporter.committed),
        ("after_soft_rollback", reporter.rolled_back),
    ]
    for name, function in listeners:
        event.listen(db, name, function)
    try:
        with _heartbeat(store), qbo_progress.reporting(reporter):
            yield reporter
    except Exception as exc:
        db.rollback()
        reporter.error(
            {"code": "IMPORT_FAILED", "message": safe_message(exc, "QBO import run")}
        )
        reporter.finish("failed")
        raise
    else:
        reporter.finish(
            "completed_with_errors"
            if reporter.state["counters"]["errors"]
            else "completed"
        )
    finally:
        for name, function in listeners:
            event.remove(db, name, function)


@contextmanager
def synchronous_run(db, entities, actor):
    store = store_for(db)
    state = store.reserve(entities, actor)
    with _run_context(db, store, state):
        yield


def start_run(db: Session, entities, actor, import_all=False):
    store = store_for(db)
    state = store.reserve(entities, actor)
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    session_class = type(db)

    def work():
        try:
            from app.services import qbo_import, qbo_ledger_import

            with session_class(bind=engine, autoflush=False) as worker_db:
                worker_db.info["acting_username"] = actor
                with _run_context(worker_db, store, state) as reporter:
                    # Import All too goes a step at a time, each committed as
                    # it finishes (qbo_import.import_all commits once, at the
                    # end): on SQLite an open write holds the company file,
                    # and the person keeps working while this runs.
                    for entity in entities:
                        function = (
                            qbo_ledger_import.import_ledger
                            if entity == "ledger"
                            else getattr(qbo_import, f"import_{entity}")
                        )
                        # A mocked/third-party importer may not use the decorator.
                        decorated = hasattr(function, "__wrapped__")
                        if not decorated:
                            reporter.begin_entity(entity)
                        result = function(worker_db)
                        if not decorated:
                            reporter.end_entity(result)
                        worker_db.commit()
        except Exception as exc:
            if state["status"] in ACTIVE:
                reporter = Reporter(store, state)
                reporter.error(
                    {
                        "code": "IMPORT_FAILED",
                        "message": safe_message(exc, "QBO import worker"),
                    }
                )
                reporter.finish("failed")
            logger.exception("Background QBO import failed")

    thread = Thread(target=work, name=f"qbo-import-{state['run_id'][:8]}", daemon=True)
    try:
        thread.start()
    except Exception:
        state.update(status="failed", finished_at=_now())
        store.publish(
            state,
            "error",
            "Could not start import worker",
            level="error",
            code="IMPORT_FAILED",
        )
        raise
    return {"run_id": state["run_id"], "status": "queued"}
