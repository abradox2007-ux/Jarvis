"""jarvis/router.py — Route a recognised command string to the right handler."""

from __future__ import annotations

import logging
import os
import re

from jarvis.handlers import apps, diary, files, info, urls, ai, system, timer
from jarvis.handlers.custom_commands import CustomCommandManager
from jarvis.plugin_manager import PluginManager

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Here are some things you can say: "
    "Open Google, Open YouTube, Open Notepad, "
    "Open notes, Create file todos, "
    "Diary I had a great day, Read diary, "
    "What time is it, What's the date, What's the weather."
)

DISMISSAL_PHRASES = {
    "stop", "bye", "goodbye", "good bye", "go to sleep", "sleep", "sleep now",
    "that's all", "thats all", "that is all", "thank you", "thanks", "thank you jarvis",
    "nevermind", "never mind", "exit", "cancel", "standby", "stand by", "close", "mute",
    "stop listening", "stop now", "please stop", "jarvis stop", "stop jarvis", "ok stop",
    "okay stop", "jarvis go to sleep", "jarvis sleep", "jarvis standby", "jarvis mute",
    "நன்றி", "போதும்", "முடிந்தது", "நிறுத்து"
}


def is_dismissal(command: str) -> bool:
    """Return True if command is a follow-up dismissal / go-to-sleep instruction."""
    if not command:
        return False
    cmd = command.strip().lower().rstrip(".!?,")
    if cmd in DISMISSAL_PHRASES:
        return True
    prefixes = (
        "stop", "bye", "goodbye", "good bye", "thank you", "thanks",
        "go to sleep", "sleep now", "never mind", "nevermind",
        "that's all", "thats all", "that is all", "standby", "stand by"
    )
    if any(cmd.startswith(prefix) for prefix in prefixes):
        return True
    if any(cmd.endswith(suffix) for suffix in ("stop", "go to sleep", "standby", "stand by", "sleep", "mute")):
        return True
    return False


