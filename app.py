"""
app.py — Auto Reels Studio (Streamlit)  ·  v14

What changed vs v13
-------------------
SPEED
- Settings/preview live in an `st.fragment`: moving a slider re-runs ONLY the panel, not the whole app
  (no re-hashing of the upload, no ffmpeg probe, no header rebuild).
- Whisper model is loaded once per process and reused (and warmed up in the background at start-up).
- Transcription uses greedy decoding by default (Transcription = fast). Switch to "accurate" for beam 5.
- Video preview is rendered only when you press "Render sample" (it used to re-render on every change).
- No animated full-page background / backdrop blur any more (they kept the GPU busy all the time).
- Fonts are downloaded in parallel and injected into the page once.

UI
- Everything fits in ONE screen (no browser scroll): header, 3 panels, fixed action bar.
- Phone preview scales with the window height and uses the real crop / zoom / blur / progress settings.
- Controls that don't apply to the chosen frame mode are hidden.
"""
import os
import re
import json
import base64
import hashlib
import shutil
import zipfile
import threading
import subprocess
import concurrent.futures
from urllib.parse import unquote

import streamlit as st

import engine

st.set_page_config(page_title="Auto Reels Studio", page_icon="🎬", layout="wide",
                   initial_sidebar_state="collapsed")

# ===================================================================== CSS ====
CSS = """
:root{--bg:#0c0e13;--panel:#13161d;--panel2:#181c25;--field:#0f1218;--line:#232836;--line2:#2f3547;
  --text:#e8eaf0;--muted:#8a91a6;--accent:#7c5cf0;--accent2:#9279ff;--ok:#34c38f;--bad:#ef5b5b;}

html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{
  height:100vh;overflow:hidden !important;background:var(--bg) !important;}
.stApp{font-family:Inter,"Segoe UI",system-ui,-apple-system,sans-serif;color:var(--text);}
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
#MainMenu,footer{display:none !important;}
.block-container{padding:12px 20px 0 20px !important;max-width:100% !important;}
[data-testid="stVerticalBlock"]{gap:.5rem !important;}
[data-testid="stHorizontalBlock"]{gap:.9rem !important;}
@media (max-width:900px){html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]
  {height:auto;overflow:auto !important;}}

/* ---------- header ---------- */
.brand{display:flex;align-items:center;gap:12px;}
.logo{width:36px;height:36px;border-radius:10px;background:var(--accent);display:flex;align-items:center;
  justify-content:center;color:#fff;font-weight:700;font-size:.85rem;letter-spacing:.02em;}
.bt{font-size:1.02rem;font-weight:650;color:var(--text);line-height:1.2;}
.bs{font-size:.74rem;color:var(--muted);line-height:1.3;}
.chip{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:7px;
  padding:1px 8px;margin-right:5px;font-size:.7rem;color:#c5cadb;}
.st-key-upbox{height:46px;overflow:hidden;}
.st-key-upbox [data-testid="stFileUploaderDropzone"]{padding:4px 12px !important;min-height:0 !important;
  height:44px;flex-direction:row;align-items:center;background:var(--field);
  border:1px dashed var(--line2);border-radius:10px;}
.st-key-upbox [data-testid="stFileUploaderDropzoneInstructions"] small,
.st-key-upbox [data-testid="stFileUploaderDropzoneInstructions"] svg{display:none !important;}
.st-key-upbox [data-testid="stFileUploaderDropzoneInstructions"] span{font-size:.78rem;color:var(--muted);}
.st-key-upbox button{min-height:30px !important;padding:0 12px !important;font-size:.78rem !important;}

/* ---------- panels ---------- */
.st-key-p_left,.st-key-p_center,.st-key-p_right{background:var(--panel);border:1px solid var(--line);
  border-radius:14px;padding:14px 16px 12px 16px;max-height:calc(100vh - 160px);overflow-y:auto;}
.st-key-p_left::-webkit-scrollbar,.st-key-p_right::-webkit-scrollbar{width:6px;}
.st-key-p_left::-webkit-scrollbar-thumb,.st-key-p_right::-webkit-scrollbar-thumb{background:var(--line2);
  border-radius:6px;}
.st-key-p_center{overflow:hidden;}
.sec{font-size:.78rem;color:var(--muted);margin:2px 0 4px 0;}
.hint{font-size:.72rem;color:var(--muted);}

/* ---------- widgets (compact) ---------- */
[data-testid="stWidgetLabel"]{min-height:0 !important;margin-bottom:1px !important;}
[data-testid="stWidgetLabel"] p,label p{font-size:.74rem !important;color:var(--muted) !important;
  font-weight:500 !important;}
div[data-baseweb="select"]>div{min-height:34px !important;background:var(--field) !important;
  border-color:var(--line) !important;font-size:.82rem !important;border-radius:9px !important;}
.stTextInput input,.stNumberInput input{min-height:34px !important;font-size:.82rem !important;
  background:var(--field) !important;border-radius:9px !important;}
[data-testid="stSlider"]{padding-top:0 !important;}
[data-testid="stSliderTickBarMin"],[data-testid="stSliderTickBarMax"]{display:none !important;}
[data-testid="stSliderThumbValue"]{font-size:.72rem !important;}
[data-testid="stColorPicker"]>div{gap:.5rem;}
.stCheckbox{padding:6px 0 0 0;}
.stCheckbox p{font-size:.8rem !important;color:var(--text) !important;}
[data-testid="stExpander"]{border:1px solid var(--line) !important;border-radius:10px !important;
  background:var(--panel2);}
[data-testid="stExpander"] summary{font-size:.8rem !important;padding:6px 10px !important;}
code{font-size:.72rem !important;}

.stButton,.stDownloadButton,[data-testid="stPopover"]{width:100%;}
.stButton>button,.stDownloadButton>button,[data-testid="stPopover"] button{width:100%;min-height:38px;border-radius:10px;font-size:.82rem;
  font-weight:600;border:1px solid var(--line2);background:var(--panel2);color:var(--text);
  transition:border-color .15s,background .15s;}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:var(--accent);color:#fff;
  background:#1d2230;}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{
  background:var(--accent);border-color:var(--accent);color:#fff;}
.stButton>button[kind="primary"]:hover,.stButton>button[data-testid="stBaseButton-primary"]:hover{
  background:var(--accent2);border-color:var(--accent2);}
.stButton>button:disabled,.stDownloadButton>button:disabled{opacity:.4;}

[data-testid="stSegmentedControl"]{width:100%;}
[data-testid="stSegmentedControl"] button{font-size:.76rem !important;padding:3px 10px !important;
  min-height:30px !important;}
[data-baseweb="tab-list"]{gap:4px;}
[data-baseweb="tab"]{height:34px;font-size:.8rem;}

/* ---------- fixed action bar ---------- */
.st-key-actionbar{position:fixed;left:0;right:0;bottom:0;z-index:60;background:rgba(12,14,19,.97);
  border-top:1px solid var(--line);padding:9px 20px 10px 20px;}
.stat{font-size:.78rem;color:var(--muted);}
.stat b{color:var(--text);font-weight:600;}
.stat.ok{color:var(--ok);} .stat.bad{color:var(--bad);}
.st-key-actionbar [data-testid="stProgress"] p{font-size:.74rem;}

/* ---------- empty state ---------- */
.hero{margin:6vh auto 0 auto;max-width:760px;text-align:center;}
.hero h1{font-size:1.7rem;font-weight:650;margin:0 0 6px 0;color:var(--text);}
.hero p{color:var(--muted);font-size:.92rem;margin:0 0 22px 0;}
.steps{display:flex;gap:12px;justify-content:center;flex-wrap:wrap;}
.step{flex:1 1 200px;max-width:240px;background:var(--panel);border:1px solid var(--line);
  border-radius:12px;padding:14px 16px;text-align:left;}
.step b{display:block;font-size:.88rem;margin-bottom:3px;color:var(--text);}
.step span{font-size:.78rem;color:var(--muted);}
.guide h4{color:#c9b8ff;margin:8px 0 3px 0;font-size:.88rem;}
.guide li,.guide p{color:#c3c7db;font-size:.8rem;margin-bottom:2px;}

/* ---------- phone preview (scales with window height) ---------- */
.phone{--ph:clamp(300px,calc(100vh - 262px),700px);position:relative;height:var(--ph);
  width:calc(var(--ph)*.573);margin:6px auto 0 auto;border-radius:calc(var(--ph)*.075);
  background:#1b1e29;border:1px solid #333a4f;box-shadow:0 14px 40px rgba(0,0,0,.55);}
.phone-screen{position:absolute;inset:calc(var(--ph)*.012);border-radius:calc(var(--ph)*.064);
  overflow:hidden;background:#000;container-type:size;}
.island{position:absolute;top:1.1cqh;left:50%;transform:translateX(-50%);width:24cqw;height:2.6cqh;
  background:#000;border-radius:3cqh;z-index:9;}
.pv-abs{position:absolute;inset:0;width:100%;height:100%;}
.pv-cap{position:absolute;left:4cqw;right:4cqw;text-align:center;font-weight:700;line-height:1.18;z-index:5;}
.pv-ov{position:absolute;left:5cqw;right:5cqw;text-align:center;font-weight:700;line-height:1.18;z-index:5;}
.pv-bar{position:absolute;top:0;left:0;z-index:6;animation:pvbar 5s linear infinite;}
.pv-pop{display:inline-block;animation:pvpop 1.3s ease-out infinite;}
.pv-fade{display:inline-block;animation:pvfade 1.3s ease-in-out infinite;}
.pv-zoom{animation:pvzoom 6s ease-in-out infinite alternate;}
@keyframes pvbar{from{width:0}to{width:100%}}
@keyframes pvpop{0%{transform:scale(.8)}18%,100%{transform:scale(1)}}
@keyframes pvfade{0%,100%{opacity:.15}25%,75%{opacity:1}}
@keyframes pvzoom{from{transform:scale(1)}to{transform:scale(1.1)}}
@media (prefers-reduced-motion:reduce){.pv-bar,.pv-pop,.pv-fade,.pv-zoom{animation:none !important;}}
"""

