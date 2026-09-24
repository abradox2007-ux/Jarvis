"""Voice Assistant Jarvis — entry point with frontend server integration."""

from __future__ import annotations

import sys
import time
import threading
import webbrowser

from jarvis.listener import Listener
from jarvis.router import CommandRouter
from jarvis.speech import shutdown as shutdown_speech
from jarvis.speech import speak
from jarvis.utils import load_config, setup_logging
from server import app as flask_app, set_status, add_history, set_router


LISTEN_TIMEOUT = 15  # seconds to wait for a command before giving up


def run_flask():
    """Run Flask in a background thread."""
    flask_app.run(host="0.0.0.0", port=5050, debug=False, use_reloader=False)


def main() -> None:
    logger = setup_logging()
    logger.info("Starting Voice Assistant Jarvis")

    try:
        config = load_config()
    except Exception as exc:
        print(f"Failed to load config.json: {exc}")
        sys.exit(1)

    router = CommandRouter(config)
    set_router(router)

    # Start Flask frontend server in background
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Frontend server started at http://localhost:5050")

    # Automatically open the localhost frontend in the default browser.
    # We use a brief delay (0.5 seconds) to ensure the server starts up first.
    try:
        threading.Timer(0.5, lambda: webbrowser.open("http://localhost:5050")).start()
    except Exception as exc:
        logger.warning("Could not open web browser automatically: %s", exc)
    network_error_spoken = False
    mic_error_spoken = False

    def on_network_error() -> None:
        nonlocal network_error_spoken
        if not network_error_spoken:
            msg = "I need an internet connection for speech recognition."
            speak(msg)
            set_status("error", msg)
            network_error_spoken = True

    def on_mic_error() -> None:
        nonlocal mic_error_spoken
        if not mic_error_spoken:
            msg = "Microphone not available. Please check your settings."
            speak(msg)
            set_status("error", msg)
            mic_error_spoken = True

    listener = Listener(
        device_index=config.get("mic_index"),
        stt_engine=config.get("stt_engine", "google"),
        whisper_model=config.get("whisper_model", "base"),
        on_network_error=on_network_error,
        on_mic_error=on_mic_error,
    )

    continuous_conversation = config.get("continuous_conversation", True)
    follow_up_timeout = float(config.get("follow_up_timeout", 8.0))
    active_on_startup = bool(config.get("active_on_startup", True))

    if config.get("startup_briefing", True):
        from jarvis.handlers.info import generate_startup_briefing
        greeting = generate_startup_briefing(config)
    else:
        user_title = config.get("user_title", "Sir")
        greeting = f"Jarvis is ready, {user_title}. How may I assist you?" if active_on_startup else f"Jarvis is ready, {user_title}. Standing by."
    
    speak(greeting)
    set_status("idle", greeting)

    first_startup = active_on_startup

    try:
        while True:
            try:
                # ── Phase 0: Wait if in manual diary mode ────────────────
                from server import get_status_phase
                while get_status_phase() == "diary_manual":
                    time.sleep(0.2)

                command = None
                if first_startup:
                    first_startup = False
                    set_status("listening", "Listening... speak your command now")
                    command = listener.capture_command(timeout=LISTEN_TIMEOUT)
                else:
                    # ── Phase 1: Wait for wake word ──────────────────────────
                    set_status("waiting", "Waiting for wake word... say \"Hey Jarvis\"")
                    _, inline_command = listener.wait_for_wake_word()

                    # ── Phase 2: Capture initial command ─────────────────────
                    if inline_command:
                        command = inline_command
                        logger.info("Executing inline command directly: '%s'", command)
                    else:
                        if sys.platform == "win32":
                            try:
                                import winsound
                                winsound.Beep(1046, 60)
                                winsound.Beep(1318, 90)
                            except Exception:
                                pass
                        set_status("listening", "Listening... speak your command now")
                        command = listener.capture_command(timeout=LISTEN_TIMEOUT)

                # ── Phase 3: Route initial command ───────────────────────
                if command:
                    set_status("processing", f'Processing: "{command}"')
                    response = router.route(command)
                    speak(response)
                    add_history(command, response, ok=True)
                    if response != "Opening manual diary panel.":
                        set_status("idle", f'Done: {response[:60]}{"…" if len(response) > 60 else ""}')

                    from jarvis.router import is_dismissal, is_termination
                    if is_termination(command):
                        logger.info("Termination command received: '%s'", command)
                        set_status("idle", "Jarvis is offline.")
                        break

                    if is_dismissal(command):
                        set_status("idle", 'Standing by. Say "Hey Jarvis" when ready.')
                        continue

                # ── Phase 4: Continuous Active Listening Loop ────────────
                should_terminate = False
                if continuous_conversation:
                    logger.info("Entering continuous conversation mode (active until 'stop')...")
                    while True:
                        from server import check_and_clear_standby, is_standby_requested
                        if check_and_clear_standby() or is_standby_requested():
                            logger.info("Standby requested via Web UI.")
                            set_status("idle", 'Standing by. Say "Hey Jarvis" when ready.')
                            break

                        set_status("listening", "Listening... (say 'stop' to standby)")
                        follow_up = listener.capture_command(timeout=LISTEN_TIMEOUT)

                        if check_and_clear_standby() or is_standby_requested():
                            logger.info("Standby requested via Web UI during capture.")
                            set_status("idle", 'Standing by. Say "Hey Jarvis" when ready.')
                            break

                        if not follow_up:
                            logger.info("Follow-up timeout (silence). Returning to standby.")
                            set_status("idle", 'Standing by. Say "Hey Jarvis" when ready.')
                            break

                        from jarvis.router import is_dismissal, is_termination
                        if is_termination(follow_up):
                            logger.info("Termination command received in follow-up: '%s'", follow_up)
                            set_status("processing", f'Processing: "{follow_up}"')
                            follow_up_res = router.route(follow_up)
                            speak(follow_up_res)
                            add_history(follow_up, follow_up_res, ok=True)
                            set_status("idle", "Jarvis is offline.")
                            should_terminate = True
                            break

                        if is_dismissal(follow_up):
                            logger.info("Dismissal command received: '%s'", follow_up)
                            set_status("processing", f'Processing: "{follow_up}"')
                            follow_up_res = router.route(follow_up)
                            speak(follow_up_res)
                            add_history(follow_up, follow_up_res, ok=True)
                            set_status("idle", 'Standing by. Say "Hey Jarvis" when ready.')
                            break

                        logger.info("Command received: '%s'", follow_up)
                        set_status("processing", f'Processing: "{follow_up}"')
                        follow_up_res = router.route(follow_up)
                        speak(follow_up_res)
                        add_history(follow_up, follow_up_res, ok=True)

                        if follow_up_res != "Opening manual diary panel.":
                            set_status("idle", f'Done: {follow_up_res[:60]}{"…" if len(follow_up_res) > 60 else ""}')

                if should_terminate:
                    break

                network_error_spoken = False
                mic_error_spoken = False

            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.exception("Unhandled error in main loop: %s", exc)
                err_msg = "Something went wrong. Try again."
                speak(err_msg)
                set_status("error", err_msg)
                time.sleep(0.5)

    except KeyboardInterrupt:
        logger.info("Shutting down on user interrupt.")
        speak("Goodbye.")
        set_status("idle", "Jarvis is offline.")
    finally:
        shutdown_speech()


if __name__ == "__main__":
    main()
