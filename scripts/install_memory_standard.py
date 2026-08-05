#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_SCRIPTS = {
    "supabase_memory_health_check.py": PROJECT_ROOT / "scripts" / "supabase_memory_health_check.py",
    "supabase_keepalive_check.py": PROJECT_ROOT / "scripts" / "supabase_keepalive_check.py",
}

HEALTH_JOB = {
    "name": "Supabase memory health",
    "schedule": "every 12h",
    "script": "supabase_memory_health_check.py",
}

KEEPALIVE_JOB = {
    "name": "Supabase keepalive check",
    "schedule": "every 8640m",
    "script": "supabase_keepalive_check.py",
}

JOB_RE = re.compile(r"^\s*(?P<id>[a-f0-9]{8,})\s+\[(?P<state>[^\]]+)\]")
NAME_RE = re.compile(r"^\s*Name:\s*(?P<name>.+?)\s*$")
SCHEDULE_RE = re.compile(r"^\s*Schedule:\s*(?P<schedule>.+?)\s*$")
SCRIPT_RE = re.compile(r"^\s*Script:\s*(?P<script>.+?)\s*$")
DELIVER_RE = re.compile(r"^\s*Deliver:\s*(?P<deliver>.+?)\s*$")
MODE_RE = re.compile(r"^\s*Mode:\s*(?P<mode>.+?)\s*$")


@dataclass
class Job:
    job_id: str
    name: str = ""
    schedule: str = ""
    script: str = ""
    deliver: str = ""
    mode: str = ""
    state: str = ""


def run(cmd: List[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def hermes_home(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return get_hermes_home()
    except Exception:
        return Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser().resolve()


def ensure_scripts(home: Path) -> List[str]:
    target = home / "scripts"
    target.mkdir(parents=True, exist_ok=True)
    installed: List[str] = []
    for filename, source in REPO_SCRIPTS.items():
        if not source.exists():
            raise FileNotFoundError(f"Missing repo script: {source}")
        dest = target / filename
        shutil.copy2(source, dest)
        try:
            dest.chmod(dest.stat().st_mode | 0o111)
        except Exception:
            pass
        installed.append(str(dest))
    return installed


def parse_jobs(text: str) -> Dict[str, Job]:
    jobs: Dict[str, Job] = {}
    current: Optional[Job] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = JOB_RE.match(line)
        if m:
            current = Job(job_id=m.group("id"), state=m.group("state"))
            jobs[current.job_id] = current
            continue
        if not current:
            continue
        for regex, attr in [
            (NAME_RE, "name"),
            (SCHEDULE_RE, "schedule"),
            (SCRIPT_RE, "script"),
            (DELIVER_RE, "deliver"),
            (MODE_RE, "mode"),
        ]:
            mm = regex.match(line)
            if mm:
                setattr(current, attr, mm.group(attr).strip())
                break
    return jobs


def list_jobs() -> Dict[str, Job]:
    proc = run(["hermes", "cron", "list"])
    return parse_jobs(proc.stdout)


def ensure_job(job: Dict[str, str], *, dry_run: bool = False) -> str:
    jobs = list_jobs()
    existing = next((j for j in jobs.values() if j.name == job["name"]), None)
    if existing:
        cmd = [
            "hermes", "cron", "edit", existing.job_id,
            "--schedule", job["schedule"],
            "--name", job["name"],
            "--deliver", "origin",
            "--script", job["script"],
            "--no-agent",
        ]
        action = f"edit:{existing.job_id}"
    else:
        cmd = [
            "hermes", "cron", "create", job["schedule"],
            "--name", job["name"],
            "--deliver", "origin",
            "--script", job["script"],
            "--no-agent",
        ]
        action = "create"

    if dry_run:
        return f"DRY-RUN {action} {' '.join(cmd)}"

    proc = run(cmd)
    return proc.stdout.strip() or f"{action} ok"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the Supabase memory health standard")
    parser.add_argument("--hermes-home", help="Target Hermes home directory (defaults to current profile)")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without changing anything")
    args = parser.parse_args()

    home = hermes_home(args.hermes_home)

    if args.dry_run:
        print(f"Target Hermes home: {home}")
        for name, source in REPO_SCRIPTS.items():
            print(f"Would install: {source} -> {home / 'scripts' / name}")
        print(f"Would ensure job: {HEALTH_JOB['name']} ({HEALTH_JOB['schedule']}, {HEALTH_JOB['script']})")
        print(f"Would ensure job: {KEEPALIVE_JOB['name']} ({KEEPALIVE_JOB['schedule']}, {KEEPALIVE_JOB['script']})")
        return 0

    installed = ensure_scripts(home)
    print("Installed scripts:")
    for path in installed:
        print(f"- {path}")

    print(ensure_job(HEALTH_JOB))
    print(ensure_job(KEEPALIVE_JOB))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
