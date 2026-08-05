#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

DEFAULT_URL_SECRET_PATH = "hermes/vault/Supabase-Salvarrey.Tech/URL"
DEFAULT_SERVICE_ROLE_PATH = "hermes/vault/Supabase-Salvarrey.Tech/service_role"
DEFAULT_CHECK_PATH = "/rest/v1/content_forge_series?select=id&limit=1"


def pass_show(path: str) -> str:
    return subprocess.check_output(["pass", "show", path], text=True).strip()


def resolve_secret_path(explicit: Optional[str], env_name: str, fallback: str) -> str:
    return explicit or os.environ.get(env_name) or fallback


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Supabase warm with a tiny authenticated GET")
    parser.add_argument("--url-secret-path")
    parser.add_argument("--service-role-secret-path")
    parser.add_argument("--check-path", default=DEFAULT_CHECK_PATH)
    args = parser.parse_args()

    url_secret = resolve_secret_path(args.url_secret_path, "SUPABASE_URL_SECRET_PATH", DEFAULT_URL_SECRET_PATH)
    role_secret = resolve_secret_path(
        args.service_role_secret_path,
        "SUPABASE_SERVICE_ROLE_SECRET_PATH",
        DEFAULT_SERVICE_ROLE_PATH,
    )

    try:
        base_url = pass_show(url_secret).rstrip("/")
        service_role = pass_show(role_secret)
    except Exception as exc:
        sys.stderr.write(f"Supabase keepalive failed: secret lookup error: {exc.__class__.__name__}: {exc}\n")
        return 1

    url = f"{base_url}{args.check_path}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "apikey": service_role,
            "Authorization": f"Bearer {service_role}",
            "Accept": "application/json",
            "Prefer": "count=exact",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        sys.stderr.write(f"Supabase keepalive failed: HTTP {exc.code} {exc.reason}\n")
        try:
            detail = exc.read().decode("utf-8", "replace")
            if detail:
                sys.stderr.write(detail[:1000] + ("\n" if not detail.endswith("\n") else ""))
        except Exception:
            pass
        return 1
    except Exception as exc:
        sys.stderr.write(f"Supabase keepalive failed: {exc.__class__.__name__}: {exc}\n")
        return 1

    try:
        rows = json.loads(body)
        row_count = len(rows) if isinstance(rows, list) else "unknown"
    except Exception:
        row_count = "unknown"

    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    print(f"Supabase keepalive OK | status={status} | rows={row_count} | checked_at={stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
