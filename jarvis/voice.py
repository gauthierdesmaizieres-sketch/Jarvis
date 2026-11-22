"""Jarvis's voice: VoiceStudio (local OmniVoice, http://127.0.0.1:3900), the app the Souffle voices came from.

If VoiceStudio isn't running these raise OSError and the page falls back to the browser's voice.
"""
import json
import urllib.request

API = "http://127.0.0.1:3900/v1"


def voices():
    """Names of the VoiceStudio voice profiles (Velours, Aube, Ancre...)."""
    with urllib.request.urlopen(f"{API}/audio/voices", timeout=3) as r:
        return sorted(v["name"] for v in json.load(r)["voices"] if v.get("type") == "profile" and v.get("language") == "fr")


def speak(text, voice):
    """One sentence as mp3 bytes. 16 steps: ~1.3 s a sentence on the GPU, close to 32 in quality."""
    text, voice = str(text).strip()[:600], str(voice)[:80]
    if not text or not voice:
        raise ValueError("text and voice are required")
    body = json.dumps({"model": "tts-1", "voice": voice, "input": text, "response_format": "mp3",
                       "language": "fr", "num_step": 16}).encode()
    req = urllib.request.Request(f"{API}/audio/speech", body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:  # the first call loads the model (~1 min)
        data = r.read()
    if len(data) < 1000:  # VoiceStudio answers a JSON error instead of audio
        raise OSError(f"VoiceStudio: {data[:200]!r}")
    return data
