"""PA-74 + PA-77 — Spotify control: play/pause/next/previous/what's playing."""
from __future__ import annotations
import re

META = {
    "name": "spotify_control",
    "description": "Controls Spotify playback and reads the current track.",
    "triggers": [
        "play music",
        "pause music",
        "pause spotify",
        "play spotify",
        "next song",
        "next track",
        "previous song",
        "previous track",
        "skip song",
        "skip track",
        "what song is playing",
        "what's playing",
        "what is playing",
        "current song",
        "what song",
        "play",
        "pause",
        "resume",
    ],
}

_NEXT_RE = re.compile(r"\b(next|skip|forward)\b", re.I)
_PREV_RE = re.compile(r"\b(previous|prev|back|last)\b", re.I)
_PAUSE_RE = re.compile(r"\b(pause|stop)\b", re.I)
_PLAY_RE = re.compile(r"\b(play|resume|start)\b", re.I)
_WHAT_RE = re.compile(r"\b(what|which|current)\b.*(song|track|playing|music)\b", re.I)


def _not_configured_msg() -> str:
    return (
        "Spotify isn't set up yet. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET "
        "to .env, then run: python scripts/spotify_auth.py"
    )


def run(args: dict | None = None) -> str:
    utterance = (args or {}).get("utterance", "")

    try:
        from backend.core.spotify_client import get_spotify, is_configured
    except ImportError:
        return "Spotify module is not available."

    if not is_configured():
        return _not_configured_msg()

    try:
        sp = get_spotify()
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Couldn't connect to Spotify: {e}"

    try:
        # What's playing?
        if _WHAT_RE.search(utterance):
            pb = sp.current_playback()
            if not pb or not pb.get("is_playing"):
                return "Nothing is playing on Spotify right now."
            track = pb["item"]
            name = track["name"]
            artists = ", ".join(a["name"] for a in track["artists"])
            return f"Playing '{name}' by {artists}."

        # Next track
        if _NEXT_RE.search(utterance):
            sp.next_track()
            return "Skipped to the next track."

        # Previous track
        if _PREV_RE.search(utterance):
            sp.previous_track()
            return "Going back to the previous track."

        # Pause
        if _PAUSE_RE.search(utterance):
            pb = sp.current_playback()
            if pb and pb.get("is_playing"):
                sp.pause_playback()
                return "Spotify paused."
            return "Spotify is already paused."

        # Play / resume
        if _PLAY_RE.search(utterance):
            pb = sp.current_playback()
            if pb and not pb.get("is_playing"):
                sp.start_playback()
                return "Spotify resumed."
            return "Spotify is already playing."

        return "Try: 'play', 'pause', 'next song', or 'what song is playing'."

    except Exception as e:
        return f"Spotify error: {e}"


def self_test() -> bool:
    # Offline-safe: test regex only
    assert _WHAT_RE.search("what song is playing") is not None
    assert _NEXT_RE.search("next track") is not None
    assert _PAUSE_RE.search("pause music") is not None
    assert _PLAY_RE.search("resume") is not None
    return True
