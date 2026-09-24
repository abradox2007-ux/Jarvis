"""jarvis/router.py — Route a recognised command string to the right handler."""

from __future__ import annotations

import logging
import os
import re

from jarvis.handlers import apps, diary, files, info, urls, ai, system, timer, whatsapp, media, smart_copy, ui_detector
from jarvis.handlers.custom_commands import CustomCommandManager
from jarvis.plugin_manager import PluginManager
from jarvis.ui.overlay import get_badge_overlay

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
    "nevermind", "never mind", "cancel", "standby", "stand by", "close", "mute",
    "stop listening", "stop now", "please stop", "jarvis stop", "stop jarvis", "ok stop",
    "okay stop", "jarvis go to sleep", "jarvis sleep", "jarvis standby", "jarvis mute",
    "நன்றி", "போதும்", "முடிந்தது", "நிறுத்து"
}

TERMINATION_PHRASES = {
    "kill", "terminate", "kill jarvis", "terminate jarvis",
    "kill terminal", "terminate terminal", "close terminal", "exit terminal", "quit terminal",
    "kill assistant", "terminate assistant", "kill the terminal", "terminate the terminal",
    "kill the assistant", "terminate the assistant",
    "kill the whole jarvis", "terminate the whole jarvis", "terminate whole jarvis", "kill whole jarvis",
    "kill jarvis to the core", "terminate jarvis to the core", "kill to the core", "terminate to the core",
    "shutdown jarvis", "shut down jarvis", "shutdown assistant", "shut down assistant",
    "shutdown system", "shut down system",
    "kill process", "terminate process", "exit jarvis", "quit jarvis",
    "exit program", "quit program", "kill program", "terminate program",
    "exit assistant", "quit assistant", "shutdown", "shut down", "quit", "exit",
    "jarvis kill", "jarvis terminate", "jarvis shutdown", "jarvis shut down", "jarvis quit", "jarvis exit",
    "முழுமையாக நிறுத்து", "முழுசா நிறுத்து", "டெர்மினல் மூடு", "டெர்மினலை மூடு",
    "ஜார்விஸை நிறுத்து", "ஜார்விஸ் நிறுத்து", "கில் பண்ணு", "டெர்மினேட் பண்ணு", "முழுசா கில் பண்ணு"
}


def is_termination(command: str) -> bool:
    """Return True if command requests complete termination of Jarvis and the terminal process."""
    if not command:
        return False
    cmd = command.strip().lower().rstrip(".!?,")
    if cmd in TERMINATION_PHRASES:
        return True

    prefixes = (
        "kill jarvis", "terminate jarvis", "shutdown jarvis", "shut down jarvis",
        "kill assistant", "terminate assistant", "kill terminal", "terminate terminal",
        "kill the terminal", "terminate the terminal", "kill the assistant", "terminate the assistant",
        "kill the whole jarvis", "terminate the whole jarvis", "kill whole jarvis", "terminate whole jarvis",
        "kill to the core", "terminate to the core", "kill jarvis to the core", "terminate jarvis to the core",
        "kill process", "terminate process", "kill program", "terminate program", "exit program", "quit program",
        "exit jarvis", "quit jarvis", "exit assistant", "quit assistant"
    )
    if any(cmd == p or cmd.startswith(p + " ") or cmd.startswith(p + ".") for p in prefixes):
        return True
    return False


def is_dismissal(command: str) -> bool:
    """Return True if command is a follow-up dismissal / go-to-sleep instruction."""
    if not command:
        return False
    cmd = command.strip().lower().rstrip(".!?,")

    # Exclude specific targeted controls from accidental dismissal
    if cmd in ("stop music", "stop media", "stop song", "stop playback", "stop timer", "stop timers", "cancel timer", "cancel timers"):
        return False

    if is_termination(cmd):
        return False

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


