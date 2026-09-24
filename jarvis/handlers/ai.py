"""jarvis/handlers/ai.py — J.A.R.V.I.S. Persona Brain, Conversational Reasoning, Tool Orchestration & Contextual Awareness."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
from collections import deque
from typing import Optional

from jarvis.memory import get_memory_store

logger = logging.getLogger(__name__)

# Memory to track recent conversation history (role, message)
_chat_history: deque[tuple[str, str]] = deque(maxlen=10)

_gemini_client = None
_last_gemini_key = None


def build_system_instruction(config: dict) -> str:
    """Construct dynamic, high-character J.A.R.V.I.S. system prompt with user title and tool registry."""
    user_title = config.get("user_title", "Sir")
    user_name = config.get("user_name", "Abinesh")
    assistant_name = config.get("assistant_name", "Jarvis")

    return f"""You are {assistant_name}, the highly capable, cultured, and witty AI personal assistant inspired by J.A.R.V.I.S. from Iron Man (voiced by Paul Bettany).
You serve {user_title} ({user_name}) with British eloquence, polite confidence, subtle dry wit, and proactivity.

Core Persona Principles:
1. Always address the user respectfully as "{user_title}" (e.g. "Right away, {user_title}.", "Consider it done, {user_title}.").
2. Keep spoken responses concise (1 to 2 sentences), natural, conversational, and easy to read aloud via Text-To-Speech.
3. When executing an action, do NOT output generic robotic status lines. Instead, accompany every action with a tailored, charming, in-character confirmation in the "reply" field.
4. If the user is having a casual conversation, answering questions, or brainstorming, respond with intelligence, warmth, and subtle wit.
5. Voice Transcription Note: User input is transcribed from speech and may contain phonetic errors or minor typos (e.g. 'not pad' -> 'notepad', 'we code' -> 'vscode', 'u tube' -> 'youtube', 'anti gravity' -> 'antigravity'). Correct these intelligently.

You MUST respond ONLY with a single JSON object in one of the following formats (no markdown formatting, no code blocks, no backticks, no external text):

1. General Conversation / Questions / Banter:
   {{"reply": "Your witty, polite, in-character spoken response here (1-2 sentences, no markdown, no bullet points)."}}

2. Open Desktop Application:
   {{"action": "open_app", "name": "appname", "reply": "Right away, {user_title}. Launching Notepad for you."}}

3. Open Website or URL:
   {{"action": "open_url", "url": "website_or_url", "reply": "Opening YouTube now, {user_title}."}}

4. Play Song on YouTube:
   {{"action": "play_song", "name": "songname", "reply": "Playing AC/DC on YouTube right away, {user_title}."}}

5. Search on Google:
   {{"action": "search_google", "query": "search query", "reply": "Searching the web for quantum computing, {user_title}."}}

6. Take Screenshot / Screen Capture:
   {{"action": "take_screenshot", "reply": "Capturing full screen now, {user_title}."}}

7. Media / Music Playback Controls (Pause, Resume, Play, Next, Previous, Stop):
   {{"action": "media_control", "command": "pause"|"play"|"play_pause"|"next"|"previous"|"stop", "reply": "Pausing music playback right away, {user_title}."}}

8. Lock Screen / Workstation:
   {{"action": "lock_workstation", "reply": "Locking workstation immediately, {user_title}."}}

9. Screen Brightness Control:
   {{"action": "set_brightness", "percent": 75, "reply": "Setting screen brightness to 75 percent, {user_title}."}}

10. Battery Status / Power Check:
    {{"action": "battery_status", "reply": "Checking power reserves now, {user_title}."}}

11. Open / View Document or File:
    {{"action": "open_file", "name": "filename", "reply": "Opening document for you, {user_title}."}}

12. Create File:
    {{"action": "create_file", "name": "filename", "reply": "I have created your file project_notes, {user_title}."}}

13. Write Notes to File:
    {{"action": "write_file", "file": "filename", "text": "content", "reply": "I've added those notes to your document, {user_title}."}}

14. Read / Open Diary:
    {{"action": "read_diary", "reply": "Opening your personal diary now, {user_title}."}}

15. Write / Append to Diary:
    {{"action": "append_diary", "text": "diary entry", "reply": "I have committed that to your diary, {user_title}."}}

16. File Management (Rename / Copy / Move):
    {{"action": "rename_file", "old_name": "old", "new_name": "new", "reply": "Renamed the file as requested, {user_title}."}}
    {{"action": "copy_file", "source": "src", "destination": "dst", "reply": "File copied successfully, {user_title}."}}
    {{"action": "move_file", "source": "src", "destination": "dst", "reply": "Moved the file for you, {user_title}."}}

17. WhatsApp Message:
    {{"action": "send_whatsapp_message", "person": "contact_name", "message": "message", "reply": "Staging WhatsApp message to contact, {user_title}."}}

