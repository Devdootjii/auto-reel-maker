"""
app.py — Free Auto Reels Generator (Streamlit)  ·  v7

Layout (per the wireframe):
  [ logo + title ......................... upload video ]
  [ home | frame | captions | animations | colors | audio | clips | how to use ]
  [ options (left) | phone preview (center) | progress + other options (right) ]
  [ Generate video | Download | Save to Drive | Upload to YouTube ]
"""
import os
import re
import json
import base64
import hashlib
import zipfile
import inspect
import subprocess
import concurrent.futures

import streamlit as st

import engine

st.set_page_config(page_title="Free Auto Reels Generator", page_icon=None, layout="wide")

st.markdown("""
<style>
  /* ---------- animated, interactive background ---------- */
  html, body, [data-testid="stAppViewContainer"] {background:#07080f;}
  .stApp {
    background:
      radial-gradient(38% 45% at 18% 22%, rgba(124,77,255,.30), transparent 60%),
      radial-gradient(34% 40% at 82% 26%, rgba(224,85,155,.24), transparent 60%),
      radial-gradient(40% 45% at 52% 82%, rgba(34,211,238,.18), transparent 62%),
      linear-gradient(135deg,#07080f,#0d0b1a,#07080f);
    background-size: 200% 200%, 200% 200%, 200% 200%, 200% 200%;
    animation: floatbg 26s ease-in-out infinite;
  }
  @keyframes floatbg {
    0%   {background-position: 0% 0%,   100% 0%,   50% 100%, 0 0;}
    50%  {background-position: 28% 22%, 70% 34%,  38% 70%,  0 0;}
    100% {background-position: 0% 0%,   100% 0%,   50% 100%, 0 0;}
  }
  .stApp::before, .stApp::after {
    content:""; position:fixed; border-radius:50%; filter:blur(90px); opacity:.30;
    z-index:0; pointer-events:none;
  }
  .stApp::before {width:360px;height:360px;background:#7c4dff;top:-90px;left:-70px;
    animation: drift1 20s ease-in-out infinite;}
  .stApp::after  {width:300px;height:300px;background:#e0559b;bottom:-90px;right:-50px;
    animation: drift2 24s ease-in-out infinite;}
  @keyframes drift1 {0%,100%{transform:translate(0,0)}50%{transform:translate(70px,45px)}}
  @keyframes drift2 {0%,100%{transform:translate(0,0)}50%{transform:translate(-55px,-35px)}}

  /* ---------- fit everything in one screen ---------- */
  header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stAppToolbar"],
  [data-testid="stDecoration"], #MainMenu, footer {display:none !important;}
  .block-container {padding:.25rem .7rem .3rem .7rem !important; max-width:100% !important;}
  div[data-testid="stElementContainer"] {margin-bottom:0 !important;}
  div[data-testid="stVerticalBlock"] {gap:.15rem !important;}
  div[data-testid="stHorizontalBlock"] {gap:.5rem !important;}

  /* ---------- compact widgets ---------- */
  label p, div[data-testid="stWidgetLabel"] p {font-size:.72rem !important; color:#9aa0b8 !important;
      margin-bottom:0 !important;}
  div[data-testid="stWidgetLabel"] {margin-bottom:-2px !important;}
  div[data-baseweb="select"] > div {min-height:28px !important; font-size:.78rem !important;}
  .stTextInput input, .stNumberInput input {min-height:28px !important; font-size:.78rem !important;}
  .stSlider {padding:0 !important;}
  .stCheckbox {margin-top:-4px !important;}
  .stButton>button, .stDownloadButton>button {
      min-height:30px !important; padding:0 10px !important; font-size:.78rem !important;
      border-radius:10px; font-weight:600; border:1px solid #3a2f66;
      background:linear-gradient(90deg,#7c4dff,#e0559b); color:#fff; transition:.2s;}
  .stButton>button:hover, .stDownloadButton>button:hover {
      color:#fff; transform:translateY(-1px); box-shadow:0 6px 18px rgba(124,77,255,.45);}
  div[data-testid="stFileUploaderDropzone"] {padding:5px 10px !important; min-height:auto !important;}
  div[data-testid="stFileUploaderDropzone"] span, div[data-testid="stFileUploaderDropzone"] small
      {font-size:.72rem !important;}
  div[data-testid="stExpander"] {border:1px solid #272b48 !important; border-radius:12px !important;}
  div[data-testid="stExpander"] summary {font-size:.78rem !important; padding:4px 10px !important;}

  /* ---------- panels (Streamlit bordered containers) ---------- */
  div[data-testid="stVerticalBlockBorderWrapper"] {
      background:rgba(17,19,33,.92); border:1px solid #272b48 !important; border-radius:14px;
      padding:8px 11px !important; box-shadow:0 8px 26px rgba(0,0,0,.35); backdrop-filter:blur(8px);
      transition:.25s;}
  div[data-testid="stVerticalBlockBorderWrapper"]:hover {
      border-color:#3b3f68 !important; box-shadow:0 10px 30px rgba(124,77,255,.22);}
  div[data-testid="stVerticalBlockBorderWrapper"] > div {gap:.15rem !important;}
  .note {color:#7b8199; font-size:.68rem;}
  .panel {background:rgba(17,19,33,.92); border:1px solid #272b48; border-radius:14px;
          padding:10px 13px; margin-bottom:8px;}

  .hdr {display:flex; align-items:center; gap:10px;}
  .logo {width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;
         font-weight:800;color:#fff;background:linear-gradient(135deg,#7c4dff,#e0559b);font-size:.82rem;
         box-shadow:0 6px 18px rgba(124,77,255,.4);}
  .apptitle {font-size:1.1rem;font-weight:800;color:#eef0fa;}
  .appsub {color:#8b90a8;font-size:.7rem;}
  .guide h4 {color:#c9b8ff; margin:8px 0 4px 0;}
  .guide li, .guide p {color:#c3c7db; font-size:.82rem; margin-bottom:3px;}
  .guide b {color:#eef0fa;}
  div[data-testid="stSegmentedControl"] {background:rgba(17,19,33,.9); border:1px solid #272b48;
      border-radius:12px; padding:4px;}
  div[data-testid="stSegmentedControl"] button {font-size:.76rem !important; padding:2px 8px !important;}
  .stCodeBlock {margin-top:2px !important;}
  code {font-size:.72rem !important;}
</style>
""", unsafe_allow_html=True)

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))

