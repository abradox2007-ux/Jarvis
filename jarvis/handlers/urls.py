"""jarvis/handlers/urls.py — Open URLs, voice bookmarking, clipboard URL opener, and browser sync."""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import sys
import urllib.parse
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)


def get_clipboard_url() -> str | None:
    """Extract a valid URL from the system clipboard."""
    text = ""
    try:
        import pyperclip
        text = (pyperclip.paste() or "").strip()
    except Exception as exc:
        logger.debug("Could not read clipboard: %s", exc)

    if not text:
        return None

    # 1. Match full http/https URLs or www links
    url_match = re.search(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", text)
    if url_match:
        url = url_match.group(0).rstrip(".,;!?'\")>]")
        return f"https://{url}" if url.startswith("www.") else url

    # 2. Match standard domain paths like 'princecollege.org/login' or 'github.com/trending/python'
    domain_match = re.search(r"\b([a-zA-Z0-9\-]+\.(?:com|org|net|edu|gov|io|in|co|dev|ai|app|me|tech|info)(?:/[^\s<>\"']*)?)\b", text, re.IGNORECASE)
    if domain_match:
        return f"https://{domain_match.group(1).rstrip('.,;!?')}"

    # 3. Fallback: whole text is a naked domain like 'sub.domain.xyz/path'
    if re.match(r"^[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*\.[a-zA-Z]{2,}(?:/[^\s]*)?$", text):
        return f"https://{text.rstrip('.,;!?')}"

    return None


def open_copied_url() -> str:
    """Open whatever URL or web address is currently in the clipboard."""
    url = get_clipboard_url()
    if not url:
        return "No valid link or web address found in your clipboard."

    try:
        webbrowser.open(url)
        domain = urllib.parse.urlparse(url).netloc or url[:30]
        return f"Opening copied link for {domain} in your browser."
    except Exception as e:
        logger.error("Failed to open clipboard URL: %s", e)
        return f"Failed to open clipboard link: {e}"


def bookmark_url_from_clipboard(nickname: str, url_aliases: dict[str, str], config_path: str = "config.json") -> str:
    """Save the clipboard URL under a custom voice nickname for instant recall."""
    clean_name = nickname.strip().lower()
    clean_name = re.sub(r"^(?:as\s+|for\s+|called\s+|website\s+|link\s+)+", "", clean_name).strip().strip("'\"")
    if not clean_name:
        return "Please specify a shortcut name for this bookmark."

    url = get_clipboard_url()
    if not url:
        return "No valid web address found in your clipboard. Please copy the URL first."

    # Update in-memory alias dictionary
    url_aliases[clean_name] = url

    # Persist to config.json
    try:
        resolved_cfg = config_path
        if not os.path.exists(resolved_cfg):
            root_cfg = Path(__file__).resolve().parent.parent.parent / "config.json"
            if root_cfg.exists():
                resolved_cfg = str(root_cfg)

        if os.path.exists(resolved_cfg):
            with open(resolved_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "url_aliases" not in cfg or not isinstance(cfg["url_aliases"], dict):
                cfg["url_aliases"] = {}
            cfg["url_aliases"][clean_name] = url
            with open(resolved_cfg, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            logger.info("Saved URL alias '%s' -> '%s' to %s", clean_name, url, resolved_cfg)
    except Exception as exc:
        logger.warning("Could not persist bookmark to %s: %s", config_path, exc)

    return f"Bookmarked '{clean_name}'. You can now say 'Open {clean_name}'."


def list_bookmarks(url_aliases: dict[str, str]) -> str:
    """List available website voice shortcuts."""
    if not url_aliases:
        return "No website bookmarks saved yet. Copy a link and say 'Bookmark this as...'."
    names = list(url_aliases.keys())
    sample = names[:10]
    return f"You have {len(names)} bookmarked websites, including: {', '.join(sample)}."


def _crawl_bookmarks_node(node: dict, out_map: dict[str, str]) -> None:
    """Recursively extract name -> url pairs from Chrome/Edge bookmarks tree."""
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type == "url":
        name = (node.get("name") or "").strip().lower()
        url = (node.get("url") or "").strip()
        if name and url and url.startswith("http"):
            out_map[name] = url
    elif node_type == "folder" or "children" in node:
        for child in node.get("children", []):
            _crawl_bookmarks_node(child, out_map)


def get_browser_bookmarks() -> dict[str, str]:
    """Retrieve saved bookmarks from local Chrome and Edge browser profiles."""
    bookmarks_map: dict[str, str] = {}
    paths: list[str] = []

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            paths.extend([
                os.path.join(local_app_data, r"Google\Chrome\User Data\Default\Bookmarks"),
                os.path.join(local_app_data, r"Microsoft\Edge\User Data\Default\Bookmarks"),
                os.path.join(local_app_data, r"BraveSoftware\Brave-Browser\User Data\Default\Bookmarks")
            ])
    else:
        home = os.path.expanduser("~")
        paths.extend([
            os.path.join(home, ".config/google-chrome/Default/Bookmarks"),
            os.path.join(home, ".config/chromium/Default/Bookmarks"),
            os.path.join(home, ".config/microsoft-edge/Default/Bookmarks"),
        ])

    for p in paths:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                roots = data.get("roots", {})
                for root_node in roots.values():
                    _crawl_bookmarks_node(root_node, bookmarks_map)
            except Exception as e:
                logger.debug("Failed reading browser bookmarks from %s: %s", p, e)

    return bookmarks_map


def open_url(name: str, url_aliases: dict[str, str]) -> str:
    """
    Open a URL by alias name, browser bookmark title, raw URL, or smart Google search fallback.
    Returns a spoken response string.
    """
    key = name.strip().lower()

    # 1. Direct alias match
    url = url_aliases.get(key)
    resolved_name = name

    # 2. Word-boundary or token subset match
    if url is None:
        for alias, link in url_aliases.items():
            if key == alias or key in alias.split() or alias in key.split():
                url = link
                resolved_name = alias
                break

    # 3. Substring match
    if url is None:
        for alias, link in url_aliases.items():
            if key in alias or (len(alias) >= 4 and alias in key):
                url = link
                resolved_name = alias
                break

    # 4. Fuzzy close matches for slight mispronunciations (e.g. "rowan" -> "rovan")
    if url is None:
        close_matches = difflib.get_close_matches(key, url_aliases.keys(), n=1, cutoff=0.72)
        if close_matches:
            matched_alias = close_matches[0]
            url = url_aliases[matched_alias]
            resolved_name = matched_alias

    # 5. Browser Bookmarks search (Chrome / Edge)
    if url is None:
        browser_bms = get_browser_bookmarks()
        if key in browser_bms:
            url = browser_bms[key]
            resolved_name = key
        else:
            bm_matches = difflib.get_close_matches(key, browser_bms.keys(), n=1, cutoff=0.75)
            if bm_matches:
                matched_bm = bm_matches[0]
                url = browser_bms[matched_bm]
                resolved_name = matched_bm

    # 6. Raw URL detection
    if url is None:
        if "." in key and " " not in key:
            url = key if key.startswith("http") else f"https://{key}"
            resolved_name = key

    # 7. Smart Direct Search Fallback (Opens top search for unrecognized websites)
    if url is None:
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(name)}"
        try:
            webbrowser.open(search_url)
            return f"I couldn't find a saved bookmark for '{name}', so I searched for it on Google."
        except Exception as e:
            return f"Failed to search for '{name}': {e}"

    try:
        webbrowser.open(url)
        return f"Opening {resolved_name} in your browser."
    except Exception as e:
        logger.error("Failed to open URL %s: %s", url, e)
        return f"Failed to open {resolved_name}: {e}"
