"""
app.py — Free Auto Reels Generator (Streamlit)  ·  v11

Key fixes:
- Settings live in ONE dict (st.session_state["S"]), NOT tied to widget keys.
  Streamlit deletes widget state for widgets not rendered on the current tab, which is
  why switching tabs reset earlier choices. Fixed.
- iPhone-style phone preview showing a real frame of YOUR video with the real caption text.
- Preview mode toggle: "frame" (instant, default) or "video" (renders a short sample).
- Border OFF by default. Description lives in the right column.
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
  .stApp {background:
      radial-gradient(38% 45% at 18% 22%, rgba(124,77,255,.28), transparent 60%),
      radial-gradient(34% 40% at 82% 26%, rgba(224,85,155,.22), transparent 60%),
      radial-gradient(40% 45% at 52% 82%, rgba(34,211,238,.16), transparent 62%),
      linear-gradient(135deg,#07080f,#0d0b1a,#07080f);
    background-size:200% 200%,200% 200%,200% 200%,200% 200%;
    animation: floatbg 26s ease-in-out infinite;}
  @keyframes floatbg {0%{background-position:0% 0%,100% 0%,50% 100%,0 0;}
    50%{background-position:28% 22%,70% 34%,38% 70%,0 0;}
    100%{background-position:0% 0%,100% 0%,50% 100%,0 0;}}
  .stApp::before,.stApp::after{content:"";position:fixed;border-radius:50%;filter:blur(90px);
    opacity:.28;z-index:0;pointer-events:none;}
  .stApp::before{width:340px;height:340px;background:#7c4dff;top:-90px;left:-70px;
    animation:drift1 20s ease-in-out infinite;}
  .stApp::after{width:290px;height:290px;background:#e0559b;bottom:-90px;right:-50px;
    animation:drift2 24s ease-in-out infinite;}
  @keyframes drift1{0%,100%{transform:translate(0,0)}50%{transform:translate(70px,45px)}}
  @keyframes drift2{0%,100%{transform:translate(0,0)}50%{transform:translate(-55px,-35px)}}

  header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stAppToolbar"],
  [data-testid="stDecoration"],#MainMenu,footer{display:none !important;}
  .block-container{padding:.25rem .7rem .3rem .7rem !important; max-width:100% !important;}
  div[data-testid="stVerticalBlock"]{gap:.12rem !important;}
  div[data-testid="stHorizontalBlock"]{gap:.4rem !important;}
  div[data-testid="stElementContainer"]{margin-bottom:0 !important;}

  label p, div[data-testid="stWidgetLabel"] p{font-size:.7rem !important;color:#9aa0b8 !important;
    margin-bottom:0 !important;}
  div[data-testid="stWidgetLabel"]{margin-bottom:-3px !important;}
  div[data-baseweb="select"] > div{min-height:26px !important;font-size:.76rem !important;}
  .stTextInput input,.stNumberInput input{min-height:26px !important;font-size:.76rem !important;}
  .stSlider{padding:0 !important;}
  .stCheckbox{margin-top:-6px !important;}
  .stButton>button,.stDownloadButton>button{min-height:28px !important;padding:0 9px !important;
    font-size:.76rem !important;border-radius:9px;font-weight:600;border:1px solid #3a2f66;
    background:linear-gradient(90deg,#7c4dff,#e0559b);color:#fff;transition:.18s;}
  .stButton>button:hover,.stDownloadButton>button:hover{color:#fff;transform:translateY(-1px);
    box-shadow:0 6px 16px rgba(124,77,255,.45);}
  div[data-testid="stFileUploaderDropzone"]{padding:4px 9px !important;min-height:auto !important;}
  div[data-testid="stFileUploaderDropzone"] span,div[data-testid="stFileUploaderDropzone"] small
    {font-size:.7rem !important;}
  div[data-testid="stExpander"]{border:1px solid #272b48 !important;border-radius:11px !important;}
  div[data-testid="stExpander"] summary{font-size:.76rem !important;padding:3px 9px !important;}

  div[data-testid="stVerticalBlockBorderWrapper"]{
    background:rgba(17,19,33,.92);border:1px solid #272b48 !important;border-radius:13px;
    padding:8px 11px !important;box-shadow:0 8px 24px rgba(0,0,0,.34);backdrop-filter:blur(8px);
    transition:.2s;}
  div[data-testid="stVerticalBlockBorderWrapper"]:hover{border-color:#3b3f68 !important;
    box-shadow:0 10px 28px rgba(124,77,255,.2);}
  div[data-testid="stVerticalBlockBorderWrapper"] > div{gap:.1rem !important;}
  .note{color:#7b8199;font-size:.68rem;}

  .hdr{display:flex;align-items:center;gap:9px;}
  .logo{width:32px;height:32px;border-radius:9px;display:flex;align-items:center;justify-content:center;
    font-weight:800;color:#fff;background:linear-gradient(135deg,#7c4dff,#e0559b);font-size:.78rem;
    box-shadow:0 6px 16px rgba(124,77,255,.4);}
  .apptitle{font-size:1.02rem;font-weight:800;color:#eef0fa;}
  .appsub{color:#8b90a8;font-size:.68rem;}
  .badge{display:inline-block;background:rgba(124,77,255,.16);border:1px solid #3a2f66;color:#c9b8ff;
    border-radius:999px;padding:1px 8px;font-size:.66rem;margin-left:6px;}

  /* ---------- iPhone-style phone ---------- */
  .phone{position:relative;width:216px;margin:0 auto;border-radius:36px;padding:8px;
    background:linear-gradient(160deg,#464b60,#15171f 60%);
    box-shadow:0 20px 50px rgba(0,0,0,.65), inset 0 0 0 1.5px #565d78, 0 0 0 1px #0b0c12;}
  .phone-screen{position:relative;width:100%;aspect-ratio:9/16;border-radius:29px;overflow:hidden;
    background:#000;}
  .island{position:absolute;top:9px;left:50%;transform:translateX(-50%);width:58px;height:15px;
    background:#000;border-radius:9px;z-index:6;box-shadow:0 0 0 1px #1a1c26;}
  .phone::after{content:"";position:absolute;right:-2px;top:120px;width:2px;height:52px;
    background:#4a5068;border-radius:2px;}

  .guide h4{color:#c9b8ff;margin:6px 0 3px 0;font-size:.9rem;}
  .guide li,.guide p{color:#c3c7db;font-size:.8rem;margin-bottom:2px;}
  .guide b{color:#eef0fa;}
  div[data-testid="stSegmentedControl"]{background:rgba(17,19,33,.9);border:1px solid #272b48;
    border-radius:11px;padding:3px;}
  div[data-testid="stSegmentedControl"] button{font-size:.72rem !important;padding:1px 7px !important;}
  code{font-size:.7rem !important;}

</style>
""", unsafe_allow_html=True)

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))