TABS = ["Home", "Frame", "Captions", "Animations", "Colors", "Audio", "Clips", "How to use"]

PERSIST = ["mode", "language", "model_size", "FONT", "caption_style", "caption_anim", "caption_box",
           "caption_box_opacity", "caption_size", "caption_color", "highlight_color", "highlight_mode",
           "caption_uppercase", "caption_max_words", "caption_pos", "caption_margin", "caption_outline",
           "slow_zoom", "fade", "progress_bar", "progress_color", "frame_mode", "bg_color", "blur_strength",
           "crop_zoom", "crop_x", "crop_y", "border", "border_color", "border_width",
           "overlay_text", "overlay_pos", "overlay_color", "overlay_size",
           "original_audio", "original_volume", "music_volume", "min_dur", "max_dur", "max_clips", "workers",
           "privacy"]

DEFAULTS = dict(mode="reels", language="auto", model_size="small", FONT="auto", caption_style="karaoke",
                caption_anim="pop", caption_box=False, caption_box_opacity=0.6, caption_size=62,
                caption_color="#FFFFFF", highlight_color="#FFD400", highlight_mode="color",
                caption_uppercase=False, caption_max_words=4, caption_pos="bottom", caption_margin=230,
                caption_outline=4, slow_zoom=False, fade=False, progress_bar=True, progress_color="#FFD400",
                frame_mode="fit_blur", bg_color="#101020", blur_strength=30, crop_zoom=1.0, crop_x=0.5,
                crop_y=0.5, border=True, border_color="#FFD400", border_width=14,
                overlay_text="", overlay_pos="top", overlay_color="#FFD400", overlay_size=54,
                original_audio="keep", original_volume=1.0, music_volume=0.15, min_dur=20, max_dur=60,
                max_clips=0, workers=2, privacy="private")

ALLOWED = {
    "mode": ["reels", "full_video", "transcribe_only"],
    "language": ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"],
    "model_size": ["tiny", "base", "small", "medium"],
    "FONT": ["auto"] + engine.FONT_CHOICES,
    "caption_style": ["karaoke", "plain", "none"],
    "caption_anim": ["pop", "fade", "none"],
    "highlight_mode": ["color", "box"],
    "caption_pos": ["bottom", "middle"],
    "frame_mode": ["fit_blur", "fit_color", "crop"],
    "overlay_pos": ["top", "bottom"],
    "original_audio": ["keep", "mute"],
    "privacy": ["private", "unlisted", "public"],
}
RANGES = [("caption_size", 30, 110), ("caption_max_words", 1, 8), ("caption_outline", 0, 10),
          ("caption_margin", 60, 500), ("caption_box_opacity", 0.0, 1.0), ("blur_strength", 0, 80),
          ("crop_zoom", 1.0, 3.0), ("crop_x", 0.0, 1.0), ("crop_y", 0.0, 1.0), ("border_width", 0, 40),
          ("overlay_size", 20, 110), ("original_volume", 0.0, 2.0), ("music_volume", 0.0, 1.0),
          ("min_dur", 5, 300), ("max_dur", 10, 600), ("max_clips", 0, 100), ("workers", 1, 8)]