# ================================================================ constants ====
WORK = "work"
OUT = os.path.join(WORK, "out")
os.makedirs(WORK, exist_ok=True)

TABS = ["General", "Frame", "Captions", "Motion", "Colors", "Audio", "Clips"]

ALLOWED = {
    "mode": ["reels", "full_video", "transcribe_only"],
    "language": ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"],
    "model_size": ["tiny", "base", "small", "medium"],
    "accuracy": ["fast", "accurate"],
    "FONT": ["auto"] + engine.FONT_CHOICES,
    "caption_style": ["karaoke", "plain", "none"],
    "caption_anim": ["pop", "fade", "none"],
    "highlight_mode": ["color", "box"],
    "caption_pos": ["bottom", "middle"],
    "frame_mode": ["fit_blur", "fit_color", "crop"],
    "overlay_pos": ["top", "bottom"],
    "original_audio": ["keep", "mute"],
    "preview_mode": ["frame", "video"],
    "privacy": ["private", "unlisted", "public"],
}

DEFAULTS = dict(mode="reels", language="auto", model_size="small", accuracy="fast", FONT="auto",
                caption_style="karaoke", caption_anim="pop", caption_box=False, caption_box_opacity=0.6,
                caption_size=62, caption_color="#FFFFFF", highlight_color="#FFD400", highlight_mode="color",
                caption_uppercase=False, caption_max_words=4, caption_pos="bottom", caption_margin=230,
                caption_outline=4, slow_zoom=False, fade=False, progress_bar=True, progress_color="#FFD400",
                frame_mode="fit_blur", bg_color="#101020", blur_strength=30, crop_zoom=1.0, crop_x=0.5,
                crop_y=0.5, border=False, border_color="#FFD400", border_width=14,
                overlay_text="", overlay_pos="top", overlay_color="#FFD400", overlay_size=54,
                original_audio="keep", original_volume=1.0, music_volume=0.15, min_dur=20, max_dur=60,
                max_clips=0, workers=2, preview_mode="frame", privacy="private")

