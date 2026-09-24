"""server.py — Real-Time SSE event stream & REST bridge between Jarvis backend and the frontend UI."""

from __future__ import annotations

import json
import logging
import queue
import time
from collections import deque
from pathlib import Path
from threading import RLock
from flask import Flask, jsonify, request, send_from_directory, Response

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="frontend")

_lock = RLock()
_state: dict = {
    "phase": "idle",          # idle | waiting | listening | processing | error
    "message": "Jarvis is offline.",
    "updated_at": time.time(),
}
_history: deque = deque(maxlen=50)   # most-recent 50 commands
_standby_requested: bool = False
_subscribers: list[queue.Queue[str]] = []

_devices: dict = {
    "light": {"name": "Living Room Light", "state": "off"},
    "ac": {"name": "Smart AC", "state": "off", "temperature": 24},
    "coffee": {"name": "Smart Coffee Maker", "state": "off"}
}
_router = None


def broadcast_event(event_type: str, data: dict) -> None:
    """Broadcast an event string to all active SSE subscribers."""
    payload = json.dumps({"type": event_type, "data": data, "ts": time.time()})
    with _lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(payload)
            except Exception:
                pass


# ── Public helpers (called from main.py / router.py / speech.py) ──────────────

def request_standby() -> None:
    global _standby_requested
    with _lock:
        _standby_requested = True
        _state["phase"] = "waiting"
        _state["message"] = "Standing by. Say \"Hey Jarvis\" when ready."
        _state["updated_at"] = time.time()
    broadcast_event("status", _state)


def is_standby_requested() -> bool:
    global _standby_requested
    with _lock:
        return _standby_requested


def check_and_clear_standby() -> bool:
    global _standby_requested
    with _lock:
        req = _standby_requested
        _standby_requested = False
        return req


def set_router(router) -> None:
    global _router
    with _lock:
        _router = router


def get_router():
    global _router
    with _lock:
        if _router is None:
            from jarvis.utils import load_config
            from jarvis.router import CommandRouter
            config = load_config()
            _router = CommandRouter(config)
        return _router


def get_devices() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _devices.items()}


def update_device(device_id: str, updates: dict) -> bool:
    with _lock:
        if device_id in _devices:
            for k, v in updates.items():
                if k in _devices[device_id]:
                    if k == "temperature":
                        try:
                            _devices[device_id][k] = int(v)
                        except (ValueError, TypeError):
                            pass
                    else:
                        _devices[device_id][k] = str(v)
            devices_copy = {k: dict(v) for k, v in _devices.items()}
        else:
            return False
    broadcast_event("devices", devices_copy)
    return True


def set_status(phase: str, message: str) -> None:
    with _lock:
        _state["phase"] = phase
        _state["message"] = message
        _state["updated_at"] = time.time()
        state_copy = dict(_state)
    broadcast_event("status", state_copy)


def get_status_phase() -> str:
    with _lock:
        return _state["phase"]


def add_history(command: str, response: str, ok: bool = True) -> None:
    entry = {
        "command": command,
        "response": response,
        "ok": ok,
        "ts": time.strftime("%H:%M:%S"),
    }
    with _lock:
        _history.appendleft(entry)
    broadcast_event("history", entry)


# ── Real-Time SSE Stream Route ────────────────────────────────────────────────

@app.route("/api/events")
def api_events():
    """Server-Sent Events (SSE) real-time event stream for zero-lag UI updates."""
    def event_stream():
        q: queue.Queue[str] = queue.Queue(maxsize=100)
        with _lock:
            _subscribers.append(q)
            initial_data = json.dumps({
                "type": "init",
                "data": {
                    "state": _state,
                    "devices": _devices,
                    "history": list(_history)
                },
                "ts": time.time()
            })
        yield f"data: {initial_data}\n\n"

        try:
            while True:
                try:
                    msg = q.get(timeout=15.0)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        finally:
            with _lock:
                if q in _subscribers:
                    _subscribers.remove(q)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


# ── REST API routes ───────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify({**_state})


@app.route("/api/history")
def api_history():
    with _lock:
        return jsonify(list(_history))


@app.route("/api/devices", methods=["GET"])
def api_get_devices():
    return jsonify(get_devices())


@app.route("/api/devices/update", methods=["POST"])
def api_update_device():
    data = request.json or {}
    device_id = data.get("device")
    updates = data.get("updates", {})
    if device_id and updates:
        success = update_device(device_id, updates)
        return jsonify({"success": success})
    return jsonify({"success": False, "error": "Invalid request parameters"}), 400


@app.route("/api/command", methods=["POST"])
def api_post_command():
    from jarvis.speech import speak
    
    data = request.json or {}
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"success": False, "error": "Empty command"}), 400
        
    set_status("processing", f'Processing: "{command}"')
    
    try:
        router = get_router()
        response = router.route(command)
        
        speak(response, block=False)
        
        add_history(command, response, ok=True)
        set_status("idle", f'Done: {response[:60]}')
        return jsonify({"success": True, "response": response})
    except Exception as exc:
        err_msg = f"Error processing command: {exc}"
        set_status("error", err_msg)
        add_history(command, err_msg, ok=False)
        return jsonify({"success": False, "response": err_msg}), 500


@app.route("/api/standby", methods=["POST"])
@app.route("/api/stop", methods=["POST"])
def api_standby():
    request_standby()
    from jarvis.speech import speak
    try:
        speak("Going on standby. Say Hey Jarvis when you need me.", block=False)
    except Exception:
        pass
    return jsonify({"success": True, "message": "Jarvis put on standby."})