def translate_tamil_to_english(cmd: str) -> str:
    """Translate common Tamil command patterns to English equivalents."""
    # Check if the command has any Tamil Unicode characters (range U+0B80 to U+0BFF)
    if not any('\u0b80' <= char <= '\u0bff' for char in cmd):
        return cmd

    t = cmd.strip().lower()

    # Transliteration of common application/website names and search queries
    tamil_to_eng_nouns = {
        "கூகுள்": "google",
        "யூடியூப்": "youtube",
        "யூடியுப்": "youtube",
        "ஃபேஸ்புக்": "facebook",
        "இன்ஸ்டாகிராம்": "instagram",
        "சாட்ஜிபிடி": "chatgpt",
        "விக்கிபீடியா": "wikipedia",
        "யாகூ": "yahoo",
        "அமேசான்": "amazon",
        "வாட்ஸ்அப்": "whatsapp",
        "வாட்ஸ் அப்": "whatsapp",
        "நெட்பிளிக்ஸ்": "netflix",
        "ட்விட்டர்": "twitter",
        "லிங்க்டின்": "linkedin",
        "கிட்ஹப்": "github",
        "நோட்பேட்": "notepad",
        "கால்குலேட்டர்": "calculator",
        "பெயிண்ட்": "paint",
        "ரோவன்": "rovan",
    }

    for tam, eng in tamil_to_eng_nouns.items():
        t = t.replace(tam, eng)

    # 1. Help / Info commands
    if any(w in t for w in ("உதவி", "வழிகாட்டி", "கட்டளைகள்", "வழிமுறை")):
        return "help"

    # 2. Time / Date / Weather
    if any(w in t for w in ("நேரம்", "மணி என்ன", "மணி என்னா", "நேரம் என்ன")):
        return "time"
    if any(w in t for w in ("தேதி", "நாள் என்ன", "தேதி என்ன")):
        return "date"
    if any(w in t for w in ("வானிலை", "மழை", "வெயில்")):
        return "weather"

    # 3. Diary manual
    if any(w in t for w in ("டைரி மேனுவல்", "மேனுவல் டைரி")):
        return "diary manual"

    # 4. Read/Open Diary
    if any(w in t for w in ("டைரி படி", "டைரியை படி", "டைரி காட்டு", "டைரியை காட்டு", "டைரி திற", "டைரியை திற")):
        return "read diary"

    # 5. Write to Diary
    diary_write_match = re.match(r"^(டைரி|நாட்குறிப்பு)\s*(.*)$", t)
    if diary_write_match:
        content = diary_write_match.group(2).strip()
        return f"diary {content}"

    # 5.5 Write / Take notes in a file (Tamil)
    write_file_match = re.match(r"^(.*)\s+(இல்|க்கு)\s+(எழுது|குறிப்பு எடு)\s*(.*)$", t)
    if write_file_match:
        filename = write_file_match.group(1).strip()
        content = write_file_match.group(4).strip()
        return f"write in {filename} {content}".strip()

    # 5.6 Rename file (Tamil)
    rename_match = re.match(r"^(.*)\s+(ஃபைலை|கோப்பை)\s+(.*)\s+(என்று|ஆக)\s+(பெயர் மாற்று|மாற்று)$", t)
    if rename_match:
        old_f = rename_match.group(1).strip()
        new_f = rename_match.group(3).strip()
        return f"rename file {old_f} to {new_f}"

    # 5.7 Copy file (Tamil)
    copy_match = re.match(r"^(.*)\s+(ஃபைலை|கோப்பை)\s+(.*)\s+(க்கு|ஆக)\s+(நகலெடு|காப்பி செய்)$", t)
    if copy_match:
        src_f = copy_match.group(1).strip()
        dst_f = copy_match.group(3).strip()
        return f"copy file {src_f} to {dst_f}"

    # 5.8 Move / Cut file (Tamil)
    move_match = re.match(r"^(.*)\s+(ஃபைலை|கோப்பை)\s+(.*)\s+(க்கு|ஆக)\s+(நகர்த்து|கட் செய்)$", t)
    if move_match:
        src_f = move_match.group(1).strip()
        dst_f = move_match.group(3).strip()
        return f"move file {src_f} to {dst_f}"

    # 6. Create file
    create_match = re.match(r"^(.*)\s+(கோப்பு உருவாக்கு|ஃபைல் உருவாக்கு|உருவாக்கு)$", t)
    if create_match:
        filename = create_match.group(1).strip()
        return f"create file {filename}"
    if t.startswith("ஃபைல் உருவாக்கு") or t.startswith("கோப்பை உருவாக்கு"):
        filename = t.replace("ஃபைல் உருவாக்கு", "").replace("கோப்பை உருவாக்கு", "").strip()
        return f"create file {filename}"

    # 7. Open target
    open_match = re.match(r"^(.*)\s+(திற|திறக்கவும்)$", t)
    if open_match:
        target = open_match.group(1).strip()
        return f"open {target}"
    if t.startswith("ஓபன்"):
        target = t.replace("ஓபன்", "").strip()
        return f"open {target}"

    # 8. Play song
    play_match = re.match(r"^(.*)\s+(ப்ளே பண்ணு|போடு|ஒலிபரப்பு|ப்ளே செய்|ப்ளே)$", t)
    if play_match:
        song = play_match.group(1).strip()
        song = song.replace("பாடல்", "").strip()
        return f"play {song}"
    if t.startswith("ப்ளே"):
        song = t.replace("ப்ளே", "").strip()
        song = song.replace("பாடல்", "").strip()
        return f"play {song}"

    # 9. Search query
    search_match = re.match(r"^(.*)\s+(தேடு|தேடவும்|சர்ச் பண்ணு|தேடி காட்டு)$", t)
    if search_match:
        query = search_match.group(1).strip()
        if query.endswith("பற்றி"):
            query = query[:-5].strip()
        return f"search {query}"
    if t.startswith("சர்ச்") or t.startswith("தேடு"):
        query = t.replace("சர்ச்", "").replace("தேடு", "").strip()
        return f"search {query}"

    return t


