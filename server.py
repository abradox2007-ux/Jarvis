"""server.py — lightweight Flask bridge between AC backend and the frontend UI."""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__, static_folder="frontend")

_lock = Lock()
_state: dict = {
    "phase": "idle",          # idle | waiting | listening | processing | error
    "message": "Jarvis is offline.",
    "updated_at": time.time(),
}
_history: deque = deque(maxlen=50)   # most-recent 50 commands
_standby_requested: bool = False

_devices: dict = {
    "light": {"name": "Living Room Light", "state": "off"},
    "ac": {"name": "Smart AC", "state": "off", "temperature": 24},
    "coffee": {"name": "Smart Coffee Maker", "state": "off"}
}
_router = None


# ── Public helpers (called from main.py / router.py) ──────────────────────────

def request_standby() -> None:
    global _standby_requested
    with _lock:
        _standby_requested = True
        _state["phase"] = "waiting"
        _state["message"] = "Standing by. Say \"Hey Jarvis\" when ready."
        _state["updated_at"] = time.time()


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
            return True
        return False


def set_status(phase: str, message: str) -> None:
    with _lock:
        _state["phase"] = phase
        _state["message"] = message
        _state["updated_at"] = time.time()


def get_status_phase() -> str:
    with _lock:
        return _state["phase"]


def add_history(command: str, response: str, ok: bool = True) -> None:
    with _lock:
        _history.appendleft({
            "command": command,
            "response": response,
            "ok": ok,
            "ts": time.strftime("%H:%M:%S"),
        })


# ── API routes ────────────────────────────────────────────────────────────────

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
    from flask import request
    data = request.json or {}
    device_id = data.get("device")
    updates = data.get("updates", {})
    if device_id and updates:
        success = update_device(device_id, updates)
        return jsonify({"success": success})
    return jsonify({"success": False, "error": "Invalid request parameters"}), 400


@app.route("/api/command", methods=["POST"])
def api_post_command():
    from flask import request
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


# ── Diary APIs ────────────────────────────────────────────────────────────────

@app.route("/api/diary", methods=["GET"])
def api_get_diary():
    from jarvis.handlers import diary
    return jsonify(diary.get_diary_entries())


@app.route("/api/diary/write", methods=["POST"])
def api_write_diary():
    from flask import request
    from jarvis.handlers import diary
    from jarvis.speech import speak
    data = request.json or {}
    text = data.get("text", "")
    
    # Speak command and response (non-blocking)
    speak(f"Diary: {text}", block=False)
    response = diary.append_diary_entry(text)
    speak(response, block=False)
    
    return jsonify({"success": True, "message": response})


@app.route("/api/diary/overwrite", methods=["POST"])
def api_overwrite_diary():
    from flask import request
    from jarvis.handlers import diary
    from jarvis.speech import speak
    data = request.json or {}
    try:
        index = int(data.get("index", -1))
    except (ValueError, TypeError):
        index = -1
    text = data.get("text", "")
    
    # Speak command (non-blocking)
    speak(f"Modify diary entry {index} to {text}", block=False)
    success = diary.update_entry(index, text)
    if success:
        speak("Diary entry updated successfully.", block=False)
    else:
        speak("Failed to update entry.", block=False)
        
    return jsonify({"success": success})


@app.route("/api/diary/delete", methods=["POST"])
def api_delete_diary():
    from flask import request
    from jarvis.handlers import diary
    from jarvis.speech import speak
    data = request.json or {}
    try:
        index = int(data.get("index", -1))
    except (ValueError, TypeError):
        index = -1
        
    # Speak command (non-blocking)
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
    from flask import request
    from jarvis.handlers import files
    name = request.args.get("name", "")
    content = files.read_file_content(name)
    return jsonify({"success": True, "name": name, "content": content})


@app.route("/api/files/save", methods=["POST"])
def api_save_file():
    from flask import request
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
    from flask import request
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
    from flask import request
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
    from flask import request
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

