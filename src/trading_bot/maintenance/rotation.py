"""Log rotation, safe to run at any time of day.

* logs/*.log and logs/*.jsonl from an earlier day move to logs/archive/<date>/
* trades.csv keeps the last 90 days; older rows go to logs/archive/trades_YYYYMMDD.csv
* safety-check-log.json is archived (and restarted) once it passes 5 MB

Everything is an atomic os.replace. Nothing is ever overwritten (a numeric suffix
is added on a name clash), and a file locked by another process is skipped.
"""
import csv
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from trading_bot.config import DECISION_LOG_PATH, LOG_DIR, TRADES_CSV
from trading_bot.timeutil import ET, now_et

LOG_SUFFIXES = {".log", ".jsonl"}
KEEP_TRADE_DAYS = 90
SAFETY_LOG_MAX_BYTES = 5 * 1024 * 1024


@dataclass
class RotationReport:
    moved: list = field(default_factory=list)
    skipped: list = field(default_factory=list)  # (path, reason)


def _unique(path: Path) -> Path:
    """`path`, or `name.1.ext`, `name.2.ext`... if it is taken."""
    candidate, n = path, 0
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.stem}.{n}{path.suffix}")
    return candidate


def _archive_move(source: Path, destination: Path) -> Path:
    destination = _unique(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)
    return destination


def _rotate_log_files(logs_dir: Path, today, report: RotationReport) -> None:
    if not logs_dir.is_dir():
        return
    for path in sorted(logs_dir.iterdir()):
        if not path.is_file() or path.suffix not in LOG_SUFFIXES:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, ET).date()
        if modified >= today:
            continue
        try:
            report.moved.append(
                _archive_move(path, logs_dir / "archive" / modified.isoformat() / path.name)
            )
        except OSError as exc:  # e.g. still open by a running process on Windows
            report.skipped.append((path, str(exc)))


def _old_enough(row: dict, cutoff) -> bool:
    try:
        return datetime.fromisoformat(row["timestamp_iso"]).astimezone(ET).date() < cutoff
    except (KeyError, ValueError, TypeError):
        return False  # unparseable rows are kept, never lost


def _rotate_trades(trades_path: Path, logs_dir: Path, today, keep_days: int,
                   report: RotationReport) -> None:
    if not trades_path.exists():
        return
    with trades_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames, rows = reader.fieldnames, list(reader)
    old = [r for r in rows if _old_enough(r, today - timedelta(days=keep_days))]
    if not old:
        return

    archive = logs_dir / "archive" / f"trades_{today:%Y%m%d}.csv"
    archive.parent.mkdir(parents=True, exist_ok=True)
    existed, size_before = archive.exists(), archive.stat().st_size if archive.exists() else 0
    temp = trades_path.with_suffix(".csv.tmp")
    try:
        with archive.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not existed:
                writer.writeheader()
            writer.writerows(old)
        keep = [r for r in rows if r not in old]
        with temp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(keep)
        os.replace(temp, trades_path)
    except OSError as exc:
        # roll back the archive so a retry doesn't duplicate rows
        temp.unlink(missing_ok=True)
        if existed:
            with archive.open("r+b") as f:
                f.truncate(size_before)
        else:
            archive.unlink(missing_ok=True)
        report.skipped.append((trades_path, str(exc)))
        return
    report.moved.append(archive)


def _rotate_safety_log(path: Path, logs_dir: Path, today, max_bytes: int,
                       report: RotationReport) -> None:
    if not path.exists() or path.stat().st_size <= max_bytes:
        return
    try:
        report.moved.append(
            _archive_move(path, logs_dir / "archive" / f"{today:%Y-%m-%d}_{path.name}")
        )
    except OSError as exc:
        report.skipped.append((path, str(exc)))


def rotate(
    *,
    logs_dir: Path,
    trades_path: Path,
    safety_log_path: Path,
    now: datetime,
    keep_days: int = KEEP_TRADE_DAYS,
    max_bytes: int = SAFETY_LOG_MAX_BYTES,
) -> RotationReport:
    report = RotationReport()
    today = now.astimezone(ET).date()
    _rotate_log_files(logs_dir, today, report)
    _rotate_trades(trades_path, logs_dir, today, keep_days, report)
    _rotate_safety_log(safety_log_path, logs_dir, today, max_bytes, report)
    return report


def format_report(report: RotationReport) -> str:
    return f"Rotated {len(report.moved)} files to logs/archive/"


def main() -> int:
    try:
        report = rotate(
            logs_dir=LOG_DIR, trades_path=TRADES_CSV,
            safety_log_path=DECISION_LOG_PATH, now=now_et(),
        )
    except Exception as exc:
        print(f"Rotation failed: {exc!r}", file=sys.stderr)
        return 1
    print(format_report(report))
    for path, reason in report.skipped:
        print(f"Skipped {path.name}: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
