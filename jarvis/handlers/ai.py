"""jarvis/handlers/ai.py — Handle conversational queries, RAG long-term memory, and task classification via Gemini, OpenAI, or Ollama."""

from __future__ import annotations

import logging
import os
import re
import json
from collections import deque

from jarvis.memory import get_memory_store

logger = logging.getLogger(__name__)

# Memory to track the last 10 messages (role, message)
_chat_history: deque[tuple[str, str]] = deque(maxlen=10)

_gemini_client = None
_last_gemini_key = None

SYSTEM_INSTRUCTION = (
    "You are a helpful smart voice assistant named Jarvis.\n"
    "Your job is to either respond conversationally or choose a specific action tool to run.\n"
    "You MUST respond ONLY with a single JSON object in one of the following formats (no markdown, no backticks, no text around it):\n"
    "1. To reply to general queries or conversation:\n"
    '   {"reply": "Your short spoken response here (under 2 sentences, no markdown, no symbols, list formats or bullet points)."}\n'
    "2. To control smart home devices (light, ac, coffee):\n"
    '   {"action": "control_device", "device": "light"|"ac"|"coffee", "state": "on"|"off", "temperature": 24 (optional integer for AC temperature change)}\n'
    "3. To create a text file:\n"
    '   {"action": "create_file", "name": "filename"}\n'
    "4. To open an application:\n"
    '   {"action": "open_app", "name": "appname"}\n'
    "5. To play a song on YouTube:\n"
    '   {"action": "play_song", "name": "songname"}\n'
    "6. To search on Google:\n"
    '   {"action": "search_google", "query": "search query"}\n'
    "7. To read the diary:\n"
    '   {"action": "read_diary"}\n'
    "8. To create or teach a new custom voice command shortcut:\n"
    '   {"action": "add_custom_command", "trigger": "voice phrase trigger", "type": "say"|"url"|"app"|"folder"|"file"|"cmd", "target": "action target or reply", "secure": false}\n'
    "9. To write or take notes in a specific named file:\n"
    '   {"action": "write_file", "file": "filename", "text": "notes/content to write"}\n'
    "10. To rename an existing file:\n"
    '   {"action": "rename_file", "old_name": "current_filename", "new_name": "new_filename"}\n'
    "11. To copy an existing file:\n"
    '   {"action": "copy_file", "source": "source_filename", "destination": "destination_filename"}\n'
    "12. To cut / move an existing file:\n"
    '   {"action": "move_file", "source": "source_filename", "destination": "destination_filename"}\n'
    "13. To store a persistent user fact or preference in long-term memory:\n"
    '   {"action": "remember", "fact": "fact or preference to remember", "category": "preference"|"fact"|"general"}\n'
    "14. To forget or delete a persistent memory item:\n"
    '   {"action": "forget", "query": "memory topic to forget"}\n'
    "15. To send or stage a WhatsApp message to a contact:\n"
    '   {"action": "send_whatsapp_message", "person": "contact name", "message": "message to send"}\n'
    "16. To play user's local music playlist:\n"
    '   {"action": "play_playlist"}\n'
    "17. To run multiple actions in sequence:\n"
    '   {"action": "multi", "commands": [array of action JSON objects]}\n'
    "\n"
    "Always reply in English. Keep any conversational 'reply' extremely brief and easy to read aloud by a text-to-speech engine."
)