SETTINGS_FILE = os.path.join(WORK, "settings.json")
FONT_FILES = {"Poppins": "Poppins-Bold.ttf", "Anton": "Anton-Regular.ttf", "Montserrat": "Montserrat.ttf",
              "Bebas Neue": "BebasNeue-Regular.ttf", "Noto Sans Devanagari": "NotoSansDevanagari.ttf"}

GUIDE = """
<div class="guide">
<h4>How to use</h4>
<ol>
<li><b>Upload</b> a video (top right).</li>
<li><b>Tune</b> it — pick a section on the left (Frame, Captions, Motion, Colors, Audio, Clips).</li>
<li><b>Preview</b> in the phone. It shows a real frame of your video with your settings.
Use <i>Video sample</i> for a real 5-second render.</li>
<li><b>Generate</b> (bottom bar) — transcribes and renders. Then <b>Download</b> or publish.</li>
</ol>
<h4>Good defaults</h4>
<ul>
<li><b>Mode</b>: <code>reels</code> = auto clips in 9:16 · <code>full_video</code> = whole video + captions.</li>
<li><b>Language</b>: set <code>hi</code> for Hindi / Hinglish (auto often mis-detects).</li>
<li><b>Whisper model</b>: <code>small</code>. <b>Transcription</b>: <code>fast</code> (use <code>accurate</code> only if needed).</li>
<li><b>Frame mode</b>: <code>fit_blur</code> for screen recordings.</li>
</ul>
<p>Settings save automatically. Reset is on the General section.</p>
</div>
"""


# ============================================================ settings state ====
def _coerce(k, v):
    d = DEFAULTS[k]
    try:
        if isinstance(d, bool):
            return bool(v)
        if isinstance(d, int):
            return int(v)
        if isinstance(d, float):
            return float(v)
        return str(v)
    except Exception:
        return d


def _load_saved():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


if "S" not in st.session_state:
    _S = dict(DEFAULTS)
    for _k, _v in _load_saved().items():
        if _k in DEFAULTS:
            _S[_k] = _coerce(_k, _v)
    for _k, _opts in ALLOWED.items():
        if _S.get(_k) not in _opts:
            _S[_k] = DEFAULTS[_k]
    st.session_state["S"] = _S
S = st.session_state["S"]          # ONE dict; survives tab switches (not a widget key)


def persist():
    blob = json.dumps({k: S[k] for k in DEFAULTS}, sort_keys=True)
    if st.session_state.get("_saved_blob") != blob:
        try:
            with open(SETTINGS_FILE, "w") as f:
                f.write(blob)
            st.session_state["_saved_blob"] = blob
        except Exception:
            pass


def reset_all():
    for k, v in DEFAULTS.items():
        S[k] = v
        st.session_state.pop("w_" + k, None)
    persist()


# widget helpers: seed once from S, write the returned value straight back into S
def _seed(k):
    st.session_state.setdefault("w_" + k, S[k])


def sel(k, label, c=st, **kw):
    _seed(k)
    S[k] = c.selectbox(label, ALLOWED[k], key="w_" + k, **kw)


def sld(k, label, lo, hi, step=None, c=st):
    _seed(k)
    S[k] = c.slider(label, lo, hi, step=step, key="w_" + k)


def chk(k, label, c=st):
    _seed(k)
    S[k] = c.checkbox(label, key="w_" + k)


def clr(k, label, c=st):
    _seed(k)
    S[k] = c.color_picker(label, key="w_" + k)


def num(k, label, lo, hi, c=st):
    _seed(k)
    S[k] = int(c.number_input(label, lo, hi, key="w_" + k))


# ================================================================ cached bits ====
def _warm():
    try:
        engine.get_model(DEFAULTS["model_size"])
    except Exception:
        pass


@st.cache_resource(show_spinner="Setting up fonts…")
def init_engine():
    fonts = engine.ensure_fonts(os.path.join(WORK, "fonts"))
    threading.Thread(target=_warm, daemon=True).start()      # preload Whisper while the user clicks around
    return fonts


@st.cache_resource(show_spinner=False)
def font_css(fonts_dir):
    """All preview fonts as @font-face, injected ONCE (not on every slider move)."""
    out = []
    for name, fname in FONT_FILES.items():
        p = os.path.join(fonts_dir, fname)
        if os.path.exists(p) and os.path.getsize(p) < 700_000:
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            out.append("@font-face{font-family:'PV_%s';src:url(data:font/ttf;base64,%s);font-weight:100 900;}"
                       % (name.replace(" ", ""), b64))
    return "".join(out)


def save_upload(u):
    """Save the upload to disk. Cheap key (name+size+first MB) — no full-file hashing."""
    try:
        buf = u.getbuffer()
    except Exception:
        buf = memoryview(u.read())
    h = hashlib.md5(f"{u.name}|{len(buf)}".encode() + bytes(buf[:1 << 20])).hexdigest()[:10]
    p = os.path.join(WORK, f"{h}_{u.name}")
    if not os.path.exists(p):
        with open(p, "wb") as f:
            f.write(buf)
    return p


def clean_stem(path):
    return re.sub(r"^[0-9a-f]{10}_", "", os.path.splitext(os.path.basename(path))[0])


