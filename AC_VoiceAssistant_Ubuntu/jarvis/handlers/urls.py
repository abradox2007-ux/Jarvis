"""ac/handlers/urls.py — Open URLs in the default browser."""

from __future__ import annotations

import webbrowser


def open_url(name: str, url_aliases: dict[str, str]) -> str:
    """
    Open a URL by alias name or raw URL.
    Returns a spoken response string.
    """
    key = name.strip().lower()
    url = url_aliases.get(key)

    if url is None:
        # Check word-boundary match
        for alias, link in url_aliases.items():
            if key == alias or key in alias.split() or alias in key.split():
                url = link
                name = alias
                break

    if url is None:
        # Treat as raw URL if it looks like one
        if "." in key and " " not in key:
            url = key if key.startswith("http") else f"https://{key}"
        else:
            return f"I don't know the website '{name}'. Add it to config.json."

    webbrowser.open(url)
    return f"Opening {name} in your browser."
