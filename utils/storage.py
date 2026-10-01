"""
Persistence for the leaderboard and Driver live state (2026-10-01).

Two backends behind one small API, chosen once per process:

- **Database** (durable): used when the deployment sets DATABASE_URL in its
  Streamlit secrets (or environment). Any SQLAlchemy URL works, e.g. a free
  Postgres from Neon or Supabase. Survives app reboots and redeploys, which
  Streamlit Community Cloud's local disk does not. Leaderboard submissions
  are append-only INSERTs, so simultaneous submits from many teams can't
  overwrite each other.
- **Local JSON files** (fallback, no setup): every read-modify-write runs
  under one process-wide lock (Streamlit serves all sessions from threads
  in a single process), and every write goes to a temp file that is then
  atomically swapped in, so a reader can never see a half-written file.
  If a file is ever unreadable, it is copied aside and the write is refused
  rather than replacing everyone's data with an empty board.

Same BYOK posture as ANTHROPIC_API_KEY (see README.md): each school's own
deployment configures its own database. Nothing is shared or committed.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

_LOCK = threading.RLock()


class StorageError(RuntimeError):
    """Raised instead of silently overwriting data that couldn't be read."""


# ── Backend selection ────────────────────────────────────────────────────────
def database_url() -> Optional[str]:
    """DATABASE_URL from Streamlit secrets, else the environment, else None."""
    try:
        import streamlit as st
        url = st.secrets.get("DATABASE_URL")
        if url:
            return str(url)
    except Exception:
        pass
    return os.environ.get("DATABASE_URL") or None


def backend_name() -> str:
    return "database" if database_url() else "file"


# ── File backend ─────────────────────────────────────────────────────────────
def _read_json(path: Path, default, strict: bool):
    """Missing file -> default. Unreadable file -> default when not strict
    (display paths), or StorageError after copying the file aside when
    strict (any path about to write back)."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        if not strict:
            return default
        backup = path.with_name(f"{path.name}.unreadable-{int(time.time())}")
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
        raise StorageError(
            f"{path.name} could not be read ({e}); a copy was saved as {backup.name} "
            "and nothing was overwritten."
        ) from e


def _write_json_atomic(path: Path, data, indent: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        # On Windows a just-written target can be briefly held open by
        # antivirus/indexing, making the swap fail with "Access is denied".
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01 * (attempt + 1))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Database backend ─────────────────────────────────────────────────────────
@lru_cache(maxsize=4)
def _engine(url: str):
    from sqlalchemy import create_engine
    if url.startswith("postgres://"):          # Heroku/Supabase-style alias SQLAlchemy rejects
        url = "postgresql://" + url[len("postgres://"):]
    eng = create_engine(url, pool_pre_ping=True, future=True)
    _ensure_schema(eng)
    return eng


def _ensure_schema(eng) -> None:
    from sqlalchemy import text
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE IF NOT EXISTS slate_leaderboard ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " created_at DOUBLE PRECISION NOT NULL,"
            " payload TEXT NOT NULL)"
            if eng.dialect.name == "sqlite" else
            "CREATE TABLE IF NOT EXISTS slate_leaderboard ("
            " id BIGSERIAL PRIMARY KEY,"
            " created_at DOUBLE PRECISION NOT NULL,"
            " payload TEXT NOT NULL)"
        ))
        c.execute(text(
            "CREATE TABLE IF NOT EXISTS slate_team_state ("
            " team_key TEXT PRIMARY KEY,"
            " updated_at DOUBLE PRECISION NOT NULL,"
            " payload TEXT NOT NULL)"
        ))


def _db():
    url = database_url()
    return _engine(url) if url else None


# ── Public API: leaderboard ──────────────────────────────────────────────────
def load_entries(file_path: Path) -> list[dict]:
    eng = _db()
    if eng is not None:
        from sqlalchemy import text
        with eng.connect() as c:
            rows = c.execute(text("SELECT payload FROM slate_leaderboard ORDER BY id")).all()
        return [json.loads(r[0]) for r in rows]
    with _LOCK:
        data = _read_json(file_path, [], strict=False)
    return data if isinstance(data, list) else []


def append_entry(file_path: Path, entry: dict) -> None:
    eng = _db()
    if eng is not None:
        from sqlalchemy import text
        with eng.begin() as c:
            c.execute(text("INSERT INTO slate_leaderboard (created_at, payload) VALUES (:t, :p)"),
                      {"t": time.time(), "p": json.dumps(entry)})
        return
    with _LOCK:
        board = _read_json(file_path, [], strict=True)
        if not isinstance(board, list):
            raise StorageError(f"{file_path.name} does not hold a list; nothing was overwritten.")
        board.append(entry)
        _write_json_atomic(file_path, board, indent=2)


def replace_entries(file_path: Path, board: list[dict]) -> None:
    """Whole-board rewrite, kept for save_leaderboard()'s existing callers.
    Prefer append_entry for new submissions."""
    eng = _db()
    if eng is not None:
        from sqlalchemy import text
        with eng.begin() as c:
            c.execute(text("DELETE FROM slate_leaderboard"))
            for e in board:
                c.execute(text("INSERT INTO slate_leaderboard (created_at, payload) VALUES (:t, :p)"),
                          {"t": e.get("timestamp", time.time()), "p": json.dumps(e)})
        return
    with _LOCK:
        _write_json_atomic(file_path, board, indent=2)


# ── Public API: Driver live state ────────────────────────────────────────────
def save_state(file_path: Path, key: str, state: dict) -> None:
    now = time.time()
    eng = _db()
    if eng is not None:
        from sqlalchemy import text
        with eng.begin() as c:
            c.execute(text("DELETE FROM slate_team_state WHERE team_key = :k"), {"k": key})
            c.execute(text("INSERT INTO slate_team_state (team_key, updated_at, payload) "
                           "VALUES (:k, :t, :p)"), {"k": key, "t": now, "p": json.dumps(state)})
        return
    with _LOCK:
        states = _read_json(file_path, {}, strict=True)
        if not isinstance(states, dict):
            raise StorageError(f"{file_path.name} does not hold an object; nothing was overwritten.")
        states[key] = {"updated_at": now, "state": state}
        _write_json_atomic(file_path, states)


def load_state(file_path: Path, key: str) -> Optional[dict]:
    eng = _db()
    if eng is not None:
        from sqlalchemy import text
        with eng.connect() as c:
            row = c.execute(text("SELECT payload FROM slate_team_state WHERE team_key = :k"),
                            {"k": key}).first()
        return json.loads(row[0]) if row else None
    with _LOCK:
        states = _read_json(file_path, {}, strict=False)
    entry = states.get(key) if isinstance(states, dict) else None
    return entry["state"] if entry else None