def split_dot_commands(text: str) -> list[str]:
    """
    Split command text by verbal 'dot', 'period', 'full stop', 'புள்ளி', or punctuation '.'
    Returns a list of clean, non-empty command strings executed in sequence.
    """
    if not text:
        return []

    # If it's an explicit diary entry like "diary. some notes", preserve it
    if re.match(r"^diary\s*[.:,]\s*", text, re.I):
        cleaned = re.sub(r"\s+\b(dot|full\s*stop|period|புள்ளி)\b\.?$", "", text, flags=re.IGNORECASE).rstrip(". ")
        return [cleaned] if cleaned else [text.strip()]

    # Preserve URLs (like google.com) and decimal numbers (like 3.14) while splitting commands on dot / period / verbal dot
    # Replace explicit verbal dots with a distinct separator token
    s = re.sub(r"\b(dot|full\s*stop|period|புள்ளி)\b", " <CMD_SEP> ", text, flags=re.IGNORECASE)

    # Also treat sentence-ending periods (period followed by whitespace or end of string) as separator,
    # except when directly between digits (3.14) or letters without space (google.com)
    s = re.sub(r"(?<!\d)\.(?:\s+|$)", " <CMD_SEP> ", s)

    parts = s.split("<CMD_SEP>")
    commands = []
    for p in parts:
        cleaned = p.strip().strip(",:;!?- ")
        if cleaned:
            commands.append(cleaned)

    return commands if commands else [text.strip()]