SETTINGS_FILE = os.path.join(WORK, "settings.json")


def load_saved():
    if os.path.exists(SETTINGS_FILE):
        try:
            return json.load(open(SETTINGS_FILE))
        except Exception:
            return {}
    return {}


def persist():
    try:
        json.dump({k: st.session_state.get(k) for k in PERSIST if k in st.session_state},
                  open(SETTINGS_FILE, "w"))
    except Exception:
        pass


_saved = load_saved()
for _k in PERSIST:
    st.session_state.setdefault(_k, _saved.get(_k, DEFAULTS[_k]))
for _k, _opts in ALLOWED.items():
    if st.session_state.get(_k) not in _opts:
        st.session_state[_k] = DEFAULTS[_k]
for _k, _lo, _hi in RANGES:
    try:
        _v = float(st.session_state.get(_k, DEFAULTS[_k]))
        if _v < _lo or _v > _hi:
            st.session_state[_k] = DEFAULTS[_k]
    except Exception:
        st.session_state[_k] = DEFAULTS[_k]


# -------------------------------------------------------------- helpers ----
def save_upload(u):
    try:
        data = u.getbuffer()
    except Exception:
        data = u.read()
    h = hashlib.md5(data).hexdigest()[:10]
    p = os.path.join(WORK, f"{h}_{u.name}")
    if not os.path.exists(p):
        open(p, "wb").write(data)
    return p