18. Smart Home / Device Control:
    {{"action": "control_device", "device": "light"|"ac"|"coffee", "state": "on"|"off", "temperature": 24, "reply": "Adjusting the climate control now, {user_title}."}}

19. Timers & Reminders:
    {{"action": "set_timer", "duration_seconds": 300, "label": "label", "reply": "Timer set for 5 minutes, {user_title}."}}

20. System Volume Control:
    {{"action": "system_volume", "command": "up"|"down"|"mute"|"set", "level": 50, "reply": "Volume adjusted, {user_title}."}}

21. Long-Term Memory (Remember / Forget):
    {{"action": "remember", "fact": "user fact", "category": "preference"|"fact", "reply": "I will certainly remember that, {user_title}."}}
    {{"action": "forget", "query": "query", "reply": "I've removed that from my memory banks, {user_title}."}}

22. Smart Text Copy / Semantic Clipboard:
    {{"action": "smart_copy", "instruction": "target", "reply": "Copied that to your clipboard, {user_title}."}}

23. Play Music Playlist:
    {{"action": "play_playlist", "reply": "Starting your personal music playlist now, {user_title}."}}

24. System Briefing / Status:
    {{"action": "system_briefing", "reply": "Running full diagnostic briefing now, {user_title}."}}

25. Multi-Action Sequence:
    {{"action": "multi", "commands": [array_of_actions], "reply": "Executing your workflow sequence right away, {user_title}."}}

26. Terminate Assistant:
    {{"action": "terminate_jarvis", "reply": "Powering down core systems. Goodbye, {user_title}."}}

Always respond in English with valid JSON."""


def clean_and_parse_json(text: str) -> dict:
    """Strip markdown formatting and parse JSON safely."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    
    # Clean possible leading/trailing non-JSON artifacts
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end+1]
    
    return json.loads(text)


def get_environmental_context(config: dict) -> str:
    """Gather live system state, time, active window, and battery for prompt context."""
    now = datetime.datetime.now()
    time_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
    context_lines = [f"- Current Time: {time_str}"]

    # Battery
    try:
        import psutil
        bat = psutil.sensors_battery()
        if bat:
            plugged = "charging" if bat.power_plugged else "on battery"
            context_lines.append(f"- System Battery: {bat.percent}% ({plugged})")
    except Exception:
        pass

    # Active Window
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd)
        if window_title:
            context_lines.append(f"- Active Focused Window: {window_title}")
    except Exception:
        pass

    return "Live System Context:\n" + "\n".join(context_lines) + "\n\n"


def call_gemini(prompt: str, config: dict) -> Optional[str]:
    """Invoke the Gemini API with automatic resilient model cascading."""
    global _gemini_client, _last_gemini_key
    api_key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    api_key = api_key.strip()
    try:
        from google import genai
        from google.genai import types

        if _gemini_client is None or _last_gemini_key != api_key:
            _gemini_client = genai.Client(api_key=api_key)
            _last_gemini_key = api_key

        system_instruction = build_system_instruction(config)
        gen_config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
        )

        # Resilient cascade of live available models
        models = [
            "gemini-2.5-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-pro-preview",
        ]
        for model in models:
            try:
                response = _gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=gen_config,
                )
                if response.text:
                    return response.text.strip()
            except Exception as e:
                logger.warning("Gemini model '%s' failed or busy: %s", model, e)
    except Exception as e:
        logger.warning("Gemini Client initialization failed: %s", e)
    return None