def human(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def media_info(path):
    store = st.session_state.setdefault("_info", {})
    if path not in store:
        dur = 0.0
        try:
            err = subprocess.run([engine.ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
            m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
            if m:
                dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        except Exception:
            pass
        store[path] = {"size": os.path.getsize(path), "dur": dur}
    return store[path]


def _lang(S_):
    return None if S_["language"] == "auto" else S_["language"]


def _beam(S_):
    return 1 if S_["accuracy"] == "fast" else 5


@st.cache_data(show_spinner=False)
def frame_uri(video_path, t):
    out = os.path.join(WORK, f"frame_{hashlib.md5((video_path + str(t)).encode()).hexdigest()[:8]}.jpg")
    engine.extract_frame(video_path, t, out, width=480)
    return "data:image/jpeg;base64," + base64.b64encode(open(out, "rb").read()).decode()


@st.cache_data(show_spinner=False)
def preview_words(video_path, ss, dur, model_size, language, beam):
    """Real words from a short window so the preview captions match the real output."""
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pw.f32"))
    segs, _ = engine.transcribe(audio, model_size, language, beam_size=beam)
    return [w.strip() for s in segs for (_, _, w) in s["words"] if w.strip()][:12]


@st.cache_data(show_spinner=False)
def preview_video_b64(video_path, ss, dur, settings_json):
    S2 = json.loads(settings_json)
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pv.f32"))
    segs, _ = engine.transcribe(audio, S2["model_size"], _lang(S2), beam_size=_beam(S2))
    for s in segs:
        s["start"] += ss
        s["end"] += ss
        s["words"] = [(a + ss, b + ss, w) for (a, b, w) in s["words"]]
    out = os.path.join(WORK, "preview.mp4")
    engine.render_segment(video_path, segs, ss, ss + dur, out, S2, st.session_state["fonts"],
                          preset="ultrafast")
    small = out + ".small.mp4"
    subprocess.run([engine.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", out, "-vf", "scale=540:960",
                    "-crf", "31", "-preset", "veryfast", "-an", small], check=True)
    return "data:video/mp4;base64," + base64.b64encode(open(small, "rb").read()).decode()


def build_settings():
    Sx = dict(S)
    Sx["caption_font"] = ("Noto Sans Devanagari" if S["language"] in {"hi", "mr", "ne"}
                          else ("Poppins" if S["FONT"] == "auto" else S["FONT"]))
    Sx["music_path"] = st.session_state.get("music_path_saved", "")
    for k in ("min_dur", "max_dur", "max_clips", "workers"):
        Sx[k] = int(Sx[k])
    return Sx


# ============================================================== phone preview ====
def phone_html(Sx, frame=None, words=None, video=None):
    """Phone whose screen is in 'reel pixels' (1080x1920) via container-query units:
    cqw = 1% of screen width, cqh = 1% of screen height. So sizes match the real output."""
    cw = lambda px: "%.3fcqw" % (px / 1080 * 100)
    ch = lambda px: "%.3fcqh" % (px / 1920 * 100)

    layers = ""
    if video:
        layers = ("<video class='pv-abs' src='%s' autoplay muted loop playsinline "
                  "style='object-fit:cover'></video>" % video)
    elif frame:
        zoom = " pv-zoom" if Sx["slow_zoom"] else ""
        fm = Sx["frame_mode"]
        if fm == "fit_blur":
            layers = ("<div class='pv-abs%s'><img class='pv-abs' src='%s' style='object-fit:cover;"
                      "transform:scale(1.2);filter:blur(%s) brightness(.7)'>"
                      "<img class='pv-abs' src='%s' style='object-fit:contain'></div>"
                      % (zoom, frame, cw(Sx["blur_strength"] * 0.6), frame))
        elif fm == "fit_color":
            layers = ("<div class='pv-abs%s' style='background:%s'><img class='pv-abs' src='%s' "
                      "style='object-fit:contain'></div>" % (zoom, Sx["bg_color"], frame))
        else:
            ox, oy = Sx["crop_x"] * 100, Sx["crop_y"] * 100
            layers = ("<div class='pv-abs%s'><img class='pv-abs' src='%s' style='object-fit:cover;"
                      "object-position:%.0f%% %.0f%%;transform:scale(%s);transform-origin:%.0f%% %.0f%%'></div>"
                      % (zoom, frame, ox, oy, Sx["crop_zoom"], ox, oy))

    if video:       # the sample already has captions / bar / border burned in
        extra = ""
    else:
        fam = "PV_%s,system-ui,sans-serif" % Sx["caption_font"].replace(" ", "")
        o = Sx["caption_outline"] / 1080 * 100
        d = o * 0.72
        shadow = ",".join("%s %s 0 #000" % (a, b) for a, b in [
            ("%.3fcqw" % o, "0"), ("-%.3fcqw" % o, "0"), ("0", "%.3fcqw" % o), ("0", "-%.3fcqw" % o),
            ("%.3fcqw" % d, "%.3fcqw" % d), ("-%.3fcqw" % d, "%.3fcqw" % d),
            ("%.3fcqw" % d, "-%.3fcqw" % d), ("-%.3fcqw" % d, "-%.3fcqw" % d)]) if o > 0 else "none"
        cap = ""
        if Sx["caption_style"] != "none" and words:
            show = words[:max(1, int(Sx["caption_max_words"]))]
            if Sx["caption_uppercase"]:
                show = [w.upper() for w in show]
            hl = min(1, len(show) - 1)
            if Sx["caption_style"] == "karaoke":
                if Sx["highlight_mode"] == "box":
                    body = " ".join("<span style='background:%s;color:#000;padding:0 .25em;border-radius:.2em;"
                                    "text-shadow:none'>%s</span>" % (Sx["highlight_color"], w) if i == hl else w
                                    for i, w in enumerate(show))
                else:
                    body = " ".join("<span style='color:%s'>%s</span>" % (Sx["highlight_color"], w) if i == hl
                                    else w for i, w in enumerate(show))
            else:
                body = " ".join(show)
            box = ("background:rgba(0,0,0,%s);padding:%s %s;border-radius:%s;text-shadow:none;"
                   % (Sx["caption_box_opacity"], cw(8), cw(18), cw(14))) if Sx["caption_box"] else ""
            anim = {"pop": " pv-pop", "fade": " pv-fade"}.get(Sx["caption_anim"], "")
            pos = ("bottom:%s;" % ch(Sx["caption_margin"]) if Sx["caption_pos"] != "middle"
                   else "top:50%;transform:translateY(-50%);")
            cap = ("<div class='pv-cap' style='%sfont-family:%s;font-size:%s;color:%s;text-shadow:%s'>"
                   "<span class='%s' style='%s'>%s</span></div>"
                   % (pos, fam, cw(Sx["caption_size"] * 0.8), Sx["caption_color"], shadow,
                      anim.strip() or "pv-none", box, body))
        ov = ""
        if Sx["overlay_text"].strip():
            txt = Sx["overlay_text"].strip().replace("<", "&lt;").replace(">", "&gt;")
            pos = "top:%s;" % ch(130) if Sx["overlay_pos"] == "top" else "bottom:%s;" % ch(300)
            ov = ("<div class='pv-ov' style='%sfont-family:%s;font-size:%s;color:%s;text-shadow:%s'>%s</div>"
                  % (pos, fam, cw(Sx["overlay_size"] * 0.8), Sx["overlay_color"], shadow, txt))
        bar = ("<div class='pv-bar' style='height:%s;background:%s'></div>"
               % (ch(18), Sx["progress_color"])) if Sx["progress_bar"] else ""
        border = ("<div class='pv-abs' style='border:%s solid %s;z-index:7;box-sizing:border-box'></div>"
                  % (cw(Sx["border_width"]), Sx["border_color"])) if Sx["border"] else ""
        extra = bar + ov + cap + border
    return ("<div class='phone'><div class='phone-screen'><div class='island'></div>%s%s</div></div>"
            % (layers, extra))


# ============================================================== google helpers ====
def load_creds(token_path, scopes):
    if not os.path.exists(token_path):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        c = Credentials.from_authorized_user_file(token_path, scopes)
        if c.expired and c.refresh_token:
            c.refresh(Request())
        return c if c.valid else None
    except Exception:
        return None


def extract_code(text):
    text = text.strip()
    m = re.search(r"[?&]?code=([^&\s]+)", text)
    return unquote(m.group(1)) if m else text


def google_connect(name, scopes, token_path, ck):
    """Manual-code OAuth flow (works on hosted Streamlit, where localhost redirect can't be caught)."""
    if ck not in st.session_state:
        st.session_state[ck] = load_creds(token_path, scopes)
    if st.session_state[ck]:
        st.markdown(f"<span class='stat ok'>{name} connected</span>", unsafe_allow_html=True)
        return
    cs = st.session_state.get("cs_path")
    if not cs:
        st.markdown(f"<span class='hint'>Upload client_secret.json above first.</span>", unsafe_allow_html=True)
        return
    if st.button(f"Get {name} link", key=f"get_{ck}"):
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(cs, scopes=scopes, redirect_uri="http://localhost:8080/")
        url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        st.session_state[ck + "_flow"], st.session_state[ck + "_url"] = flow, url
    if st.session_state.get(ck + "_url"):
        st.markdown(f"[1 · Open & approve]({st.session_state[ck + '_url']})  \n"
                    "<span class='hint'>2 · Copy the code (or whole URL) from the address bar after redirect.</span>",
                    unsafe_allow_html=True)
        code = st.text_input("Code", key=f"code_{ck}", placeholder="paste code or full URL")
        if st.button(f"Connect {name}", key=f"con_{ck}") and code.strip():
            try:
                flow = st.session_state[ck + "_flow"]
                flow.fetch_token(code=extract_code(code))
                st.session_state[ck] = flow.credentials
                with open(token_path, "w") as f:
                    f.write(flow.credentials.to_json())
                st.rerun()
            except Exception as e:
                st.error(f"Connect failed: {e}")


# =================================================================== panels ====
def tab_general():
    c1, c2 = st.columns(2)
    sel("mode", "Mode", c1)
    sel("language", "Language", c2)
    sel("model_size", "Whisper model", c1)
    sel("accuracy", "Transcription", c2, help="fast = greedy decoding (2-3x faster). accurate = beam 5.")
    sel("FONT", "Caption font")
    st.button("Reset all settings", on_click=reset_all)
    st.markdown("<span class='hint'>Settings save automatically. Hindi/Marathi automatically use "
                "the Devanagari font.</span>", unsafe_allow_html=True)


def tab_frame():
    sel("frame_mode", "Frame mode")
    c1, c2 = st.columns(2)
    if S["frame_mode"] == "fit_blur":
        sld("blur_strength", "Background blur", 0, 80, c=c1)
    elif S["frame_mode"] == "fit_color":
        clr("bg_color", "Background colour", c1)
    else:
        sld("crop_zoom", "Zoom", 1.0, 3.0, 0.1, c1)
        sld("crop_x", "Crop X", 0.0, 1.0, 0.05, c2)
        sld("crop_y", "Crop Y", 0.0, 1.0, 0.05, c1)
    st.markdown("<div class='sec'>Border</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    chk("border", "Show border", c1)
    if S["border"]:
        sld("border_width", "Width", 2, 40, c=c2)
        clr("border_color", "Border colour", c1)


def tab_captions():
    c1, c2 = st.columns(2)
    sel("caption_style", "Style", c1)
    sel("caption_pos", "Position", c2)
    sld("caption_size", "Size", 30, 110, c=c1)
    sld("caption_max_words", "Words per line", 1, 8, c=c2)
    sld("caption_outline", "Outline", 0, 10, c=c1)
    sld("caption_margin", "Bottom margin", 60, 500, c=c2)
    sel("highlight_mode", "Highlight", c1)
    chk("caption_uppercase", "UPPERCASE", c2)
    chk("caption_box", "Background box", c1)
    if S["caption_box"]:
        sld("caption_box_opacity", "Box opacity", 0.0, 1.0, 0.05, c2)
    _seed("overlay_text")
    S["overlay_text"] = st.text_input("Overlay text", key="w_overlay_text", placeholder="e.g. Follow for more")
    sel("overlay_pos", "Overlay position", c1)
    sld("overlay_size", "Overlay size", 20, 110, c=c2)


def tab_motion():
    sel("caption_anim", "Caption animation")
    c1, c2 = st.columns(2)
    chk("slow_zoom", "Slow zoom", c1)
    chk("fade", "Fade in / out", c2)
    chk("progress_bar", "Progress bar", c1)
    st.markdown("<span class='hint'>The preview loops these effects so you can see them.</span>",
                unsafe_allow_html=True)


def tab_colors():
    c1, c2 = st.columns(2)
    clr("caption_color", "Caption text", c1)
    clr("highlight_color", "Highlight", c2)
    clr("overlay_color", "Overlay text", c1)
    clr("progress_color", "Progress bar", c2)
    clr("border_color", "Border", c1)
    clr("bg_color", "Background (fit_color)", c2)


def tab_audio():
    c1, c2 = st.columns(2)
    sel("original_audio", "Original audio", c1)
    sld("original_volume", "Original volume", 0.0, 2.0, 0.05, c2)
    mp = st.session_state.get("music_path_saved", "")
    if mp:
        st.markdown("<span class='chip'>%s</span>" % os.path.basename(mp).replace("music_", "", 1)[:40],
                    unsafe_allow_html=True)
        st.button("Remove music", on_click=lambda: st.session_state.update(music_path_saved=""))
    else:
        mf = st.file_uploader("Background music", type=["mp3", "m4a", "wav", "aac"], key="music_file")
        if mf is not None:
            mp = os.path.join(WORK, "music_" + mf.name)
            if not os.path.exists(mp):
                with open(mp, "wb") as f:
                    f.write(mf.getbuffer())
            st.session_state["music_path_saved"] = mp
            st.rerun(scope="fragment")
    sld("music_volume", "Music volume", 0.0, 1.0, 0.05)


def tab_clips():
    c1, c2 = st.columns(2)
    num("min_dur", "Min clip (s)", 5, 300, c1)
    num("max_dur", "Max clip (s)", 10, 600, c2)
    num("max_clips", "Max clips (0 = all)", 0, 100, c1)
    num("workers", "Parallel renders", 1, 8, c2)
    st.markdown("<span class='hint'>Clips are cut at topic changes inside your min/max range.</span>",
                unsafe_allow_html=True)


TAB_FN = {"General": tab_general, "Frame": tab_frame, "Captions": tab_captions, "Motion": tab_motion,
          "Colors": tab_colors, "Audio": tab_audio, "Clips": tab_clips}


def panel_preview(primary, dur_total):
    Sx = build_settings()
    top = st.columns([1.3, 1], vertical_alignment="center")
    _seed("preview_mode")
    with top[0]:
        pm = st.segmented_control("Preview", ALLOWED["preview_mode"], key="w_preview_mode",
                                  format_func=lambda x: "Frame" if x == "frame" else "Video sample",
                                  label_visibility="collapsed")
    S["preview_mode"] = pm or S["preview_mode"]

    slot = st.empty()
    t = min(8.0, max(0.0, dur_total / 2))
    try:
        frame = frame_uri(primary, t)
    except Exception as e:
        st.warning(f"Could not read a frame: {e}")
        return
    hindi = S["language"] in ("hi", "mr", "ne")
    fallback = ["आज", "हम", "बात", "करेंगे"] if hindi else ["Here", "is", "how", "it", "works"]

    if S["preview_mode"] == "video":
        sig = json.dumps({**{k: v for k, v in Sx.items() if k not in ("preview_mode", "privacy")},
                          "mode": "reels"}, sort_keys=True)
        with top[1]:
            go = st.button("Render sample", key="btn_pv")
        if go:
            with st.spinner("Rendering 5 s sample…"):
                try:
                    st.session_state["pv"] = (sig, preview_video_b64(primary, 0.0, 5.0, sig))
                except Exception as e:
                    st.error(f"Sample failed: {e}")
        pv = st.session_state.get("pv")
        if pv:
            slot.markdown(phone_html(Sx, video=pv[1]), unsafe_allow_html=True)
            if pv[0] != sig:
                st.markdown("<span class='hint'>Settings changed — render again to refresh.</span>",
                            unsafe_allow_html=True)
        else:
            slot.markdown(phone_html(Sx, frame, fallback), unsafe_allow_html=True)
            st.markdown("<span class='hint'>Press “Render sample” for a real 5-second clip.</span>",
                        unsafe_allow_html=True)
        return

    slot.markdown(phone_html(Sx, frame, fallback), unsafe_allow_html=True)      # instant
    if S["caption_style"] != "none":
        pmodel = S["model_size"] if S["model_size"] in ("tiny", "base", "small") else "small"
        try:
            words = preview_words(primary, 0.0, 6.0, pmodel, _lang(S), _beam(S))
        except Exception:
            words = None
        if words:
            slot.markdown(phone_html(Sx, frame, words), unsafe_allow_html=True)  # real words


def panel_right():
    t1, t2 = st.tabs(["Post details", "Publish"])
    with t1:
        det = st.session_state.get("details", [])
        if det:
            pick = st.selectbox("File", [d["file"] for d in det], label_visibility="collapsed")
            x = next(d for d in det if d["file"] == pick)
            body = f"{x['title']}\n\n{x['desc']}\n\n{x['tags']} #shorts #reels"
            try:
                st.code(body, language=None, wrap_lines=True)
            except TypeError:
                st.code(body, language=None)
        else:
            st.markdown("<span class='hint'>Titles, descriptions and hashtags for every generated "
                        "file will appear here after you press Generate.</span>", unsafe_allow_html=True)
    with t2:
        cs = st.file_uploader("client_secret.json (Google OAuth)", type=["json"], key="cs")
        if cs is not None:
            cp = os.path.join(WORK, "client_secret.json")
            with open(cp, "wb") as f:
                f.write(cs.getbuffer())
            st.session_state["cs_path"] = cp
        with st.expander("YouTube"):
            google_connect("YouTube", ["https://www.googleapis.com/auth/youtube.upload"],
                           os.path.join(WORK, "yt_token.json"), "yt_creds")
            _seed("privacy")
            S["privacy"] = st.selectbox("Privacy", ALLOWED["privacy"], key="w_privacy")
        with st.expander("Google Drive"):
            google_connect("Drive", ["https://www.googleapis.com/auth/drive.file"],
                           os.path.join(WORK, "drive_token.json"), "dr_creds")
            st.markdown("<span class='hint'>Enable the Drive API for the same project.</span>",
                        unsafe_allow_html=True)


@st.fragment
def studio():
    """Left: options · centre: phone · right: details/publish. Reruns on its own — fast."""
    primary = st.session_state["primary"]
    dur_total = media_info(primary)["dur"]
    left, center, right = st.columns([1.25, 0.85, 1.0], gap="medium")
    with left:
        with st.container(key="p_left"):
            st.session_state.setdefault("w_tab", "General")
            st.segmented_control("Section", TABS, key="w_tab", label_visibility="collapsed")
            tab = st.session_state.get("w_tab") or "General"
            TAB_FN[tab]()
    with center:
        with st.container(key="p_center"):
            panel_preview(primary, dur_total)
    with right:
        with st.container(key="p_right"):
            panel_right()
    persist()


# ============================================================ generate/publish ====
def run_generate(paths, slot):
    Sfull = build_settings()
    prog = slot.progress(0.0, text="Starting…")
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "transcripts"), exist_ok=True)
    fonts = st.session_state["fonts"]
    lang, beam = _lang(S), _beam(S)

    trans = {}
    store = st.session_state.setdefault("tr", {})
    for i, vp in enumerate(paths):
        stem = clean_stem(vp)
        key = f"{vp}|{S['model_size']}|{lang}|{beam}"
        if key not in store:
            def cb(frac, _s=stem, _i=i):
                prog.progress(min(1.0, (_i + frac) / len(paths)) * 0.6,
                              text=f"Transcribing {_s}… {int(frac * 100)}%")
            audio = engine.extract_audio(vp, out=os.path.join(WORK, "full.f32"))
            store[key], _ = engine.transcribe(audio, S["model_size"], lang, progress=cb, beam_size=beam)
        trans[vp] = store[key]
        with open(os.path.join(OUT, "transcripts", f"{stem}.txt"), "w", encoding="utf-8") as f:
            for s in trans[vp]:
                f.write(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text'].strip()}\n")

    tasks, details = [], []
    for vp in paths:
        stem = clean_stem(vp)
        segs = trans[vp]
        if S["mode"] == "transcribe_only":
            continue
        if S["mode"] == "full_video":
            os.makedirs(os.path.join(OUT, "captioned"), exist_ok=True)
            end = max((x["end"] for x in segs), default=0)
            out = os.path.join(OUT, "captioned", f"{stem}_captioned.mp4")
            tasks.append((vp, segs, 0.0, end, out))
            txt = engine.clip_text(segs, 0, end)
            details.append({"file": f"{stem}_captioned.mp4", "path": out, "title": txt[:90] or stem,
                            "desc": txt, "tags": engine.hashtags(txt)})
        else:
            clips = engine.find_clips(segs, Sfull["min_dur"], Sfull["max_dur"], max_clips=Sfull["max_clips"])
            os.makedirs(os.path.join(OUT, "reels", stem), exist_ok=True)
            for i, (s, e) in enumerate(clips):
                out = os.path.join(OUT, "reels", stem, f"reel_{i + 1:02d}.mp4")
                tasks.append((vp, segs, s, e, out))
                txt = engine.clip_text(segs, s, e)
                details.append({"file": f"{stem}/reel_{i + 1:02d}.mp4", "path": out,
                                "title": txt[:90] or f"Reel {i + 1}", "desc": txt, "tags": engine.hashtags(txt)})

    results = []
    if tasks:
        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=int(Sfull["workers"])) as ex:
            futs = [ex.submit(engine.render_segment, vp, sg, s, e, o, Sfull, fonts) for (vp, sg, s, e, o) in tasks]
            for f in concurrent.futures.as_completed(futs):
                results.append(f.result())
                done += 1
                prog.progress(0.6 + 0.4 * done / len(tasks), text=f"Rendering {done}/{len(tasks)}…")
    results.sort()

    with open(os.path.join(OUT, "post_details.txt"), "w", encoding="utf-8") as f:
        f.write("POST DETAILS\n" + "=" * 40 + "\n\n")
        for x in details:
            f.write(f"FILE: {x['file']}\nTITLE: {x['title']}\nDESCRIPTION:\n{x['desc']}\n"
                    f"HASHTAGS: {x['tags']} #shorts #reels\n" + "-" * 40 + "\n")
    zpath = os.path.join(WORK, "output.zip")
    with zipfile.ZipFile(zpath, "w") as z:                      # videos are already compressed -> store
        for root, _, files in os.walk(OUT):
            for fn in files:
                if fn.endswith(".ass"):
                    continue
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, OUT))
    st.session_state["results"], st.session_state["details"] = results, details
    st.session_state["last_msg"] = ("ok", f"Done — {len(results)} file(s) ready. Download or publish.")