# ── Memory (RAG) APIs ─────────────────────────────────────────────────────────

@app.route("/api/memories", methods=["GET"])
def api_get_memories():
    from jarvis.memory import get_memory_store
    return jsonify(get_memory_store().list_memories())


@app.route("/api/memories/store", methods=["POST"])
def api_store_memory():
    from jarvis.memory import get_memory_store
    data = request.json or {}
    content = data.get("content", "").strip()
    cat = data.get("category", "general")
    if not content:
        return jsonify({"success": False, "error": "Empty content"}), 400
    res = get_memory_store().store_memory(content, category=cat)
    broadcast_event("memory", {"action": "store", "content": content})
    return jsonify({"success": True, "message": res})


@app.route("/api/memories/delete", methods=["POST"])
def api_delete_memory():
    from jarvis.memory import get_memory_store
    data = request.json or {}
    try:
        mem_id = int(data.get("id", -1))
    except (ValueError, TypeError):
        mem_id = -1
    success = get_memory_store().delete_memory(mem_id)
    broadcast_event("memory", {"action": "delete", "id": mem_id})
    return jsonify({"success": success})


# ── Diary APIs ────────────────────────────────────────────────────────────────

@app.route("/api/diary", methods=["GET"])
def api_get_diary():
    from jarvis.handlers import diary
    return jsonify(diary.get_diary_entries())


@app.route("/api/diary/write", methods=["POST"])
def api_write_diary():
    from jarvis.handlers import diary
    from jarvis.speech import speak
    data = request.json or {}
    text = data.get("text", "")
    
    speak(f"Diary: {text}", block=False)
    response = diary.append_diary_entry(text)
    speak(response, block=False)
    
    return jsonify({"success": True, "message": response})


@app.route("/api/diary/overwrite", methods=["POST"])
def api_overwrite_diary():
    from jarvis.handlers import diary
    from jarvis.speech import speak
    data = request.json or {}
    try:
        index = int(data.get("index", -1))
    except (ValueError, TypeError):
        index = -1
    text = data.get("text", "")
    
    speak(f"Modify diary entry {index} to {text}", block=False)
    success = diary.update_entry(index, text)
    if success:
        speak("Diary entry updated successfully.", block=False)
    else:
        speak("Failed to update entry.", block=False)
        
    return jsonify({"success": success})


@app.route("/api/diary/delete", methods=["POST"])
def api_delete_diary():
    from jarvis.handlers import diary
    from jarvis.speech import speak
    data = request.json or {}
    try:
        index = int(data.get("index", -1))
    except (ValueError, TypeError):
        index = -1
        
    speak(f"Delete diary entry {index}", block=False)
    success = diary.delete_entry(index)
    if success:
        speak("Diary entry deleted successfully.", block=False)
    else:
        speak("Failed to delete entry.", block=False)
        
    return jsonify({"success": success})


@app.route("/api/status/reset", methods=["POST"])
def api_status_reset():
    set_status("idle", "Jarvis is ready.")
    return jsonify({"success": True})


# ── Files Management APIs ─────────────────────────────────────────────────────

@app.route("/api/files", methods=["GET"])
def api_get_files():
    from jarvis.handlers import files
    return jsonify(files.list_data_files())


@app.route("/api/files/read", methods=["GET"])
def api_read_file():
    from jarvis.handlers import files
    name = request.args.get("name", "")
    content = files.read_file_content(name)
    return jsonify({"success": True, "name": name, "content": content})


@app.route("/api/files/save", methods=["POST"])
def api_save_file():
    from jarvis.handlers import files
    from jarvis.speech import speak
    data = request.json or {}
    name = data.get("name", "").strip()
    content = data.get("content", "")
    success = files.save_file_content(name, content)
    if success:
        speak(f"Saved changes to {name}.", block=False)
    return jsonify({"success": success})


@app.route("/api/files/rename", methods=["POST"])
def api_rename_file():
    from jarvis.handlers import files
    from jarvis.speech import speak
    data = request.json or {}
    old_name = data.get("old_name", "").strip()
    new_name = data.get("new_name", "").strip()
    response = files.rename_file(old_name, new_name)
    speak(response, block=False)
    success = not response.startswith("Could not") and not response.startswith("Failed")
    return jsonify({"success": success, "message": response})


@app.route("/api/files/copy", methods=["POST"])
def api_copy_file():
    from jarvis.handlers import files
    from jarvis.speech import speak
    data = request.json or {}
    source = data.get("source", "").strip()
    destination = data.get("destination", "").strip()
    response = files.copy_file(source, destination)
    speak(response, block=False)
    success = not response.startswith("Could not") and not response.startswith("Failed")
    return jsonify({"success": success, "message": response})


@app.route("/api/files/move", methods=["POST"])
def api_move_file():
    from jarvis.handlers import files
    from jarvis.speech import speak
    data = request.json or {}
    source = data.get("source", "").strip()
    destination = data.get("destination", "").strip()
    response = files.move_file(source, destination)
    speak(response, block=False)
    success = not response.startswith("Could not") and not response.startswith("Failed")
    return jsonify({"success": success, "message": response})


# ── Serve the frontend ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("frontend", "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory("frontend", filename)


@app.after_request
def add_header(response):
    """Disable caching for all requests to prevent frontend cache issues."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