class CommandRouter:
    def __init__(self, config: dict) -> None:
        self._config = config
        self._url_aliases: dict[str, str] = config.get("url_aliases", {})
        self._app_aliases: dict[str, str] = config.get("app_aliases", {})
        self._search_paths: list[str] = config.get("search_paths", [])
        self._weather_city: str = config.get("weather_city", "Chennai")
        self._weather_country: str = config.get("weather_country", "IN")
        self._custom_mgr = CustomCommandManager(config)
        self._plugin_mgr = PluginManager(config.get("plugins_dir", "./plugins"))

    def route(self, command: str) -> str:
        """Dispatch *command* to the appropriate handler and return a response."""
        if not command or not command.strip():
            return "What can I help you with?"

        sub_commands = split_dot_commands(command)
        if len(sub_commands) > 1:
            responses = []
            for sub_cmd in sub_commands:
                res = self._route_single(sub_cmd)
                if res:
                    responses.append(res)
            return " ".join(responses) if responses else "Done."
        elif len(sub_commands) == 1:
            return self._route_single(sub_commands[0])
        else:
            return self._route_single(command)

    def _route_single(self, command: str) -> str:
        """Dispatch a single atomic command to the appropriate handler."""
        # ── Check Pending Passkey Authorization ──────────────────────────────
        if self._custom_mgr.authenticator.has_pending():
            pending_cmd = self._custom_mgr.authenticator.get_pending()
            if self._custom_mgr.authenticator.verify_input(command):
                self._custom_mgr.authenticator.clear_pending()
                if pending_cmd:
                    return self._custom_mgr.execute_command(pending_cmd)
                return "Authorization granted."
            else:
                self._custom_mgr.authenticator.clear_pending()
                return "Passkey authorization failed. Command cancelled."

        translated_command = translate_tamil_to_english(command)
        cmd = translated_command.strip().lower()
        cmd = cmd.replace("dairy", "diary")
        logger.debug("Routing single command: %s (original: %s)", cmd, command)

        # ── Safety: no delete ────────────────────────────────────────────────
        if any(w in cmd for w in ("delete", "remove", "erase", "unlink")):
            return "Delete commands are not supported for safety reasons."

        # ── Follow-up Dismissal / Standby ────────────────────────────────────
        if is_dismissal(cmd):
            if any(w in cmd for w in ("thank", "thanks", "நன்றி")):
                return "You're very welcome. Standing by."
            return "Going on standby. Say Hey Jarvis when you need me."

        # ── Live Custom Commands ─────────────────────────────────────────────
        matched_custom = self._custom_mgr.find_matching_command(command) or self._custom_mgr.find_matching_command(translated_command)
        if matched_custom:
            custom_cmd, _ = matched_custom
            needs_auth = custom_cmd.is_secure or (
                custom_cmd.action_type in ("cmd", "shell") and self._custom_mgr.require_passkey_shell
            )
            if needs_auth:
                _, is_auth = self._custom_mgr.authenticator.extract_inline_passkey(command)
                if is_auth:
                    return self._custom_mgr.execute_command(custom_cmd)
                else:
                    self._custom_mgr.authenticator.set_pending(custom_cmd)
                    return "Passkey required. Please state your authorization code."
            else:
                return self._custom_mgr.execute_command(custom_cmd)

        # ── Dynamic Plugins Engine ───────────────────────────────────────────
        plugin_res = self._plugin_mgr.dispatch(command, self._config) or self._plugin_mgr.dispatch(translated_command, self._config)
        if plugin_res is not None:
            return plugin_res

        # ── Long-Term Memory (RAG) ───────────────────────────────────────────
        if cmd.startswith("remember that ") or cmd.startswith("remember "):
            fact = translated_command
            for prefix in ("remember that ", "remember "):
                if cmd.startswith(prefix):
                    fact = translated_command[len(prefix):].strip()
                    break
            from jarvis.memory import get_memory_store
            return get_memory_store().store_memory(fact, category="user_preference")

        if cmd.startswith("forget that ") or cmd.startswith("forget "):
            q = translated_command
            for prefix in ("forget that ", "forget "):
                if cmd.startswith(prefix):
                    q = translated_command[len(prefix):].strip()
                    break
            from jarvis.memory import get_memory_store
            return get_memory_store().forget_by_query(q)

        if cmd in ("what do you remember", "list memories", "show memories", "read memories"):
            from jarvis.memory import get_memory_store
            mems = get_memory_store().list_memories()
            if not mems:
                return "I don't have any memories stored yet."
            items = [m["content"] for m in mems[:5]]
            return f"Here is what I remember: {'; '.join(items)}."

        # ── System Controls (Volume, Media, Workstation) ─────────────────────
        if cmd in ("mute volume", "unmute volume", "toggle mute"):
            return system.mute_volume()
        if any(cmd == p or cmd.startswith(p + " ") for p in ("volume up", "increase volume", "louder", "turn it up")):
            return system.volume_up()
        if any(cmd == p or cmd.startswith(p + " ") for p in ("volume down", "decrease volume", "lower volume", "quieter", "turn it down")):
            return system.volume_down()
        vol_match = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)(?:\s*%)?", cmd)
        if vol_match:
            return system.set_volume_percent(int(vol_match.group(1)))

        if cmd in ("pause", "resume", "pause music", "resume music", "play pause", "media play", "media pause"):
            return system.media_play_pause()
        if cmd in ("next track", "next song", "skip track", "skip song"):
            return system.media_next()
        if cmd in ("previous track", "previous song", "prev track", "prev song"):
            return system.media_previous()
        if cmd in ("stop music", "media stop"):
            return system.media_stop()

        if cmd in ("lock workstation", "lock screen", "lock computer", "lock pc", "lock windows"):
            return system.lock_workstation()
        if cmd in ("screenshot", "take screenshot", "capture screen", "take a screenshot"):
            return system.take_screenshot()
        if cmd in ("battery", "battery status", "battery level", "check battery", "power status"):
            return system.get_battery_status()

        # ── Timers & Reminders ───────────────────────────────────────────────
        if any(cmd.startswith(p) for p in ("timer", "set timer", "set a timer", "remind me", "countdown")):
            parsed = timer.parse_time_duration(command) or timer.parse_time_duration(translated_command)
            if parsed:
                secs, label = parsed
                return timer.create_timer(secs, label)
        if cmd in ("list timers", "show timers", "active timers", "check timers"):
            return timer.list_timers()
        if cmd in ("cancel timer", "stop timer", "cancel all timers", "clear timers"):
            return timer.cancel_all_timers()

        # ── Add / Teach Custom Command by Voice ──────────────────────────────
        add_cmd_match = re.match(
            r"^(?:add|create|new|teach|save)\s+(?:custom\s+)?command\s+(?:when\s+i\s+say\s+|trigger\s+)?['\"]?(.+?)['\"]?\s+(?:to\s+|=>\s*)?(say|tell|open url|open website|open app|open folder|open file|open|launch|run|cmd|say:)\s+['\"]?(.+?)['\"]?$",
            translated_command,
            re.IGNORECASE
        )
        if add_cmd_match:
            trigger_phrase = add_cmd_match.group(1).strip()
            act_verb = add_cmd_match.group(2).strip().lower().rstrip(":")
            act_target = add_cmd_match.group(3).strip()

            if act_verb in ("say", "tell"):
                atype = "say"
            elif act_verb in ("open url", "open website"):
                atype = "url"
            elif act_verb in ("open app", "launch"):
                atype = "app"
            elif act_verb in ("open folder",):
                atype = "folder"
            elif act_verb in ("open file",):
                atype = "file"
            elif act_verb in ("run", "cmd"):
                atype = "cmd"
            elif act_verb == "open":
                if act_target.startswith("http://") or act_target.startswith("https://") or act_target.startswith("www."):
                    atype = "url"
                elif "." in act_target and ("/" in act_target or "\\" in act_target):
                    atype = "file"
                else:
                    atype = "app"
            else:
                atype = "say"

            return self._custom_mgr.add_custom_command(trigger_phrase, atype, act_target)

        # ── Help ─────────────────────────────────────────────────────────────
        if cmd in ("help", "what can you do", "commands"):
            return HELP_TEXT

        # ── View/Read/Watch Diary ────────────────────────────────────────────
        if any(p in cmd for p in (
            "read diary", "show diary", "view diary", "open diary", "watch diary",
            "read the diary", "show the diary", "view the diary", "open the diary", "watch the diary",
            "watch the content of the diary", "show the content of the diary", "read the content of the diary"
        )):
            return diary.open_diary()

        # ── Diary Manual Panel ───────────────────────────────────────────────
        if cmd in ("diary manual", "manual diary"):
            from server import set_status
            set_status("diary_manual", "Opening manual diary panel...")
            return "Opening manual diary panel."

        # ── Diary (must come before "open" check) ────────────────────────────
        diary_match = re.match(r"^diary\b\s*[,.:|-]?\s*(.*)$", cmd)
        if diary_match:
            entry_text = re.sub(r"^diary\b\s*[,.:|-]?\s*", "", translated_command, flags=re.IGNORECASE).strip()
            return diary.append_diary_entry(entry_text)

        # ── Weather ──────────────────────────────────────────────────────────
        if "weather" in cmd:
            return info.tell_weather(self._weather_city, self._weather_country)

        # ── Time ─────────────────────────────────────────────────────────────
        if any(p in cmd for p in ("time", "clock")):
            return info.tell_time()

        # ── Date ─────────────────────────────────────────────────────────────
        if any(p in cmd for p in ("date", "today")):
            return info.tell_date()

        # ── Create file ──────────────────────────────────────────────────────
        if cmd.startswith("create file "):
            name = translated_command[len("create file "):].strip()
            return files.create_file(name)

        # ── Write / Add / Take notes to specific file ────────────────────────
        # 1. "take notes for/in/to <filename> <content>" / "takes notes for <filename> <content>"
        match_take_notes = re.match(
            r"^(?:take|takes)\s+notes?\s+(?:for|in|on|to)\s+([a-zA-Z0-9_\- .]+?)(?:\s+(?:that|saying|:|content|is)\s+|\s*:\s*|\s+)(.+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_take_notes:
            fname = match_take_notes.group(1).strip()
            content = match_take_notes.group(2).strip()
            return files.write_to_file(fname, content, self._search_paths)

        # 2. "add (this)? to/in <filename> <content>" / "copy (this)? to <filename> <content>" / "have (this)? to <filename> <content>" / "save to <filename> <content>"
        match_add_to = re.match(
            r"^(?:add|copy|have|save|append)\s+(?:this\s+)?(?:to|in|into)\s+([a-zA-Z0-9_\- .]+?)(?:\s+(?:that|saying|:|content|is)\s+|\s*:\s*|\s+)(.+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_add_to:
            fname = match_add_to.group(1).strip()
            content = match_add_to.group(2).strip()
            return files.write_to_file(fname, content, self._search_paths)

        # 3. "write (to/in/into) <filename> <content>"
        match_write_to = re.match(
            r"^write\s+(?:to|in|into)\s+([a-zA-Z0-9_\- .]+?)(?:\s+(?:that|saying|:|content|is)\s+|\s*:\s*|\s+)(.+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_write_to:
            fname = match_write_to.group(1).strip()
            content = match_write_to.group(2).strip()
            return files.write_to_file(fname, content, self._search_paths)

        # 4. "note down (in/to/for) <filename> <content>" / "record in <filename> <content>"
        match_note_down = re.match(
            r"^(?:note\s+down|record)\s+(?:in|to|for|into)\s+([a-zA-Z0-9_\- .]+?)(?:\s+(?:that|saying|:|content|is)\s+|\s*:\s*|\s+)(.+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_note_down:
            fname = match_note_down.group(1).strip()
            content = match_note_down.group(2).strip()
            return files.write_to_file(fname, content, self._search_paths)

        # 5. "write <filename> : <content>" or "write <filename> that/saying <content>"
        match_write_direct = re.match(
            r"^write\s+([a-zA-Z0-9_\- .]+?)(?:\s*:\s*|\s+(?:that|saying|content)\s+)(.+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_write_direct:
            fname = match_write_direct.group(1).strip()
            content = match_write_direct.group(2).strip()
            return files.write_to_file(fname, content, self._search_paths)

        # 6. "write <filename>" without content
        if re.match(r"^(?:write\s+(?:to|in|into)?|take\s+notes?\s+(?:for|in|to)|add\s+(?:this\s+)?to|copy\s+(?:this\s+)?to|have\s+(?:this\s+)?to)\s+([a-zA-Z0-9_\- .]+)$", cmd):
            fname_match = re.search(r"\b(?:to|in|into|for|write)\s+([a-zA-Z0-9_\- .]+)$", cmd)
            fname = fname_match.group(1).strip() if fname_match else "notes"
            return f"What would you like me to write in {fname}?"

        # ── Rename File ──────────────────────────────────────────────────────
        match_rename = re.match(
            r"^(?:rename(?:\s+file)?|change(?:\s+the)?(?:\s+file)?\s+name\s+of)\s+([a-zA-Z0-9_\- .]+?)\s+(?:to|as)\s+([a-zA-Z0-9_\- .]+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_rename:
            old_f = match_rename.group(1).strip()
            new_f = match_rename.group(2).strip()
            return files.rename_file(old_f, new_f, self._search_paths)

        # ── Copy / Paste File ────────────────────────────────────────────────
        match_copy_paste = re.match(
            r"^(?:copy(?:\s+file)?)\s+([a-zA-Z0-9_\- .]+?)\s+(?:and\s+paste(?:\s+it)?\s+as|to|as)\s+([a-zA-Z0-9_\- .]+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_copy_paste and not any(p in cmd for p in ("take notes", "add this to", "copy this to", "have this to", "write")):
            src_f = match_copy_paste.group(1).strip()
            dst_f = match_copy_paste.group(2).strip()
            return files.copy_file(src_f, dst_f, self._search_paths)

        # ── Cut / Move File ──────────────────────────────────────────────────
        match_move = re.match(
            r"^(?:cut(?:\s+file)?|move(?:\s+file)?)\s+([a-zA-Z0-9_\- .]+?)\s+(?:and\s+paste(?:\s+it)?\s+as|to|into|as)\s+([a-zA-Z0-9_\- .]+)$",
            translated_command,
            re.IGNORECASE
        )
        if match_move:
            src_f = match_move.group(1).strip()
            dst_f = match_move.group(2).strip()
            return files.move_file(src_f, dst_f, self._search_paths)

        # ── Search ───────────────────────────────────────────────────────────
        if cmd == "search" or cmd.startswith("search "):
            query = translated_command[len("search "):].strip()
            if query:
                import urllib.parse
                import webbrowser
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                webbrowser.open(url)
                return f"Searching for '{query}' on Google."
            else:
                return "What would you like me to search for?"

        # ── Play ─────────────────────────────────────────────────────────────
        if cmd == "play" or cmd.startswith("play "):
            song = translated_command[len("play "):].strip()
            if song:
                import urllib.parse
                import webbrowser
                import requests

                try:
                    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    html = requests.get(search_url, headers=headers, timeout=5).text
                    video_ids = re.findall(r"watch\?v=(\S{11})", html)
                    if video_ids:
                        url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                        webbrowser.open(url)
                        return f"Playing '{song}' on YouTube."
                except Exception:
                    pass

                # Fallback to search results page if scraping fails
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}"
                webbrowser.open(url)
                return f"Playing '{song}' on YouTube."
            else:
                return "What song would you like me to play?"

        # ── Open ─────────────────────────────────────────────────────────────
        if cmd.startswith("open "):
            target = translated_command[len("open "):].strip()
            target_lower = target.lower()

            # URL alias?
            if target_lower in self._url_aliases or any(
                target_lower == a or target_lower in a.split() or a in target_lower.split() for a in self._url_aliases
            ):
                return urls.open_url(target, self._url_aliases)

            # App alias?
            if target_lower in self._app_aliases or any(
                target_lower == a or target_lower in a.split() or a in target_lower.split() for a in self._app_aliases
            ):
                return apps.open_app(target, self._app_aliases)

            # File fallback
            response = files.open_file(target, self._search_paths)
            if "No file matching" not in response:
                return response

            # Last resort: try as URL
            return urls.open_url(target, self._url_aliases)

        # ── Unknown / AI Fallback ────────────────────────────────────────────
        has_gemini = bool(self._config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY"))
        has_openai = bool(self._config.get("openai_api_key"))
        has_ollama = bool(self._config.get("use_ollama") or self._config.get("ollama_enabled"))

        if has_gemini or has_openai or has_ollama:
            response = ai.generate_voice_response(command, self._config)
            return self.handle_llm_json_response(response)

        if any(w in cmd for w in ("why", "what", "how", "who", "where", "when", "tell me")):
            return "To ask general questions, please configure your gemini_api_key in config.json."

        return f"Sorry, I didn't understand '{command}'. Say 'help' for a list of commands."

    def handle_llm_json_response(self, response_str: str) -> str:
        """Parse LLM JSON response and execute any structured tool actions."""
        try:
            from jarvis.handlers.ai import clean_and_parse_json
            parsed = clean_and_parse_json(response_str)
        except Exception as e:
            logger.warning("Failed to parse LLM response as JSON: %s (Response: %s)", e, response_str)
            return response_str

        if "reply" in parsed:
            return parsed["reply"]

        action = parsed.get("action")
        if not action:
            return response_str

        if action == "multi":
            results = []
            commands = parsed.get("commands", [])
            for cmd in commands:
                res = self.execute_single_action(cmd)
                results.append(res)
            return "Executed actions: " + " and ".join(results)
        else:
            return self.execute_single_action(parsed)

    def execute_single_action(self, action_dict: dict) -> str:
        """Dispatch a single structured JSON command to its Python handler."""
        action = action_dict.get("action")
        if not action:
            return "No action specified."

        # 1. Smart home control
        if action == "control_device":
            device = action_dict.get("device")
            state = action_dict.get("state")
            temp = action_dict.get("temperature")
            
            from server import update_device
            updates = {}
            if state:
                updates["state"] = state
            if temp is not None:
                updates["temperature"] = temp
                
            if device and updates:
                success = update_device(device, updates)
                if success:
                    status_str = f"turned {state}" if state else ""
                    if temp is not None:
                        status_str += f" and set to {temp} degrees"
                    return f"Smart {device} {status_str.strip()} successfully."
                return f"Failed to update smart {device}."
            return "Missing device or state parameters."

        # 2. Create file
        elif action == "create_file":
            from jarvis.handlers import files
            name = action_dict.get("name", "untitled")
            return files.create_file(name)

        # 3. Open application
        elif action == "open_app":
            from jarvis.handlers import apps
            name = action_dict.get("name")
            if name:
                return apps.open_app(name, self._app_aliases)
            return "No application name provided."

        # 4. Play song
        elif action == "play_song":
            song = action_dict.get("name")
            if song:
                import urllib.parse
                import webbrowser
                import requests
                try:
                    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}"
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    html = requests.get(search_url, headers=headers, timeout=5).text
                    video_ids = re.findall(r"watch\?v=(\S{11})", html)
                    if video_ids:
                        url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                        webbrowser.open(url)
                        return f"Playing '{song}' on YouTube."
                except Exception:
                    pass
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}"
                webbrowser.open(url)
                return f"Playing '{song}' on YouTube."
            return "No song name provided."

        # 5. Search Google
        elif action == "search_google":
            query = action_dict.get("query")
            if query:
                import urllib.parse
                import webbrowser
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                webbrowser.open(url)
                return f"Searching for '{query}' on Google."
            return "No query provided."

        # 6. Read diary
        elif action == "read_diary":
            from jarvis.handlers import diary
            return diary.open_diary()

        # 7. Write/Append to diary
        elif action == "append_diary":
            from jarvis.handlers import diary
            text = action_dict.get("text", "")
            return diary.append_diary_entry(text)

        # 8. Write/Append to named file
        elif action in ("write_file", "append_file", "write_to_file"):
            from jarvis.handlers import files
            fname = action_dict.get("file") or action_dict.get("name") or action_dict.get("filename", "notes")
            content = action_dict.get("text") or action_dict.get("content", "")
            return files.write_to_file(fname, content, self._search_paths)

        # 8.1 Rename file
        elif action in ("rename_file", "rename"):
            from jarvis.handlers import files
            old_f = action_dict.get("old_name") or action_dict.get("source") or action_dict.get("file", "")
            new_f = action_dict.get("new_name") or action_dict.get("destination") or action_dict.get("name", "")
            return files.rename_file(old_f, new_f, self._search_paths)

        # 8.2 Copy file
        elif action in ("copy_file", "copy"):
            from jarvis.handlers import files
            src_f = action_dict.get("source") or action_dict.get("old_name") or action_dict.get("file", "")
            dst_f = action_dict.get("destination") or action_dict.get("new_name") or action_dict.get("target", "")
            return files.copy_file(src_f, dst_f, self._search_paths)

        # 8.3 Cut / Move file
        elif action in ("move_file", "cut_file", "cut", "move"):
            from jarvis.handlers import files
            src_f = action_dict.get("source") or action_dict.get("old_name") or action_dict.get("file", "")
            dst_f = action_dict.get("destination") or action_dict.get("new_name") or action_dict.get("target", "")
            return files.move_file(src_f, dst_f, self._search_paths)

        # 8.4 Add / Create Custom Command
        elif action in ("add_custom_command", "create_custom_command"):
            trig = action_dict.get("trigger", "")
            atype = action_dict.get("type", "say")
            targ = action_dict.get("target", "")
            sec = bool(action_dict.get("secure", False))
            return self._custom_mgr.add_custom_command(trig, atype, targ, sec)

        # 8.5 Long-Term Memory (RAG) Actions
        elif action == "remember":
            from jarvis.memory import get_memory_store
            fact = action_dict.get("fact") or action_dict.get("content", "")
            cat = action_dict.get("category", "general")
            return get_memory_store().store_memory(fact, category=cat)

        elif action == "forget":
            from jarvis.memory import get_memory_store
            q = action_dict.get("query") or action_dict.get("fact", "")
            return get_memory_store().forget_by_query(q)

        elif action in ("list_memories", "show_memories"):
            from jarvis.memory import get_memory_store
            mems = get_memory_store().list_memories()
            if not mems:
                return "No memories stored."
            return f"Memories: {'; '.join(m['content'] for m in mems[:5])}"

        # 9. Time/Date/Weather info fallback
        elif action == "tell_time":
            from jarvis.handlers import info
            return info.tell_time()
        elif action == "tell_date":
            from jarvis.handlers import info
            return info.tell_date()
        elif action == "tell_weather":
            from jarvis.handlers import info
            return info.tell_weather(self._weather_city, self._weather_country)

        return f"Action '{action}' is not supported yet."
