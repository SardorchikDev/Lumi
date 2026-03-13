"""
Lumi voice utilities.
- Input:  record mic → transcribe via Groq Whisper (free)
- Output: system TTS (espeak / say / pyttsx3 fallback)
"""
import os
import subprocess
import tempfile


def _has_cmd(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None

# ── Voice Input (Groq Whisper) ────────────────────────────────

def record_audio(seconds: int = 5) -> str | None:
    """Record mic for N seconds, return path to wav file."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    try:
        if _has_cmd("arecord"):
            # Linux ALSA
            subprocess.run(
                ["arecord", "-d", str(seconds), "-f", "cd", "-r", "16000", path],
                check=True, capture_output=True
            )
        elif _has_cmd("sox"):
            subprocess.run(
                ["sox", "-d", "-r", "16000", "-c", "1", path, "trim", "0", str(seconds)],
                check=True, capture_output=True
            )
        elif _has_cmd("ffmpeg"):
            subprocess.run(
                ["ffmpeg", "-f", "alsa", "-i", "default", "-t", str(seconds),
                 "-ar", "16000", "-ac", "1", path, "-y"],
                check=True, capture_output=True
            )
        else:
            return None
        return path
    except Exception:
        return None

def transcribe_groq(audio_path: str) -> str:
    """Transcribe audio file using Groq Whisper API."""
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        return ""
    try:
        import urllib.request
        # Groq Whisper endpoint
        boundary = "LumiBoundary"
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            f"Content-Type: audio/wav\r\n\r\n"
        ).encode() + audio_data + (
            f"\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="model"\r\n\r\n'
            f"whisper-large-v3-turbo\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            }
        )
        import json
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("text", "").strip()
    except Exception:
        return ""

# ── Voice Output (System TTS) ─────────────────────────────────

def speak(text: str) -> bool:
    """Speak text using available system TTS. Returns True if successful."""
    # Strip markdown/ANSI for cleaner speech
    import re
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    clean = re.sub(r"[`*#_~]", "", clean)
    clean = clean[:1000]  # cap length

    if _has_cmd("espeak-ng"):
        subprocess.run(["espeak-ng", "-s", "160", clean], capture_output=True)
        return True
    if _has_cmd("espeak"):
        subprocess.run(["espeak", "-s", "160", clean], capture_output=True)
        return True
    if _has_cmd("say"):  # macOS
        subprocess.run(["say", clean], capture_output=True)
        return True
    if _has_cmd("festival"):
        proc = subprocess.Popen(["festival", "--tts"], stdin=subprocess.PIPE)
        proc.communicate(clean.encode())
        return True
    # Python fallback
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.say(clean)
        engine.runAndWait()
        return True
    except Exception:
        return False
