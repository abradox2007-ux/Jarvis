"""jarvis/handlers/custom_commands.py — Safe Dynamic Custom Commands Engine with Passkey Security."""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Destructive and dangerous patterns blocklist ─────────────────────────────
DANGEROUS_COMMAND_PATTERNS = [
    # Recursive/Forced Deletions
    r"\bdel\s+(?:/[a-z\?]\s+)*[/\\][sfq]",
    r"\bdel\s+.*[/\\][sfq]",
    r"\berase\s+.*[/\\][sfq]",
    r"\brmdir\s+.*[/\\][sq]",
    r"\brd\s+.*[/\\][sq]",
    r"\brm\s+-(?:r|f|rf|fr)\b",
    r"\bshred\b",
    # Disk & System Modifiers
    r"\bformat\b(?:\s+[a-z]:)?",
    r"\bdiskpart\b",
    r"\bbcdedit\b",
    r"\bvssadmin\b",
    r"\bfsutil\b",
    r"\bchkdsk\s+.*[/\\][frx]",
    # Registry & System File Tampering
    r"\breg\s+(?:delete|add|copy|restore|import)\b",
    r"\bregedit\b",
    r"c:\\windows\\system32",
    r"c:\\windows\\syswow64",
    r"c:\\program files",
    # Privilege Escalation / User Management
    r"\bnet\s+user\b",
    r"\bnet\s+localgroup\b",
    r"\btakeown\b",
    r"\bicacls\b.*(?:grant|deny|setowner)",
    # Dangerous Script/Execution Wrappers
    r"powershell.*-(?:enc|encodedcommand|executionpolicy\s+bypass)",
    r"\bshutdown\b\s+.*[/\\][srt]",
]


