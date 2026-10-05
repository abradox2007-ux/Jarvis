"""jarvis/handlers/files.py — Open existing files and create new text files."""

from __future__ import annotations

import os
from pathlib import Path

from jarvis.utils import find_best_file_match, sanitize_filename

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def open_file(query: str, search_paths: list[str]) -> str:
    """Find and open the best-matching file. Returns spoken response."""
    paths = [Path(p) for p in search_paths]
    best, matches = find_best_file_match(query, paths)

    if best is None:
        return f"No file matching '{query}' found in your search paths."

    from jarvis.utils import open_file_crossplatform
    if open_file_crossplatform(best):
        return f"Opening {best.name}."
    else:
        return f"Found {best.name} but couldn't open it."


def create_file(name: str) -> str:
    """Create a new .txt file in the data/ directory. Returns spoken response."""
    safe_name = sanitize_filename(name)
    if not safe_name:
        return "That filename isn't valid. Please try a different name."

    DATA_DIR.mkdir(exist_ok=True)
    file_path = DATA_DIR / f"{safe_name}.txt"

    if file_path.exists():
        return f"'{safe_name}.txt' already exists in your data folder."

    file_path.write_text("", encoding="utf-8")
    return f"Created '{safe_name}.txt' in your data folder."


def write_to_file(name: str, text: str, search_paths: list[str] | None = None) -> str:
    """
    Write or append text content to an existing or new text file.
    Returns spoken response.
    """
    safe_name = sanitize_filename(name)
    if not safe_name:
        return "That filename isn't valid. Please specify a file name."

    if not text or not text.strip():
        return f"What would you like me to write in {safe_name}?"

    content = text.strip()

    # 1. Search for existing file in search paths and data directory
    paths = [Path(p) for p in search_paths] if search_paths else []
    if DATA_DIR not in paths:
        paths.append(DATA_DIR)

    best, _ = find_best_file_match(safe_name, paths)

    if best is not None and best.is_file():
        target_path = best
    else:
        DATA_DIR.mkdir(exist_ok=True)
        target_path = DATA_DIR / f"{safe_name}.txt"

    try:
        if target_path.exists() and target_path.stat().st_size > 0:
            existing = target_path.read_text(encoding="utf-8")
            if not existing.endswith("\n"):
                existing += "\n"
            target_path.write_text(existing + content + "\n", encoding="utf-8")
        else:
            target_path.write_text(content + "\n", encoding="utf-8")

        return f"Added to {target_path.stem}: '{content}'."
    except Exception as exc:
        return f"Could not write to {target_path.name}: {exc}"


def rename_file(old_name: str, new_name: str, search_paths: list[str] | None = None) -> str:
    """
    Rename an existing file in data/ or search_paths.
    Returns spoken response.
    """
    old_clean = sanitize_filename(old_name)
    new_clean = sanitize_filename(new_name)

    if not old_clean or not new_clean:
        return "Please specify both the current file name and the new file name."

    paths = [Path(p) for p in search_paths] if search_paths else []
    if DATA_DIR not in paths:
        paths.append(DATA_DIR)

    best, _ = find_best_file_match(old_clean, paths)
    if best is None or not best.is_file():
        return f"Could not find the file '{old_clean}' to rename."

    # Preserve original extension if not supplied in new_clean
    target_ext = best.suffix if not Path(new_clean).suffix else ""
    new_file_name = f"{new_clean}{target_ext}"
    dest_path = best.parent / new_file_name

    if dest_path.exists() and dest_path != best:
        return f"A file named '{new_file_name}' already exists."

    try:
        best.rename(dest_path)
        return f"Renamed '{best.name}' to '{new_file_name}'."
    except Exception as exc:
        return f"Failed to rename '{best.name}': {exc}"


def copy_file(source_name: str, dest_name: str, search_paths: list[str] | None = None) -> str:
    """
    Copy an existing file to a new destination name in data/.
    Returns spoken response.
    """
    import shutil

    src_clean = sanitize_filename(source_name)
    dst_clean = sanitize_filename(dest_name)

    if not src_clean or not dst_clean:
        return "Please specify both the source file and destination file name."

    paths = [Path(p) for p in search_paths] if search_paths else []
    if DATA_DIR not in paths:
        paths.append(DATA_DIR)

    best, _ = find_best_file_match(src_clean, paths)
    if best is None or not best.is_file():
        return f"Could not find source file '{src_clean}' to copy."

    target_ext = best.suffix if not Path(dst_clean).suffix else ""
    new_file_name = f"{dst_clean}{target_ext}"
    dest_path = DATA_DIR / new_file_name

    try:
        DATA_DIR.mkdir(exist_ok=True)
        shutil.copy2(best, dest_path)
        return f"Copied '{best.name}' to '{new_file_name}'."
    except Exception as exc:
        return f"Failed to copy '{best.name}': {exc}"


def move_file(source_name: str, dest_name: str, search_paths: list[str] | None = None) -> str:
    """
    Cut / Move an existing file to a new destination name or location.
    Returns spoken response.
    """
    import shutil

    src_clean = sanitize_filename(source_name)
    dst_clean = sanitize_filename(dest_name)

    if not src_clean or not dst_clean:
        return "Please specify both the source file and destination file name."

    paths = [Path(p) for p in search_paths] if search_paths else []
    if DATA_DIR not in paths:
        paths.append(DATA_DIR)

    best, _ = find_best_file_match(src_clean, paths)
    if best is None or not best.is_file():
        return f"Could not find file '{src_clean}' to move."

    target_ext = best.suffix if not Path(dst_clean).suffix else ""
    new_file_name = f"{dst_clean}{target_ext}"
    dest_path = DATA_DIR / new_file_name

    try:
        DATA_DIR.mkdir(exist_ok=True)
        shutil.move(str(best), str(dest_path))
        return f"Moved '{best.name}' to '{new_file_name}'."
    except Exception as exc:
        return f"Failed to move '{best.name}': {exc}"


def list_data_files() -> list[dict]:
    """Return a list of all files in the data/ directory."""
    import time
    DATA_DIR.mkdir(exist_ok=True)
    results = []
    for p in DATA_DIR.iterdir():
        if p.is_file() and not p.name.startswith("."):
            try:
                stat = p.stat()
                preview = ""
                if p.suffix in (".txt", ".md", ".json", ".log", ""):
                    try:
                        preview = p.read_text(encoding="utf-8", errors="ignore")[:200]
                    except Exception:
                        pass
                results.append({
                    "name": p.name,
                    "stem": p.stem,
                    "size": stat.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    "preview": preview,
                })
            except Exception:
                pass
    return sorted(results, key=lambda x: x["name"].lower())


def read_file_content(name: str) -> str:
    """Read the full text content of a file in data/ or search paths."""
    safe = sanitize_filename(name)
    if not safe:
        return ""

    direct = DATA_DIR / safe
    if direct.is_file():
        try:
            return direct.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"Error reading file: {e}"

    direct_txt = DATA_DIR / f"{safe}.txt"
    if direct_txt.is_file():
        try:
            return direct_txt.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"Error reading file: {e}"

    best, _ = find_best_file_match(safe, [DATA_DIR])
    if best and best.is_file():
        try:
            return best.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"Error reading file: {e}"
    return ""


def save_file_content(name: str, content: str) -> bool:
    """Save/overwrite full text content of a file in data/."""
    safe = sanitize_filename(name)
    if not safe:
        return False

    target_path = DATA_DIR / safe if Path(safe).suffix else DATA_DIR / f"{safe}.txt"
    try:
        DATA_DIR.mkdir(exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False