def parse_choice_number(text: str) -> int | None:
    """Parse verbal or numeric choice from user response (e.g. 'one', 'number 2', 'இரண்டு')."""
    if not text:
        return None
    t = text.lower().strip().rstrip(".!?,")
    words = {
        "1": 1, "one": 1, "first": 1, "1st": 1, "ஒன்று": 1, "ஒன்னு": 1, "முதல்": 1,
        "2": 2, "two": 2, "second": 2, "2nd": 2, "இரண்டு": 2, "ரெண்டு": 2, "இரண்டாவது": 2,
        "3": 3, "three": 3, "third": 3, "3rd": 3, "மூன்று": 3, "மூணு": 3, "மூன்றாவது": 3,
        "4": 4, "four": 4, "fourth": 4, "4th": 4, "நான்கு": 4, "நாலு": 4, "நான்காவது": 4,
        "5": 5, "five": 5, "fifth": 5, "5th": 5, "ஐந்து": 5, "அஞ்சு": 5, "ஐந்தாவது": 5,
        "6": 6, "six": 6, "sixth": 6, "6th": 6, "ஆறு": 6,
        "7": 7, "seven": 7, "seventh": 7, "7th": 7, "ஏழு": 7,
        "8": 8, "eight": 8, "eighth": 8, "8th": 8, "எட்டு": 8,
        "9": 9, "nine": 9, "ninth": 9, "9th": 9, "ஒன்பது": 9,
    }
    if t in words:
        return words[t]
    m = re.search(r"\b(?:number|bar|option|choose|select|box|எண்|பார்|நம்பர்)?\s*(\d+|one|two|three|four|five|six|seven|eight|nine|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth)\b", t)
    if m:
        w = m.group(1).lower()
        if w in words:
            return words[w]
        if w.isdigit():
            return int(w)
    return None


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

    # 0. Terminate / Kill (Tamil)
    if any(w in t for w in ("முழுமையாக நிறுத்து", "முழுசா நிறுத்து", "டெர்மினல் மூடு", "டெர்மினலை மூடு", "ஜார்விஸை நிறுத்து", "கில் பண்ணு", "டெர்மினேட் பண்ணு", "முழுசா கில் பண்ணு")):
        return "terminate jarvis"

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

    # 5.9 Smart Text Copy / Clipboard (Tamil)
    if any(k in t for k in ("காப்பி செய்", "நகலெடு", "காப்பி பண்ணு", "கிளிப்போர்டுக்கு காப்பி செய்")):
        if not any(f in t for f in ("ஃபைலை", "கோப்பை", "file")):
            if "முதல் பத்தி" in t or "முதல் பத்தியை" in t:
                return "copy the first paragraph"
            if "இரண்டாவது பத்தி" in t or "இரண்டாவது பத்தியை" in t:
                return "copy the second paragraph"
            if "கடைசி பத்தி" in t or "கடைசி பத்தியை" in t:
                return "copy the last paragraph"
            if "முதல் வரி" in t or "முதல் வரியை" in t:
                return "copy the first line"
            if "கடைசி வரி" in t or "கடைசி வரியை" in t:
                return "copy the last line"
            if "மின்னஞ்சல்" in t or "மின்னஞ்சலை" in t:
                return "copy the email"
            if "குறியீடு" in t or "கோட்" in t:
                return "copy the code"
            if "இணைப்பு" in t or "லிங்க்" in t:
                return "copy the link"
            return "copy that"

    # 5.10 UI Input selector / Search bar (Tamil)
    if any(k in t for k in ("டைப் பண்ணு", "டைப்பிங் பார்", "சர்ச் பார்", "தேடல் பார்", "செலக்ட் பண்ணு")):
        return "select typing bar"

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

    # 7.5 Play Playlist (Tamil)
    if any(k in t for k in ("பிளேலிஸ்ட்", "பிளேலிஸ்ட்டை")):
        if any(w in t for w in ("ப்ளே", "போடு", "திற", "ஒலிபரப்பு", "ஸ்டார்ட்")):
            return "play my playlist"

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

    # 10. WhatsApp / Send Message (Tamil)
    wa_tam_match = re.match(r"^(?:வாட்ஸ்அப்(?:பில்)?\s+)?(.+?)\s+(?:க்கு|என்பவருக்கு)\s+(.+?)\s*(?:என்று|ஆக)?\s*(?:செய்தி\s+)?அனுப்பு$", t)
    if wa_tam_match:
        person = wa_tam_match.group(1).strip()
        msg = wa_tam_match.group(2).strip()
        return f"send message to {person} saying {msg}"

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
        self._pending_whatsapp: dict[str, str] | None = None
        self._pending_message_state: dict[str, str] | None = None
        self._whatsapp_wait_seconds: float = float(config.get("whatsapp_web_wait_seconds", 18.0))
        self._local_playlist_dir: str = config.get("local_playlist_dir", r"C:\Users\Abinesh\Music\My_playlist")
        self._pending_ui_fields: list[dict] | None = None
        self._pending_dictation_field: dict | None = None
        self._pending_search_action: bool = False
        self._last_search_query: str | None = None

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

        # ── Check Pending UI Field Selection (Numbered Badges Overlay) ──────
        if self._pending_ui_fields:
            fields = self._pending_ui_fields
            clean_cmd = cmd.strip().rstrip(".!?,")
            if clean_cmd in ("no", "cancel", "stop", "nevermind", "never mind", "dismiss", "close", "இல்லை", "வேண்டாம்", "ரத்து"):
                self._pending_ui_fields = None
                self._pending_search_action = False
                try:
                    get_badge_overlay().hide_badges()
                except Exception:
                    pass
                return "Cancelled selection."

            choice_num = parse_choice_number(command) or parse_choice_number(translated_command)
            if choice_num is not None:
                chosen_field = next((f for f in fields if f.get("index") == choice_num), None)
                if chosen_field:
                    try:
                        get_badge_overlay().hide_badges()
                    except Exception:
                        pass
                    ui_detector.focus_and_click_field(chosen_field)
                    self._pending_ui_fields = None
                    self._pending_dictation_field = chosen_field
                    return f"Selected typing bar {choice_num}. What would you like to type?"
                else:
                    return f"Please choose a number between 1 and {len(fields)}."
            else:
                return f"Please select a number between 1 and {len(fields)}, or say cancel."

        # ── Check Pending UI Dictation ───────────────────────────────────────
        if self._pending_dictation_field:
            field = self._pending_dictation_field
            clean_cmd = cmd.strip().rstrip(".!?,")
            if clean_cmd in ("no", "cancel", "stop", "nevermind", "never mind", "dismiss", "இல்லை", "வேண்டாம்", "ரத்து"):
                self._pending_dictation_field = None
                self._pending_search_action = False
                return "Cancelled typing."

            press_enter = self._pending_search_action
            self._pending_dictation_field = None
            self._pending_search_action = False

            dictated_text = command.strip()
            ui_detector.type_into_field(field, dictated_text, press_enter=press_enter)
            if press_enter:
                return f"Searched for '{dictated_text}'."
            return "Typed into field."

        # ── Check Pending Multi-Turn Message State ───────────────────────────
        if self._pending_message_state:
            state = self._pending_message_state
            clean_cmd = cmd.strip().rstrip(".!?,")
            if clean_cmd in ("no", "cancel", "stop", "nevermind", "never mind", "இல்லை", "வேண்டாம்", "ரத்து"):
                self._pending_message_state = None
                return "Message cancelled."

            # Case 1: We already know the recipient, now user spoke the message text
            if state.get("step") == "need_message":
                person = state.get("person", "")
                self._pending_message_state = None
                msg_txt = translated_command.strip()
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person,
                    message=msg_txt,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person, "message": msg_txt}
                return response_txt

            # Case 2: We asked "Who would you like to send a message to, and what should it say?"
            elif state.get("step") == "need_person_and_message":
                self._pending_message_state = None
                m_to = re.match(r"^(?:to\s+)?([a-zA-Z0-9_\- .]+?)(?:\s+(?:saying|that|is|:)\s+|\s*:\s*|\s+)(.+)$", translated_command, re.I)
                if m_to and not m_to.group(1).strip().lower() in ("my", "the", "a"):
                    person = m_to.group(1).strip().strip("'\"")
                    msg_txt = m_to.group(2).strip().strip("'\"")
                    success, response_txt = whatsapp.stage_whatsapp_message(
                        person=person,
                        message=msg_txt,
                        wait_seconds=self._whatsapp_wait_seconds
                    )
                    if success:
                        self._pending_whatsapp = {"person": person, "message": msg_txt}
                    return response_txt
                else:
                    person = translated_command.strip().strip("'\"")
                    self._pending_message_state = {"step": "need_message", "person": person}
                    return f"What message would you like to send to {person}?"

        # ── Check Pending WhatsApp Message Confirmation ──────────────────────
        if self._pending_whatsapp:
            pending = self._pending_whatsapp
            clean_cmd = cmd.strip().rstrip(".!?,")
            tokens = set(clean_cmd.split())

            is_yes = (
                clean_cmd in (
                    "yes", "yeah", "yep", "sure", "send", "send it", "confirm", "go ahead",
                    "send message", "send the message", "ஆம்", "சரி", "அனுப்பு", "send now",
                    "ok send", "okay send", "please send", "yes please", "yes send", "yes send it",
                    "ok", "okay", "do it", "yes do it", "send that", "send this", "alright",
                    "yes jarvis", "send jarvis", "go for it", "proceed", "done", "fine", "it is fine",
                    "all good", "good", "perfect", "send please", "pls send", "please send it"
                )
                or bool(tokens & {
                    "yes", "yeah", "yep", "sure", "send", "confirm", "sendit", "ஆம்", "சரி",
                    "அனுப்பு", "proceed", "ok", "okay", "done", "fine", "perfect", "alright"
                })
            )
            is_no = (
                clean_cmd in (
                    "no", "cancel", "wrong", "don't send", "dont send", "stop", "nope",
                    "இல்லை", "வேண்டாம்", "ரத்து", "no cancel", "cancel it", "do not send",
                    "no don't send", "no dont send", "incorrect", "no wrong", "nevermind", "never mind"
                )
                or bool(tokens & {"no", "cancel", "wrong", "dont", "nope", "இல்லை", "வேண்டாம்", "ரத்து"})
            )

            if is_yes and not is_no:
                self._pending_whatsapp = None
                return whatsapp.confirm_send_whatsapp_message(pending.get("person", ""))
            elif is_no:
                self._pending_whatsapp = None
                return whatsapp.cancel_whatsapp_message()
            else:
                # User provided a different command, clear pending state and continue routing
                self._pending_whatsapp = None

        # ── Safety: no delete ────────────────────────────────────────────────
        if any(w in cmd for w in ("delete", "remove", "erase", "unlink")):
            return "Delete commands are not supported for safety reasons."

        # ── Core Termination: Kill / Terminate / Exit ────────────────────────
        if is_termination(cmd) or is_termination(command) or is_termination(translated_command):
            return system.terminate_jarvis()

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

        # ── LLM Orchestrator Mode (Only when explicitly enabled in config) ───
        if self._config.get("orchestrator_mode", False) and (
            self._config.get("use_ollama") or self._config.get("ollama_enabled") or self._config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        ):
            llm_raw = ai.generate_voice_response(command, self._config)
            if llm_raw and "I had trouble connecting" not in llm_raw:
                return self.handle_llm_json_response(llm_raw)

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

        # ── Ollama / Local AI Status ──────────────────────────────────────────
        if any(p in cmd for p in (
            "check ollama", "check whether ollama is running", "check whether the ollama is running",
            "check if ollama is running", "check if the ollama is running", "is ollama running",
            "is the ollama running", "ollama status", "local ai status", "ai status"
        )):
            return ai.check_ollama_status(self._config)

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

        # ── Smart Contextual / Semantic Text Copy to Clipboard ──────────────
        if re.search(r"\b(?:copy|clipboard)\b", cmd) or any(k in cmd for k in ("நகலெடு", "காப்பி")):
            is_file_op = bool(re.match(r"^(?:please\s+|can\s+you\s+)?copy\s+(?:file\s+)?[a-zA-Z0-9_\- .]+\s+(?:to|as|and\s+paste)\s+[a-zA-Z0-9_\- .]+$", cmd)) and not any(k in cmd for k in ("clipboard", "clip board"))
            is_notes_op = bool(re.match(r"^(?:please\s+|can\s+you\s+)?copy\s+(?:this\s+)?(?:to|in|into)\s+([a-zA-Z0-9_\- .]+?)(?:\s+(?:that|saying|:|content|is)\s+|\s*:\s*|\s+)(.+)$", cmd)) and not any(k in cmd for k in ("clipboard", "clip board"))
            if not is_file_op and not is_notes_op:
                return smart_copy.handle_smart_copy(command=translated_command, config=self._config, last_search=self._last_search_query)

        # ── UI Input Field Selector & Overlay ("select", "search", "dial", "type") ──
        if cmd in (
            "select", "dial", "type", "search bar", "type bar", "typing bar",
            "select typing bar", "select search bar", "choose typing bar", "choose search bar",
            "focus typing bar", "focus search bar", "input bar", "select bar", "choose bar",
            "டைப் பண்ணு", "சர்ச் பார்", "தேடல் பார்", "டைப்பிங் பார்", "செலக்ட் பண்ணு", "டயல்"
        ):
            fields = ui_detector.find_input_fields()
            is_search = "search" in cmd or "தேடு" in cmd or "தேடல்" in cmd
            self._pending_search_action = is_search

            if not fields:
                return "No typing or search bar detected on the active window."
            elif len(fields) == 1:
                ui_detector.focus_and_click_field(fields[0])
                self._pending_dictation_field = fields[0]
                self._pending_ui_fields = None
                return "Typing bar selected. What would you like to type?"
            else:
                self._pending_ui_fields = fields
                try:
                    get_badge_overlay().show_badges(fields)
                except Exception as e:
                    logger.debug("Overlay display failed: %s", e)
                return f"Found {len(fields)} typing bars. Which number should I choose?"

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

        # ── WhatsApp / Send Message ──────────────────────────────────────────
        # 1. "send (a)? (whatsapp)? message <msg> to <person>"
        match_msg_to = re.match(
            r"^(?:send\s+)?(?:a\s+)?(?:whatsapp\s+)?message\s+(?:saying\s+|that\s+)?['\"]?(.+?)['\"]?\s+to\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?$",
            translated_command,
            re.IGNORECASE
        )
        if match_msg_to and not match_msg_to.group(1).strip().lower().startswith("to "):
            msg_content = match_msg_to.group(1).strip().strip("'\"")
            person_name = match_msg_to.group(2).strip().strip("'\"")
            if msg_content and person_name:
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person_name,
                    message=msg_content,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person_name, "message": msg_content}
                return response_txt

        # 2. "send (a)? (whatsapp)? message to <person> saying/that/content/: <msg>" or without keyword
        match_msg_to_person = re.match(
            r"^(?:send\s+)?(?:a\s+)?(?:whatsapp\s+)?message\s+to\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?\s*(?::|\s+(?:saying|that|content|is)\s+|\s+)\s*['\"]?(.+?)['\"]?$",
            translated_command,
            re.IGNORECASE
        )
        if match_msg_to_person:
            person_name = match_msg_to_person.group(1).strip().strip("'\"")
            msg_content = match_msg_to_person.group(2).strip().strip("'\"")
            if person_name and msg_content:
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person_name,
                    message=msg_content,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person_name, "message": msg_content}
                return response_txt

        # 3. "send <person> (a)? (whatsapp)? message (saying/that/:)? <msg>"
        match_send_person_msg = re.match(
            r"^send\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?\s+(?:a\s+)?(?:whatsapp\s+)?message\s*(?::|\s+(?:saying|that|content|is)\s+|\s+)?\s*['\"]?(.+?)['\"]?$",
            translated_command,
            re.IGNORECASE
        )
        if match_send_person_msg and not match_send_person_msg.group(1).strip().lower().startswith("to "):
            person_name = match_send_person_msg.group(1).strip().strip("'\"")
            msg_content = match_send_person_msg.group(2).strip().strip("'\"")
            if person_name and msg_content:
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person_name,
                    message=msg_content,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person_name, "message": msg_content}
                return response_txt

        # 4. "send <msg> to <person> on/via/through whatsapp"
        match_send_on_wa = re.match(
            r"^send\s+['\"]?(.+?)['\"]?\s+to\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?\s+(?:on|via|in|through)\s+whatsapp$",
            translated_command,
            re.IGNORECASE
        )
        if match_send_on_wa:
            msg_content = match_send_on_wa.group(1).strip().strip("'\"")
            person_name = match_send_on_wa.group(2).strip().strip("'\"")
            if msg_content and person_name:
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person_name,
                    message=msg_content,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person_name, "message": msg_content}
                return response_txt

        # 5. "send to <person> (saying/that/:)? <msg>"
        match_send_to = re.match(
            r"^send\s+to\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?\s*(?::|\s+(?:saying|that|content|is)\s+|\s+)\s*['\"]?(.+?)['\"]?$",
            translated_command,
            re.IGNORECASE
        )
        if match_send_to:
            person_name = match_send_to.group(1).strip().strip("'\"")
            msg_content = match_send_to.group(2).strip().strip("'\"")
            if person_name and msg_content:
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person_name,
                    message=msg_content,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person_name, "message": msg_content}
                return response_txt

        # 6. "whatsapp/message <person> saying/that/: <msg>" or "<person> <msg>"
        match_wa_direct = re.match(
            r"^(?:whatsapp|message)\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?\s*(?::|\s+(?:saying|that|content|is)\s+|\s+)\s*['\"]?(.+?)['\"]?$",
            translated_command,
            re.IGNORECASE
        )
        if match_wa_direct and not match_wa_direct.group(1).strip().lower() in ("to", "a", "the", "message", "web"):
            person_name = match_wa_direct.group(1).strip().strip("'\"")
            msg_content = match_wa_direct.group(2).strip().strip("'\"")
            if person_name and msg_content:
                success, response_txt = whatsapp.stage_whatsapp_message(
                    person=person_name,
                    message=msg_content,
                    wait_seconds=self._whatsapp_wait_seconds
                )
                if success:
                    self._pending_whatsapp = {"person": person_name, "message": msg_content}
                return response_txt

        # Incomplete command fallbacks with state tracking
        if re.match(r"^(?:send\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to|send\s+to|message|whatsapp)\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?$", translated_command, re.I):
            m = re.match(r"^(?:send\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to|send\s+to|message|whatsapp)\s+['\"]?([a-zA-Z0-9_\- .]+?)['\"]?$", translated_command, re.I)
            person_name = m.group(1).strip().strip("'\"") if m else ""
            if person_name and person_name.lower() not in ("google", "youtube", "notepad", "notes", "diary", "web", "app"):
                self._pending_message_state = {"step": "need_message", "person": person_name}
                return f"What message would you like to send to {person_name}?"

        if cmd in (
            "send message", "send a message", "send whatsapp message", "whatsapp message",
            "send a whatsapp message", "send message on whatsapp", "send message in whatsapp",
            "send a message on whatsapp", "message on whatsapp"
        ):
            self._pending_message_state = {"step": "need_person_and_message"}
            return "Who would you like to send a message to, and what should it say?"

        # ── Open WhatsApp ────────────────────────────────────────────────────
        if cmd in (
            "open whatsapp", "open whatsapp web", "open whats app", "open what's app",
            "open what'sapp", "open what's app web", "open what'sapp web", "launch whatsapp",
            "start whatsapp", "whatsapp web", "open web whatsapp", "open whatsapp app"
        ):
            whatsapp._open_whatsapp_web_in_browser()
            return "Opening WhatsApp in your browser."

        # ── Search ───────────────────────────────────────────────────────────
        if cmd == "search" or cmd.startswith("search "):
            query = translated_command[len("search "):].strip()
            if query:
                self._last_search_query = query
                import urllib.parse
                import webbrowser
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
                webbrowser.open(url)
                return f"Searching for '{query}' on Google."
            else:
                return "What would you like me to search for?"

        # ── Local Playlist ───────────────────────────────────────────────────
        if (
            cmd in (
                "start my playlist", "play my playlist", "start playlist", "play playlist",
                "open my playlist", "open playlist", "my playlist", "play my songs", "start my songs",
                "resume my playlist", "resume playlist", "play songs", "start songs",
                "shuffle my playlist", "shuffle playlist", "play random songs", "shuffle songs",
                "play random songs from my playlist", "play random songs from playlist", "play my playlist in random",
                "play random songs from the my_playlist folder", "play random songs from my_playlist folder"
            )
            or re.match(r"^(?:start|play|open|resume|shuffle)\s+(?:my\s+)?(?:random\s+)?playlists?(?:\s+in\s+random)?$", cmd)
            or re.match(r"^(?:play|start|shuffle)\s+(?:random\s+)?(?:my\s+)?songs?(?:\s+from\s+(?:my\s+)?playlist)?$", cmd)
        ):
            return media.play_local_playlist(self._local_playlist_dir)

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

        # 0. Core Termination
        if action in ("terminate_jarvis", "kill_jarvis", "kill_assistant", "shutdown_jarvis", "terminate", "kill", "exit"):
            return system.terminate_jarvis()

        # 1. Smart home control
        elif action == "control_device":
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

        # 4.1 Play local playlist
        elif action in ("play_playlist", "start_playlist", "open_playlist"):
            return media.play_local_playlist(self._local_playlist_dir)

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

        # 8.6 WhatsApp / Send Message
        elif action in ("send_whatsapp_message", "send_message", "whatsapp_message"):
            person = action_dict.get("person") or action_dict.get("to") or action_dict.get("contact", "")
            message_txt = action_dict.get("message") or action_dict.get("text") or action_dict.get("content", "")
            success, res = whatsapp.stage_whatsapp_message(person, message_txt, self._whatsapp_wait_seconds)
            if success:
                self._pending_whatsapp = {"person": person, "message": message_txt}
            return res

        # 8.7 Open URL / Website
        elif action in ("open_url", "open_website"):
            url_target = action_dict.get("url") or action_dict.get("target") or action_dict.get("name", "")
            return urls.open_url(url_target, self._url_aliases)

        # 8.8 Timer / Countdown
        elif action in ("set_timer", "create_timer", "timer"):
            secs = action_dict.get("duration_seconds") or action_dict.get("seconds")
            label = action_dict.get("label", "Timer")
            if secs is not None:
                try:
                    return timer.create_timer(int(secs), str(label))
                except Exception:
                    pass
            return "Could not set timer with specified duration."

        # 8.9 System Volume Control
        elif action in ("system_volume", "volume_control", "volume"):
            cmd_type = action_dict.get("command", "").lower()
            lvl = action_dict.get("level")
            if cmd_type == "mute" or action_dict.get("mute"):
                return system.mute_volume()
            elif cmd_type == "up":
                return system.volume_up()
            elif cmd_type == "down":
                return system.volume_down()
            elif lvl is not None:
                try:
                    return system.set_volume_percent(int(lvl))
                except Exception:
                    pass
            return "Adjusted volume."

        # 8.10 Check Ollama / AI Status
        elif action in ("check_ollama", "ollama_status", "ai_status"):
            return ai.check_ollama_status(self._config)

        # 8.11 Smart Text / Semantic Copy
        elif action in ("smart_copy", "copy_text", "copy_content"):
            instr = action_dict.get("instruction") or action_dict.get("target") or "copy that"
            return smart_copy.handle_smart_copy(command=instr, config=self._config, last_search=self._last_search_query)

        # 9. Time/Date/Weather info fallback
        elif action in ("tell_time", "time"):
            from jarvis.handlers import info
            return info.tell_time()
        elif action in ("tell_date", "date"):
            from jarvis.handlers import info
            return info.tell_date()
        elif action in ("tell_weather", "weather"):
            from jarvis.handlers import info
            w_city = action_dict.get("city") or self._weather_city
            return info.tell_weather(w_city, self._weather_country)

        return f"Action '{action}' is not supported yet."
