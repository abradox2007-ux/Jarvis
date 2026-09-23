"""jarvis/handlers/media.py — Local Playlist playback handler."""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".wma", ".opus"}


def play_local_playlist(folder_path: str = r"C:\Users\Abinesh\Music\My_playlist", shuffle: bool = True) -> str:
    """
    Scan the local playlist folder, create an .m3u playlist file with songs shuffled randomly,
    and start playback of all songs one by one.
    """
    path = Path(os.path.expanduser(folder_path))
    if not path.exists() or not path.is_dir():
        logger.warning("Playlist directory does not exist: %s", path)
        return f"Playlist directory not found at {path.name}."

    songs = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS]
    if not songs:
        logger.warning("No audio files found in %s", path)
        return "No songs found in your playlist folder."

    # Shuffle songs randomly so a random song starts first and all songs play in random order
    if shuffle:
        random.shuffle(songs)
    else:
        songs.sort(key=lambda s: s.name.lower())

    # Generate an .m3u playlist file in the directory
    m3u_file = path / "playlist.m3u"
    try:
        with open(m3u_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for song in songs:
                f.write(f"{song.name}\n")
    except Exception as e:
        logger.warning("Failed to create .m3u playlist file: %s", e)

    # Launch playback with default media player
    try:
        if m3u_file.exists():
            os.startfile(str(m3u_file))
        else:
            os.startfile(str(songs[0]))
        return f"Playing {len(songs)} songs from your playlist."
    except Exception as e:
        logger.error("Failed to start media player for playlist: %s", e)
        try:
            os.startfile(str(songs[0]))
            return f"Playing {len(songs)} songs from your playlist."
        except Exception as exc:
            return f"Could not play playlist: {exc}"