TABS = ["Home", "Frame", "Captions", "Animations", "Colors", "Audio", "Clips", "How to use"]

TAB_KEYS = {
    "Home": ["mode", "language", "model_size", "FONT"],
    "Frame": ["frame_mode", "blur_strength", "crop_zoom", "crop_x", "crop_y", "border", "border_width"],
    "Captions": ["caption_style", "caption_box", "caption_pos", "caption_size", "caption_max_words",
                 "caption_uppercase", "highlight_mode", "caption_outline", "caption_margin",
                 "caption_box_opacity", "overlay_text", "overlay_pos", "overlay_size"],
    "Animations": ["caption_anim", "slow_zoom", "fade", "progress_bar"],
    "Colors": ["caption_color", "highlight_color", "border_color", "bg_color", "progress_color", "overlay_color"],
    "Audio": ["original_audio", "original_volume", "music_volume"],
    "Clips": ["min_dur", "max_dur", "max_clips", "workers"],
}

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
    "preview_mode": ["frame", "video"],
    "privacy": ["private", "unlisted", "public"],
}

DEFAULTS = dict(mode="reels", language="auto", model_size="small", FONT="auto", caption_style="karaoke",
                caption_anim="pop", caption_box=False, caption_box_opacity=0.6, caption_size=62,
                caption_color="#FFFFFF", highlight_color="#FFD400", highlight_mode="color",
                caption_uppercase=False, caption_max_words=4, caption_pos="bottom", caption_margin=230,
                caption_outline=4, slow_zoom=False, fade=False, progress_bar=True, progress_color="#FFD400",
                frame_mode="fit_blur", bg_color="#101020", blur_strength=30, crop_zoom=1.0, crop_x=0.5,
                crop_y=0.5, border=False, border_color="#FFD400", border_width=14,
                overlay_text="", overlay_pos="top", overlay_color="#FFD400", overlay_size=54,
                original_audio="keep", original_volume=1.0, music_volume=0.15, min_dur=20, max_dur=60,
                max_clips=0, workers=2, preview_mode="frame", privacy="private")

