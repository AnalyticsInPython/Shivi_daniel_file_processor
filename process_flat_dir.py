#!/usr/bin/env python3
"""Copy files from a flat directory into a processed tree.

The script scans a flat directory for files whose names contain:
- a big-tech company name, and/or
- a valid date in some recognizable format.

If both are found, it copies the file into:
    <input_dir>/processed/<year>/<month>/<day>/
with the destination filename set to the company name only (keeping the original extension).

If either the company name or date cannot be determined, the file is copied into:
    <input_dir>/processed/random/

This script never edits files in place; it copies them into a new processed directory.
"""

from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path


LOG_FILE_NAME = "copy_log.txt"

COMPANY_ALIASES = {
    "apple": "Apple",
    "microsoft": "Microsoft",
    "amazon": "Amazon",
    "google": "Alphabet",
    "alphabet": "Alphabet",
    "meta": "Meta",
    "facebook": "Meta",
    "nvidia": "Nvidia",
    "tesla": "Tesla",
    "intel": "Intel",
    "amd": "AMD",
    "oracle": "Oracle",
    "salesforce": "Salesforce",
    "snowflake": "Snowflake",
}

DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y_%m_%d",
    "%Y.%m.%d",
    "%Y/%m/%d",
    "%Y%m%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d_%m_%Y",
    "%m-%d-%Y",
    "%m.%d.%Y",
    "%m/%d/%Y",
    "%m_%d_%Y",
    "%d-%b-%Y",
    "%d.%b.%Y",
    "%d/%b/%Y",
    "%b %d %Y",
    "%B %d %Y",
    "%d %b %Y",
    "%d %B %Y",
]


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def detect_company(filename: str) -> str | None:
    lower_name = filename.lower()

    matches: list[tuple[int, str]] = []
    for alias, canonical in COMPANY_ALIASES.items():
        pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pattern, lower_name):
            matches.append((len(alias), canonical))

    if not matches:
        return None

    # Prefer the longest alias so more specific names win.
    _, company = sorted(matches, key=lambda item: item[0], reverse=True)[0]
    return company


def extract_date_like_tokens(filename: str) -> list[str]:
    """Return candidate date substrings from a filename."""
    tokens: list[str] = []

    # Common date separators: -, _, ., /, spaces
    patterns = [
        r"\d{4}[-_/\.\s]\d{1,2}[-_/\.\s]\d{1,2}",
        r"\d{1,2}[-_/\.\s]\d{1,2}[-_/\.\s]\d{2,4}",
        r"\d{8}",
        r"\d{1,2}[\s.-/_]\w{3,9}[\s.-/_]\d{2,4}",
        r"\w{3,9}[\s.-/_]\d{1,2}[\s.-/_]\d{2,4}",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, filename, flags=re.IGNORECASE):
            token = match.group(0)
            if token not in tokens:
                tokens.append(token)

    return tokens


def detect_date(filename: str) -> datetime | None:
    for token in extract_date_like_tokens(filename):
        candidate = token.strip().replace("_", "-").replace("/", "-").replace(".", "-")
        # Normalize month names to a parse-friendly format without disturbing numeric dates.
        # Example: "15-Jan-2024" -> "15-Jan-2024"
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue

        # Some sequences like "2024-01-15" are already normalized by the previous loop.
        # Try a second pass with relaxed separators and month names using a wide set of variants.
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y"):
            for alt in (candidate, token):
                try:
                    return datetime.strptime(alt, fmt)
                except ValueError:
                    pass

    return None


def unique_destination(path: Path, preferred_name: str) -> Path:
    """Return a path that avoids overwriting existing files."""
    candidate = path / preferred_name
    if not candidate.exists():
        return candidate

    stem = path.name if not path.suffix else path.name.rsplit(".", 1)[0]
    suffix = path.suffix
    counter = 1
    while True:
        alt_name = f"{stem}_{counter}{suffix}"
        candidate = path / alt_name
        if not candidate.exists():
            return candidate
        counter += 1


def build_output_path(root_dir: Path, company: str | None, detected_date: datetime | None) -> tuple[Path, str]:
    """Return the target directory and destination filename."""
    processed_root = root_dir / "processed"

    if company and detected_date:
        target_dir = processed_root / str(detected_date.year) / f"{detected_date.month:02d}" / f"{detected_date.day:02d}"
        return target_dir, f"{company}"

    target_dir = processed_root / "random"
    return target_dir, ""


def copy_file(source: Path, root_dir: Path, log_file: Path) -> None:
    file_name = source.name
    company = detect_company(file_name)
    detected_date = detect_date(file_name)

    target_dir, dest_name = build_output_path(root_dir, company, detected_date)
    target_dir.mkdir(parents=True, exist_ok=True)

    if company and detected_date:
        ext = source.suffix
        final_name = f"{company}{ext}"
    else:
        final_name = file_name

    destination = target_dir / final_name
    if destination.exists():
        stem = destination.stem
        suffix = destination.suffix
        counter = 1
        while destination.exists():
            destination = target_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    shutil.copy2(source, destination)

    with log_file.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"{source} -> {destination}\n")


def iter_files(folder: Path):
    for child in sorted(folder.iterdir()):
        if child.is_file() and child.name != LOG_FILE_NAME:
            yield child


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy flat files into a processed directory tree.")
    parser.add_argument("folder", nargs="?", default="flat_dir", help="Flat directory to scan for files.")
    args = parser.parse_args()

    source_dir = Path(args.folder).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Directory not found: {source_dir}")

    log_file = source_dir / LOG_FILE_NAME
    log_file.write_text("", encoding="utf-8")

    for file_path in iter_files(source_dir):
        copy_file(file_path, source_dir, log_file)

    print(f"Processed files from {source_dir}")
    print(f"Copy log written to {log_file}")


if __name__ == "__main__":
    main()
