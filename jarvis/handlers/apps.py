"""ac/handlers/apps.py — Launch desktop applications."""

from __future__ import annotations

import subprocess
from pathlib import Path


def open_app(name: str, app_aliases: dict[str, str], path: str | None = None) -> str:
    """
    Launch an application by alias name, optionally opening a file or folder path.
    Returns a spoken response string.
    """
    key = name.strip().lower()
    exe = app_aliases.get(key)

    if exe is None:
        for alias, target_exe in app_aliases.items():
            if key == alias or key in alias.split() or alias in key.split():
                exe = target_exe
                name = alias
                break

    if exe is None:
        return f"I don't know the app '{name}'. Add it to config.json."

    try:
        if path and str(path).strip():
            target_arg = str(path).strip().strip("'\"")
            resolved = Path(target_arg).expanduser()
            if not resolved.is_absolute():
                desktop = Path.home() / "Desktop" / target_arg
                if desktop.exists():
                    resolved = desktop
                else:
                    resolved = Path.cwd() / target_arg

            cmd_str = f'{exe} "{str(resolved)}"'
            subprocess.Popen(cmd_str, shell=True)
            return f"Opening {name} with '{Path(resolved).name}'."
        else:
            subprocess.Popen(exe, shell=True)
            return f"Opening {name}."
    except Exception as exc:
        return f"Failed to open {name}: {exc}"