def clean_and_parse_json(text: str) -> dict:
    """Helper to strip markdown tags and parse JSON robustly."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def call_gemini(prompt: str, config: dict) -> str | None:
    """Invoke the Gemini API."""
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

        gen_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7,
        )

        models = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-flash-lite-latest"
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
                logger.warning("Gemini model %s failed: %s", model, e)
    except Exception as e:
        logger.warning("Gemini Client initialization failed: %s", e)
    return None


def call_openai(prompt: str, config: dict) -> str | None:
    """Invoke the OpenAI Chat Completion API."""
    api_key = config.get("openai_api_key")
    if not api_key:
        return None

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json"
        }
        data = {
            "model": config.get("openai_model", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 300
        }
        response = requests.post("https://api.openai.com/v1/chat/completions", json=data, headers=headers, timeout=5)
        if response.status_code == 200:
            res_json = response.json()
            return res_json["choices"][0]["message"]["content"].strip()
        else:
            logger.warning("OpenAI error: Status %s, %s", response.status_code, response.text)
    except Exception as e:
        logger.warning("OpenAI API call failed: %s", e)
    return None


def call_ollama(prompt: str, config: dict) -> str | None:
    """Invoke a local Ollama model API."""
    url = config.get("ollama_url") or "http://localhost:11434"
    model = config.get("ollama_model") or "llama3.2"

    try:
        import requests
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 300
            }
        }
        response = requests.post(f"{url.rstrip('/')}/api/chat", json=data, timeout=12)
        if response.status_code == 200:
            res_json = response.json()
            return res_json["message"]["content"].strip()
    except Exception as e:
        logger.debug("Ollama API call failed: %s", e)
    return None


def check_ollama_status(config: dict) -> str:
    """Check if local Ollama server is running and which models are available."""
    url = config.get("ollama_url") or "http://localhost:11434"
    model = config.get("ollama_model") or "llama3.2"
    try:
        import requests
        res = requests.get(f"{url.rstrip('/')}/api/tags", timeout=2)
        if res.status_code == 200:
            data = res.json()
            models = [m.get("name") for m in data.get("models", [])]
            return f"Ollama is running locally with {len(models)} model{'s' if len(models) != 1 else ''} available, using {model}."
        return f"Ollama server responded with status code {res.status_code}."
    except Exception:
        return "Ollama is currently not running or not reachable on localhost."


def generate_voice_response(prompt: str, config: dict) -> str:
    """
    Route prompt to Gemini, OpenAI, or Ollama with Long-Term Memory (RAG) injection.
    Returns a JSON string matching SYSTEM_INSTRUCTION.
    """
    # 1. RAG: Retrieve relevant long-term memories from SQLite
    mem_store = get_memory_store()
    retrieved_memories = mem_store.query_memories(prompt, top_k=3, threshold=0.22)
    memory_context = ""
    if retrieved_memories:
        memory_context = "Relevant User Facts & Long-Term Memories:\n" + "\n".join(f"- {m}" for m in retrieved_memories) + "\n\n"

    # 2. Format history context
    history_str = ""
    if _chat_history:
        history_str = "Recent conversation history:\n"
        for role, text in _chat_history:
            speaker = "User" if role == "user" else "Assistant"
            history_str += f"{speaker}: {text}\n"
        history_str += "\n"

    formatted_prompt = f"{memory_context}{history_str}New User Query: {prompt}"

    # 3. Determine provider order based on explicit tag or implicit routing
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
        # Implicit keyword routing & configuration preference
        coding_words = ["code", "python", "javascript", "html", "css", "programming", "function", "compile", "develop", "bug", "regex", "algorithm"]
        if any(w in p_lower for w in coding_words) and config.get("openai_api_key"):
            provider_order = ["openai", "gemini", "ollama"]
        elif config.get("use_ollama") or config.get("ollama_enabled") or config.get("primary_ai_provider") == "ollama":
            provider_order = ["ollama", "gemini", "openai"]
        else:
            provider_order = ["gemini", "openai", "ollama"]

    # 4. Request completion
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
        return '{"reply": "I had trouble connecting to my AI models. Please check your internet connection or API keys."}'

    logger.info("Routed query to provider: %s", selected_provider)

    # 5. Parse output and log history context
    try:
        parsed = clean_and_parse_json(response_text)
        reply_content = ""
        if "reply" in parsed:
            reply_content = parsed["reply"]
        elif "action" in parsed:
            act = parsed["action"]
            if act == "multi":
                reply_content = f"Executing: {[c.get('action') for c in parsed.get('commands', [])]}"
            elif act == "remember":
                reply_content = f"Remembering: {parsed.get('fact')}"
            elif act == "forget":
                reply_content = f"Forgetting: {parsed.get('query')}"
            else:
                reply_content = f"Triggering action '{act}'."
        else:
            reply_content = response_text

        _chat_history.append(("user", prompt))
        _chat_history.append(("assistant", reply_content))
    except Exception:
        _chat_history.append(("user", prompt))
        _chat_history.append(("assistant", response_text))

    return response_text