def run_drive(slot):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    svc = build("drive", "v3", credentials=st.session_state["dr_creds"])
    media = MediaFileUpload(os.path.join(WORK, "output.zip"), resumable=True)
    f = svc.files().create(body={"name": "auto_reels_output.zip"}, media_body=media,
                           fields="id,webViewLink").execute()
    st.session_state["last_msg"] = ("ok", "Saved to Drive: " + f.get("webViewLink", ""))


def run_youtube(slot):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=st.session_state["yt_creds"])
    meta = {x["path"]: x for x in st.session_state.get("details", [])}
    files = [p for p in st.session_state["results"] if os.path.exists(p)]
    links = []
    for n, p in enumerate(files, 1):
        slot.progress(n / len(files), text=f"Uploading {n}/{len(files)} to YouTube…")
        m = meta.get(p, {})
        body = {"snippet": {"title": (m.get("title") or os.path.basename(p))[:95],
                            "description": m.get("desc", "") + "\n\n" + m.get("tags", ""), "categoryId": "22"},
                "status": {"privacyStatus": S["privacy"], "selfDeclaredMadeForKids": False}}
        r = yt.videos().insert(part="snippet,status", body=body,
                               media_body=MediaFileUpload(p, chunksize=-1, resumable=True)).execute()
        links.append(f"https://youtu.be/{r['id']}")
    st.session_state["last_msg"] = ("ok", "Uploaded: " + "  ".join(links))


