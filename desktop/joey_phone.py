"""
JOEY & RYAN - phone app (home Wi-Fi)
Talk to Joey and Ryan from your phone while it's on the same Wi-Fi as your PC, and hear their real voices.
It runs inside Joey on your PC (joey_app.py). Every page needs your private key from setup_phone.py,
so other people on your Wi-Fi can't use it. Nothing to install on the phone.

Setup once:  python setup_phone.py
"""

import io
import json
import secrets
import ssl
import threading
import time
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765          # normal page (home Wi-Fi)
SECURE_PORT = 8766   # secure page, so the phone allows the microphone
CONFIG_FILE = Path(__file__).parent / "joey_phone.json"
COLORS = {"joey": "#46b9ff", "ryan": "#ff9623"}
ACCENTS = {"joey": "#ffc43c", "ryan": "#5ad2ff"}


def load_config():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return cfg if cfg.get("key") else None
    except Exception:
        return None


def make_config():
    cfg = load_config() or {"key": secrets.token_urlsafe(24)}
    cfg["mode"] = "wifi"
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def local_ip():
    """This PC's address on your home network, e.g. 192.168.1.23."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 1))  # no data is sent; this just picks the Wi-Fi/Ethernet address
        return s.getsockname()[0]
    except Exception:
        return socket.gethostbyname(socket.gethostname())
    finally:
        s.close()


def make_icon():
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (512, 512), (10, 14, 23))
        d = ImageDraw.Draw(img)
        d.ellipse([56, 56, 456, 456], outline=(70, 185, 255), width=26)
        d.arc([120, 120, 392, 392], 200, 340, fill=(255, 150, 35), width=22)
        d.arc([120, 120, 392, 392], 20, 160, fill=(255, 196, 60), width=22)
        d.ellipse([196, 196, 316, 316], fill=(215, 230, 245))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    except Exception:
        return b""


class Job:
    def __init__(self):
        self.lines, self.done, self.error = [], False, None


class PhoneServer:
    def __init__(self, ui, brains, brain_lock, duet):
        from joey import CHARACTERS
        from joey_remote import Router
        self.characters = CHARACTERS
        self.ui = ui
        self.router = Router(brains, brain_lock, duet)
        cfg = load_config()
        self.key = cfg["key"]
        self.wifi = cfg.get("mode", "wifi") == "wifi"   # open to the home network (not just this PC)
        self.secure = not self.wifi
        self.jobs, self.audio = {}, {}
        self.icon = make_icon()
        self.ca_cert = None

    # ----- answering a message -----
    def run_job(self, job, text):
        import joey_voice

        def out_line(who, line, sources):
            audio_id = None
            try:
                if joey_voice.USE_NATURAL_VOICE:
                    audio_id = uuid.uuid4().hex
                    self.audio[audio_id] = (time.time(), joey_voice.speech_audio(line, who))
            except Exception as e:
                print(f"  [phone voice failed: {e}]")
                audio_id = None
            name = self.characters[who]["name"]
            job.lines.append({"who": who, "name": name, "text": line,
                              "audio": f"/audio/{audio_id}.wav" if audio_id else None,
                              "sources": [[t, u] for t, u in (sources or [])[:4]]})
            if self.ui:
                self.ui.joey(f"📱 {name}: {line}")

        try:
            if self.ui:
                self.ui.you(f"📱 {text}")
            self.router.handle(text, out_line)
        except Exception as e:
            import traceback
            job.error = f"{e.__class__.__name__}: {e}"
            print(f"  [phone message failed: {job.error}]")
            traceback.print_exc()
        job.done = True
        # tidy up old audio and finished jobs
        cutoff = time.time() - 600
        for k in [k for k, (t, _) in self.audio.items() if t < cutoff]:
            self.audio.pop(k, None)

    def state(self):
        return {"who": self.router.who,
                "characters": {k: {"name": c["name"], "color": COLORS.get(k, "#46b9ff"),
                                   "accent": ACCENTS.get(k, "#ffc43c")} for k, c in self.characters.items()}}

    # ----- web server -----
    def handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _authorised(self):
                query = parse_qs(urlparse(self.path).query)
                if query.get("key", [""])[0] == server.key:
                    return "set"
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                return "ok" if "joey_key" in cookie and cookie["joey_key"].value == server.key else None

            def _send(self, code, body, ctype="application/json", extra=None):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode("utf-8")
                elif isinstance(body, str):
                    body = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/manifest.webmanifest":
                    return self._send(200, MANIFEST, "application/manifest+json")
                if path == "/icon.png":
                    return self._send(200, server.icon, "image/png")
                if path == "/joey-ca.crt" and server.ca_cert:   # the certificate to install on the phone
                    return self._send(200, server.ca_cert, "application/x-x509-ca-cert",
                                      {"Content-Disposition": 'attachment; filename="Joey-Home.crt"'})
                auth = self._authorised()
                if not auth:
                    return self._send(403, LOCKED_PAGE, "text/html; charset=utf-8")
                cookie_header = None
                if auth == "set":  # remember this phone (Lax so it also works when opened from the Camera app)
                    secure = server.secure or isinstance(self.connection, ssl.SSLSocket)
                    cookie_header = {"Set-Cookie": f"joey_key={server.key}; Max-Age=31536000; Path=/; HttpOnly; "
                                                   f"SameSite=Lax" + ("; Secure" if secure else "")}
                    if path == "/mic-setup":
                        return self._send(200, server.mic_page(), "text/html; charset=utf-8", cookie_header)
                    if path != "/":
                        return self._send(302, "", "text/plain", {"Location": "/", **cookie_header})
                if path == "/":
                    return self._send(200, PAGE, "text/html; charset=utf-8", cookie_header)
                if path == "/mic-setup":
                    return self._send(200, server.mic_page(), "text/html; charset=utf-8")
                if path == "/api/state":
                    return self._send(200, server.state())
                if path.startswith("/api/job/"):
                    job = server.jobs.get(path.rsplit("/", 1)[-1])
                    if not job:
                        return self._send(404, {"error": "unknown"})
                    start = int(parse_qs(urlparse(self.path).query).get("from", ["0"])[0])
                    return self._send(200, {"lines": job.lines[start:], "done": job.done,
                                            "error": job.error, "who": server.router.who})
                if path.startswith("/audio/"):
                    item = server.audio.get(path[7:].replace(".wav", ""))
                    if not item:
                        return self._send(404, b"", "text/plain")
                    return self._send(200, item[1], "audio/wav")
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                if not self._authorised():
                    return self._send(403, {"error": "locked"})
                if urlparse(self.path).path != "/api/message":
                    return self._send(404, {"error": "not found"})
                length = min(int(self.headers.get("Content-Length", "0") or 0), 64_000)  # cap uploads
                try:
                    text = (json.loads(self.rfile.read(length) or b"{}").get("text") or "").strip()
                except Exception:
                    text = ""
                if not text:
                    return self._send(400, {"error": "empty"})
                job_id = uuid.uuid4().hex
                job = server.jobs[job_id] = Job()
                threading.Thread(target=server.run_job, args=(job, text[:2000]), daemon=True).start()
                return self._send(200, {"job": job_id})

        return Handler

    def mic_page(self):
        ip = local_ip()
        voice_link = f"https://{ip}:{SECURE_PORT}/?key={self.key}" if self.ca_cert else ""
        return MIC_PAGE.replace("{VOICE_LINK}", voice_link).replace("{HAS_CERT}", "1" if self.ca_cert else "")

    def serve(self):
        host = "0.0.0.0" if self.wifi else "127.0.0.1"   # home Wi-Fi, or only this PC
        httpd = ThreadingHTTPServer((host, PORT), self.handler())
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        where = f"http://{local_ip()}:{PORT}" if self.wifi else f"port {PORT}"
        print(f"  [phone app ready at {where}]")
        if self.wifi:
            self.serve_secure(host)
        return httpd

    def serve_secure(self, host):
        """The https door, so the phone lets the page use the microphone."""
        try:
            import joey_certs
            cert, key = joey_certs.server_cert_for(local_ip())
            self.ca_cert = joey_certs.CA_CERT.read_bytes()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            httpsd = ThreadingHTTPServer((host, SECURE_PORT), self.handler())
            httpsd.socket = context.wrap_socket(httpsd.socket, server_side=True)
            threading.Thread(target=httpsd.serve_forever, daemon=True).start()
            print(f"  [phone voice app ready at https://{local_ip()}:{SECURE_PORT}]")
        except ImportError:
            print("  [for voice on the phone, run: pip install cryptography]")
        except Exception as e:
            print(f"  [secure phone page unavailable: {e}]")


def start(ui, brains, brain_lock, duet):
    return PhoneServer(ui, brains, brain_lock, duet).serve()


MANIFEST = json.dumps({
    "name": "Joey & Ryan", "short_name": "Joey", "start_url": "/", "display": "standalone",
    "background_color": "#0a0e17", "theme_color": "#0a0e17",
    "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png"}],
})

MIC_PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Turn on voice</title>
<style>
 body{background:#0a0e17;color:#e8ecf4;font-family:-apple-system,system-ui,sans-serif;margin:0;padding:22px 20px 40px;line-height:1.45}
 h2{margin:0 0 6px} p{color:#aab3c5} ol{padding-left:20px} li{margin:10px 0}
 .btn{display:block;text-align:center;background:#46b9ff;color:#0a0e17;font-weight:600;text-decoration:none;
      padding:14px;border-radius:14px;margin:14px 0} .btn.alt{background:#1d2638;color:#e8ecf4}
 b{color:#fff} .step{background:#121826;border-radius:14px;padding:4px 16px;margin:14px 0}
</style></head><body>
<h2>🎤 Turn on voice</h2>
<p>Phones only let a page use the microphone over a secure link. Your PC made its own security
certificate for this. Install it once (about 2 minutes) and then just tap the mic and talk.</p>
<div class="step"><ol>
<li>Tap <b>Download certificate</b> below, then tap <b>Allow</b>.</li>
<li>Open <b>Settings</b>. Tap <b>Profile Downloaded</b> near the top (or <b>General → VPN &amp; Device Management</b>) → <b>Joey Home Certificate</b> → <b>Install</b>.</li>
<li>Then <b>Settings → General → About → Certificate Trust Settings</b> → switch <b>ON</b> “Joey Home Certificate”.</li>
<li>Come back here and tap <b>Open Joey with voice</b>. Then <b>Share → Add to Home Screen</b>.</li>
</ol></div>
<a class="btn alt" href="/joey-ca.crt">1. Download certificate</a>
<a class="btn" id="go" href="{VOICE_LINK}">2. Open Joey with voice</a>
<p style="font-size:13px">Android: open the downloaded file, or Settings → Security → Encryption &amp; credentials →
Install a certificate → CA certificate.<br>The certificate only works for your PC at home; nothing leaves your network.</p>
<script>if(!"{HAS_CERT}"){document.body.innerHTML='<h2>Almost</h2><p>On your PC run <b>pip install cryptography</b> and restart Joey, then reload this page.</p>';}</script>
</body></html>"""

