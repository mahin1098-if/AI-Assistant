"""
JOEY - Step 2: voice
Joey listens through your microphone and talks back out loud.
Uses the same brain and tools as joey.py (keep both files in the same folder).

Setup (Windows), once:
  pip install SpeechRecognition sounddevice numpy pyttsx3

Run:
  python joey_voice.py

How to use:
  - Press Enter, then speak. Joey stops listening when you go quiet.
  - Or type a message and press Enter, like before.
  - Say or type "quit" to exit.
"""

import os
import re
import threading

import numpy as np
import pyttsx3
import sounddevice as sd
import speech_recognition as sr
import joey_powers
from joey import CHARACTERS, DEFAULT_CHARACTER, NAME, Brain

LANGUAGE = "en-AU"   # accent Joey listens for (en-US, en-GB, en-IN ...)
# Natural voice: Piper, free and runs on your own PC (no internet needed after the first download).
# Some female voices to try (downloaded automatically the first time, about 60 MB each):
#   en_US-lessac-medium (American, clear)     en_US-amy-medium (American, friendly)
#   en_US-hfc_female-medium (American)        en_US-kristin-medium (American, soft)
#   en_GB-jenny_dioco-medium (British)        en_GB-alba-medium (Scottish)
# Hear samples of all voices at https://rhasspy.github.io/piper-samples/
PIPER_VOICE = "en_US-lessac-medium"  # fallback only: each character's voice is set in CHARACTERS in joey.py
PIPER_SPEED = 1.0          # 0.9 = a bit faster, 1.15 = a bit slower
USE_NATURAL_VOICE = True   # set to False to go back to the robotic offline Windows voice

# Robotic offline Windows voice (used if the natural voice can't connect)
VOICE_INDEX = None   # set to 0, 1, 2 ... to pick a different Windows voice
SPEAKING_RATE = 185  # words per minute
MIC_DEVICE = None    # set to a number from mic_test.py if Joey can't hear you
SENSITIVITY = 2.0    # lower = hears quieter voices (try 1.5); higher = ignores more noise

RATE = 16000                 # microphone sample rate
BLOCK_SECONDS = 0.03


# ---------- Ears: microphone -> text ----------

class Mic:
    """Opens a microphone in whatever format it supports and hands back mono sound."""

    def __init__(self, device=None):
        info = sd.query_devices(device, "input")
        self.name = info["name"]
        self.rate = int(info["default_samplerate"])
        self.channels = max(1, min(int(info["max_input_channels"]), 2))
        self.block = int(self.rate * BLOCK_SECONDS)
        self.stream = sd.InputStream(device=device, samplerate=self.rate,
                                     channels=self.channels, dtype="int16", blocksize=self.block)

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, *args):
        self.stream.stop()
        self.stream.close()

    def read(self):
        block, _ = self.stream.read(self.block)
        mono = block.astype(np.float32).mean(axis=1)
        loudness = float(np.sqrt(np.mean(mono ** 2)))
        return mono, loudness


def to_speech_audio(chunks, rate):
    """Join the recorded pieces and convert to the 16 kHz format speech recognition wants."""
    sound = np.concatenate(chunks)
    if rate != RATE:
        new_length = int(len(sound) * RATE / rate)
        sound = np.interp(np.linspace(0, len(sound) - 1, new_length), np.arange(len(sound)), sound)
    pcm = np.clip(sound, -32768, 32767).astype(np.int16)
    return sr.AudioData(pcm.tobytes(), RATE, 2)


def measure_background_noise() -> float:
    """Listen to the room for a moment to learn how loud 'quiet' is."""
    levels = []
    with Mic(MIC_DEVICE) as mic:
        for _ in range(int(0.8 / BLOCK_SECONDS)):
            levels.append(mic.read()[1])
    noise = float(np.median(levels))
    return max(noise * SENSITIVITY, 120)  # speech must be louder than the room


def record_speech(threshold: float, wait_seconds=8, max_seconds=15, pause_seconds=1.2):
    """Wait for you to start talking, record, and stop after a short pause."""
    before, frames = [], []
    started, waited, quiet, loudest = False, 0.0, 0.0, 0.0
    with Mic(MIC_DEVICE) as mic:
        while True:
            block, loudness = mic.read()
            loudest = max(loudest, loudness)
            if not started:
                before = (before + [block])[-10:]  # keep the start of your first word
                if loudness > threshold:
                    started, frames = True, before
                else:
                    waited += BLOCK_SECONDS
                    if waited > wait_seconds:
                        print(f"  [loudest sound: {int(loudest)}, needed: {int(threshold)}]")
                        return None  # nobody spoke
            else:
                frames.append(block)
                quiet = quiet + BLOCK_SECONDS if loudness < threshold else 0.0
                if quiet > pause_seconds or len(frames) * BLOCK_SECONDS > max_seconds:
                    break
        rate = mic.rate
    return to_speech_audio(frames, rate)


