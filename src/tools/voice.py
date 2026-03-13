import os
import subprocess


def record_audio(output_file="/tmp/lumi_voice.wav", duration=5):
    """Records audio using ALSA's arecord command for a set duration."""
    try:
        # -q for quiet, -f cd for CD quality, -d for duration
        subprocess.run(
            ["arecord", "-q", "-f", "cd", "-d", str(duration), output_file],
            check=True
        )
        return output_file
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to record audio with arecord: {e}")
    except FileNotFoundError:
        raise RuntimeError("arecord not found! Ensure ALSA utils are installed.")

def transcribe_audio_hf(audio_file="/tmp/lumi_voice.wav"):
    """
    Transcribes using HuggingFace Inference API (requires HF_TOKEN in env).
    If no token, falls back or simply returns what it can.
    """
    import requests
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN not found in environment for Voice Transcription.")

    API_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
    headers = {"Authorization": f"Bearer {token}"}

    with open(audio_file, "rb") as f:
        data = f.read()

    response = requests.post(API_URL, headers=headers, data=data)
    response.raise_for_status()
    result = response.json()

    # Whisper APIs typically return {'text': '...' }
    if isinstance(result, dict) and "text" in result:
        return result["text"].strip()
    return str(result)
