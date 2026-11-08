"""
JOEY & RYAN - on your phone (Telegram)
Message your own private Telegram bot and Joey or Ryan reply - from anywhere, while your PC is on
and Joey is running. Only YOUR Telegram account can use it; everyone else is ignored.

Setup once:  python setup_telegram.py
Voice notes (talk to them and hear them answer):  pip install av
"""

import io
import json
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

VOICE_REPLIES = True        # when you send a voice note, they answer with a voice note too (plus the text)
LISTEN_LANGUAGE = "en-AU"   # accent for understanding your voice notes

CONFIG_FILE = Path(__file__).parent / "joey_telegram.json"
API = "https://api.telegram.org/bot{token}/{method}"


def load_config():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return cfg if cfg.get("token") and cfg.get("owner_id") else None
    except Exception:
        return None


def call(token, method, timeout=35, **params):
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(API.format(token=token, method=method), data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    if not out.get("ok"):
        raise RuntimeError(out.get("description", "Telegram error"))
    return out["result"]


def download_file(token, file_id):
    info = call(token, "getFile", timeout=20, file_id=file_id)
    url = f"https://api.telegram.org/file/bot{token}/{info['file_path']}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def _pcm(data, rate):
    """Any audio file -> 16-bit mono samples at the given rate (needs: pip install av)."""
    import av
    out = bytearray()
    resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
    with av.open(io.BytesIO(data)) as box:
        for frame in box.decode(audio=0):
            for f in resampler.resample(frame):
                out += f.to_ndarray().tobytes()
    for f in resampler.resample(None):
        out += f.to_ndarray().tobytes()
    return bytes(out)


def transcribe(data):
    """A Telegram voice note -> the words in it (or '' if nothing was understood)."""
    import speech_recognition as sr
    rate = 16000
    audio = sr.AudioData(_pcm(data, rate), rate, 2)
    try:
        return sr.Recognizer().recognize_google(audio, language=LISTEN_LANGUAGE).strip()
    except sr.UnknownValueError:
        return ""


def to_voice_note(wav_bytes):
    """WAV -> OGG/Opus, the format Telegram shows as a voice-note bubble."""
    import av
    out = io.BytesIO()
    resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
    with av.open(io.BytesIO(wav_bytes)) as src, av.open(out, "w", format="ogg") as dst:
        stream = dst.add_stream("libopus", rate=48000, layout="mono")
        stream.bit_rate = 32000
        frames = [f for frame in src.decode(audio=0) for f in resampler.resample(frame)]
        frames += resampler.resample(None)
        for f in frames:
            for packet in stream.encode(f):
                dst.mux(packet)
        for packet in stream.encode(None):
            dst.mux(packet)
    return out.getvalue()


class TelegramLink:
    """Listens for your messages and sends replies. on_message(text) runs for each message."""

    def __init__(self, config, on_message):
        self.token = config["token"]
        self.owner = int(config["owner_id"])
        self.chat = int(config.get("chat_id", self.owner))
        self.on_message = on_message
        self.offset = None
        self.running = False
        self._local = threading.local()   # remembers, per message, whether you sent a voice note

    def wants_voice(self):
        return VOICE_REPLIES and getattr(self._local, "voice", False)

    def send_voice(self, ogg_bytes):
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{self.chat}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"voice\"; filename=\"reply.ogg\"\r\n"
                f"Content-Type: audio/ogg\r\n\r\n").encode() + ogg_bytes + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(API.format(token=self.token, method="sendVoice"), data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read().decode("utf-8"))
        if not out.get("ok"):
            raise RuntimeError(out.get("description", "Telegram error"))

    def say(self, text, character):
        """Send text as a voice note in the character's voice (only when you spoke to them)."""
        if not self.wants_voice():
            return
        try:
            import joey_voice
            self.action("record_voice")
            self.send_voice(to_voice_note(joey_voice.speech_audio(text, character)))
        except ImportError:
            pass
        except Exception as e:
            print(f"  [telegram voice reply failed: {e}]")

    def action(self, what):
        try:
            call(self.token, "sendChatAction", timeout=10, chat_id=self.chat, action=what)
        except Exception:
            pass

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def send(self, text):
        text = (text or "").strip() or "(no reply)"
        for i in range(0, len(text), 4000):  # Telegram's limit is 4096 characters per message
            call(self.token, "sendMessage", chat_id=self.chat, text=text[i:i + 4000],
                 link_preview_options={"is_disabled": True})

    def typing(self):
        try:
            call(self.token, "sendChatAction", timeout=10, chat_id=self.chat, action="typing")
        except Exception:
            pass

    def _loop(self):
        # skip messages sent while Joey was off (they'd be stale)
        try:
            old = call(self.token, "getUpdates", timeout=15, offset=-1)
            if old:
                self.offset = old[-1]["update_id"] + 1
        except Exception as e:
            print(f"  [telegram: {e}]")
        print("  [phone link: listening for Telegram messages]")
        while self.running:
            try:
                params = {"timeout": 25, "allowed_updates": ["message"]}
                if self.offset is not None:
                    params["offset"] = self.offset
                for update in call(self.token, "getUpdates", **params):
                    self.offset = update["update_id"] + 1
                    msg = update.get("message") or {}
                    sender = (msg.get("from") or {}).get("id")
                    text = msg.get("text")
                    if sender != self.owner:
                        continue          # not you: ignore completely
                    sound = msg.get("voice") or msg.get("audio") or msg.get("video_note")
                    if sound and not text:
                        threading.Thread(target=self._handle_voice, args=(sound["file_id"],), daemon=True).start()
                        continue
                    if not text:
                        self.send("I can read text messages and voice notes.")
                        continue
                    threading.Thread(target=self._handle, args=(text,), daemon=True).start()
            except Exception as e:
                print(f"  [telegram connection problem: {e}; retrying]")
                time.sleep(5)

    def _handle_voice(self, file_id):
        self.action("typing")
        try:
            heard = transcribe(download_file(self.token, file_id))
        except ImportError:
            self.send("To understand voice notes, run  pip install av  on the PC and restart Joey. "
                      "Typing works in the meantime.")
            return
        except Exception as e:
            print(f"  [telegram voice note failed: {e}]")
            self.send("Sorry, I couldn't hear that voice note. Try again, or type it.")
            return
        if not heard:
            self.send("I couldn't make out any words in that one. Try again a bit closer to the mic?")
            return
        self.send(f"🎤 {heard}")
        self._local.voice = True
        try:
            self._handle(heard)
        finally:
            self._local.voice = False

    def _handle(self, text):
        try:
            self.on_message(text)
        except Exception as e:
            print(f"  [telegram message failed: {e}]")
            try:
                self.send("Sorry, something went wrong on the PC.")
            except Exception:
                pass