@st.fragment
def action_bar():
    zpath = os.path.join(WORK, "output.zip")
    have = bool(st.session_state.get("results")) and os.path.exists(zpath)
    with st.container(key="actionbar"):
        c1, c2, c3, c4, c5 = st.columns([1.1, 1, 1, 1.15, 3], vertical_alignment="center")
        gen = c1.button("Generate", type="primary", key="btn_gen")
        if have:
            with open(zpath, "rb") as f:
                c2.download_button("Download .zip", f, file_name="output.zip")
        else:
            c2.button("Download .zip", disabled=True)
        drive = c3.button("Save to Drive", disabled=not have)
        yt = c4.button("Upload to YouTube", disabled=not have)
        slot = c5.empty()

        kind, msg = st.session_state.get("last_msg", ("", "Ready. Tune the options, then press Generate."))
        slot.markdown(f"<span class='stat {kind}'>{msg}</span>", unsafe_allow_html=True)

        try:
            if gen:
                run_generate(st.session_state["paths"], slot)
                st.rerun()
            if drive:
                if not st.session_state.get("dr_creds"):
                    st.session_state["last_msg"] = ("bad", "Connect Drive first: right panel → Publish.")
                else:
                    slot.markdown("<span class='stat'>Uploading to Drive…</span>", unsafe_allow_html=True)
                    run_drive(slot)
                st.rerun()
            if yt:
                if not st.session_state.get("yt_creds"):
                    st.session_state["last_msg"] = ("bad", "Connect YouTube first: right panel → Publish.")
                else:
                    run_youtube(slot)
                st.rerun()
        except Exception as e:
            if type(e).__name__ in ("RerunException", "StopException"):
                raise
            st.session_state["last_msg"] = ("bad", f"Failed: {str(e)[:160]}")
            st.rerun()


