"""jarvis/handlers/smart_copy.py — Contextual and semantic text extraction to clipboard."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import requests
import pyperclip

logger = logging.getLogger(__name__)

ORDINAL_MAP = {
    "first": 0, "1st": 0, "one": 0, "1": 0, "முதல்": 0,
    "second": 1, "2nd": 1, "two": 1, "2": 1, "இரண்டாவது": 1,
    "third": 2, "3rd": 2, "three": 2, "3": 2, "மூன்றாவது": 2,
    "fourth": 3, "4th": 3, "four": 3, "4": 3, "நான்காவது": 3,
    "fifth": 4, "5th": 4, "five": 4, "5": 4, "ஐந்தாவது": 4,
    "sixth": 5, "6th": 5, "six": 5, "6": 5, "ஆறாவது": 5,
    "seventh": 6, "7th": 6, "seven": 6, "7": 6, "ஏழாவது": 6,
    "eighth": 7, "8th": 7, "eight": 7, "8": 7, "எட்டாவது": 7,
    "ninth": 8, "9th": 8, "nine": 8, "9": 8, "ஒன்பதாவது": 8,
    "tenth": 9, "10th": 9, "ten": 9, "10": 9, "பத்தாவது": 9,
    "eleventh": 10, "11th": 10, "11": 10,
    "twelfth": 11, "12th": 11, "12": 11,
    "thirteenth": 12, "13th": 12, "13": 12,
    "fourteenth": 13, "14th": 13, "14": 13,
    "fifteenth": 14, "15th": 14, "15": 14,
    "last": -1, "final": -1, "end": -1, "கடைசி": -1,
}

ORDINAL_NAMES = {
    0: "first", 1: "second", 2: "third", 3: "fourth", 4: "fifth",
    5: "sixth", 6: "seventh", 7: "eighth", 8: "ninth", 9: "tenth",
    10: "eleventh", 11: "twelfth", 12: "thirteenth", 13: "fourteenth", 14: "fifteenth",
    -1: "last"
}


def _is_web_boilerplate(line: str) -> bool:
    """Identify and filter out search navigation crumbs, URLs, and UI metadata."""
    t = line.strip()
    if not t:
        return True
    if re.match(r"^(?:https?://|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b|\w+\.\w+)", t) or "›" in t or " > " in t:
        return True
    if re.search(r"About\s+[\d,.]+\s+results|\bresults\s*\(\d+.*seconds\)", t, re.I):
        return True
    boilerplate_tokens = {
        "google", "search", "images", "videos", "news", "shopping", "maps", "books",
        "flights", "finance", "tools", "all filters", "filters", "all", "more",
        "sign in", "people also ask", "feedback", "web result with site links",
        "sponsored", "search results", "clear filters", "switch to english",
        "wikipedia", "overview", "menu", "navigation", "share", "copy link",
        "quick links", "related searches", "see more", "table of contents",
        "privacy", "terms", "settings", "dark theme", "send feedback"
    }
    if t.lower() in boilerplate_tokens:
        return True
    if re.match(r"^.+?\s+-\s+(Wikipedia|AWS|IBM|YouTube|GitHub|Reddit|Microsoft|Google)$", t, re.I):
        return True
    # Standalone short label, section title, or FAQ question (e.g. 'What is LLM in AI?' or 'Applications:')
    if len(t.split()) <= 6 and (t.endswith("?") or t.endswith(":") or t.isupper()):
        return True
    return False


def clean_and_extract_paragraphs(raw_text: str) -> list[str]:
    """
    Split raw document/webpage text into clean, isolated human-readable paragraphs,
    stripping website navigation bars, breadcrumbs, search headers, and metadata.
    Handles both double-newline paragraphs and single-newline article extracts.
    """
    if not raw_text:
        return []

    raw_blocks = [b.strip() for b in re.split(r"\n\s*\n+", raw_text) if b.strip()]
    candidates: list[str] = []

    if len(raw_blocks) > 1:
        for block in raw_blocks:
            if block.startswith("```") and block.endswith("```"):
                candidates.append(block)
                continue
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            filtered = [l for l in lines if not _is_web_boilerplate(l)]
            if filtered:
                combined = " ".join(filtered).strip()
                if len(combined.split()) >= 4:
                    candidates.append(combined)
    else:
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        cur_para: list[str] = []
        for ln in lines:
            if _is_web_boilerplate(ln):
                if cur_para:
                    candidates.append(" ".join(cur_para).strip())
                    cur_para = []
                continue

            # Standalone paragraph line (>= 10 words and ends with sentence punctuation)
            if len(ln.split()) >= 10 and re.search(r"[.!?]$", ln):
                if cur_para:
                    candidates.append(" ".join(cur_para).strip())
                    cur_para = []
                candidates.append(ln)
            else:
                cur_para.append(ln)
        if cur_para:
            candidates.append(" ".join(cur_para).strip())

    clean: list[str] = []
    for c in candidates:
        s = c.strip()
        if s and (s.startswith("```") or len(s.split()) >= 4):
            clean.append(s)

    return clean or [raw_text.strip()]


def _clear_screen_selection() -> None:
    """Clear any active text selection across browsers, documents, or editors."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.press("escape")
        time.sleep(0.01)
        pyautogui.press("right")
        time.sleep(0.01)
        w, h = pyautogui.size()
        # Safe margin click (right side margin away from center search results and links)
        pyautogui.click(x=max(10, w - 25), y=max(50, h // 2))
    except Exception:
        pass


def _focus_target_window() -> bool:
    """Ensure a browser or document/reader window is focused, bypassing terminal/IDE focus."""
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        for w in windows:
            title = (w.title or "").strip().lower()
            if not title:
                continue
            if any(b in title for b in ("chrome", "edge", "firefox", "brave", "opera", "google", "wikipedia", "notepad", "document", "pdf", "word")):
                excluded = ("antigravity", "visual studio", "vscode", "terminal", "powershell", "cmd.exe", "ac_voiceassistant")
                if not any(ex in title for ex in excluded):
                    try:
                        if hasattr(w, "_hWnd"):
                            import ctypes
                            ctypes.windll.user32.SetForegroundWindow(w._hWnd)
                        else:
                            w.activate()
                        time.sleep(0.12)
                        return True
                    except Exception:
                        pass
    except Exception:
        pass
    return False


def _capture_explicit_selection(timeout_sec: float = 0.08) -> str:
    """Check if the user has already highlighted text manually on screen."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        sentinel = f"__JARVIS_SENTINEL_{time.time_ns()}__"
        pyperclip.copy(sentinel)
        time.sleep(0.02)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(timeout_sec)
        copied = pyperclip.paste() or ""
        if copied and copied != sentinel and copied.strip():
            logger.info("Captured explicit user highlighted text (%d chars).", len(copied))
            return copied.strip()
    except Exception as e:
        logger.debug("Explicit selection capture failed: %s", e)
    return ""


def capture_active_text(timeout_sec: float = 0.08) -> str:
    """
    Capture text from the active window.
    1. UIAutomation inspection for document / text boxes.
    2. Fallback keyboard capture with immediate deselect so no blue highlight remains on screen.
    """
    _focus_target_window()

    # ── Step 1: UIAutomation ────────────────────────────────────────────────
    try:
        import uiautomation as auto
        focused = auto.GetFocusedControl()
        if focused:
            val = ""
            try:
                val_pattern = focused.GetValuePattern()
                if val_pattern:
                    val = val_pattern.Value
            except Exception:
                pass
            if not val:
                try:
                    val = focused.Name
                except Exception:
                    pass
            if val and val.strip():
                return val.strip()
    except Exception as e:
        logger.debug("UIAutomation focused text extraction failed: %s", e)

    # ── Step 2: Keyboard capture with instant screen deselection ─────────────
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        sentinel = f"__JARVIS_SENTINEL_{time.time_ns()}__"
        pyperclip.copy(sentinel)
        time.sleep(0.02)

        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(timeout_sec)

        # Clear blue selection immediately
        _clear_screen_selection()

        full_doc_text = pyperclip.paste() or ""
        if full_doc_text and full_doc_text != sentinel and full_doc_text.strip():
            logger.info("Captured active document text (%d chars).", len(full_doc_text))
            return full_doc_text.strip()
    except Exception as e:
        logger.debug("Keyboard copy simulation failed: %s", e)

    return ""


def fetch_topic_summary(query: str, config: dict | None = None) -> str:
    """Fetch online encyclopedic / search summary with full multi-paragraph depth for a recent query."""
    if not query or not query.strip():
        return ""

    clean_q = query.strip()
    logger.info("Fetching rich multi-paragraph topic summary for '%s'...", clean_q)

    # 1. Try Wikipedia rich extracts API (returns full multi-paragraph intro)
    try:
        url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&titles={urllib.parse.quote(clean_q)}&format=json&redirects=1"
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                extract = pdata.get("extract", "")
                if extract and len(extract.strip()) > 80:
                    return extract.strip()
    except Exception as e:
        logger.debug("Wikipedia rich extract error: %s", e)

    # 2. Fallback to Wikipedia summary API
    try:
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(clean_q)}"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "JarvisAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            extract = data.get("extract")
            if extract and extract.strip():
                return extract.strip()
    except Exception as e:
        logger.debug("Wikipedia summary lookup error: %s", e)

    # 3. Try DuckDuckGo Instant Answer API
    try:
        ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_q)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(ddg_url, headers={"User-Agent": "JarvisAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            abstract = data.get("AbstractText") or data.get("Abstract")
            if abstract and abstract.strip():
                return abstract.strip()
    except Exception as e:
        logger.debug("DuckDuckGo summary lookup error: %s", e)

    # 4. Try Gemini / AI multi-paragraph generation
    if config:
        gemini_key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                prompt = (
                    f"Provide a comprehensive, factual 3-paragraph explanation of {clean_q}.\n"
                    f"Paragraph 1: Core definition and high-level concept.\n"
                    f"Paragraph 2: Architecture, mechanics, and underlying technology.\n"
                    f"Paragraph 3: Key applications, capabilities, and impact."
                )
                response = client.models.generate_content(
                    model=config.get("gemini_model", "gemini-2.0-flash"),
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                logger.debug("Gemini summary fallback error: %s", e)

    return ""


def extract_with_heuristics(raw_text: str, command: str) -> tuple[str | None, str | None]:
    """
    Evaluate deterministic patterns like paragraphs, lines, emails, code blocks, URLs.
    Returns (extracted_text, confirmation_message) or (None, None) if heuristic doesn't match.
    """
    cmd = command.lower().strip()

    # 1. Generic full copy
    if cmd in (
        "copy that", "copy this", "copy text", "copy to clipboard", "copy content",
        "copy page", "copy all", "copy", "காப்பி செய்", "அதை காப்பி பண்ணு", "கிளிப்போர்டுக்கு காப்பி செய்"
    ):
        return raw_text, "Copied selected text to clipboard."

    paragraphs = clean_and_extract_paragraphs(raw_text)

    # 2. Check paragraph indexing: "copy the 1st paragraph", "copy the second paragraph", "copy paragraph 3"
    idx: int | None = None

    # Check numeric e.g. "paragraph 2", "2nd paragraph", "para 5"
    m_num = re.search(r"\b(?:paragraph|para|பத்தி)\s*#?\s*(\d+)\b", cmd)
    if m_num:
        idx = max(0, int(m_num.group(1)) - 1)
    else:
        m_num_ord = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+(?:paragraph|para|பத்தி)\b", cmd)
        if m_num_ord:
            idx = max(0, int(m_num_ord.group(1)) - 1)
        else:
            for word, val in ORDINAL_MAP.items():
                if (
                    re.search(r"\b" + re.escape(word) + r"\s+(?:paragraph|para|பத்தி)\b", cmd) or
                    re.search(r"\b(?:paragraph|para|பத்தி)\s+" + re.escape(word) + r"\b", cmd)
                ):
                    idx = val
                    break

    if idx is not None:
        if paragraphs:
            if idx == -1:
                return paragraphs[-1], "Copied the last paragraph to clipboard."
            elif 0 <= idx < len(paragraphs):
                num_label = ORDINAL_NAMES.get(idx, f"number {idx+1}")
                return paragraphs[idx], f"Copied the {num_label} paragraph to clipboard."
            else:
                # Target index is beyond available paragraphs — let Local AI handle or synthesize
                return None, None
        elif raw_text:
            return raw_text, "Copied the available text to clipboard."

    # 3. Check Definition / Summary / Answer / Explanation
    if re.search(r"\b(?:definition|summary|explanation|overview|answer|snippet)\b", cmd, re.I):
        if paragraphs:
            return paragraphs[0], "Copied summary to clipboard."
        elif raw_text:
            return raw_text, "Copied content to clipboard."

    # 4. Check lines
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    l_match = re.search(
        r"\b(?:(?:first|second|third|fourth|fifth|last|final|1st|2nd|3rd|4th|5th|1|2|3|4|5|one|two|three|முதல்|இரண்டாவது|கடைசி)\s+(?:line|வரி)|(?:line|வரி)\s+(?:first|second|third|fourth|fifth|last|final|1st|2nd|3rd|4th|5th|1|2|3|4|5|one|two|three))\b",
        cmd,
        re.I
    )
    if l_match:
        matched_str = l_match.group(0).lower()
        l_idx = 0
        for word, val in ORDINAL_MAP.items():
            if re.search(r"\b" + re.escape(word) + r"\b", matched_str):
                l_idx = val
                break

        if lines:
            if l_idx == -1:
                return lines[-1], "Copied the last line to clipboard."
            elif 0 <= l_idx < len(lines):
                num_label = ORDINAL_NAMES.get(l_idx, f"number {l_idx+1}")
                return lines[l_idx], f"Copied the {num_label} line to clipboard."
            else:
                return lines[0], "Copied the first line to clipboard."

    # 5. Email address
    if re.search(r"\b(?:email|e-mail|mail|மின்னஞ்சல்)\b", cmd, re.I):
        emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", raw_text)
        if emails:
            return emails[0], "Copied email address to clipboard."

    # 6. URL / Link
    if re.search(r"\b(?:url|link|website|இணைப்பு|லிங்க்)\b", cmd, re.I):
        urls = [u.rstrip(".,;!?:)'\"") for u in re.findall(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", raw_text)]
        if urls:
            return urls[0], "Copied URL link to clipboard."

    # 7. Code block
    if re.search(r"\b(?:code|code block|code snippet|குறியீடு|கோட்)\b", cmd, re.I):
        code_match = re.search(r"```(?:\w+)?\n?(.*?)```", raw_text, re.DOTALL)
        if code_match:
            return code_match.group(1).strip(), "Copied code block to clipboard."

    return None, None


def extract_with_local_ai(raw_text: str, command: str, config: dict | None = None) -> tuple[str, str]:
    """
    Use Local AI (Ollama) or Gemini fallback to intelligently analyze the document/text,
    distinguish paragraphs, and extract strictly the requested paragraph or snippet.
    """
    config = config or {}
    url = config.get("ollama_url") or "http://localhost:11434"
    model = config.get("ollama_model") or "llama3.2"

    instruction = command
    prefixes_to_strip = (
        "please copy ", "can you copy ", "could you copy ", "just copy ",
        "copy that ", "copy this ", "copy the ", "copy ",
        "நகலெடு ", "காப்பி செய் "
    )
    for p in prefixes_to_strip:
        if instruction.lower().startswith(p):
            instruction = instruction[len(p):].strip()

    prompt = (
        f"You are an expert document extraction and semantic analysis AI.\n"
        f"USER REQUEST: Extract '{instruction}'.\n\n"
        f"SOURCE TEXT:\n\"\"\"{raw_text[:4000]}\"\"\"\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Break down the SOURCE TEXT into individual paragraphs.\n"
        f"2. If the user asked for a specific numbered paragraph (e.g. 1st, 2nd, 3rd, 4th, last), locate and extract that exact paragraph.\n"
        f"3. If the user asked for a specific topic, concept, or section, locate the corresponding paragraph.\n"
        f"4. Do NOT summarize or explain. Do NOT add conversational filler or markdown code quotes.\n"
        f"5. Output ONLY the isolated text content.\n\n"
        f"EXTRACTED TEXT:"
    )

    # 1. Try local Ollama endpoint
    try:
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 350}
        }
        resp = requests.post(f"{url.rstrip('/')}/api/chat", json=data, timeout=8)
        if resp.status_code == 200:
            content = resp.json().get("message", {}).get("content", "").strip()
            if content:
                if (content.startswith('"') and content.endswith('"')) or (content.startswith("'") and content.endswith("'")):
                    content = content[1:-1].strip()
                return content, f"Copied the requested {instruction} to clipboard."
    except Exception as e:
        logger.debug("Ollama extraction failed: %s", e)

    # 2. Try Gemini fallback if configured
    gemini_key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model=config.get("gemini_model", "gemini-2.0-flash"),
                contents=prompt
            )
            if response and response.text:
                content = response.text.strip()
                if (content.startswith('"') and content.endswith('"')) or (content.startswith("'") and content.endswith("'")):
                    content = content[1:-1].strip()
                return content, f"Copied the requested {instruction} to clipboard."
        except Exception as e:
            logger.debug("Gemini extraction fallback failed: %s", e)

    paragraphs = clean_and_extract_paragraphs(raw_text)
    if paragraphs:
        return paragraphs[0], "Copied paragraph to clipboard."
    return raw_text, "Copied selected text to clipboard."





def handle_smart_copy(command: str, config: dict | None = None, last_search: str | None = None) -> str:
    """
    Main entry point for 'copy' voice commands.
    Extracts text context, isolates the target portion, and copies strictly that portion to the clipboard.
    """
    raw_text = ""

    # 1. If user explicitly highlighted text on screen, capture that first (zero screen disturbance)
    raw_text = _capture_explicit_selection()

    # 2. If no text was highlighted, and this follows a recent web search (e.g. "search LLM"),
    # use high-quality topic summary directly without selecting the user's entire screen in blue
    if not raw_text and last_search:
        logger.info("Using recent search topic '%s' for clean text extraction.", last_search)
        raw_text = fetch_topic_summary(last_search, config)

    # 3. If still no text (e.g. user is viewing a local document/page without search query), capture active window
    if not raw_text:
        raw_text = capture_active_text()

    if not raw_text:
        return "No text was highlighted or found on screen to copy."

    # 4. Extract only the requested piece (1st paragraph, 2nd paragraph, code, email, etc.)
    extracted, speech_msg = extract_with_heuristics(raw_text, command)

    # 2. If no direct heuristic matched, invoke AI extraction
    if not extracted:
        extracted, speech_msg = extract_with_local_ai(raw_text, command, config)

    if not extracted or not extracted.strip():
        return "Could not find the specified content to copy."

    # Set to system clipboard
    try:
        pyperclip.copy(extracted)
    except Exception as e:
        logger.warning("pyperclip copy failed: %s", e)
        try:
            import ctypes
            if sys.platform == "win32":
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                user32.OpenClipboard(0)
                user32.EmptyClipboard()
                h_mem = kernel32.GlobalAlloc(0x0042, len(extracted.encode('utf-16le')) + 2)
                p_mem = kernel32.GlobalLock(h_mem)
                ctypes.memmove(p_mem, extracted.encode('utf-16le'), len(extracted.encode('utf-16le')) + 2)
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(13, h_mem)
                user32.CloseClipboard()
        except Exception:
            pass

    return speech_msg or "Copied to clipboard."