class SafetyGuard:
    """Scans and safely executes shell commands with multi-layered protections."""

    @staticmethod
    def is_safe_command(command_str: str) -> Tuple[bool, str]:
        """Check if command passes safety inspection.
        
        Returns (is_safe, reason).
        """
        if not command_str or not command_str.strip():
            return False, "Empty command."

        cmd_lower = command_str.strip().lower()

        # Check against blocklist regexes
        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                logger.warning("SafetyGuard: Blocked dangerous command matching pattern '%s': %s", pattern, command_str)
                return False, f"Command contains potentially harmful instructions (matched safety rule: {pattern})."

        # Check for attempts to touch root drive partitions or destructive wildcards
        if re.search(r"\b(?:del|rmdir|rd|erase|rm)\s+(?:[a-zA-Z]:\\|\*|\.\.)", cmd_lower):
            return False, "Command attempts destructive file operations on system drives."

        return True, "Safe"

    @staticmethod
    def execute_shell(command_str: str, cwd: Optional[str] = None, timeout: int = 8) -> Tuple[bool, str]:
        """Execute a validated shell command within a restricted subprocess with timeout."""
        is_safe, reason = SafetyGuard.is_safe_command(command_str)
        if not is_safe:
            return False, f"Safety alert: {reason}"

        try:
            # Default working directory to assistant root if not specified
            work_dir = cwd or os.getcwd()

            # Execute via subprocess with strict timeout
            logger.info("SafetyGuard: Executing command in %s: %s", work_dir, command_str)
            proc = subprocess.run(
                command_str,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()

            if proc.returncode == 0:
                if stdout:
                    first_line = stdout.splitlines()[0][:120]
                    return True, f"Command completed successfully: {first_line}"
                return True, "Command executed successfully."
            else:
                err_msg = stderr.splitlines()[0][:120] if stderr else f"Exit code {proc.returncode}"
                return False, f"Command failed: {err_msg}"

        except subprocess.TimeoutExpired:
            logger.error("SafetyGuard: Command timed out after %s seconds: %s", timeout, command_str)
            return False, f"Command timed out after {timeout} seconds."
        except Exception as exc:
            logger.error("SafetyGuard: Exception executing command '%s': %s", command_str, exc)
            return False, f"Error executing command: {exc}"


@dataclass
class CustomCommand:
    triggers: List[str]
    action_type: str  # 'url', 'app', 'folder', 'file', 'say', 'cmd'
    target: str
    is_secure: bool = False
    description: str = ""


class PasskeyAuthenticator:
    """Manages passkey verification and pending authorization states for voice dialogue."""

    def __init__(self, config_passkey: str = "1312", pending_timeout: float = 20.0) -> None:
        self.config_passkey = str(config_passkey).strip().lower()
        self.pending_timeout = pending_timeout
        self._pending_command: Optional[CustomCommand] = None
        self._pending_timestamp: float = 0.0

    def set_pending(self, cmd: CustomCommand) -> None:
        self._pending_command = cmd
        self._pending_timestamp = time.time()

    def clear_pending(self) -> None:
        self._pending_command = None
        self._pending_timestamp = 0.0

    def has_pending(self) -> bool:
        if self._pending_command is None:
            return False
        if time.time() - self._pending_timestamp > self.pending_timeout:
            self.clear_pending()
            return False
        return True

    def get_pending(self) -> Optional[CustomCommand]:
        if self.has_pending():
            return self._pending_command
        return None

    def verify_input(self, spoken_text: str) -> bool:
        """Check if spoken input contains or matches the configured passkey."""
        if not self.config_passkey:
            return True

        clean = spoken_text.strip().lower()
        # Remove punctuation
        clean_no_punct = re.sub(r"[^\w\s]", "", clean)
        passkey_no_punct = re.sub(r"[^\w\s]", "", self.config_passkey)

        # Check exact equality, words, or numbers
        if passkey_no_punct in clean_no_punct or self.config_passkey in clean:
            return True

        # Check spoken digits: e.g. "seven seven eight eight" -> "7788"
        digit_map = {
            "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
            "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"
        }
        spoken_digits = "".join(digit_map[word] for word in clean_no_punct.split() if word in digit_map)
        if spoken_digits and (spoken_digits == self.config_passkey or passkey_no_punct in spoken_digits):
            return True

        return False

    def extract_inline_passkey(self, text: str) -> Tuple[str, bool]:
        """Extract inline passkey if spoken in a single sentence (e.g. 'run backup passkey 7788').
        
        Returns (cleaned_text, is_authorized).
        """
        match = re.search(r"\b(?:passkey|pin|code|password|auth(?:orization)?)\s+([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
        if match:
            spoken_code = match.group(1).strip()
            is_valid = self.verify_input(spoken_code)
            # Remove the passkey part from text
            cleaned_text = re.sub(r"\b(?:passkey|pin|code|password|auth(?:orization)?)\s+[a-zA-Z0-9_\-]+", "", text, flags=re.IGNORECASE).strip()
            return cleaned_text, is_valid

        return text, False


class CustomCommandManager:
    """Loads, watches, and executes live custom commands from file."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.commands_file = config.get("custom_commands_file", "data/custom_commands.txt")
        self.enabled = config.get("custom_commands_enabled", True)
        self.allow_shell = config.get("allow_custom_shell_commands", False)
        self.require_passkey_shell = config.get("require_passkey_for_all_shell_cmds", True)
        self.shell_timeout = int(config.get("shell_command_timeout_seconds", 8))
        
        passkey = str(config.get("custom_command_passkey", "7788"))
        self.authenticator = PasskeyAuthenticator(config_passkey=passkey)

        self._commands: List[CustomCommand] = []
        self._last_mtime: float = 0.0

        self.reload_if_changed()

    def reload_if_changed(self) -> None:
        """Check file mtime and reload commands if modified."""
        if not os.path.exists(self.commands_file):
            return

        try:
            mtime = os.path.getmtime(self.commands_file)
            if mtime != self._last_mtime:
                self._load_commands()
                self._last_mtime = mtime
        except Exception as e:
            logger.error("Failed to check mtime for %s: %s", self.commands_file, e)

    def _load_commands(self) -> None:
        """Parse custom commands from .txt or .json file."""
        commands: List[CustomCommand] = []
        filepath = Path(self.commands_file)
        if not filepath.is_file():
            return

        try:
            content = filepath.read_text(encoding="utf-8")
            if filepath.suffix.lower() == ".json":
                data = json.loads(content)
                for item in data:
                    triggers = [t.strip().lower() for t in item.get("triggers", []) if t.strip()]
                    action_type = item.get("type", "").strip().lower()
                    target = item.get("target", "").strip()
                    is_secure = bool(item.get("secure", False))
                    if triggers and action_type and target:
                        commands.append(CustomCommand(triggers, action_type, target, is_secure))
            else:
                # Parse custom .txt format
                # Format: [secure] trigger1 | trigger2 => action_type: target
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    is_secure = False
                    if line.lower().startswith("[secure]"):
                        is_secure = True
                        line = line[8:].strip()

                    if "=>" in line:
                        parts = line.split("=>", 1)
                        raw_triggers = parts[0].strip()
                        raw_action = parts[1].strip()

                        if ":" in raw_action:
                            act_type, target = raw_action.split(":", 1)
                            act_type = act_type.strip().lower()
                            target = target.strip()
                        else:
                            act_type = "say"
                            target = raw_action

                        triggers = [t.strip().lower() for t in raw_triggers.split("|") if t.strip()]
                        if triggers and target:
                            commands.append(CustomCommand(triggers, act_type, target, is_secure))

            self._commands = commands
            logger.info("CustomCommandManager: Loaded %d live custom commands from %s", len(self._commands), self.commands_file)
        except Exception as e:
            logger.error("CustomCommandManager: Error reading %s: %s", self.commands_file, e)

    def find_matching_command(self, query: str) -> Optional[Tuple[CustomCommand, str]]:
        """Find a matching CustomCommand for the spoken query.
        
        Returns (command, matched_trigger) or None.
        """
        self.reload_if_changed()
        if not self.enabled:
            return None

        q = query.strip().lower()
        # Direct clean punctuation
        q_clean = re.sub(r"[^\w\s]", "", q).strip()

        # 1. Exact match
        for cmd in self._commands:
            for trigger in cmd.triggers:
                trig_clean = re.sub(r"[^\w\s]", "", trigger).strip()
                if q == trigger or q_clean == trig_clean:
                    return cmd, trigger

        # 2. Contained trigger match (e.g. "hey jarvis open github trending please")
        for cmd in self._commands:
            for trigger in cmd.triggers:
                trig_clean = re.sub(r"[^\w\s]", "", trigger).strip()
                # Ensure word-boundary matching
                pattern = r"\b" + re.escape(trig_clean) + r"\b"
                if re.search(pattern, q_clean):
                    return cmd, trigger

        return None

    def execute_command(self, cmd: CustomCommand) -> str:
        """Execute the action defined in the custom command."""
        act = cmd.action_type
        target = cmd.target

        logger.info("Executing custom command [%s]: %s", act, target)

        if act == "url":
            if not (target.startswith("http://") or target.startswith("https://")):
                target = "https://" + target
            webbrowser.open(target)
            return f"Opening {target} in your browser."

        elif act == "app":
            try:
                # Launch app via os.startfile on Windows or subprocess
                if hasattr(os, "startfile"):
                    os.startfile(target)
                else:
                    subprocess.Popen(shlex.split(target))
                return f"Launching {target}."
            except Exception as e:
                logger.error("Failed to launch app %s: %s", target, e)
                return f"Unable to launch application: {target}."

        elif act == "folder":
            try:
                folder_path = os.path.expandvars(os.path.expanduser(target))
                if os.path.exists(folder_path):
                    if hasattr(os, "startfile"):
                        os.startfile(folder_path)
                    else:
                        subprocess.Popen(["explorer", folder_path])
                    return f"Opening folder {os.path.basename(folder_path)}."
                else:
                    return f"Folder not found: {target}"
            except Exception as e:
                logger.error("Failed to open folder %s: %s", target, e)
                return f"Unable to open folder: {target}."

        elif act == "file":
            try:
                file_path = os.path.expandvars(os.path.expanduser(target))
                if os.path.exists(file_path):
                    if hasattr(os, "startfile"):
                        os.startfile(file_path)
                    else:
                        subprocess.Popen(["notepad", file_path])
                    return f"Opening file {os.path.basename(file_path)}."
                else:
                    return f"File not found: {target}"
            except Exception as e:
                logger.error("Failed to open file %s: %s", target, e)
                return f"Unable to open file: {target}."

        elif act == "say" or act == "text":
            return target

        elif act == "cmd" or act == "shell":
            if not self.allow_shell:
                return "Shell execution is disabled in config. Set 'allow_custom_shell_commands' to true to enable."

            ok, output_msg = SafetyGuard.execute_shell(target, timeout=self.shell_timeout)
            return output_msg

        return f"Unknown action type '{act}' for target '{target}'."