def call_openai(prompt: str, config: dict) -> Optional[str]:
    """Invoke the OpenAI Chat Completion API."""
    api_key = config.get("openai_api_key")
    if not api_key:
        return None

    try:
        import requests
        system_instruction = build_system_instruction(config)
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        data = {
            "model": config.get("openai_model", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 300
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", json=data, headers=headers, timeout=6)
        if response.status_code == 200:
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"].strip()
        else:
            logger.warning("OpenAI error: Status %s, %s", response.status_code, response.text)
    except Exception as e:
        logger.warning("OpenAI API call failed: %s", e)
    return None


def call_ollama(prompt: str, config: dict) -> Optional[str]:
    """Invoke a local Ollama model API."""
    url = config.get("ollama_url") or "http://localhost:11434"
    model = config.get("ollama_model") or "llama3.2"
    keep_alive = config.get("ollama_keep_alive", "30m")
    temperature = float(config.get("ollama_temperature", 0.2))

    try:
        import requests
        system_instruction = build_system_instruction(config)
        
        # Test models to try (e.g. llama3.2, llama3.2:latest)
        models_to_try = [model]
        if ":" not in model:
            models_to_try.append(f"{model}:latest")

        for m_name in models_to_try:
            try:
                data = {
                    "model": m_name,
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "format": "json",
                    "keep_alive": keep_alive,
                    "options": {
                        "temperature": temperature,
                        "num_predict": 180
                    }
                }
                response = requests.post(f"{url.rstrip('/')}/api/chat", json=data, timeout=25)
                if response.status_code == 200:
                    res_json = response.json()
                    return res_json["message"]["content"].strip()
            except Exception as sub_e:
                logger.debug("Ollama attempt with model '%s' failed: %s", m_name, sub_e)
    except Exception as e:
        logger.debug("Ollama API call failed: %s", e)
    return None


def check_ollama_status(config: dict) -> str:
    """Check if local Ollama server is running and which models are available."""
    url = config.get("ollama_url") or "http://localhost:11434"
    model = config.get("ollama_model") or "llama3.2"
    user_title = config.get("user_title", "Sir")
    try:
        import requests
        res = requests.get(f"{url.rstrip('/')}/api/tags", timeout=2)
        if res.status_code == 200:
            data = res.json()
            models = [m.get("name") for m in data.get("models", [])]
            return f"Ollama is running locally with {len(models)} model{'s' if len(models) != 1 else ''} available, using {model}, {user_title}."
        return f"Ollama server responded with status code {res.status_code}, {user_title}."
    except Exception:
        return f"Ollama is currently not reachable on localhost, {user_title}."


def generate_voice_response(prompt: str, config: dict) -> str:
    """
    Route prompt to Gemini, OpenAI, or Ollama with RAG memory and environmental context.
    Returns a JSON string matching the J.A.R.V.I.S. schema.
    """
    user_title = config.get("user_title", "Sir")

    # 1. Environmental State
    env_context = get_environmental_context(config)

    # 2. RAG: Retrieve relevant long-term memories from SQLite
    mem_store = get_memory_store()
    retrieved_memories = mem_store.query_memories(prompt, top_k=3, threshold=0.22)
    memory_context = ""
    if retrieved_memories:
        memory_context = "Relevant Long-Term Memories & User Facts:\n" + "\n".join(f"- {m}" for m in retrieved_memories) + "\n\n"

    # 3. Format history context
    history_str = ""
    if _chat_history:
        history_str = "Recent Conversation Turns:\n"
        for role, text in _chat_history:
            speaker = "User" if role == "user" else "Jarvis"
            history_str += f"{speaker}: {text}\n"
        history_str += "\n"

    formatted_prompt = f"{env_context}{memory_context}{history_str}User Input: {prompt}"

    # 4. Determine provider cascade
    p_lower = prompt.lower().strip()
    provider_order = []

    if p_lower.startswith(("ask openai ", "ask chatgpt ", "ask gpt ")):
        prompt = re.sub(r"^ask (openai|chatgpt|gpt)\s+", "", prompt, flags=re.IGNORECASE)
        provider_order = ["openai", "gemini", "ollama"]
    elif p_lower.startswith(("ask gemini ", "ask google ")):
        prompt = re.sub(r"^ask (gemini|google)\s+", "", prompt, flags=re.IGNORECASE)
        provider_order = ["gemini", "openai", "ollama"]
    elif p_lower.startswith(("ask local ", "ask ollama ", "ask offline ")):
        prompt = re.sub(r"^ask (local|ollama|offline)\s+", "", prompt, flags=re.IGNORECASE)
        provider_order = ["ollama", "gemini", "openai"]
    else:
        coding_words = ["code", "python", "javascript", "html", "css", "programming", "function", "compile", "develop", "bug", "regex", "algorithm"]
        if any(w in p_lower for w in coding_words) and config.get("openai_api_key"):
            provider_order = ["openai", "gemini", "ollama"]
        elif config.get("use_ollama") or config.get("ollama_enabled") or config.get("primary_ai_provider") == "ollama":
            provider_order = ["ollama", "gemini", "openai"]
        else:
            provider_order = ["gemini", "openai", "ollama"]

    # 5. Request completion
    response_text = None
    selected_provider = None

    for provider in provider_order:
        if provider == "gemini":
            response_text = call_gemini(formatted_prompt, config)
            if response_text:
                selected_provider = "Gemini"
                break
        elif provider == "openai":
            response_text = call_openai(formatted_prompt, config)
            if response_text:
                selected_provider = "OpenAI"
                break
        elif provider == "ollama":
            response_text = call_ollama(formatted_prompt, config)
            if response_text:
                selected_provider = "Ollama"
                break

    if not response_text:
        return json.dumps({
            "reply": f"My apologies, {user_title}. I am experiencing a brief communication issue with my neural networks."
        })

    logger.info("Routed query to provider: %s", selected_provider)

    # 6. Parse output and track conversation history
    try:
        parsed = clean_and_parse_json(response_text)
        spoken_reply = parsed.get("reply") or parsed.get("spoken_response") or ""
        if not spoken_reply and "action" in parsed:
            spoken_reply = f"Executing action: {parsed['action']}."
        
        _chat_history.append(("user", prompt))
        _chat_history.append(("assistant", spoken_reply if spoken_reply else response_text))
    except Exception:
        _chat_history.append(("user", prompt))
        _chat_history.append(("assistant", response_text))

    return response_text
