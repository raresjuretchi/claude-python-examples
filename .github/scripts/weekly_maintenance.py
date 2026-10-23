#!/usr/bin/env python3
"""Weekly maintenance for this repository.

Run by .github/workflows/weekly-maintenance.yml, which wakes up every two hours.
This script decides whether "now" is past this week's random slot and, if the
week's maintenance has not happened yet, it:

  1. checks PyPI for newer releases of every pinned dependency,
  2. bumps the pins (within the same major version unless MAINT_ALLOW_MAJOR=true),
  3. reinstalls and runs the test suite, keeping only the bumps that pass,
  4. records the outcome in MAINTENANCE.md, the README status line and the state file.

The slot is derived from the repository name and the ISO week, so it is stable
within a week (re-runs are harmless) but lands on a different day and time each
week, and differs between repositories.

Settings (environment variables, all optional):
  FORCE=true              run now, ignoring the slot and the once-a-week guard
  MAINT_TZ                time zone for the slot window (default Europe/Madrid)
  MAINT_START_HOUR        earliest local hour for the slot (default 8)
  MAINT_END_HOUR          latest local hour, exclusive (default 22)
  MAINT_ALLOW_MAJOR=true  also take new major versions
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / ".github" / "maintenance-state.json"
LOG_FILE = ROOT / "MAINTENANCE.md"
README = ROOT / "README.md"
REQUIREMENT_FILES = ("requirements.txt", "requirements-dev.txt")
MAX_LOG_ROWS = 52

PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?P<extras>\[[^\]]+\])?"
    r"==(?P<version>[^\s;#]+)(?P<rest>.*)$"
)
README_START = "<!-- maintenance:start -->"
README_END = "<!-- maintenance:end -->"
LOG_TABLE_HEADER = "| Date | Dependencies | Tests |\n|---|---|---|"


@dataclass
class Pin:
    file: str
    line_no: int
    name: str
    version: str
    extras: str
    rest: str


@dataclass
class Bump:
    pin: Pin
    new: str

    @property
    def label(self) -> str:
        return f"{self.pin.name} {self.pin.version} → {self.new}"


# --------------------------------------------------------------------------- slot


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def week_key(moment: dt.datetime) -> str:
    iso = moment.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def weekly_slot(repo: str, now_local: dt.datetime, start_hour: int, end_hour: int) -> dt.datetime:
    """Pseudo-random local datetime for this repo's maintenance in now_local's ISO week."""
    if not 0 <= start_hour < end_hour <= 24:
        raise ValueError("need 0 <= MAINT_START_HOUR < MAINT_END_HOUR <= 24")
    digest = hashlib.sha256(f"{repo}|{week_key(now_local)}".encode()).digest()
    n = int.from_bytes(digest[:8], "big")
    day = n % 7
    minute = (n // 7) % ((end_hour - start_hour) * 60)
    monday = (now_local - dt.timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    naive = monday.replace(tzinfo=None) + dt.timedelta(days=day, minutes=start_hour * 60 + minute)
    return naive.replace(tzinfo=now_local.tzinfo)


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


# ------------------------------------------------------------------ dependencies


def read_pins() -> list[Pin]:
    pins = []
    for file in REQUIREMENT_FILES:
        path = ROOT / file
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text().splitlines()):
            match = PIN_RE.match(line.strip())
            if match:
                pins.append(Pin(file, i, match["name"], match["version"], match["extras"] or "", match["rest"]))
    return pins


def latest_release(name: str) -> Version | None:
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.load(resp)
    except Exception as exc:  # network hiccups must not break the run
        print(f"  ! could not query PyPI for {name}: {exc}")
        return None
    best = None
    for raw, files in data.get("releases", {}).items():
        try:
            version = Version(raw)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        if not files or all(f.get("yanked") for f in files):
            continue
        if best is None or version > best:
            best = version
    return best


def plan_bumps(pins: list[Pin], allow_major: bool) -> tuple[list[Bump], list[str]]:
    bumps, held = [], []
    for pin in pins:
        latest = latest_release(pin.name)
        try:
            current = Version(pin.version)
        except InvalidVersion:
            continue
        if latest is None or latest <= current:
            continue
        if latest.major != current.major and not allow_major:
            held.append(f"{pin.name} {latest} (new major, not auto-applied)")
            continue
        bumps.append(Bump(pin, str(latest)))
    return bumps, held


def write_pins(bumps: list[Bump], originals: dict[str, str]) -> None:
    """Rewrite requirement files from their original text plus the given bumps."""
    by_file: dict[str, list[Bump]] = {}
    for bump in bumps:
        by_file.setdefault(bump.pin.file, []).append(bump)
    for file, text in originals.items():
        lines = text.splitlines()
        for bump in by_file.get(file, []):
            p = bump.pin
            lines[p.line_no] = f"{p.name}{p.extras}=={bump.new}{p.rest}"
        (ROOT / file).write_text("\n".join(lines) + "\n")


def run_tests() -> tuple[bool, str]:
    files = [arg for f in REQUIREMENT_FILES if (ROOT / f).exists() for arg in ("-r", f)]
    install = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *files],
        cwd=ROOT, capture_output=True, text=True,
    )
    if install.returncode != 0:
        print(install.stdout[-2000:], install.stderr[-2000:])
        return False, "dependency install failed"
    test = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True,
    )
    lines = [ln for ln in test.stdout.splitlines() if ln.strip()]
    summary = re.sub(r"\s+in\s+[\d.]+s.*$", "", lines[-1] if lines else "no output").strip("= ")
    if test.returncode != 0:
        print(test.stdout[-4000:], test.stderr[-2000:])
    return test.returncode == 0, summary


def try_bumps(bumps: list[Bump], originals: dict[str, str]) -> tuple[list[Bump], list[str], bool, str]:
    """Apply bumps, keeping only those that keep the tests green."""
    if not bumps:
        write_pins([], originals)
        ok, summary = run_tests()
        return [], [], ok, summary

    write_pins(bumps, originals)
    ok, summary = run_tests()
    if ok:
        return bumps, [], ok, summary

    print("Tests failed with all bumps applied; trying each bump on its own.")
    kept, rejected = [], []
    for bump in bumps:
        write_pins([bump], originals)
        single_ok, _ = run_tests()
        (kept if single_ok else rejected).append(bump)
    notes = [f"{b.label} held back (tests failed)" for b in rejected]
    if kept:
        write_pins(kept, originals)
        ok, summary = run_tests()
        if ok:
            return kept, notes, ok, summary
        notes += [f"{b.label} held back (failed in combination)" for b in kept]
    write_pins([], originals)
    ok, summary = run_tests()
    return [], notes, ok, summary


# ----------------------------------------------------------------------- records


def update_log(date: str, deps: str, tests: str) -> None:
    title = "# Maintenance log\n\nUpdated automatically once a week by the *Weekly maintenance* workflow.\n"
    rows: list[str] = []
    if LOG_FILE.exists():
        rows = [ln for ln in LOG_FILE.read_text().splitlines() if ln.startswith("| ") and not ln.startswith("| Date")]
    deps_cell = deps.replace("|", "\\|")
    rows.insert(0, f"| {date} | {deps_cell} | {tests} |")
    LOG_FILE.write_text(f"{title}\n{LOG_TABLE_HEADER}\n" + "\n".join(rows[:MAX_LOG_ROWS]) + "\n")


def update_readme(line: str) -> None:
    if not README.exists():
        return
    text = README.read_text()
    block = f"{README_START}\n{line}\n{README_END}"
    if README_START in text and README_END in text:
        text = re.sub(re.escape(README_START) + r".*?" + re.escape(README_END), block, text, flags=re.S)
    else:
        text = text.rstrip() + f"\n\n{block}\n"
    README.write_text(text)


def set_output(**values: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    for key, value in values.items():
        print(f"output {key}={value}")
        if path:
            with open(path, "a") as fh:
                fh.write(f"{key}={value}\n")


# -------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="run now (same as FORCE=true)")
    parser.add_argument("--check", action="store_true", help="only print this week's slot")
    parser.add_argument("--now", help="pretend the current time is this ISO timestamp (testing)")
    args = parser.parse_args(argv)

    tz = ZoneInfo(os.getenv("MAINT_TZ", "Europe/Madrid"))
    start_hour = int(os.getenv("MAINT_START_HOUR", "8"))
    end_hour = int(os.getenv("MAINT_END_HOUR", "22"))
    force = args.force or env_bool("FORCE")
    repo = os.getenv("GITHUB_REPOSITORY") or ROOT.name

    now = dt.datetime.fromisoformat(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    now_local = now.astimezone(tz)
    week = week_key(now_local)
    slot = weekly_slot(repo, now_local, start_hour, end_hour)
    state = load_state()

    print(f"Repository: {repo}")
    print(f"Now:        {now_local:%a %Y-%m-%d %H:%M %Z} ({week})")
    print(f"Slot:       {slot:%a %Y-%m-%d %H:%M %Z}")
    print(f"Last run:   {state.get('last_week', 'never')}")

    if args.check:
        return 0
    if not force:
        if state.get("last_week") == week:
            print("This week's maintenance is already done.")
            set_output(changed="false")
            return 0
        if now_local < slot:
            print("Not yet; waiting for this week's slot.")
            set_output(changed="false")
            return 0

    print("Running weekly maintenance…")
    allow_major = env_bool("MAINT_ALLOW_MAJOR")
    originals = {f: (ROOT / f).read_text() for f in REQUIREMENT_FILES if (ROOT / f).exists()}
    pins = read_pins()
    bumps, held = plan_bumps(pins, allow_major)
    for bump in bumps:
        print(f"  candidate: {bump.label}")
    kept, notes, tests_ok, test_summary = try_bumps(bumps, originals)
    notes = held + notes

    date = now_local.strftime("%Y-%m-%d")
    if kept:
        deps = "Updated " + ", ".join(b.label for b in kept)
    else:
        deps = f"All {len(pins)} pinned packages current"
    if notes:
        deps += "; " + "; ".join(notes)
    tests = ("✅ " if tests_ok else "❌ ") + test_summary

    update_log(date, deps, tests)
    update_readme(f"**Last maintenance:** {date} · {deps} · tests {tests}")
    state.update(last_week=week, last_run=now.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
                 last_slot=slot.isoformat(timespec="minutes"), tests_ok=tests_ok)
    save_state(state)

    if kept:
        title = "chore(deps): bump " + ", ".join(f"{b.pin.name} to {b.new}" for b in kept)
        if len(title) > 72:
            title = f"chore(deps): bump {len(kept)} dependencies ({week})"
    else:
        title = f"chore: weekly maintenance check ({week})"
    body = [f"- {b.label}" for b in kept] + [f"- {n}" for n in notes] + [f"- Tests: {test_summary}"]
    msg_dir = Path(os.getenv("RUNNER_TEMP", "/tmp"))
    msg_file = msg_dir / "maintenance-commit-message.txt"
    msg_file.write_text(title + "\n\n" + "\n".join(body) + "\n")

    set_output(changed="true", tests_ok=str(tests_ok).lower(), commit_message_file=str(msg_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