def get_duration(path):
    try:
        err = subprocess.run([engine.ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    except Exception:
        return 0.0


def grab_frame(video_path, t, out, width=360):
    fn = getattr(engine, "extract_frame", None)
    if callable(fn):
        try:
            if "width" in inspect.signature(fn).parameters:
                return fn(video_path, t, out, width=width)
            return fn(video_path, t, out)
        except Exception:
            pass
    subprocess.run([engine.ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(t), "-i", video_path,
                    "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", out], check=True)
    return out


def do_transcribe(audio, model_size, language, progress=None):
    try:
        return engine.transcribe(audio, model_size, language, progress=progress)
    except TypeError:
        return engine.transcribe(audio, model_size, language)


@st.cache_data(show_spinner=False)
def frame_uri(video_path, t):
    out = os.path.join(WORK, f"frame_{hashlib.md5((video_path+str(t)).encode()).hexdigest()[:8]}.jpg")
    grab_frame(video_path, t, out)
    return "data:image/jpeg;base64," + base64.b64encode(open(out, "rb").read()).decode()


FONT_FILES = {"Poppins": "Poppins-Bold.ttf", "Anton": "Anton-Regular.ttf", "Montserrat": "Montserrat.ttf",
              "Bebas Neue": "BebasNeue-Regular.ttf", "Noto Sans Devanagari": "NotoSansDevanagari.ttf"}


@st.cache_data(show_spinner=False)
def font_face(font_name):
    fname = FONT_FILES.get(font_name)
    if not fname:
        return ""
    p = os.path.join(FONTS, fname)
    if not os.path.exists(p) or os.path.getsize(p) > 300_000:
        return ""
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    return "@font-face{font-family:'PV';src:url(data:font/ttf;base64," + b64 + ");font-weight:700;}"


SAMPLE = {"hi": (["आज", "हम", "बात", "करेंगे", "क्रिकेट", "की"], 2),
          "default": (["Here", "is", "how", "it", "works", "for", "you"], 2)}


def preview_html(frame, S, lang, box_w=185):
    box_h = int(box_w * 16 / 9)
    words, hl = SAMPLE["hi"] if lang in ("hi", "mr", "ne") else SAMPLE["default"]
    if S.get("caption_uppercase"):
        words = [w.upper() for w in words]
    if S["frame_mode"] == "fit_blur":
        bg = ("background-image:url('" + frame + "');background-size:cover;background-position:center;"
              "filter:blur(" + str(int(S.get("blur_strength", 30) / 2.6)) + "px) brightness(.72);")
        fg = ("background-image:url('" + frame + "');background-size:contain;background-position:center;"
              "background-repeat:no-repeat;")
    elif S["frame_mode"] == "fit_color":
        bg = "background:" + S["bg_color"] + ";"
        fg = ("background-image:url('" + frame + "');background-size:contain;background-position:center;"
              "background-repeat:no-repeat;")
    else:
        bg = "background:#000;"
        fg = "background-image:url('" + frame + "');background-size:cover;background-position:center;"
    fs = max(8, round(S["caption_size"] * box_w / 1080 * 2.1))
    ow = max(1, round(S.get("caption_outline", 4) / 2))
    outline = ("text-shadow:-" + str(ow) + "px 0 #000," + str(ow) + "px 0 #000,0 -" + str(ow) + "px #000,"
               "0 " + str(ow) + "px #000;")
    op = float(S.get("caption_box_opacity", 0.6))
    cap_box = "background:rgba(0,0,0," + str(op) + ");padding:3px 9px;border-radius:7px;" if S["caption_box"] else ""
    cap = ""
    if S["caption_style"] != "none":
        if S["caption_style"] == "karaoke":
            if S.get("highlight_mode") == "box":
                body = " ".join(("<span style='background:" + S["highlight_color"] +
                                 ";color:#000;padding:0 3px;border-radius:4px;'>" + w + "</span>")
                                if i == hl else w for i, w in enumerate(words))
            else:
                body = " ".join(("<span style='color:" + S["highlight_color"] + "'>" + w + "</span>")
                                if i == hl else w for i, w in enumerate(words))
        else:
            body = " ".join(words)
        vpos = ("bottom:" + str(round(S.get("caption_margin", 230) * box_h / 1920)) + "%;"
                if S.get("caption_pos", "bottom") != "middle" else "top:47%;")
        cap = ("<div style='position:absolute;left:6%;right:6%;" + vpos + "text-align:center;"
               "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:" + str(fs) + "px;"
               "color:" + S["caption_color"] + ";" + outline + "'>"
               "<span style='" + cap_box + "'>" + body + "</span></div>")
    ov = ""
    if S["overlay_text"].strip():
        pos = "top:8%;" if S["overlay_pos"] == "top" else "bottom:22%;"
        ov = ("<div style='position:absolute;left:6%;right:6%;" + pos + "text-align:center;"
              "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:"
              + str(max(7, round(S.get("overlay_size", 54) * box_w / 1080 * 2.1))) + "px;"
              "color:" + S["overlay_color"] + ";" + outline + "'>" + S["overlay_text"] + "</div>")
    prog = ("<div style='position:absolute;top:0;left:0;height:5px;width:42%;background:"
            + S.get("progress_color", S["border_color"]) + ";'></div>") if S["progress_bar"] else ""
    bw = S["border_width"] if S["border"] else 0
    frame_css = ("position:relative;width:" + str(box_w) + "px;height:" + str(box_h) + "px;margin:0 auto;"
                 "border-radius:22px;overflow:hidden;border:" + str(bw) + "px solid " + S["border_color"] + ";"
                 "box-shadow:0 12px 34px rgba(0,0,0,.55);")
    return ("<style>" + font_face(S["caption_font"]) + "</style><div style='" + frame_css + "'>"
            "<div style='position:absolute;inset:0;" + bg + "'></div>"
            "<div style='position:absolute;inset:0;" + fg + "'></div>" + prog + ov + cap + "</div>")


def full_transcript(video_path, model_size, language, progress_cb=None):
    key = f"{video_path}|{model_size}|{language}"
    store = st.session_state.setdefault("tr", {})
    if key in store:
        return store[key]
    audio = engine.extract_audio(video_path, out=os.path.join(WORK, "full.f32"))
    segs, _ = do_transcribe(audio, model_size, language, progress_cb)
    store[key] = segs
    return segs


def G(k):
    return st.session_state.get(k, DEFAULTS[k])


def build_S(music_path):
    S = {k: G(k) for k in DEFAULTS}
    S["caption_font"] = "Noto Sans Devanagari" if G("language") in {"hi", "mr", "ne"} else \
                        ("Poppins" if G("FONT") == "auto" else G("FONT"))
    S["music_path"] = music_path
    for k in ("min_dur", "max_dur", "max_clips", "workers"):
        S[k] = int(S[k])
    return S


GUIDE = """
<div class="panel guide">
<h4>How to use this tool — 5 steps</h4>
<ol>
<li><b>Upload your video</b> (top right). One or more files.</li>
<li><b>Pick a tab</b> at the top — <b>Frame, Captions, Animations, Colors, Audio, Clips</b>.
    Each tab opens its own options on the left.</li>
<li><b>Watch the preview</b> in the middle. It updates instantly — it does <i>not</i> process the
    video, it just shows one real frame with your settings drawn on top. So you always see exactly
    where the caption, border and overlay will land.</li>
<li><b>Generate video</b> (bottom bar). This transcribes and renders for real. You'll see progress
    on the right. Reels land in <code>output.zip</code>.</li>
<li><b>Download</b>, or connect <b>YouTube / Google Drive</b> in “Other options” (right side) and
    push the reels straight there.</li>
</ol>
<h4>Good defaults to start with</h4>
<ul>
<li><b>Mode</b>: <code>reels</code> = clips banake 9:16. <code>full_video</code> = poori video pe
    captions. <code>transcribe_only</code> = sirf text.</li>
<li><b>Language</b>: Hindi/Hinglish ke liye <code>hi</code> rakho, warna galat detect ho sakta hai.</li>
<li><b>Whisper model</b>: <code>small</code> (ye host CPU-only hai).</li>
<li><b>Frame mode</b>: screen recordings ke liye <code>fit_blur</code> — poora screen dikhta hai.</li>
</ul>
<h4>Tips</h4>
<ul>
<li>Your settings are <b>saved automatically</b> and reloaded next time — set once, reuse forever.
    Use <b>Reset settings</b> on the Home tab if you want to start over.</li>
<li>Karaoke captions (word highlight) stop the scroll the best.</li>
<li>Keep clips 20–60s for Reels.</li>
</ul>
</div>
"""


# ------------------------------------------------------------------ UI -----
def main():
    h1, h2 = st.columns([2, 1.1])
    with h1:
        st.markdown('<div class="hdr"><span class="logo">AR</span>'
                    '<span><span class="apptitle">Free Auto Reels Generator</span><br>'
                    '<span class="appsub">Upload a video, tune the look, preview instantly, generate.</span>'
                    '</span></div>', unsafe_allow_html=True)
    with h2:
        uploads = st.file_uploader("Upload video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                                   accept_multiple_files=True, label_visibility="collapsed")

    if not uploads:
        with st.container(border=True):
            st.markdown("Upload a video to begin. Not sure how it works? See the **How to use** tab.")
        st.markdown(GUIDE, unsafe_allow_html=True)
        return

    paths = [save_upload(u) for u in uploads]
    primary = paths[0]
    dur_total = get_duration(primary)

    try:
        tab = st.segmented_control("Section", TABS, default="Home", label_visibility="collapsed") or "Home"
    except Exception:
        tab = st.radio("Section", TABS, horizontal=True, label_visibility="collapsed")

    if tab == "How to use":
        st.markdown(GUIDE, unsafe_allow_html=True)
        return

    have_out = bool(st.session_state.get("results"))
    zpath = os.path.join(WORK, "output.zip")
    left, center, right = st.columns([1, 0.9, 0.82], gap="medium")

    # ---- left: options for the selected tab ----
    with left:
        with st.container(border=True):
            st.markdown(f"**{tab}**")
            if tab == "Home":
                st.selectbox("Mode", ALLOWED["mode"], key="mode")
                st.selectbox("Language", ALLOWED["language"], key="language")
                st.selectbox("Whisper model", ALLOWED["model_size"], key="model_size")
                st.selectbox("Caption font", ALLOWED["FONT"], key="FONT")
                if st.button("Reset settings", use_container_width=True):
                    for k, v in DEFAULTS.items():
                        st.session_state[k] = v
                    persist(); st.rerun()
            elif tab == "Frame":
                st.selectbox("Frame mode", ALLOWED["frame_mode"], key="frame_mode")
                st.slider("Blur strength", 0, 80, key="blur_strength")
                st.slider("Crop zoom", 1.0, 3.0, key="crop_zoom", step=0.1)
                c1, c2 = st.columns(2)
                c1.slider("Crop X", 0.0, 1.0, key="crop_x", step=0.05)
                c2.slider("Crop Y", 0.0, 1.0, key="crop_y", step=0.05)
                c1.checkbox("Border", key="border")
                c2.slider("Border width", 0, 40, key="border_width")
            elif tab == "Captions":
                st.selectbox("Caption style", ALLOWED["caption_style"], key="caption_style")
                c1, c2 = st.columns(2)
                c1.checkbox("Box", key="caption_box")
                c2.selectbox("Position", ALLOWED["caption_pos"], key="caption_pos")
                c1.slider("Size", 30, 110, key="caption_size")
                c2.slider("Words/line", 1, 8, key="caption_max_words")
                c1.checkbox("UPPERCASE", key="caption_uppercase")
                c2.selectbox("Highlight", ALLOWED["highlight_mode"], key="highlight_mode")
                c1.slider("Outline", 0, 10, key="caption_outline")
                c2.slider("Bottom margin", 60, 500, key="caption_margin")
                st.slider("Box opacity", 0.0, 1.0, key="caption_box_opacity", step=0.05)
                st.text_input("Overlay text", key="overlay_text", placeholder="Follow for more")
                c1, c2 = st.columns(2)
                c1.selectbox("Overlay position", ALLOWED["overlay_pos"], key="overlay_pos")
                c2.slider("Overlay size", 20, 110, key="overlay_size")
            elif tab == "Animations":
                st.selectbox("Caption animation", ALLOWED["caption_anim"], key="caption_anim")
                c1, c2 = st.columns(2)
                c1.checkbox("Slow zoom", key="slow_zoom")
                c2.checkbox("Fade in/out", key="fade")
                st.checkbox("Progress bar", key="progress_bar")
            elif tab == "Colors":
                c1, c2 = st.columns(2)
                c1.color_picker("Caption text", key="caption_color")
                c2.color_picker("Highlight", key="highlight_color")
                c1.color_picker("Border", key="border_color")
                c2.color_picker("Background", key="bg_color")
                c1.color_picker("Progress bar", key="progress_color")
                c2.color_picker("Overlay text", key="overlay_color")
            elif tab == "Audio":
                st.selectbox("Original audio", ALLOWED["original_audio"], key="original_audio")
                st.slider("Original volume", 0.0, 2.0, key="original_volume", step=0.05)
                st.file_uploader("Background music", type=["mp3", "m4a", "wav", "aac"], key="music_file")
                st.slider("Music volume", 0.0, 1.0, key="music_volume", step=0.05)
            elif tab == "Clips":
                c1, c2 = st.columns(2)
                c1.number_input("Min clip (s)", 5, 300, key="min_dur")
                c2.number_input("Max clip (s)", 10, 600, key="max_dur")
                c1.number_input("Max clips (0=all)", 0, 100, key="max_clips")
                c2.number_input("Parallel jobs", 1, 8, key="workers")

    persist()

    music_file = st.session_state.get("music_file")
    music_path = st.session_state.get("music_path_saved", "")
    if music_file is not None:
        mp = os.path.join(WORK, "music_" + music_file.name)
        if not os.path.exists(mp):
            open(mp, "wb").write(music_file.getbuffer())
        st.session_state["music_path_saved"] = mp
        music_path = mp
    S = build_S(music_path)

    # ---- center: phone preview ----
    with center:
        with st.container(border=True):
            try:
                t = min(10, max(0, dur_total / 2))
                st.markdown(preview_html(frame_uri(primary, t), S, G("language")), unsafe_allow_html=True)
            except Exception as e:
                st.warning(f"Preview nahi bana: {e}")
        if have_out:
            with st.expander("Title / description / hashtags (copy karo)"):
                for x in st.session_state.get("details", []):
                    st.markdown(f"`{x['file']}`")
                    st.code(f"{x['title']}\n\n{x['desc']}\n\n{x['tags']} #shorts #reels", language=None)

    # ---- right: progress + other options ----
    with right:
        with st.container(border=True):
            st.markdown("**Progress**")
            prog = st.empty()
            status = st.empty()
            status.markdown('<span class="note">Idle. Press “Generate video”.</span>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("**Other options**")
        with st.expander("YouTube"):
            SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
            tp = os.path.join(WORK, "yt_token.json")
            if "yt_creds" not in st.session_state:
                st.session_state["yt_creds"] = None
                if os.path.exists(tp):
                    try:
                        from google.oauth2.credentials import Credentials
                        from google.auth.transport.requests import Request
                        c = Credentials.from_authorized_user_file(tp, SCOPES)
                        if c.expired and c.refresh_token:
                            c.refresh(Request())
                        if c.valid:
                            st.session_state["yt_creds"] = c
                    except Exception:
                        pass
            if st.session_state["yt_creds"]:
                st.success("YouTube connected.")
            else:
                cs = st.file_uploader("client_secret.json", type=["json"], key="cs")
                if cs is not None:
                    cp = os.path.join(WORK, "client_secret.json")
                    open(cp, "wb").write(cs.getbuffer())
                    st.session_state["cs_path"] = cp
                if st.button("Get YouTube link") and st.session_state.get("cs_path"):
                    from google_auth_oauthlib.flow import Flow
                    flow = Flow.from_client_secrets_file(st.session_state["cs_path"], scopes=SCOPES,
                                                         redirect_uri="http://localhost:8080/")
                    url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                    st.session_state["yt_flow"] = flow
                    st.session_state["yt_url"] = url
                if st.session_state.get("yt_url"):
                    st.markdown(f"[Open & approve]({st.session_state['yt_url']})")
                    code = st.text_input("Paste code", key="yt_code")
                    if st.button("Connect YouTube") and code.strip():
                        try:
                            st.session_state["yt_flow"].fetch_token(code=code.strip())
                            st.session_state["yt_creds"] = st.session_state["yt_flow"].credentials
                            open(tp, "w").write(st.session_state["yt_flow"].credentials.to_json())
                            st.rerun()
                        except Exception as e:
                            st.error(f"Connect fail: {e}")
            st.selectbox("Privacy", ALLOWED["privacy"], key="privacy")
        with st.expander("Google Drive"):
            DSP = ["https://www.googleapis.com/auth/drive.file"]
            dp = os.path.join(WORK, "drive_token.json")
            if "dr_creds" not in st.session_state:
                st.session_state["dr_creds"] = None
                if os.path.exists(dp):
                    try:
                        from google.oauth2.credentials import Credentials
                        from google.auth.transport.requests import Request
                        c = Credentials.from_authorized_user_file(dp, DSP)
                        if c.expired and c.refresh_token:
                            c.refresh(Request())
                        if c.valid:
                            st.session_state["dr_creds"] = c
                    except Exception:
                        pass
            if st.session_state["dr_creds"]:
                st.success("Drive connected.")
            else:
                st.markdown('<span class="note">Uses the same client_secret.json as YouTube '
                            '(enable the Drive API in the same Google Cloud project).</span>',
                            unsafe_allow_html=True)
                if st.button("Get Drive link") and st.session_state.get("cs_path"):
                    from google_auth_oauthlib.flow import Flow
                    flow = Flow.from_client_secrets_file(st.session_state["cs_path"], scopes=DSP,
                                                         redirect_uri="http://localhost:8080/")
                    url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                    st.session_state["dr_flow"] = flow
                    st.session_state["dr_url"] = url
                if st.session_state.get("dr_url"):
                    st.markdown(f"[Open & approve]({st.session_state['dr_url']})")
                    dcode = st.text_input("Paste code", key="dr_code")
                    if st.button("Connect Drive") and dcode.strip():
                        try:
                            st.session_state["dr_flow"].fetch_token(code=dcode.strip())
                            st.session_state["dr_creds"] = st.session_state["dr_flow"].credentials
                            open(dp, "w").write(st.session_state["dr_flow"].credentials.to_json())
                            st.rerun()
                        except Exception as e:
                            st.error(f"Connect fail: {e}")
    # ---- bottom action bar ----
    b1, b2, b3, b4 = st.columns(4)
    do_generate = b1.button("Generate video", type="primary", use_container_width=True)
    if have_out and os.path.exists(zpath):
        with open(zpath, "rb") as f:
            b2.download_button("Download", f, file_name="output.zip", use_container_width=True)
    else:
        b2.button("Download", disabled=True, use_container_width=True)
    do_drive = b3.button("Save to Drive", use_container_width=True)
    do_yt = b4.button("Upload to YouTube", use_container_width=True)

    if do_generate:
        prog.progress(0.0, text="Shuru…")
        try:
            trans = {}
            for i, vp in enumerate(paths):
                stem = os.path.splitext(os.path.basename(vp))[0]

                def cb(frac, _s=stem, _i=i):
                    prog.progress((_i + frac) / len(paths) * 0.6, text=f"Transcribing {_s}… {int(frac*100)}%")

                trans[vp] = full_transcript(vp, G("model_size"),
                                            None if G("language") == "auto" else G("language"), cb)
                os.makedirs("transcripts", exist_ok=True)
                with open(f"transcripts/{stem}.txt", "w", encoding="utf-8") as f:
                    for s in trans[vp]:
                        f.write(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text'].strip()}\n")

            tasks, details = [], []
            for vp in paths:
                stem = os.path.splitext(os.path.basename(vp))[0]
                segs = trans[vp]
                if S["mode"] == "transcribe_only":
                    continue
                if S["mode"] == "full_video":
                    os.makedirs("captioned", exist_ok=True)
                    end = max(x["end"] for x in segs) if segs else 0
                    out = f"captioned/{stem}_captioned.mp4"
                    tasks.append((vp, segs, 0.0, end, out))
                    txt = engine.clip_text(segs, 0, end)
                    details.append({"file": os.path.basename(out), "title": txt[:90] or stem,
                                    "desc": txt, "tags": engine.hashtags(txt)})
                else:
                    try:
                        clips = engine.find_clips(segs, S["min_dur"], S["max_dur"], max_clips=S["max_clips"])
                    except TypeError:
                        clips = engine.find_clips(segs, S["min_dur"], S["max_dur"])
                    os.makedirs(f"reels/{stem}", exist_ok=True)
                    for i, (s, e) in enumerate(clips):
                        out = f"reels/{stem}/reel_{i+1:02d}.mp4"
                        tasks.append((vp, segs, s, e, out))
                        txt = engine.clip_text(segs, s, e)
                        details.append({"file": f"{stem}/reel_{i+1:02d}.mp4",
                                        "title": txt[:90] or f"Reel {i+1}", "desc": txt,
                                        "tags": engine.hashtags(txt)})
            results = []
            if tasks:
                done = 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=int(S["workers"])) as ex:
                    futs = {ex.submit(engine.render_segment, vp, sg, s, e, o, S, FONTS): o
                            for (vp, sg, s, e, o) in tasks}
                    for f in concurrent.futures.as_completed(futs):
                        results.append(f.result()); done += 1
                        prog.progress(0.6 + 0.4 * done / len(tasks), text=f"Rendering {done}/{len(tasks)}…")
            results.sort()
            with open("post_details.txt", "w", encoding="utf-8") as f:
                f.write("POST DETAILS\n" + "=" * 40 + "\n\n")
                for x in details:
                    f.write(f"FILE: {x['file']}\nTITLE: {x['title']}\nDESCRIPTION:\n{x['desc']}\n")
                    f.write(f"HASHTAGS: {x['tags']} #shorts #reels\n" + "-" * 40 + "\n")
            with zipfile.ZipFile(zpath, "w") as z:
                for rp in results:
                    z.write(rp, os.path.basename(rp))
                if os.path.exists("post_details.txt"):
                    z.write("post_details.txt", "post_details.txt")
                if os.path.isdir("transcripts"):
                    for root, _, files in os.walk("transcripts"):
                        for fn in files:
                            full = os.path.join(root, fn)
                            z.write(full, os.path.relpath(full, "."))
            prog.progress(1.0, text="Ho gaya.")
            st.session_state["results"] = results
            st.session_state["details"] = details
            status.markdown(f'<span class="note">{len(results)} file(s) ready. '
                            f'Use Download / Save to Drive / Upload to YouTube below.</span>',
                            unsafe_allow_html=True)
            st.rerun()
        except Exception as e:
            st.error(f"Generate fail: {e}")


    if do_drive:
        creds = st.session_state.get("dr_creds")
        if not creds:
            st.warning("Pehle right side “Other options -> Google Drive” me connect karo.")
        elif not os.path.exists(zpath):
            st.warning("Pehle Generate video dabao.")
        else:
            try:
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload
                svc = build("drive", "v3", credentials=creds)
                media = MediaFileUpload(zpath, resumable=True)
                f = svc.files().create(body={"name": "auto_reels_output.zip"}, media_body=media,
                                       fields="id,webViewLink").execute()
                st.success(f"Drive pe save ho gaya: {f.get('webViewLink','')}")
            except Exception as e:
                st.error(f"Drive fail: {e}")

    if do_yt:
        creds = st.session_state.get("yt_creds")
        if not creds:
            st.warning("Pehle right side “Other options -> YouTube” me connect karo.")
        elif not st.session_state.get("results"):
            st.warning("Pehle Generate video dabao.")
        else:
            try:
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload
                yt = build("youtube", "v3", credentials=creds)
                files = [p for p in st.session_state["results"] if os.path.exists(p)]
                meta = {x["file"]: x for x in st.session_state.get("details", [])}
                for p in files:
                    key = os.path.basename(p) if p.startswith("captioned/") else "/".join(p.split("/")[-2:])
                    m = meta.get(key, {})
                    body = {"snippet": {"title": (m.get("title") or os.path.basename(p))[:95],
                                        "description": (m.get("desc", "") + "\n\n" + m.get("tags", "")),
                                        "categoryId": "22"},
                            "status": {"privacyStatus": G("privacy"), "selfDeclaredMadeForKids": False}}
                    media = MediaFileUpload(p, chunksize=-1, resumable=True)
                    r = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
                    st.write(f"{os.path.basename(p)} -> https://youtu.be/{r['id']}")
            except Exception as e:
                st.error(f"YouTube fail: {e}")


try:
    main()
except Exception as _e:
    if type(_e).__name__ == "StopException":
        raise
    st.error("App error. Ye message screenshot karke bhej do:")
    st.exception(_e)