# ===================================================================== main ====
def main():
    fonts = init_engine()
    st.session_state["fonts"] = fonts
    st.markdown(f"<style>{CSS}{font_css(fonts)}</style>", unsafe_allow_html=True)

    ukey = st.session_state.setdefault("ukey", 0)
    h1, h2, h3 = st.columns([2.6, 0.9, 1.7], vertical_alignment="center")
    info = h1.empty()
    with h2:
        hc = st.columns(2)
        with hc[0].popover("Help"):
            st.markdown(GUIDE, unsafe_allow_html=True)
        clear = hc[1].button("Clear", key="btn_clear",
                             disabled=not st.session_state.get("paths"))
    with h3:
        with st.container(key="upbox"):
            uploads = st.file_uploader("Upload video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                                       accept_multiple_files=True, label_visibility="collapsed",
                                       key=f"up_{ukey}")
    if clear:
        st.session_state["ukey"] = ukey + 1
        for k in ("paths", "primary", "results", "details", "pv", "last_msg"):
            st.session_state.pop(k, None)
        st.rerun()

    brand = ('<div class="brand"><div class="logo">AR</div><div><div class="bt">Auto Reels Studio</div>'
             '<div class="bs">%s</div></div></div>')
    if not uploads:
        st.session_state.pop("paths", None)
        info.markdown(brand % "Upload, tune, preview, generate.", unsafe_allow_html=True)
        st.markdown(
            '<div class="hero"><h1>Turn long videos into captioned reels</h1>'
            '<p>Upload a video from the top-right corner to begin.</p><div class="steps">'
            '<div class="step"><b>1 · Upload</b><span>MP4, MOV, MKV, WebM or AVI up to 2 GB.</span></div>'
            '<div class="step"><b>2 · Tune</b><span>Frame, captions, colours, audio and clip length.</span></div>'
            '<div class="step"><b>3 · Generate</b><span>Auto-cut clips with word-by-word captions.</span></div>'
            '</div></div>', unsafe_allow_html=True)
        return

    paths = [save_upload(u) for u in uploads]
    st.session_state["paths"], st.session_state["primary"] = paths, paths[0]
    mi = media_info(paths[0])
    chips = (f'<span class="chip">{clean_stem(paths[0])[:30]}</span>'
             f'<span class="chip">{human(mi["size"])}</span><span class="chip">{mi["dur"] / 60:.1f} min</span>')
    if len(paths) > 1:
        chips += f'<span class="chip">+{len(paths) - 1} more</span>'
    info.markdown(brand % chips, unsafe_allow_html=True)

    studio()
    action_bar()


try:
    main()
except Exception as _e:
    if type(_e).__name__ in ("StopException", "RerunException"):
        raise
    st.error("App error — please send this message:")
    st.exception(_e)
