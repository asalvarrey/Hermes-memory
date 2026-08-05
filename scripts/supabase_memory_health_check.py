#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_REPORT_NAME = "supabase_memory_health"
DEFAULT_DB_FILENAME = "supabase_cache.db"
DEFAULT_FALLBACK_DB = Path("/var/lib/hermes-root/cache/supabase_cache.db")


def resolve_hermes_home(explicit: Optional[str] = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return get_hermes_home()
    except Exception:
        return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()


def resolve_db_path(explicit: Optional[str], hermes_home: Path) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()

    candidate = hermes_home / "cache" / DEFAULT_DB_FILENAME
    if candidate.exists():
        return candidate

    if DEFAULT_FALLBACK_DB.exists():
        return DEFAULT_FALLBACK_DB

    return candidate


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_counts(cur: sqlite3.Cursor, table: str) -> int:
    cur.execute(f"select count(*) from {table}")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def read_recent_dead_letters(cur: sqlite3.Cursor, limit: int = 5) -> List[Dict[str, Any]]:
    cur.execute(
        "select id, operation, payload, retries, last_error, failed_at "
        "from dead_letter order by failed_at desc, id desc limit ?",
        (limit,),
    )
    rows: List[Dict[str, Any]] = []
    for rid, operation, payload, retries, last_error, failed_at in cur.fetchall():
        session_id = None
        try:
            session_id = json.loads(payload).get("session_id")
        except Exception:
            pass
        rows.append(
            {
                "id": rid,
                "operation": operation,
                "session_id": session_id,
                "retries": retries,
                "last_error": last_error,
                "failed_at": failed_at,
            }
        )
    return rows


def write_reports(report_dir: Path, summary: Dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json = report_dir / f"{DEFAULT_REPORT_NAME}.json"
    report_md = report_dir / f"{DEFAULT_REPORT_NAME}.md"

    report_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [f"# {DEFAULT_REPORT_NAME.replace('_', ' ').title()}", ""]
    for key, value in summary.items():
        if key == "recent_dead_letters":
            continue
        md_lines.append(f"- **{key}**: {value}")
    md_lines.append("")
    md_lines.append("## Recent dead letters")
    recent = summary.get("recent_dead_letters") or []
    if recent:
        for row in recent:
            md_lines.append(
                f"- id={row['id']} op={row['operation']} session_id={row['session_id']} "
                f"retries={row['retries']} last_error={row['last_error']}"
            )
    else:
        md_lines.append("- none")
    md_lines.append("")
    report_md.write_text("\n".join(md_lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Supabase memory health for Hermes")
    parser.add_argument("--hermes-home", help="Hermes home directory for the target profile")
    parser.add_argument("--db-path", help="Optional explicit SQLite cache path")
    args = parser.parse_args()

    hermes_home = resolve_hermes_home(args.hermes_home)
    db_path = resolve_db_path(args.db_path, hermes_home)
    report_dir = hermes_home / "cache" / "reports"
    checked_at = utc_now()

    if not db_path.exists():
        summary = {
            "status": "OFFLINE",
            "checked_at": checked_at,
            "db": str(db_path),
            "reason": "db_missing",
            "pending_sync": None,
            "dead_letter": None,
            "memory_cache": None,
            "profile_cache": None,
            "recent_dead_letters": [],
        }
        write_reports(report_dir, summary)
        print(f"SUPABASE_MEMORY_HEALTH OFFLINE | db_missing={db_path} | checked_at={checked_at}")
        return 1

    conn: Optional[sqlite3.Connection] = None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        pending_sync = read_counts(cur, "pending_sync")
        dead_letter = read_counts(cur, "dead_letter")
        memory_cache = read_counts(cur, "memory_cache")
        profile_cache = read_counts(cur, "profile_cache")
        recent_dead_letters = read_recent_dead_letters(cur, limit=5) if dead_letter else []
    except Exception as exc:
        summary = {
            "status": "OFFLINE",
            "checked_at": checked_at,
            "db": str(db_path),
            "reason": f"{exc.__class__.__name__}: {exc}",
            "pending_sync": None,
            "dead_letter": None,
            "memory_cache": None,
            "profile_cache": None,
            "recent_dead_letters": [],
        }
        write_reports(report_dir, summary)
        print(f"SUPABASE_MEMORY_HEALTH OFFLINE | error={summary['reason']} | checked_at={checked_at}")
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    if pending_sync == 0 and dead_letter == 0:
        status = "OK"
        exit_code = 0
    else:
        status = "DEGRADED"
        exit_code = 2

    summary = {
        "status": status,
        "checked_at": checked_at,
        "db": str(db_path),
        "pending_sync": pending_sync,
        "dead_letter": dead_letter,
        "memory_cache": memory_cache,
        "profile_cache": profile_cache,
        "recent_dead_letters": recent_dead_letters,
    }
    write_reports(report_dir, summary)

    print(
        f"SUPABASE_MEMORY_HEALTH {status} | pending_sync={pending_sync} | dead_letter={dead_letter} "
        f"| memory_cache={memory_cache} | profile_cache={profile_cache} | checked_at={checked_at}"
    )
    if recent_dead_letters and status != "OK":
        for row in recent_dead_letters[:3]:
            print(
                f"  dead_letter id={row['id']} op={row['operation']} session_id={row['session_id']} "
                f"retries={row['retries']} last_error={row['last_error']}"
            )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