SETTINGS_FILE = os.path.join(WORK, "settings.json")


def load_saved():
    if os.path.exists(SETTINGS_FILE):
        try:
            return json.load(open(SETTINGS_FILE))
        except Exception:
            return {}
    return {}


# --- S is the single source of truth; it is NOT a widget key, so it survives tab switches ---
if "S" not in st.session_state:
    _saved = load_saved()
    S = dict(DEFAULTS)
    for k, v in _saved.items():
        if k in DEFAULTS:
            S[k] = v
    for k, opts in ALLOWED.items():
        if S.get(k) not in opts:
            S[k] = DEFAULTS[k]
    st.session_state["S"] = S
S = st.session_state["S"]


def persist():
    try:
        json.dump({k: S[k] for k in DEFAULTS}, open(SETTINGS_FILE, "w"))
    except Exception:
        pass


def seed(k):
    """Give the widget its starting value WITHOUT tying the value to the widget's lifetime."""
    st.session_state.setdefault("w_" + k, S.get(k, DEFAULTS[k]))


def sync(keys):
    for k in keys:
        if "w_" + k in st.session_state:
            S[k] = st.session_state["w_" + k]


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


def human(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"


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


@st.cache_data(show_spinner=False)
def preview_words(video_path, ss, dur, model_size, language):
    """Real words from a short window, so the preview captions match the real output."""
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pw.f32"))
    segs, _ = do_transcribe(audio, model_size, language)
    out = []
    for s in segs:
        for (a, b, w) in s["words"]:
            if w.strip():
                out.append(w.strip())
    return out[:12]


@st.cache_data(show_spinner=False)
def render_preview_video(video_path, ss, dur, model_size, language, settings_json):
    S2 = json.loads(settings_json)
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pv.f32"))
    segs, _ = do_transcribe(audio, model_size, language)
    for s in segs:
        s["start"] += ss; s["end"] += ss
        s["words"] = [(a + ss, b + ss, w) for (a, b, w) in s["words"]]
    out = os.path.join(WORK, "preview.mp4")
    engine.render_segment(video_path, segs, ss, ss + dur, out, S2, FONTS)
    return out


@st.cache_data(show_spinner=False)
def preview_video_b64(video_path, ss, dur, model_size, language, settings_json):
    """Render a small sample and return it as a data URI, so it can play INSIDE the phone."""
    out = render_preview_video(video_path, ss, dur, model_size, language, settings_json)
    small = out + ".small.mp4"
    subprocess.run([engine.ffmpeg_exe(), "-y", "-loglevel", "error", "-i", out,
                    "-vf", "scale=540:960", "-crf", "31", "-preset", "veryfast", "-an", small], check=True)
    return "data:video/mp4;base64," + base64.b64encode(open(small, "rb").read()).decode()


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


def phone_html(frame, S, words, video_b64=None):
    """iPhone-style phone with the real frame + settings drawn on top."""
    bw = S["border_width"] if S["border"] else 0
    if not video_b64:
        if S["frame_mode"] == "fit_blur":
            bg = ("background-image:url(" + frame + ");background-size:cover;background-position:center;"
                  "filter:blur(" + str(int(S["blur_strength"] / 2.6)) + "px) brightness(.72);")
            fg = ("background-image:url(" + frame + ");background-size:contain;background-position:center;"
                  "background-repeat:no-repeat;")
        elif S["frame_mode"] == "fit_color":
            bg = "background:" + S["bg_color"] + ";"
            fg = ("background-image:url(" + frame + ");background-size:contain;background-position:center;"
                  "background-repeat:no-repeat;")
        else:
            bg = "background:#000;"
            fg = "background-image:url(" + frame + ");background-size:cover;background-position:center;"

    box_w = 200
    fs = max(8, round(S["caption_size"] * box_w / 1080 * 2.1))
    ow = max(1, round(S["caption_outline"] / 2))
    outline = ("text-shadow:-" + str(ow) + "px 0 #000," + str(ow) + "px 0 #000,0 -" + str(ow) + "px #000,"
               "0 " + str(ow) + "px #000;")
    cap_box = ("background:rgba(0,0,0," + str(S["caption_box_opacity"]) + ");padding:2px 8px;"
               "border-radius:6px;") if S["caption_box"] else ""

    cap = ""
    if S["caption_style"] != "none" and words:
        show = words[:int(S["caption_max_words"])] or words[:4]
        hl = min(1, len(show) - 1)
        if S["caption_uppercase"]:
            show = [w.upper() for w in show]
        if S["caption_style"] == "karaoke":
            if S["highlight_mode"] == "box":
                body = " ".join(("<span style='background:" + S["highlight_color"] +
                                 ";color:#000;padding:0 3px;border-radius:4px;'>" + w + "</span>")
                                if i == hl else w for i, w in enumerate(show))
            else:
                body = " ".join(("<span style='color:" + S["highlight_color"] + "'>" + w + "</span>")
                                if i == hl else w for i, w in enumerate(show))
        else:
            body = " ".join(show)
        vpos = ("bottom:" + str(round(S["caption_margin"] * 16 / 1920 * 2.4)) + "%;"
                if S["caption_pos"] != "middle" else "top:46%;")
        cap = ("<div style='position:absolute;left:5%;right:5%;" + vpos + "text-align:center;"
               "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:" + str(fs) + "px;"
               "color:" + S["caption_color"] + ";" + outline + "'>"
               "<span style='" + cap_box + "'>" + body + "</span></div>")

    ov = ""
    if S["overlay_text"].strip():
        pos = "top:8%;" if S["overlay_pos"] == "top" else "bottom:22%;"
        ov = ("<div style='position:absolute;left:5%;right:5%;" + pos + "text-align:center;"
              "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:"
              + str(max(7, round(S["overlay_size"] * box_w / 1080 * 2.1))) + "px;"
              "color:" + S["overlay_color"] + ";" + outline + "'>" + S["overlay_text"] + "</div>")

    prog = ("<div style='position:absolute;top:0;left:0;height:4px;width:42%;background:"
            + S["progress_color"] + ";'></div>") if S["progress_bar"] else ""
    if video_b64:
        screen = ("<video src='" + video_b64 + "' autoplay muted loop playsinline "
                  "style='position:absolute;inset:0;width:100%;height:100%;object-fit:cover;'></video>")
    else:
        screen = ("<div style='position:absolute;inset:0;" + bg + "'></div>"
                  "<div style='position:absolute;inset:0;" + fg + "'></div>")
    inner = screen + prog + ov + cap
    if bw:
        inner = "<div style='position:absolute;inset:0;border:" + str(bw) + "px solid " + \
                S["border_color"] + ";border-radius:29px;z-index:7;'></div>" + inner
    return ("<style>" + font_face(S["caption_font"]) + "</style>"
            "<div class='phone'><div class='phone-screen'>"
            "<div class='island'></div>" + inner + "</div></div>")


def full_transcript(video_path, model_size, language, progress_cb=None):
    key = f"{video_path}|{model_size}|{language}"
    store = st.session_state.setdefault("tr", {})
    if key in store:
        return store[key]
    audio = engine.extract_audio(video_path, out=os.path.join(WORK, "full.f32"))
    segs, _ = do_transcribe(audio, model_size, language, progress_cb)
    store[key] = segs
    return segs


def build_settings(music_path):
    Sx = dict(S)
    Sx["caption_font"] = "Noto Sans Devanagari" if S["language"] in {"hi", "mr", "ne"} else \
                         ("Poppins" if S["FONT"] == "auto" else S["FONT"])
    Sx["music_path"] = music_path
    for k in ("min_dur", "max_dur", "max_clips", "workers"):
        Sx[k] = int(Sx[k])
    return Sx


GUIDE = """
<div class="guide">
<h4>How to use — 5 steps</h4>
<ol>
<li><b>Upload your video</b> (top right).</li>
<li><b>Pick a tab</b> — Frame, Captions, Animations, Colors, Audio, Clips — options open on the left.</li>
<li><b>Watch the phone preview</b> in the middle. It shows a real frame of your video with your
settings drawn on top, so you see exactly what the output will look like. It updates instantly.</li>
<li><b>Generate video</b> (bottom bar) — this transcribes and renders for real.</li>
<li><b>Download</b>, or connect <b>YouTube / Google Drive</b> on the right and push the reels there.</li>
</ol>
<h4>Good defaults</h4>
<ul>
<li><b>Mode</b>: <code>reels</code> = clips → 9:16 · <code>full_video</code> = whole video + captions.</li>
<li><b>Language</b>: set <code>hi</code> for Hindi/Hinglish (auto often mis-detects).</li>
<li><b>Whisper model</b>: <code>small</code> on this CPU host.</li>
<li><b>Frame mode</b>: <code>fit_blur</code> for screen recordings.</li>
</ul>
<h4>Tips</h4>
<ul><li>Settings save automatically and reload next time. Reset is on the Home tab.</li>
<li>Preview mode on the right: <b>Frame</b> (instant) or <b>Video</b> (short real render).</li></ul>
</div>
"""


def main():
    h1, h2 = st.columns([1.5, 1])
    with h1:
        st.markdown('<div class="hdr"><span class="logo">AR</span>'
                    '<span><span class="apptitle">Free Auto Reels Generator</span><br>'
                    '<span class="appsub">Upload, tune, preview, generate.</span></span></div>',
                    unsafe_allow_html=True)
    with h2:
        uploads = st.file_uploader("Upload video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                                   accept_multiple_files=True, label_visibility="collapsed")

    if not uploads:
        with st.container(border=True):
            st.markdown("Upload a video to begin — see the **How to use** tab.")
        st.markdown(GUIDE, unsafe_allow_html=True)
        return

    paths = [save_upload(u) for u in uploads]
    primary = paths[0]
    dur_total = get_duration(primary)
    st.markdown('<span class="note">Loaded:</span> <span class="badge">' +
                os.path.basename(primary) + " · " + human(os.path.getsize(primary)) +
                f" · {dur_total/60:.1f} min" + "</span>" +
                (f' <span class="badge">+{len(paths)-1} more</span>' if len(paths) > 1 else ""),
                unsafe_allow_html=True)

    try:
        tab = st.segmented_control("Section", TABS, default="Home", label_visibility="collapsed") or "Home"
    except Exception:
        tab = st.radio("Section", TABS, horizontal=True, label_visibility="collapsed")

    if tab == "How to use":
        st.markdown(GUIDE, unsafe_allow_html=True)
        return

    left, center, right = st.columns([1, 0.86, 0.9], gap="medium")
    have_out = bool(st.session_state.get("results"))
    zpath = os.path.join(WORK, "output.zip")

    # ---------- left: options ----------
    with left:
        with st.container(border=True):
            st.markdown(f"**{tab}**")
            if tab == "Home":
                seed("mode"); st.selectbox("Mode", ALLOWED["mode"], key="w_mode")
                seed("language"); st.selectbox("Language", ALLOWED["language"], key="w_language")
                seed("model_size"); st.selectbox("Whisper model", ALLOWED["model_size"], key="w_model_size")
                seed("FONT"); st.selectbox("Caption font", ALLOWED["FONT"], key="w_FONT")
                if st.button("Reset settings", use_container_width=True):
                    for k, v in DEFAULTS.items():
                        S[k] = v
                        st.session_state["w_" + k] = v
                    persist(); st.rerun()
            elif tab == "Frame":
                seed("frame_mode"); st.selectbox("Frame mode", ALLOWED["frame_mode"], key="w_frame_mode")
                seed("blur_strength"); st.slider("Blur strength", 0, 80, key="w_blur_strength")
                seed("crop_zoom"); st.slider("Crop zoom", 1.0, 3.0, key="w_crop_zoom", step=0.1)
                c1, c2 = st.columns(2)
                seed("crop_x"); c1.slider("Crop X", 0.0, 1.0, key="w_crop_x", step=0.05)
                seed("crop_y"); c2.slider("Crop Y", 0.0, 1.0, key="w_crop_y", step=0.05)
                seed("border"); c1.checkbox("Border", key="w_border")
                seed("border_width"); c2.slider("Border width", 0, 40, key="w_border_width")
            elif tab == "Captions":
                seed("caption_style"); st.selectbox("Style", ALLOWED["caption_style"], key="w_caption_style")
                c1, c2 = st.columns(2)
                seed("caption_box"); c1.checkbox("Box", key="w_caption_box")
                seed("caption_pos"); c2.selectbox("Position", ALLOWED["caption_pos"], key="w_caption_pos")
                seed("caption_size"); c1.slider("Size", 30, 110, key="w_caption_size")
                seed("caption_max_words"); c2.slider("Words/line", 1, 8, key="w_caption_max_words")
                seed("caption_uppercase"); c1.checkbox("UPPERCASE", key="w_caption_uppercase")
                seed("highlight_mode"); c2.selectbox("Highlight", ALLOWED["highlight_mode"], key="w_highlight_mode")
                seed("caption_outline"); c1.slider("Outline", 0, 10, key="w_caption_outline")
                seed("caption_margin"); c2.slider("Margin", 60, 500, key="w_caption_margin")
                seed("caption_box_opacity"); st.slider("Box opacity", 0.0, 1.0, key="w_caption_box_opacity", step=0.05)
                seed("overlay_text"); st.text_input("Overlay text", key="w_overlay_text", placeholder="Follow for more")
                c1, c2 = st.columns(2)
                seed("overlay_pos"); c1.selectbox("Overlay pos", ALLOWED["overlay_pos"], key="w_overlay_pos")
                seed("overlay_size"); c2.slider("Overlay size", 20, 110, key="w_overlay_size")
            elif tab == "Animations":
                seed("caption_anim"); st.selectbox("Caption animation", ALLOWED["caption_anim"], key="w_caption_anim")
                c1, c2 = st.columns(2)
                seed("slow_zoom"); c1.checkbox("Slow zoom", key="w_slow_zoom")
                seed("fade"); c2.checkbox("Fade in/out", key="w_fade")
                seed("progress_bar"); st.checkbox("Progress bar", key="w_progress_bar")
            elif tab == "Colors":
                c1, c2 = st.columns(2)
                seed("caption_color"); c1.color_picker("Caption text", key="w_caption_color")
                seed("highlight_color"); c2.color_picker("Highlight", key="w_highlight_color")
                seed("border_color"); c1.color_picker("Border", key="w_border_color")
                seed("bg_color"); c2.color_picker("Background", key="w_bg_color")
                seed("progress_color"); c1.color_picker("Progress bar", key="w_progress_color")
                seed("overlay_color"); c2.color_picker("Overlay text", key="w_overlay_color")
            elif tab == "Audio":
                seed("original_audio"); st.selectbox("Original audio", ALLOWED["original_audio"], key="w_original_audio")
                seed("original_volume"); st.slider("Original volume", 0.0, 2.0, key="w_original_volume", step=0.05)
                st.file_uploader("Background music", type=["mp3", "m4a", "wav", "aac"], key="music_file")
                seed("music_volume"); st.slider("Music volume", 0.0, 1.0, key="w_music_volume", step=0.05)
            elif tab == "Clips":
                c1, c2 = st.columns(2)
                seed("min_dur"); c1.number_input("Min clip (s)", 5, 300, key="w_min_dur")
                seed("max_dur"); c2.number_input("Max clip (s)", 10, 600, key="w_max_dur")
                seed("max_clips"); c1.number_input("Max clips (0=all)", 0, 100, key="w_max_clips")
                seed("workers"); c2.number_input("Parallel jobs", 1, 8, key="w_workers")
        sync(TAB_KEYS.get(tab, []))
        persist()

    music_file = st.session_state.get("music_file")
    music_path = st.session_state.get("music_path_saved", "")
    if music_file is not None:
        mp = os.path.join(WORK, "music_" + music_file.name)
        if not os.path.exists(mp):
            open(mp, "wb").write(music_file.getbuffer())
        st.session_state["music_path_saved"] = mp
        music_path = mp
    Sfull = build_settings(music_path)

    # ---------- centre: phone preview ----------
    with center:
        with st.container(border=True):
            if S["preview_mode"] == "video":
                with st.spinner("Sample render…"):
                    try:
                        vb = preview_video_b64(primary, 0.0, 5.0, S["model_size"],
                                               None if S["language"] == "auto" else S["language"],
                                               json.dumps(Sfull, sort_keys=True))
                        st.markdown(phone_html(None, Sfull, None, video_b64=vb), unsafe_allow_html=True)
                    except Exception as e:
                        st.warning(f"Video preview nahi bana: {e}")
            else:
                words = None
                try:
                    words = preview_words(primary, 0.0, 6.0, S["model_size"],
                                          None if S["language"] == "auto" else S["language"])
                except Exception:
                    words = None
                if not words:
                    words = (["आज", "हम", "बात", "करेंगे"] if S["language"] in ("hi", "mr", "ne")
                             else ["Here", "is", "how", "it", "works"])
                try:
                    t = min(8, max(0, dur_total / 2))
                    st.markdown(phone_html(frame_uri(primary, t), Sfull, words), unsafe_allow_html=True)
                except Exception as e:
                    st.warning(f"Preview nahi bana: {e}")

    # ---------- right: preview mode, progress, description, other ----------
    with right:
        with st.container(border=True):
            seed("preview_mode")
            st.radio("Preview", ALLOWED["preview_mode"], key="w_preview_mode", horizontal=True,
                     label_visibility="collapsed")
            sync(["preview_mode"]); persist()
        with st.container(border=True):
            st.markdown("**Progress**")
            prog = st.empty()
            status = st.empty()
            status.markdown('<span class="note">Idle. Press “Generate video”.</span>', unsafe_allow_html=True)
        if have_out:
            with st.container(border=True):
                st.markdown("**Title / description / hashtags**")
                for x in st.session_state.get("details", []):
                    st.markdown(f"`{x['file']}`")
                    st.code(f"{x['title']}\n\n{x['desc']}\n\n{x['tags']} #shorts #reels", language=None)
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
                seed("privacy"); st.selectbox("Privacy", ALLOWED["privacy"], key="w_privacy")
                sync(["privacy"]); persist()
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
                    st.markdown('<span class="note">Same client_secret.json; enable the Drive API too.</span>',
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

    # ---------- bottom action bar ----------
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

                trans[vp] = full_transcript(vp, S["model_size"],
                                            None if S["language"] == "auto" else S["language"], cb)
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
                        clips = engine.find_clips(segs, Sfull["min_dur"], Sfull["max_dur"],
                                                  max_clips=Sfull["max_clips"])
                    except TypeError:
                        clips = engine.find_clips(segs, Sfull["min_dur"], Sfull["max_dur"])
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=int(Sfull["workers"])) as ex:
                    futs = {ex.submit(engine.render_segment, vp, sg, s, e, o, Sfull, FONTS): o
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
            st.rerun()
        except Exception as e:
            st.error(f"Generate fail: {e}")

    if do_drive:
        creds = st.session_state.get("dr_creds")
        if not creds:
            st.warning("Right side → Other options → Google Drive me pehle connect karo.")
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
                st.success("Drive pe save ho gaya: " + f.get("webViewLink", ""))
            except Exception as e:
                st.error(f"Drive fail: {e}")

    if do_yt:
        creds = st.session_state.get("yt_creds")
        if not creds:
            st.warning("Right side → Other options → YouTube me pehle connect karo.")
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
                            "status": {"privacyStatus": S["privacy"], "selfDeclaredMadeForKids": False}}
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
