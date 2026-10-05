"""jarvis/utils.py — Shared utilities: config, logging, cross-platform file helpers."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
LOG_DIR = Path(__file__).parent.parent / "logs"


def load_config() -> dict:
    """Load config.json and expand ~ in search_paths."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["search_paths"] = [
        str(Path(p).expanduser()) for p in cfg.get("search_paths", [])
    ]
    return cfg


def setup_logging() -> logging.Logger:
    """Set up file + console logging and return the root logger."""
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / "jarvis.log"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("jarvis")


def sanitize_filename(name: str) -> str:
    """Remove illegal filename characters and strip whitespace and trailing dots."""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.rstrip(". ")
    return name


def open_file_crossplatform(path: str | Path) -> bool:
    """Open a file or directory using the OS default application."""
    path_str = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path_str)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path_str])
        else:
            subprocess.Popen(["xdg-open", path_str])
        return True
    except Exception as e:
        logger.warning("Failed to open path %s: %s", path_str, e)
        return False


def find_best_file_match(
    query: str, search_paths: list[Path | str]
) -> tuple[Optional[Path], list[Path]]:
    """
    Search *search_paths* for files whose stem or full name matches *query* (case-insensitive).
    Returns (best_match, all_matches). best_match is None if nothing found.
    """
    query_clean = query.strip()
    query_lower = query_clean.lower()
    query_stem_lower = Path(query_clean).stem.lower()
    all_matches: list[Path] = []

    for root in search_paths:
        root_path = Path(root)
        if not root_path.exists():
            continue

        # Direct file checks for rapid exact lookups
        direct = root_path / query_clean
        if direct.is_file() and direct not in all_matches:
            all_matches.append(direct)
        direct_txt = root_path / f"{query_clean}.txt"
        if direct_txt.is_file() and direct_txt not in all_matches:
            all_matches.append(direct_txt)

        try:
            for current_root, dirs, files in os.walk(str(root_path)):
                rel_depth = len(Path(current_root).relative_to(root_path).parts)
                if rel_depth >= 3:
                    dirs.clear()
                for fname in files:
                    fpath = Path(current_root) / fname
                    fname_lower = fname.lower()
                    fstem_lower = fpath.stem.lower()
                    if (
                        query_lower == fname_lower
                        or query_lower == fstem_lower
                        or query_stem_lower == fstem_lower
                        or query_lower in fname_lower
                        or query_lower in fstem_lower
                        or query_stem_lower in fstem_lower
                    ):
                        if fpath not in all_matches:
                            all_matches.append(fpath)
        except Exception:
            continue

    if not all_matches:
        return None, []

    # Priority 1: Exact full name match
    for p in all_matches:
        if p.name.lower() == query_lower:
            return p, all_matches

    # Priority 2: Exact stem match
    for p in all_matches:
        if p.stem.lower() == query_lower or p.stem.lower() == query_stem_lower:
            return p, all_matches

    return all_matches[0], all_matches