recognizer = sr.Recognizer()


def listen(threshold: float):
    print("  [listening... speak now]")
    audio = record_speech(threshold)
    if audio is None:
        print("  [didn't hear anything]")
        return None
    try:
        text = recognizer.recognize_google(audio, language=LANGUAGE)
        print(f"You (said): {text}")
        return text
    except sr.UnknownValueError:
        print("  [couldn't understand that, try again]")
    except sr.RequestError as e:
        print(f"  [speech service problem: {e}]")
    return None


# ---------- Mouth: text -> speech ----------

_speak_lock = threading.Lock()  # stops two things talking at once (e.g. a timer going off)


VOICES_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
_piper = {}  # the loaded voice, kept so it only loads once
_piper_lock = threading.Lock()


def _load_piper(voice_name=None):
    with _piper_lock:
        return _load_piper_locked(voice_name or PIPER_VOICE)


def _load_piper_locked(PIPER_VOICE):
    if PIPER_VOICE not in _piper:
        from pathlib import Path

        from piper import PiperVoice
        from piper.download_voices import download_voice

        folder = Path(VOICES_FOLDER)
        folder.mkdir(exist_ok=True)
        model = folder / f"{PIPER_VOICE}.onnx"
        if not model.exists():
            print(f"  [downloading voice {PIPER_VOICE}, one time only, please wait...]")
            download_voice(PIPER_VOICE, folder)
        try:
            # with sound-by-sound timing for lip sync (needs: pip install onnx)
            _piper[PIPER_VOICE] = PiperVoice.load(model, include_alignments=True)
        except Exception as e:
            print(f"  [lip-sync timing unavailable ({e}); run: pip install onnx]")
            _piper[PIPER_VOICE] = PiperVoice.load(model)
    return _piper[PIPER_VOICE]


def on_speech(envelope, step, phonemes=None):
    """Called just before Joey starts talking. joey_app.py replaces this to move the face's lips.
    envelope: list of loudness values (0..1), one every `step` seconds. None if unknown.
    phonemes: list of (sound, start, end) in seconds, for exact lip sync. None if unknown."""


def speech_envelope(path: str, step: float = 0.04):
    """How loud the voice is every `step` seconds, so the lips can move in time."""
    import wave
    with wave.open(path, "rb") as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16 if width == 2 else np.uint8)
    if channels > 1:
        data = data[::channels]
    chunk = max(1, int(rate * step))
    levels = [float(np.sqrt(np.mean(data[i:i + chunk].astype(np.float32) ** 2)))
              for i in range(0, len(data), chunk)]
    peak = max(levels) if levels else 1.0
    return [min(1.0, (v / peak) ** 0.7 * 1.1) if peak else 0.0 for v in levels]


def synthesize(text: str, voice_name=None, wav_target=None):
    """Make speech audio as a WAV (to a file path or a file-like object).
    Returns the timing of each sound: [(sound, start, end), ...] or None if not available."""
    import wave

    from piper import SynthesisConfig

    voice = _load_piper(voice_name)
    phonemes, clock, aligned = [], 0.0, True
    with wave.open(wav_target, "wb") as wav_file:
        first = True
        for chunk in voice.synthesize(text, syn_config=SynthesisConfig(length_scale=PIPER_SPEED),
                                      include_alignments=True):
            if first:
                wav_file.setframerate(chunk.sample_rate)
                wav_file.setsampwidth(chunk.sample_width)
                wav_file.setnchannels(chunk.sample_channels)
                first = False
            wav_file.writeframes(chunk.audio_int16_bytes)
            if chunk.phoneme_alignments:
                for a in chunk.phoneme_alignments:  # which sound is said when
                    length = a.num_samples / chunk.sample_rate
                    phonemes.append((a.phoneme, clock, clock + length))
                    clock += length
            else:
                aligned = False
                clock += len(chunk.audio_int16_bytes) / 2 / chunk.sample_rate
    return phonemes if aligned and phonemes else None


