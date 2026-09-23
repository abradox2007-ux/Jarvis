"""Automated tests for Jarvis command routing and handlers (no microphone)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.router import CommandRouter
from jarvis.utils import find_best_file_match, load_config, sanitize_filename


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config()
        cls.router = CommandRouter(cls.config)

    def test_delete_rejected(self) -> None:
        result = self.router.route("delete file test")
        self.assertIn("not supported", result.lower())

    def test_diary_priority_over_open(self) -> None:
        with patch("jarvis.handlers.diary.append_diary_entry", return_value="Added to your diary.") as mock:
            result = self.router.route("diary open google was fun")
            mock.assert_called_once_with("open google was fun")
            self.assertEqual(result, "Added to your diary.")

    def test_diary_empty(self) -> None:
        with patch("jarvis.handlers.diary.append_diary_entry", return_value="What would you like to add to your diary?") as mock:
            result = self.router.route("diary")
            mock.assert_called_once_with("")
            self.assertEqual(result, "What would you like to add to your diary?")
            
            mock.reset_mock()
            result_spaces = self.router.route("diary   ")
            mock.assert_called_once_with("")
            self.assertEqual(result_spaces, "What would you like to add to your diary?")

    def test_diary_with_punctuation(self) -> None:
        with patch("jarvis.handlers.diary.append_diary_entry", return_value="Added to your diary.") as mock:
            result_comma = self.router.route("diary, I had a great day")
            mock.assert_called_once_with("I had a great day")
            self.assertEqual(result_comma, "Added to your diary.")

            mock.reset_mock()
            result_colon = self.router.route("diary: another entry")
            mock.assert_called_once_with("another entry")
            self.assertEqual(result_colon, "Added to your diary.")

            mock.reset_mock()
            result_period = self.router.route("diary. a third entry")
            mock.assert_called_once_with("a third entry")
            self.assertEqual(result_period, "Added to your diary.")

    def test_open_diary(self) -> None:
        with patch("jarvis.handlers.diary.open_diary", return_value="Opening your diary.") as mock:
            result_read = self.router.route("read diary")
            mock.assert_called_once()
            self.assertEqual(result_read, "Opening your diary.")

            mock.reset_mock()
            result_watch = self.router.route("watch the content of the diary")
            mock.assert_called_once()
            self.assertEqual(result_watch, "Opening your diary.")

    def test_diary_manual(self) -> None:
        with patch("server.set_status") as mock_status:
            result = self.router.route("diary manual")
            mock_status.assert_called_once_with("diary_manual", "Opening manual diary panel...")
            self.assertEqual(result, "Opening manual diary panel.")

            mock_status.reset_mock()
            result_homophone = self.router.route("Dairy manual")
            mock_status.assert_called_once_with("diary_manual", "Opening manual diary panel...")
            self.assertEqual(result_homophone, "Opening manual diary panel.")

    def test_time_query(self) -> None:
        result = self.router.route("what time is it")
        self.assertIn("time is", result.lower())
        result2 = self.router.route("what's the time now")
        self.assertIn("time is", result2.lower())

    def test_date_query(self) -> None:
        result = self.router.route("what's the date")
        self.assertIn("today is", result.lower())

    def test_weather_query(self) -> None:
        with patch("jarvis.handlers.info.tell_weather", return_value="The weather in Chennai is clear."):
            result = self.router.route("what's the weather")
            self.assertIn("weather", result.lower())
            result2 = self.router.route("what's the weather today")
            self.assertIn("weather", result2.lower())

    def test_create_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("jarvis.handlers.files.DATA_DIR", Path(tmp)):
                name = "unittest_create_file"
                path = Path(tmp) / f"{name}.txt"
                if path.exists():
                    path.unlink()
                result = self.router.route(f"create file {name}")
                self.assertIn("Created", result)
                self.assertTrue(path.exists())
                result2 = self.router.route(f"create file {name}")
                self.assertIn("already exists", result2.lower())

    def test_open_url_not_file(self) -> None:
        with patch("jarvis.handlers.urls.webbrowser.open") as mock_open:
            result = self.router.route("open google")
            mock_open.assert_called_once()
            self.assertIn("Opening google", result)

    def test_open_app_not_url(self) -> None:
        with patch("jarvis.handlers.apps.subprocess.Popen") as mock_popen:
            result = self.router.route("open notepad")
            mock_popen.assert_called_once()
            self.assertIn("Opening notepad", result)

    def test_open_file_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "notes.txt"
            test_file.write_text("hello", encoding="utf-8")
            config = dict(self.config)
            config["search_paths"] = [tmp]
            router = CommandRouter(config)
            with patch("jarvis.handlers.files.os.startfile") as mock_start:
                result = router.route("open notes")
                mock_start.assert_called_once()
                self.assertIn("Opening notes.txt", result)

    def test_unknown_command(self) -> None:
        with patch.dict(self.router._config, {"gemini_api_key": ""}):
            result = self.router.route("do something random xyz")
            self.assertIn("didn't understand", result.lower())

    def test_search_command(self) -> None:
        with patch("webbrowser.open") as mock_open:
            result = self.router.route("search quantum computing")

            mock_open.assert_called_once_with("https://www.google.com/search?q=quantum%20computing")
            self.assertIn("Searching for 'quantum computing' on Google", result)

        # Empty query
        result_empty = self.router.route("search ")
        self.assertEqual(result_empty, "What would you like me to search for?")

    def test_play_command(self) -> None:
        with patch("requests.get") as mock_get, patch("webbrowser.open") as mock_open:
            mock_get.return_value.text = 'href="/watch?v=dQw4w9WgXcQ"'
            result = self.router.route("play bohemian rhapsody")
            mock_open.assert_called_once_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertIn("Playing 'bohemian rhapsody' on YouTube", result)

        # Empty query
        result_empty = self.router.route("play ")
        self.assertEqual(result_empty, "What song would you like me to play?")

    def test_ai_fallback_configured(self) -> None:
        custom_config = dict(self.config)
        custom_config["gemini_api_key"] = "test-api-key"
        custom_router = CommandRouter(custom_config)

        with patch("jarvis.router.ai.generate_voice_response", return_value='{"reply": "Mocked Gemini response."}') as mock_ai:
            result = custom_router.route("why is the sky blue")
            mock_ai.assert_called_once_with("why is the sky blue", custom_config)
            self.assertEqual(result, "Mocked Gemini response.")

    def test_smart_home_routing(self) -> None:
        custom_config = dict(self.config)
        custom_config["gemini_api_key"] = "test-api-key"
        custom_router = CommandRouter(custom_config)

        with patch("server.update_device", return_value=True) as mock_update:
            json_response = '{"action": "control_device", "device": "light", "state": "on"}'
            with patch("jarvis.router.ai.generate_voice_response", return_value=json_response):
                result = custom_router.route("turn on the light")
                mock_update.assert_called_once_with("light", {"state": "on"})
                self.assertIn("successfully", result.lower())


    def test_help_command(self) -> None:
        result = self.router.route("help")
        self.assertIn("open google", result.lower())

    def test_dismissal_commands(self) -> None:
        from jarvis.router import is_dismissal
        self.assertTrue(is_dismissal("stop"))
        self.assertTrue(is_dismissal("jarvis stop"))
        self.assertTrue(is_dismissal("stop listening"))
        self.assertTrue(is_dismissal("go to sleep"))
        self.assertTrue(is_dismissal("standby"))
        self.assertTrue(is_dismissal("bye"))
        self.assertFalse(is_dismissal("open notepad"))
        self.assertFalse(is_dismissal("create file test"))

        res = self.router.route("stop")
        self.assertIn("standby", res.lower())

        res2 = self.router.route("thank you")
        self.assertIn("welcome", res2.lower())

    def test_dot_command_execution(self) -> None:
        from jarvis.router import split_dot_commands

        # Test single command with trailing dot word
        self.assertEqual(split_dot_commands("open notepad dot"), ["open notepad"])
        self.assertEqual(split_dot_commands("create file project sample our best."), ["create file project sample our best"])
        self.assertEqual(split_dot_commands("create file project sample our best dot"), ["create file project sample our best"])

        # Test multi-command separated by dot
        self.assertEqual(split_dot_commands("open notepad dot open calculator dot"), ["open notepad", "open calculator"])
        self.assertEqual(split_dot_commands("open google. open youtube."), ["open google", "open youtube"])

        # Test execution through router
        with patch("subprocess.Popen") as mock_popen:
            res = self.router.route("open notepad dot")
            mock_popen.assert_called_once()
            self.assertIn("Opening notepad", res)

    def test_write_and_take_notes_commands(self) -> None:
        with patch("jarvis.handlers.files.write_to_file", return_value="Added to notes: 'meeting at 5pm'.") as mock_write:
            res1 = self.router.route("take notes for notes meeting at 5pm")
            mock_write.assert_called_with("notes", "meeting at 5pm", self.router._search_paths)
            self.assertIn("Added to notes", res1)

            res2 = self.router.route("add this to notes meeting at 5pm")
            self.assertIn("Added to notes", res2)

            res3 = self.router.route("copy this to notes meeting at 5pm")
            self.assertIn("Added to notes", res3)

            res4 = self.router.route("have this to notes meeting at 5pm")
            self.assertIn("Added to notes", res4)

            res5 = self.router.route("write to notes meeting at 5pm")
            self.assertIn("Added to notes", res5)

            res6 = self.router.route("note down in notes meeting at 5pm")
            self.assertIn("Added to notes", res6)

    def test_write_file_ai_action(self) -> None:
        custom_config = dict(self.config)
        custom_config["gemini_api_key"] = "test-api-key"
        custom_router = CommandRouter(custom_config)

        with patch("jarvis.handlers.files.write_to_file", return_value="Added to project sample: 'testing AI'.") as mock_write:
            json_response = '{"action": "write_file", "file": "project sample", "text": "testing AI"}'
            with patch("jarvis.router.ai.generate_voice_response", return_value=json_response):
                result = custom_router.route("please write in my project sample that testing AI")
                mock_write.assert_called_once_with("project sample", "testing AI", custom_router._search_paths)
                self.assertIn("Added to project sample", result)

    def test_file_rename_copy_move_commands(self) -> None:
        with patch("jarvis.handlers.files.rename_file", return_value="Renamed 'old.txt' to 'new.txt'.") as mock_ren:
            res_ren = self.router.route("rename file old to new")
            mock_ren.assert_called_with("old", "new", self.router._search_paths)
            self.assertIn("Renamed", res_ren)

        with patch("jarvis.handlers.files.copy_file", return_value="Copied 'src.txt' to 'dst.txt'.") as mock_cp:
            res_cp = self.router.route("copy file src to dst")
            mock_cp.assert_called_with("src", "dst", self.router._search_paths)
            self.assertIn("Copied", res_cp)

        with patch("jarvis.handlers.files.move_file", return_value="Moved 'src.txt' to 'dst.txt'.") as mock_mv:
            res_mv = self.router.route("cut file src to dst")
            mock_mv.assert_called_with("src", "dst", self.router._search_paths)
            self.assertIn("Moved", res_mv)

            res_mv2 = self.router.route("move file src to dst")
            self.assertIn("Moved", res_mv2)

    def test_files_handler_crud(self) -> None:
        from jarvis.handlers import files
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("jarvis.handlers.files.DATA_DIR", tmp_path):
                # 1. Write file
                files.write_to_file("my_note", "Hello World")
                self.assertTrue((tmp_path / "my_note.txt").exists())
                self.assertEqual(files.read_file_content("my_note"), "Hello World\n")

                # 2. Copy file
                res_copy = files.copy_file("my_note", "my_note_backup")
                self.assertIn("Copied", res_copy)
                self.assertTrue((tmp_path / "my_note_backup.txt").exists())

                # 3. Rename file
                res_ren = files.rename_file("my_note_backup", "renamed_note")
                self.assertIn("Renamed", res_ren)
                self.assertTrue((tmp_path / "renamed_note.txt").exists())
                self.assertFalse((tmp_path / "my_note_backup.txt").exists())

                # 4. Move / Cut file
                res_mov = files.move_file("renamed_note", "final_note")
                self.assertIn("Moved", res_mov)
                self.assertTrue((tmp_path / "final_note.txt").exists())

                # 5. List files
                file_list = files.list_data_files()
                self.assertEqual(len(file_list), 2)  # my_note.txt and final_note.txt

    def test_tamil_command_routing(self) -> None:
        from jarvis.router import translate_tamil_to_english
        self.assertEqual(translate_tamil_to_english("நேரம் என்ன"), "time")
        self.assertEqual(translate_tamil_to_english("தேதி என்ன"), "date")
        self.assertEqual(translate_tamil_to_english("வானிலை என்ன"), "weather")
        self.assertEqual(translate_tamil_to_english("கூகுள் திற"), "open google")
        self.assertEqual(translate_tamil_to_english("ஓபன் யூடியூப்"), "open youtube")
        self.assertEqual(translate_tamil_to_english("டைரி இன்று மகிழ்ச்சியாக இருந்தது"), "diary இன்று மகிழ்ச்சியாக இருந்தது")

        with patch("jarvis.handlers.urls.webbrowser.open") as mock_open:
            result = self.router.route("கூகுள் திறக்கவும்")
            mock_open.assert_called_once()
            self.assertIn("Opening google", result)


class UtilsTests(unittest.TestCase):
    def test_sanitize_filename(self) -> None:
        self.assertEqual(sanitize_filename('  my/file<>name  '), "myfilename")

    def test_find_best_file_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "report.txt").write_text("x", encoding="utf-8")
            (root / "notes.txt").write_text("y", encoding="utf-8")
            best, all_matches = find_best_file_match("notes", [root])
            self.assertIsNotNone(best)
            assert best is not None
            self.assertEqual(best.name, "notes.txt")
            self.assertGreaterEqual(len(all_matches), 1)


class ListenerTests(unittest.TestCase):
    def test_wake_word_detection(self) -> None:
        from jarvis.listener import Listener

        self.assertTrue(Listener.contains_wake_word("hey jarvis open google"))
        self.assertTrue(Listener.contains_wake_word("Hey jarvis diary test"))
        self.assertFalse(Listener.contains_wake_word("hello open google"))

    def test_extract_inline_command(self) -> None:
        from jarvis.listener import Listener

        cmd = Listener.extract_command_from_wake("hey jarvis open youtube")
        self.assertEqual(cmd, "open youtube")


class DiaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.diary_path = Path(self.tmp_dir.name) / "Diary.txt"
        self.patcher = patch("jarvis.handlers.diary.DIARY_PATH", self.diary_path)
        self.patcher.start()
        
    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp_dir.cleanup()
        
    def test_crud_operations(self) -> None:
        from jarvis.handlers.diary import append_diary_entry, get_diary_entries, update_entry, delete_entry
        
        self.assertEqual(get_diary_entries(), [])
        
        append_diary_entry("First entry")
        append_diary_entry("Second entry")
        
        entries = get_diary_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["text"], "First entry")
        self.assertEqual(entries[1]["text"], "Second entry")
        
        update_entry(0, "Modified first entry")
        entries = get_diary_entries()
        self.assertEqual(entries[0]["text"], "Modified first entry")
        
        delete_entry(0)
        entries = get_diary_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "Second entry")


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        from server import app
        self.app = app.test_client()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.diary_path = Path(self.tmp_dir.name) / "Diary.txt"
        self.patcher = patch("jarvis.handlers.diary.DIARY_PATH", self.diary_path)
        self.patcher.start()
        
    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp_dir.cleanup()

    @patch("jarvis.speech.speak")
    def test_api_diary_write_speaks(self, mock_speak) -> None:
        response = self.app.post("/api/diary/write", json={"text": "Today was a good day"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        self.assertEqual(mock_speak.call_count, 2)
        mock_speak.assert_any_call("Diary: Today was a good day", block=False)
        mock_speak.assert_any_call("Added to your diary.", block=False)

    @patch("jarvis.speech.speak")
    def test_api_diary_overwrite_speaks(self, mock_speak) -> None:
        from jarvis.handlers.diary import append_diary_entry
        append_diary_entry("First entry")
        
        response = self.app.post("/api/diary/overwrite", json={"index": 0, "text": "Modified entry"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        self.assertEqual(mock_speak.call_count, 2)
        mock_speak.assert_any_call("Modify diary entry 0 to Modified entry", block=False)
        mock_speak.assert_any_call("Diary entry updated successfully.", block=False)

    @patch("jarvis.speech.speak")
    def test_api_diary_delete_speaks(self, mock_speak) -> None:
        from jarvis.handlers.diary import append_diary_entry
        append_diary_entry("First entry")
        
        response = self.app.post("/api/diary/delete", json={"index": 0})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        self.assertEqual(mock_speak.call_count, 2)
        mock_speak.assert_any_call("Delete diary entry 0", block=False)
        mock_speak.assert_any_call("Diary entry deleted successfully.", block=False)

    @patch("jarvis.speech.speak")
    def test_api_standby(self, mock_speak) -> None:
        from server import is_standby_requested
        response = self.app.post("/api/standby")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        self.assertTrue(is_standby_requested())
        mock_speak.assert_called_once_with("Going on standby. Say Hey Jarvis when you need me.", block=False)


class SystemHandlerTests(unittest.TestCase):
    @patch("jarvis.handlers.system._send_virtual_key")
    def test_volume_and_media_controls(self, mock_key) -> None:
        from jarvis.handlers import system
        
        res = system.mute_volume()
        self.assertIn("mute", res.lower())
        self.assertTrue(mock_key.called)
        
        mock_key.reset_mock()
        res = system.volume_up(3)
        self.assertIn("increased volume", res.lower())
        self.assertEqual(mock_key.call_count, 3)

        mock_key.reset_mock()
        res = system.volume_down(2)
        self.assertIn("decreased volume", res.lower())
        self.assertEqual(mock_key.call_count, 2)

        mock_key.reset_mock()
        res = system.set_volume_percent(50)
        self.assertIn("50 percent", res.lower())

        mock_key.reset_mock()
        res = system.media_play_pause()
        self.assertIn("media", res.lower())

        res = system.media_next()
        self.assertIn("next", res.lower())

        res = system.media_previous()
        self.assertIn("previous", res.lower())

        res = system.media_stop()
        self.assertIn("stopped", res.lower())

    @patch("ctypes.windll.user32.LockWorkStation", create=True)
    def test_lock_workstation(self, mock_lock) -> None:
        from jarvis.handlers import system
        res = system.lock_workstation()
        self.assertIn("workstation", res.lower())

    def test_battery_status(self) -> None:
        from jarvis.handlers import system
        res = system.get_battery_status()
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)


class TimerHandlerTests(unittest.TestCase):
    def test_parse_time_duration(self) -> None:
        from jarvis.handlers.timer import parse_time_duration
        
        p1 = parse_time_duration("set a timer for 5 minutes")
        self.assertIsNotNone(p1)
        self.assertEqual(p1[0], 300)

        p2 = parse_time_duration("timer 30 seconds")
        self.assertIsNotNone(p2)
        self.assertEqual(p2[0], 30)

        p3 = parse_time_duration("remind me to call John in 1 hour and 30 minutes")
        self.assertIsNotNone(p3)
        self.assertEqual(p3[0], 5400)
        self.assertEqual(p3[1], "call John")

    def test_timer_lifecycle(self) -> None:
        from jarvis.handlers.timer import create_timer, list_timers, cancel_all_timers
        
        cancel_all_timers()
        res_create = create_timer(100, "Test Timer")
        self.assertIn("timer set for", res_create.lower())

        res_list = list_timers()
        self.assertIn("active timer", res_list.lower())

        res_cancel = cancel_all_timers()
        self.assertIn("cancelled", res_cancel.lower())


class CustomCommandHandlerTests(unittest.TestCase):
    def test_safety_guard_blocks_dangerous_commands(self) -> None:
        from jarvis.handlers.custom_commands import SafetyGuard
        
        safe, reason = SafetyGuard.is_safe_command("del /s /q C:\\*")
        self.assertFalse(safe)

        safe, reason = SafetyGuard.is_safe_command("rm -rf /")
        self.assertFalse(safe)

        safe, reason = SafetyGuard.is_safe_command("format D:")
        self.assertFalse(safe)

        safe, reason = SafetyGuard.is_safe_command("echo Hello World")
        self.assertTrue(safe)

    def test_passkey_authenticator(self) -> None:
        from jarvis.handlers.custom_commands import PasskeyAuthenticator, CustomCommand
        
        auth = PasskeyAuthenticator(config_passkey="1312")
        self.assertTrue(auth.verify_input("1312"))
        self.assertTrue(auth.verify_input("my code is 1312"))
        self.assertTrue(auth.verify_input("one three one two"))
        self.assertFalse(auth.verify_input("9999"))

        cmd = CustomCommand(["test trigger"], "say", "Hello", is_secure=True)
        auth.set_pending(cmd)
        self.assertTrue(auth.has_pending())
        self.assertEqual(auth.get_pending(), cmd)
        auth.clear_pending()
        self.assertFalse(auth.has_pending())


class PluginManagerTests(unittest.TestCase):
    def test_plugin_loading_and_dispatch(self) -> None:
        from jarvis.plugin_manager import PluginManager
        
        pm = PluginManager(plugins_dir="./plugins")
        self.assertIn("ip_plugin", pm.plugins)
        
        res = pm.dispatch("what is my local ip", {})
        self.assertIsNotNone(res)
        self.assertIn("local ip", res.lower())


class RouterExtendedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config()
        cls.router = CommandRouter(cls.config)

    @patch("jarvis.handlers.system._send_virtual_key")
    def test_router_system_commands(self, mock_key) -> None:
        res_vol = self.router.route("volume up")
        self.assertIn("increased volume", res_vol.lower())

        res_mute = self.router.route("mute volume")
        self.assertIn("mute", res_mute.lower())

        res_pause = self.router.route("pause music")
        self.assertIn("media", res_pause.lower())

    def test_router_timer_commands(self) -> None:
        from jarvis.handlers.timer import cancel_all_timers
        cancel_all_timers()
        
        res = self.router.route("set a timer for 10 minutes")
        self.assertIn("timer set for", res.lower())

        res_list = self.router.route("list timers")
        self.assertIn("active timer", res_list.lower())

        res_cancel = self.router.route("cancel all timers")
        self.assertIn("cancelled", res_cancel.lower())

    def test_router_custom_command(self) -> None:
        res = self.router.route("my shortcut")
        self.assertIn("Hello test!", res)

    def test_router_plugin_dispatch(self) -> None:
        res = self.router.route("what is my local ip")
        self.assertIn("local ip", res.lower())

    def test_router_voice_add_custom_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_cmd_file = Path(tmp) / "custom_commands.txt"
            with patch.object(self.router._custom_mgr, "commands_file", str(tmp_cmd_file)):
                res = self.router.route("add custom command when I say test voice trigger say Voice created successfully")
                self.assertIn("successfully added", res.lower())
                
                # Test executing it immediately
                res_exec = self.router.route("test voice trigger")
                self.assertEqual(res_exec, "Voice created successfully")

    def test_speech_stop_speaking_and_barge_in(self) -> None:
        from jarvis.speech import is_speaking, stop_speaking, speak
        # Verify stop_speaking resets flags and does not throw
        stop_speaking()
        self.assertFalse(is_speaking())

    def test_kokoro_model_files_exist(self) -> None:
        kokoro_model = Path("bin/kokoro/kokoro-v1.0.onnx")
        voices_bin = Path("bin/kokoro/voices-v1.0.bin")
        if kokoro_model.exists() and voices_bin.exists():
            from kokoro_onnx import Kokoro
            k = Kokoro(str(kokoro_model), str(voices_bin))
            samples, sr = k.create("Kokoro test", voice="af_heart", speed=1.0, lang="en-us")
            self.assertGreater(len(samples), 0)
            self.assertEqual(sr, 24000)

    def test_memory_store_crud_and_similarity(self) -> None:
        from jarvis.memory import MemoryStore
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_memory.db"
            store = MemoryStore(db_path=db_path)

            # Store memory
            res = store.store_memory("My preferred AC temperature is 22 degrees.", category="preference")
            self.assertIn("Remembered", res)

            # Store another memory
            store.store_memory("My project deadline is on Friday afternoon.", category="task")

            # Semantic Query
            results = store.query_memories("what temperature do I like for AC?", top_k=2)
            self.assertGreater(len(results), 0)
            self.assertIn("22 degrees", results[0])

            # Query project deadline
            deadline_res = store.query_memories("when is my project due?", top_k=2)
            self.assertGreater(len(deadline_res), 0)
            self.assertIn("Friday afternoon", deadline_res[0])

            # List memories
            all_mems = store.list_memories()
            self.assertEqual(len(all_mems), 2)

            # Delete memory
            mem_id = all_mems[0]["id"]
            self.assertTrue(store.delete_memory(mem_id))
            self.assertEqual(len(store.list_memories()), 1)

    def test_router_remember_and_forget_commands(self) -> None:
        from jarvis.memory import MemoryStore, get_memory_store
        with tempfile.TemporaryDirectory() as tmpdir:
            test_store = MemoryStore(db_path=Path(tmpdir) / "test_mem.db")
            with patch("jarvis.memory.get_memory_store", return_value=test_store):
                # Test remember
                res_rem = self.router.route("remember that my wifi password is secret_token_123")
                self.assertIn("Remembered", res_rem)

                # Test list memories
                res_list = self.router.route("what do you remember")
                self.assertIn("secret_token_123", res_list)

                # Test forget
                res_forget = self.router.route("forget that wifi password")
                self.assertIn("Forgot", res_forget)

    def test_server_memory_and_sse_endpoints(self) -> None:
        from server import app
        client = app.test_client()

        # Test GET /api/memories
        res = client.get("/api/memories")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.get_json(), list)

        # Test POST /api/memories/store
        store_res = client.post("/api/memories/store", json={"content": "Meeting at 3pm", "category": "schedule"})
        self.assertEqual(store_res.status_code, 200)
        self.assertTrue(store_res.get_json()["success"])


    def test_whatsapp_message_routing_patterns(self) -> None:
        from unittest.mock import MagicMock
        with patch("jarvis.handlers.whatsapp.stage_whatsapp_message", return_value=(True, "I have prepared your message to Charan: 'Good afternoon'. Should I send it?")) as mock_stage:
            # Pattern 1: send message <msg> to <person>
            res1 = self.router.route("send message Good afternoon to Charan")
            mock_stage.assert_called_with(person="Charan", message="Good afternoon", wait_seconds=18.0)
            self.assertIn("prepared your message", res1)
            self.assertIsNotNone(self.router._pending_whatsapp)

            # Reset pending
            self.router._pending_whatsapp = None
            mock_stage.reset_mock()

            # Pattern 1 with quotes: send message "Good afternoon" to "Charan"
            res_quotes = self.router.route('send message "Good afternoon" to "Charan"')
            mock_stage.assert_called_with(person="Charan", message="Good afternoon", wait_seconds=18.0)
            self.assertIn("prepared your message", res_quotes)

            self.router._pending_whatsapp = None
            mock_stage.reset_mock()

            # Pattern 2: send message to <person> saying <msg>
            res2 = self.router.route("send message to Charan saying Good afternoon")
            mock_stage.assert_called_with(person="Charan", message="Good afternoon", wait_seconds=18.0)
            self.assertIn("prepared your message", res2)

            self.router._pending_whatsapp = None
            mock_stage.reset_mock()

            # Pattern 2 with 'that': send a message to Charan that I will be late
            res3 = self.router.route("send a message to Charan that I will be late")
            mock_stage.assert_called_with(person="Charan", message="I will be late", wait_seconds=18.0)
            self.assertIn("prepared your message", res3)

            self.router._pending_whatsapp = None
            mock_stage.reset_mock()

            # Pattern 3: send <msg> to <person> on whatsapp
            res4 = self.router.route("send Good afternoon to Charan on whatsapp")
            mock_stage.assert_called_with(person="Charan", message="Good afternoon", wait_seconds=18.0)
            self.assertIn("prepared your message", res4)

            self.router._pending_whatsapp = None
            mock_stage.reset_mock()

            # Pattern 4: whatsapp <person> saying <msg>
            res5 = self.router.route("whatsapp Charan saying Good afternoon")
            mock_stage.assert_called_with(person="Charan", message="Good afternoon", wait_seconds=18.0)
            self.assertIn("prepared your message", res5)

    def test_whatsapp_confirmation_and_cancellation_flow(self) -> None:
        with patch("jarvis.handlers.whatsapp.stage_whatsapp_message", return_value=(True, "I have prepared your message to Charan: 'Good afternoon'. Should I send it?")):
            with patch("jarvis.handlers.whatsapp.confirm_send_whatsapp_message", return_value="Message sent to Charan.") as mock_confirm:
                with patch("jarvis.handlers.whatsapp.cancel_whatsapp_message", return_value="Message cancelled. Who would you like to message and what should it say?") as mock_cancel:
                    # 1. Stage message
                    prep_res = self.router.route("send message Good afternoon to Charan")
                    self.assertIn("prepared your message", prep_res)
                    self.assertEqual(self.router._pending_whatsapp, {"person": "Charan", "message": "Good afternoon"})

                    # 2. Confirm with "yes", "send it", "ok", "sure", "done", "fine"
                    for affirmative_word in ("yes", "send it", "ok", "sure", "done", "fine", "okay", "send"):
                        self.router._pending_whatsapp = {"person": "Charan", "message": "Good afternoon"}
                        mock_confirm.reset_mock()
                        res = self.router.route(affirmative_word)
                        mock_confirm.assert_called_once_with("Charan")
                        self.assertEqual(res, "Message sent to Charan.")
                        self.assertIsNone(self.router._pending_whatsapp)

                    # 3. Stage again and cancel with "no"
                    self.router.route("send message Hello to Charan Babu")
                    self.assertEqual(self.router._pending_whatsapp, {"person": "Charan Babu", "message": "Hello"})
                    cancel_res = self.router.route("no")
                    mock_cancel.assert_called_once()
                    self.assertIn("Message cancelled", cancel_res)
                    self.assertIsNone(self.router._pending_whatsapp)

    def test_whatsapp_handler_automation(self) -> None:
        from jarvis.handlers import whatsapp
        with patch("webbrowser.open") as mock_browser:
            with patch("time.sleep"):
                with patch("pyautogui.press") as mock_press:
                    with patch("pyautogui.hotkey") as mock_hotkey:
                        with patch("jarvis.handlers.whatsapp._copy_to_clipboard") as mock_clip:
                            success, msg = whatsapp.stage_whatsapp_message("Charan Babu", "Good afternoon", wait_seconds=0.1)
                            self.assertTrue(success)
                            self.assertIn("prepared your message to Charan Babu", msg)
                            mock_browser.assert_called_with("https://web.whatsapp.com")
                            # Verify person and message copied to clipboard
                            mock_clip.assert_any_call("Charan Babu")
                            mock_clip.assert_any_call("Good afternoon")

                            # Test confirm
                            confirm_out = whatsapp.confirm_send_whatsapp_message("Charan Babu")
                            self.assertEqual(confirm_out, "Message sent to Charan Babu.")
                            mock_press.assert_called_with("enter")

                            # Test cancel
                            cancel_out = whatsapp.cancel_whatsapp_message()
                            self.assertIn("Message cancelled", cancel_out)


    def test_local_playlist_commands(self) -> None:
        with patch("jarvis.handlers.media.play_local_playlist", return_value="Playing 3 songs from your playlist.") as mock_play:
            for phrase in (
                "start my playlist",
                "play my playlist",
                "start playlist",
                "play playlist",
                "open my playlist",
                "my playlist",
                "play my songs",
                "start my songs",
                "shuffle my playlist",
                "shuffle playlist",
                "play random songs",
                "play random songs from my playlist",
            ):
                mock_play.reset_mock()
                res = self.router.route(phrase)
                mock_play.assert_called_once()
                self.assertEqual(res, "Playing 3 songs from your playlist.")

    def test_media_handler_local_playlist(self) -> None:
        from jarvis.handlers import media
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Empty folder test
            res_empty = media.play_local_playlist(str(tmppath))
            self.assertIn("No songs found", res_empty)

            # Create dummy audio files
            (tmppath / "song1.mp3").write_bytes(b"dummy")
            (tmppath / "song2.wav").write_bytes(b"dummy")
            (tmppath / "song3.flac").write_bytes(b"dummy")

            with patch("os.startfile") as mock_startfile:
                res_songs = media.play_local_playlist(str(tmppath), shuffle=True)
                self.assertEqual(res_songs, "Playing 3 songs from your playlist.")
                mock_startfile.assert_called_once()
                # Verify .m3u playlist exists and contains all the songs
                m3u_file = tmppath / "playlist.m3u"
                self.assertTrue(m3u_file.exists())
                content = m3u_file.read_text(encoding="utf-8")
                self.assertIn("song1.mp3", content)
                self.assertIn("song2.wav", content)
                self.assertIn("song3.flac", content)


if __name__ == "__main__":
    unittest.main()