LOCKED_PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<body style="background:#0a0e17;color:#cfd6e4;font-family:system-ui;padding:32px;text-align:center">
<h2>Joey &amp; Ryan</h2><p>Open the link shown by <b>setup_phone.py</b> on your PC to connect this phone.</p></body>"""

PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0a0e17">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Joey">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon.png">
<title>Joey &amp; Ryan</title>
<style>
  :root { --bg:#0a0e17; --panel:#121826; --text:#e8ecf4; --muted:#7d879c; --c:#46b9ff; }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  html,body { margin:0; height:100%; background:var(--bg); color:var(--text);
    font-family:-apple-system,system-ui,"Segoe UI",Roboto,sans-serif; overflow:hidden; }
  .app { display:flex; flex-direction:column; height:100%; padding:env(safe-area-inset-top) 16px
    calc(12px + env(safe-area-inset-bottom)); max-width:560px; margin:0 auto; }
  .tabs { display:flex; gap:8px; justify-content:center; padding-top:12px; }
  .tab { border:1px solid #243049; background:transparent; color:var(--muted); padding:7px 18px;
    border-radius:999px; font-size:15px; }
  .tab.on { color:var(--bg); background:var(--c); border-color:var(--c); font-weight:600; }
  .stage { position:relative; flex:0 0 auto; display:flex; justify-content:center; margin-top:8px; }
  canvas { width:min(78vw,330px); height:min(78vw,330px); }
  .status { text-align:center; color:var(--muted); font-size:14px; min-height:20px; margin-top:2px; }
  .log { flex:1 1 auto; overflow-y:auto; margin:10px 0; display:flex; flex-direction:column; gap:8px;
    -webkit-mask-image:linear-gradient(to bottom,transparent 0,#000 18px); padding-top:14px; }
  .msg { padding:9px 13px; border-radius:14px; max-width:88%; line-height:1.38; font-size:15px; }
  .me { align-self:flex-end; background:#1d2638; color:#cfd6e4; }
  .bot { align-self:flex-start; background:var(--panel); border-left:3px solid var(--mc,#46b9ff); }
  .bot b { color:var(--mc,#46b9ff); font-weight:600; }
  .src { margin-top:5px; font-size:12px; color:var(--muted); }
  .src a { color:#6fb6ff; margin-right:8px; }
  .bar { display:flex; align-items:center; gap:10px; }
  .bar input { flex:1; background:var(--panel); border:1px solid #1f2738; color:var(--text);
    border-radius:999px; padding:12px 16px; font-size:16px; outline:none; }
  .mic { width:66px; height:66px; border-radius:50%; border:none; background:var(--c); color:var(--bg);
    display:grid; place-items:center; flex:0 0 auto; box-shadow:0 0 22px -4px var(--c); }
  .mic.live { animation:pulse 1.1s infinite; background:#ff4d6d; box-shadow:0 0 26px -2px #ff4d6d; }
  .mic svg { width:28px; height:28px; }
  @keyframes pulse { 50% { transform:scale(1.08); } }
  .hint { text-align:center; color:var(--muted); font-size:12px; margin-top:6px; }
</style></head>
<body><div class="app">
  <div class="tabs" id="tabs"></div>
  <div class="stage"><canvas id="ring" width="660" height="660"></canvas></div>
  <div class="status" id="status">Tap the mic and talk</div>
  <div class="log" id="log"></div>
  <form class="bar" id="form">
    <input id="text" placeholder="Type a message…" autocomplete="off" enterkeyhint="send">
    <button class="mic" id="mic" type="button" aria-label="Talk">
      <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-2.08A7 7 0 0 0 19 12h-2Z"/></svg>
    </button>
  </form>
  <div class="hint" id="hint"></div>
</div>
<script>
if (location.search.includes("key=")) history.replaceState(null, "", "/");  // keep the key out of view
const $ = s => document.querySelector(s);
let chars = {}, who = "joey", speaker = null, mode = "idle", level = 0;
const player = new Audio(); player.playsInline = true;
let queue = [], playing = false, actx = null, analyser = null, data = null;

function color(k){ return (chars[k] && chars[k].color) || "#46b9ff"; }
function setActive(k){ who = k; document.documentElement.style.setProperty("--c", color(k)); drawTabs(); }
function drawTabs(){
  $("#tabs").innerHTML = Object.entries(chars).map(([k,c]) =>
    `<button class="tab ${k===who?'on':''}" data-k="${k}">${c.name}</button>`).join("");
  document.querySelectorAll(".tab").forEach(b => b.onclick = () => {
    if (b.dataset.k !== who) send(`switch to ${chars[b.dataset.k].name}`);
  });
}
function status(t){ $("#status").textContent = t; }
function addMsg(cls, html, k){
  const d = document.createElement("div"); d.className = "msg " + cls; d.innerHTML = html;
  if (k) d.style.setProperty("--mc", color(k));
  $("#log").appendChild(d); $("#log").scrollTop = 1e9;
}
const esc = s => s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// ---- sound (unlocked by the first tap, needed on iPhone) ----
function unlock(){
  if (actx) return;
  try {
    actx = new (window.AudioContext || window.webkitAudioContext)();
    const src = actx.createMediaElementSource(player);
    analyser = actx.createAnalyser(); analyser.fftSize = 256;
    src.connect(analyser); analyser.connect(actx.destination);
    data = new Uint8Array(analyser.frequencyBinCount);
  } catch(e) {}
  player.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";
  player.play().catch(()=>{});
}
function playNext(){
  if (playing || !queue.length){ if (!playing && mode==="speaking"){ mode="idle"; status("Tap the mic and talk"); } return; }
  const line = queue.shift(); playing = true; speaker = line.who; setActive(line.who);
  mode = "speaking"; status(`${line.name} speaking…`);
  if (!line.audio){ playing = false; setTimeout(playNext, 400); return; }
  player.src = line.audio;
  if (actx && actx.state === "suspended") actx.resume();
  player.play().catch(() => { playing = false; playNext(); });
}
player.onended = () => { playing = false; playNext(); };
function stopSpeaking(){ queue = []; player.pause(); playing = false; mode = "idle"; status("Tap the mic and talk"); }

// ---- talking to Joey & Ryan ----
async function send(text){
  text = text.trim(); if (!text) return;
  unlock(); stopSpeaking();
  addMsg("me", esc(text)); mode = "thinking"; status("Thinking…");
  try {
    const r = await fetch("/api/message", {method:"POST", headers:{"Content-Type":"application/json"},
                          body: JSON.stringify({text})});
    if (!r.ok) throw new Error(r.status === 403 ? "This phone isn't connected" : "PC didn't answer");
    const {job} = await r.json(); let seen = 0, done = false;
    while (!done){
      await new Promise(res => setTimeout(res, 350));
      const j = await (await fetch(`/api/job/${job}?from=${seen}`)).json();
      for (const line of j.lines){
        seen++;
        const src = (line.sources||[]).map(([t,u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(new URL(u).hostname.replace("www.",""))}</a>`).join("");
        addMsg("bot", `<b>${esc(line.name)}</b> ${esc(line.text)}` + (src ? `<div class="src">Sources: ${src}</div>` : ""), line.who);
        queue.push(line); playNext();
      }
      done = j.done; if (j.error) addMsg("bot", "Sorry, something went wrong on the PC: " + esc(j.error));
      if (done && mode === "thinking"){ mode = "idle"; status("Tap the mic and talk"); setActive(j.who); }
    }
  } catch(e) {
    mode = "idle"; status(/fetch|Load failed|NetworkError/i.test(e.message) ? "Can't reach your PC - same Wi-Fi? Is Joey running?" : e.message);
  }
}
$("#form").onsubmit = e => { e.preventDefault(); const t = $("#text"); send(t.value); t.value = ""; t.blur(); };

// ---- the microphone (speech is recognised by the phone itself) ----
// On home Wi-Fi (not a secure https link) phones don't allow the page's own microphone,
// so the mic button opens the keyboard - tap the 🎤 on the keyboard to talk.
const SR = window.isSecureContext ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
let rec = null;
if (!SR){
  $("#hint").innerHTML = '<a href="/mic-setup" style="color:#6fb6ff">🎤 Turn on voice (one-time setup)</a> · or use the 🎤 on your keyboard';
}
$("#mic").onclick = () => {
  unlock();
  if (mode === "speaking"){ stopSpeaking(); return; }
  if (!SR){ if (!window.isSecureContext) location.href = "/mic-setup"; else $("#text").focus(); return; }
  if (rec){ rec.stop(); return; }
  rec = new SR(); rec.lang = "en-AU"; rec.interimResults = true; rec.continuous = false;
  let finalText = "";
  rec.onstart = () => { $("#mic").classList.add("live"); mode = "listening"; status("Listening…"); };
  rec.onresult = e => {
    let interim = ""; finalText = "";
    for (const r of e.results){ if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript; }
    status(finalText || interim || "Listening…");
  };
  rec.onerror = e => { status(e.error === "not-allowed" ? "Allow the microphone for this page" : "Didn't catch that"); };
  rec.onend = () => {
    $("#mic").classList.remove("live"); rec = null;
    if (finalText.trim()) send(finalText); else if (mode === "listening"){ mode = "idle"; status("Tap the mic and talk"); }
  };
  rec.start();
};

// ---- the HUD ring ----
const cv = $("#ring"), g = cv.getContext("2d"), N = 420, pts = [];
for (let i=0;i<N;i++){ const y=1-2*(i+.5)/N, r=Math.sqrt(1-y*y), a=i*2.39996; pts.push([Math.cos(a)*r,y,Math.sin(a)*r]); }
let rot = 0, last = performance.now();
function hexA(h,a){ const n=parseInt(h.slice(1),16); return `rgba(${n>>16},${(n>>8)&255},${n&255},${a})`; }
function frame(t){
  const dt = Math.min(.05,(t-last)/1000); last = t;
  if (analyser && playing){ analyser.getByteTimeDomainData(data); let s=0; for (const v of data){ s+=(v-128)**2; } level += (Math.min(1,Math.sqrt(s/data.length)/40)-level)*.4; }
  else level *= .85;
  const speed = {idle:.3,listening:.9,thinking:2.4,speaking:.9}[mode]||.3; rot += dt*speed;
  const c = color(mode==="speaking"&&speaker?speaker:who), acc = (chars[who]&&chars[who].accent)||"#ffc43c";
  const W=660, cx=330, cy=330; g.clearRect(0,0,W,W); g.lineCap="round";
  const glow = (col,b)=>{ g.shadowColor=col; g.shadowBlur=b; };
  glow(c,18); g.strokeStyle=c; g.lineWidth=8;
  for (let k=0;k<4;k++){ const a0=rot*.35+k*Math.PI/2+.1; g.beginPath(); g.arc(cx,cy,262,a0,a0+1.15); g.stroke(); }
  g.lineWidth=2; g.globalAlpha=.55;
  for (let i=0;i<72;i++){ const a=-rot*.6+i*Math.PI/36, r0=i%6?226:218; g.beginPath();
    g.moveTo(cx+Math.cos(a)*r0,cy+Math.sin(a)*r0); g.lineTo(cx+Math.cos(a)*236,cy+Math.sin(a)*236); g.stroke(); }
  g.globalAlpha=1; const fill = .28+.6*(mode==="speaking"?level:mode==="listening"?.5:.25);
  for (let i=0;i<Math.floor(28*fill)+4;i++){ const a0=3.5+rot*.12+i*.17; g.beginPath();
    g.arc(cx,cy,190,a0,a0+.14); g.lineWidth=34; g.strokeStyle=hexA(c,.32); g.stroke(); }
  glow(acc,10); g.strokeStyle=acc; g.lineWidth=4; const ya=-rot*.9;
  g.beginPath(); g.arc(cx,cy,162,ya+2.6,ya+3.7); g.stroke();
  glow("#dff3ff",22+30*level); g.strokeStyle="#e9f6ff"; g.lineWidth=6+5*level;
  g.beginPath(); g.arc(cx,cy,144,0,7); g.stroke(); g.shadowBlur=0;
  const R = 118*(1+.07*level), ca=Math.cos(rot*.5), sa=Math.sin(rot*.5);
  for (const [x,y,z] of pts){ const X=x*ca+z*sa, Z=-x*sa+z*ca, d=(Z+1)/2;
    g.fillStyle=`rgba(215,230,245,${(.15+.75*d*d)*(.7+.6*level)})`; g.fillRect(cx+X*R,cy+y*R,2.4,2.4); }
  requestAnimationFrame(frame);
}
fetch("/api/state").then(r=>r.json()).then(s => { chars = s.characters; setActive(s.who);
  addMsg("bot", `<b>${esc(chars[s.who].name)}</b> Hi! Tap the mic and talk, or type below.`, s.who); });
requestAnimationFrame(frame);
</script></body></html>
"""