def speech_audio(text: str, character: str = None) -> bytes:
    """The character's voice saying text, as WAV bytes (used by the phone app)."""
    import io

    character = character or DEFAULT_CHARACTER
    clean = re.sub(r"[*_#`>]", "", text)
    buf = io.BytesIO()
    synthesize(clean, CHARACTERS.get(character, {}).get("voice", PIPER_VOICE), buf)
    return buf.getvalue()


def speak_natural(text: str, voice_name=None):
    import tempfile
    import winsound

    path = os.path.join(tempfile.gettempdir(), f"joey_voice_{threading.get_ident()}.wav")
    phonemes = synthesize(text, voice_name, path)
    try:
        try:
            on_speech(speech_envelope(path), 0.04, phonemes)
        except Exception as e:
            print(f"  [lip sync error: {e}]")
        winsound.PlaySound(path, winsound.SND_FILENAME)  # Windows' built-in player
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# Robotic Windows voice to use for each character if the natural voice isn't available
WINDOWS_VOICE_HINT = {"joey": "zira", "ryan": "david"}


def speak(text: str, character: str = None):
    """Say text out loud in the given character's voice (Joey if not given)."""
    character = character or DEFAULT_CHARACTER
    clean = re.sub(r"[*_#`>]", "", text)  # don't read out formatting symbols
    if not clean.strip():
        return
    with _speak_lock:
        if USE_NATURAL_VOICE:
            try:
                speak_natural(clean, CHARACTERS.get(character, {}).get("voice", PIPER_VOICE))
                return
            except Exception as e:
                print(f"  [natural voice unavailable ({e}), using Windows voice]")
        if threading.current_thread() is not threading.main_thread():
            try:  # Windows speech needs this when talking from a timer
                import comtypes
                comtypes.CoInitialize()
            except Exception:
                pass
        on_speech(None, 0, None)  # Windows voice: lips move without exact timing
        engine = pyttsx3.init()  # a fresh engine each time avoids a Windows freeze bug
        voices = engine.getProperty("voices")
        hint = WINDOWS_VOICE_HINT.get(character, "")
        match = [v for v in voices if hint and hint in v.name.lower()]
        if match:
            engine.setProperty("voice", match[0].id)
        elif VOICE_INDEX is not None and voices:
            engine.setProperty("voice", voices[VOICE_INDEX % len(voices)].id)
        engine.setProperty("rate", SPEAKING_RATE)
        engine.say(clean)
        engine.runAndWait()
        engine.stop()


def announce(text: str):
    """Used by timers and reminders so Joey says them out loud."""
    print(f"\n{NAME}: {text}")
    try:
        speak(text)
    except Exception as e:
        print(f"  [couldn't speak: {e}]")


joey_powers.announce = announce


def list_voices():
    print("\nFemale English voices you can put in PIPER_VOICE (in joey_voice.py):")
    for v in ["en_US-lessac-medium", "en_US-amy-medium", "en_US-hfc_female-medium",
              "en_US-kristin-medium", "en_GB-jenny_dioco-medium", "en_GB-alba-medium",
              "en_GB-cori-medium", "en_GB-southern_english_female-low"]:
        print(f"  {v}")
    print("Hear them all at https://rhasspy.github.io/piper-samples/\n")


# ---------- Putting it together ----------

def main():
    try:
        brain = Brain()
    except Exception:
        print("No API key found. Run:  setx ANTHROPIC_API_KEY \"your-key-here\"")
        print("Then close this window, open a new one, and try again.")
        return

    print("Checking your microphone, stay quiet for a second...")
    try:
        print(f"Using microphone: {sd.query_devices(MIC_DEVICE, 'input')['name']}")
        threshold = measure_background_noise()
    except Exception as e:
        print(f"Couldn't open the microphone: {e}")
        print("Check it's plugged in and allowed in Settings > Privacy & security > Microphone.")
        return

    print(f"\n{NAME} online.")
    print("Press Enter and speak, or type a message. Type 'voices' to list voices, 'quit' to exit.\n")
    speak(f"{NAME} online. How can I help?")

    while True:
        typed = input("> Press Enter to talk (or type): ").strip()
        if typed.lower() == "voices":
            list_voices()
            continue
        user_text = typed or listen(threshold)
        if not user_text:
            continue
        if user_text.lower().strip(" .!") in {"quit", "exit", "bye", "goodbye"}:
            print(f"{NAME}: Shutting down. Goodbye.")
            speak("Shutting down. Goodbye.")
            break
        try:
            reply = brain.ask(user_text)
        except Exception as e:
            reply = "Sorry, something went wrong."
            print(f"  [error: {e}]")
        print(f"{NAME}: {reply}\n")
        speak(reply)


if __name__ == "__main__":
    main()
