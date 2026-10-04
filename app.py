"""
app.py — Auto Reel Maker (Streamlit)  ·  v5

- Ribbon tabs (Word jaisa). Tab pe click -> options left me.
- Live preview turant (koi render nahi) aur chhota (phone-size, no scrolling).
- Zyada customization options.
- Settings automatically save + reload -> har baar dobara set nahi karna padta.
- Parallel rendering, copy-ready descriptions, YouTube upload.
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

st.set_page_config(page_title="Auto Reel Maker", page_icon=None, layout="wide")

st.markdown("""
<style>
  .stApp {background: linear-gradient(135deg,#080910,#131024,#0b0d18,#0e1224);
          background-size: 300% 300%; animation: bgmove 24s ease infinite;}
  @keyframes bgmove {0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
  .block-container {padding: .9rem 1.4rem 1.6rem 1.4rem; max-width: 1500px;}
  header[data-testid="stHeader"] {background: transparent;}
  section[data-testid="stSidebar"] {display:none;}
  .brand {font-size:1.5rem; font-weight:800;
          background:linear-gradient(90deg,#8b5cf6,#e879a6,#f0b429);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent;}
  .sub {color:#8b90a8; font-size:.8rem;}
  .panel {background:rgba(19,21,36,.86); border:1px solid #272b48; border-radius:16px;
          padding:14px 16px; box-shadow:0 6px 24px rgba(0,0,0,.28); backdrop-filter:blur(6px);}
  .panel h4 {margin:2px 0 8px 0; color:#e8eaf5; font-size:.98rem;}
  .stButton>button, .stDownloadButton>button {border-radius:11px; font-weight:600;
      border:1px solid #3a2f66; background:linear-gradient(90deg,#7c4dff,#e0559b); color:#fff;}
  .stButton>button:hover, .stDownloadButton>button:hover {color:#fff; opacity:.93;}
  div[data-testid="stSegmentedControl"] {background:rgba(19,21,36,.86); border:1px solid #272b48;
      border-radius:14px; padding:5px;}
  .ribbon-note {color:#7b8199; font-size:.76rem; margin-top:2px;}
  label, .stMarkdown p {font-size:.84rem;}
</style>
""", unsafe_allow_html=True)

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))

TABS = ["Home", "Captions", "Animation", "Framing", "Overlay", "Audio", "Clips", "YouTube"]

# keys we persist between visits
PERSIST = ["mode", "language", "model_size", "FONT", "caption_style", "caption_anim", "caption_box",
           "caption_box_opacity", "caption_size", "caption_color", "highlight_color", "highlight_mode",
           "caption_uppercase", "caption_max_words", "caption_pos", "caption_margin", "caption_outline",
           "slow_zoom", "fade", "progress_bar", "progress_color", "frame_mode", "bg_color", "blur_strength",
           "crop_zoom", "crop_x", "crop_y", "border", "border_color", "border_width",
           "overlay_text", "overlay_pos", "overlay_color", "overlay_size",
           "original_audio", "original_volume", "music_volume", "min_dur", "max_dur", "max_clips", "workers"]

DEFAULTS = dict(mode="reels", language="auto", model_size="small", FONT="auto", caption_style="karaoke",
                caption_anim="pop", caption_box=False, caption_box_opacity=0.6, caption_size=62,
                caption_color="#FFFFFF", highlight_color="#FFD400", highlight_mode="color",
                caption_uppercase=False, caption_max_words=4, caption_pos="bottom", caption_margin=230,
                caption_outline=4, slow_zoom=False, fade=False, progress_bar=True, progress_color="#FFD400",
                frame_mode="fit_blur", bg_color="#101020", blur_strength=30, crop_zoom=1.0, crop_x=0.5,
                crop_y=0.5, border=True, border_color="#FFD400", border_width=14,
                overlay_text="", overlay_pos="top", overlay_color="#FFD400", overlay_size=54,
                original_audio="keep", original_volume=1.0, music_volume=0.15, min_dur=20, max_dur=60,
                max_clips=0, workers=2)

SETTINGS_FILE = os.path.join(WORK, "settings.json")


def load_saved():
    if os.path.exists(SETTINGS_FILE):
        try:
            return json.load(open(SETTINGS_FILE))
        except Exception:
            return {}
    return {}


def persist():
    data = {k: st.session_state.get(k) for k in PERSIST if k in st.session_state}
    try:
        json.dump(data, open(SETTINGS_FILE, "w"))
    except Exception:
        pass


# seed session_state from the saved file so choices survive between visits
_saved = load_saved()
for _k in PERSIST:
    st.session_state.setdefault(_k, _saved.get(_k, DEFAULTS[_k]))


# -------------------------------------------------------------- helpers ----
def save_upload(u):
    data = u.getbuffer()
    h = hashlib.md5(data).hexdigest()[:10]
    p = os.path.join(WORK, f"{h}_{u.name}")
    if not os.path.exists(p):
        open(p, "wb").write(data)
    return p


def get_duration(path):
    err = subprocess.run([engine.ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


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


def preview_html(frame, S, lang, box_w=228):
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
    cap_box = ("background:rgba(0,0,0," + str(op) + ");padding:3px 9px;border-radius:7px;"
               if S["caption_box"] else "")

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
                 "border-radius:14px;overflow:hidden;border:" + str(bw) + "px solid " + S["border_color"] + ";"
                 "box-shadow:0 12px 34px rgba(0,0,0,.55);")
    return ("<style>" + font_face(S["caption_font"]) + "</style><div style='" + frame_css + "'>"
            "<div style='position:absolute;inset:0;" + bg + "'></div>"
            "<div style='position:absolute;inset:0;" + fg + "'></div>" + prog + ov + cap + "</div>")


@st.cache_data(show_spinner=False)
def transcript_window(video_path, ss, dur, model_size, language):
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pv.f32"))
    segs, _ = do_transcribe(audio, model_size, language)
    for s in segs:
        s["start"] += ss; s["end"] += ss
        s["words"] = [(a + ss, b + ss, w) for (a, b, w) in s["words"]]
    return segs


def full_transcript(video_path, model_size, language, progress_cb=None):
    key = f"{video_path}|{model_size}|{language}"
    store = st.session_state.setdefault("tr", {})
    if key in store:
        return store[key]
    audio = engine.extract_audio(video_path, out=os.path.join(WORK, "full.f32"))
    segs, _ = do_transcribe(audio, model_size, language, progress_cb)
    store[key] = segs
    return segs


# ----------------------------------------------------------------- header --
st.markdown('<div class="brand">Auto Reel Maker</div>'
            '<div class="sub">Tab chuno, options set karo, turant preview dekho. '
            'Settings apne aap save rehti hain.</div>', unsafe_allow_html=True)

uploads = st.file_uploader("Upload video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                           accept_multiple_files=True, label_visibility="collapsed")
if not uploads:
    st.markdown('<div class="panel">Shuru karne ke liye apni video upload karo.<br>'
                '<span class="ribbon-note">Preview turant banega — koi video process nahi hoti '
                'jab tak Generate na dabao.</span></div>', unsafe_allow_html=True)
    st.stop()

paths = [save_upload(u) for u in uploads]
primary = paths[0]
dur_total = get_duration(primary)

try:
    tab = st.segmented_control("Section", TABS, default="Home", label_visibility="collapsed") or "Home"
except Exception:
    tab = st.radio("Section", TABS, horizontal=True, label_visibility="collapsed")

col_set, col_prev = st.columns([1, 1.0], gap="large")

# ------------------------------------------------------------- settings ----
with col_set:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f"<h4>{tab}</h4>", unsafe_allow_html=True)

    if tab == "Home":
        st.selectbox("Mode", ["reels", "full_video", "transcribe_only"], key="mode")
        st.selectbox("Language", ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"], key="language")
        st.selectbox("Whisper model", ["tiny", "base", "small", "medium"], key="model_size",
                     help="CPU pe 'small' best.")
        st.selectbox("Caption font", ["auto"] + engine.FONT_CHOICES, key="FONT")
        c1, c2 = st.columns(2)
        if c1.button("Reset settings", use_container_width=True):
            for k, v in DEFAULTS.items():
                st.session_state[k] = v
            persist(); st.rerun()
        c2.markdown('<span class="ribbon-note">Settings auto-save hoti hain.</span>', unsafe_allow_html=True)

    elif tab == "Captions":
        st.selectbox("Caption style", ["karaoke", "plain", "none"], key="caption_style")
        c1, c2 = st.columns(2)
        c1.checkbox("Box behind text", key="caption_box")
        c2.selectbox("Position", ["bottom", "middle"], key="caption_pos")
        c1.slider("Caption size", 30, 110, key="caption_size")
        c2.slider("Words per line", 1, 8, key="caption_max_words")
        c1.color_picker("Text colour", key="caption_color")
        c2.color_picker("Highlight colour", key="highlight_color")
        c1.selectbox("Highlight mode", ["color", "box"], key="highlight_mode")
        c2.checkbox("UPPERCASE text", key="caption_uppercase")
        c1.slider("Outline width", 0, 10, key="caption_outline")
        c2.slider("Bottom margin", 60, 500, key="caption_margin")
        st.slider("Box opacity", 0.0, 1.0, key="caption_box_opacity", step=0.05)

    elif tab == "Animation":
        st.selectbox("Caption animation", ["pop", "fade", "none"], key="caption_anim")
        c1, c2 = st.columns(2)
        c1.checkbox("Slow zoom on video", key="slow_zoom")
        c2.checkbox("Fade in / out", key="fade")
        c1.checkbox("Progress bar", key="progress_bar")
        c2.color_picker("Progress bar colour", key="progress_color")

    elif tab == "Framing":
        st.selectbox("Frame mode", ["fit_blur", "fit_color", "crop"], key="frame_mode")
        c1, c2 = st.columns(2)
        c1.color_picker("Background colour", key="bg_color")
        c2.slider("Blur strength", 0, 80, key="blur_strength")
        c1.slider("Crop zoom", 1.0, 3.0, key="crop_zoom", step=0.1)
        c2.slider("Crop X", 0.0, 1.0, key="crop_x", step=0.05)
        st.slider("Crop Y", 0.0, 1.0, key="crop_y", step=0.05)
        c1, c2 = st.columns(2)
        c1.checkbox("Border", key="border")
        c2.color_picker("Border colour", key="border_color")
        st.slider("Border width", 0, 40, key="border_width")

    elif tab == "Overlay":
        st.text_input("Overlay text", key="overlay_text", placeholder="Follow for more")
        c1, c2 = st.columns(2)
        c1.selectbox("Position", ["top", "bottom"], key="overlay_pos")
        c2.color_picker("Colour", key="overlay_color")
        st.slider("Overlay size", 20, 110, key="overlay_size")

    elif tab == "Audio":
        st.selectbox("Original audio", ["keep", "mute"], key="original_audio")
        st.slider("Original volume", 0.0, 2.0, key="original_volume", step=0.05)
        st.file_uploader("Background music (optional)", type=["mp3", "m4a", "wav", "aac"], key="music_file")
        st.slider("Music volume", 0.0, 1.0, key="music_volume", step=0.05)

    elif tab == "Clips":
        c1, c2 = st.columns(2)
        c1.number_input("Min clip (seconds)", 5, 300, key="min_dur")
        c2.number_input("Max clip (seconds)", 10, 600, key="max_dur")
        c1.number_input("Max clips (0 = all)", 0, 100, key="max_clips")
        c2.number_input("Parallel jobs", 1, 8, key="workers")

    elif tab == "YouTube":
        st.markdown('<span class="ribbon-note">Pehle Generate karo, phir yahan se upload.</span>',
                    unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

persist()

G = lambda k: st.session_state.get(k, DEFAULTS[k])
caption_font = "Noto Sans Devanagari" if G("language") in {"hi", "mr", "ne"} else \
               ("Poppins" if G("FONT") == "auto" else G("FONT"))

music_file = st.session_state.get("music_file")
music_path = st.session_state.get("music_path_saved", "")
if music_file is not None:
    mp = os.path.join(WORK, "music_" + music_file.name)
    if not os.path.exists(mp):
        open(mp, "wb").write(music_file.getbuffer())
    st.session_state["music_path_saved"] = mp
    music_path = mp

S = {k: G(k) for k in DEFAULTS}
S["caption_font"] = caption_font
S["music_path"] = music_path
S["min_dur"] = int(S["min_dur"]); S["max_dur"] = int(S["max_dur"])
S["max_clips"] = int(S["max_clips"]); S["workers"] = int(S["workers"])

# ---------------------------------------------------------------- preview --
with col_prev:
    st.markdown('<div class="panel"><h4>Live preview</h4>'
                '<span class="ribbon-note">Turant — video process nahi hoti.</span>',
                unsafe_allow_html=True)
    t = min(10, max(0, dur_total / 2))
    try:
        st.markdown(preview_html(frame_uri(primary, t), S, G("language")), unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Preview nahi bana: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><h4>Process</h4>', unsafe_allow_html=True)
    if st.button("Generate", type="primary", use_container_width=True):
        bar = st.progress(0.0, text="Shuru…")
        try:
            trans = {}
            for i, vp in enumerate(paths):
                stem = os.path.splitext(os.path.basename(vp))[0]

                def cb(frac, _s=stem, _i=i):
                    bar.progress((_i + frac) / len(paths) * 0.6, text=f"Transcribing {_s}… {int(frac*100)}%")

                trans[vp] = full_transcript(vp, G("model_size"), None if G("language") == "auto" else G("language"), cb)
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
                        bar.progress(0.6 + 0.4 * done / len(tasks), text=f"Rendering {done}/{len(tasks)}…")
            results.sort()

            with open("post_details.txt", "w", encoding="utf-8") as f:
                f.write("POST DETAILS\n" + "=" * 40 + "\n\n")
                for x in details:
                    f.write(f"FILE: {x['file']}\nTITLE: {x['title']}\nDESCRIPTION:\n{x['desc']}\n")
                    f.write(f"HASHTAGS: {x['tags']} #shorts #reels\n" + "-" * 40 + "\n")

            zpath = os.path.join(WORK, "output.zip")
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
            bar.progress(1.0, text="Ho gaya.")
            st.session_state["results"] = results
            st.session_state["details"] = details
            st.success(f"{len(results)} file(s) taiyaar.")
        except Exception as e:
            st.error(f"Fail: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("results"):
        st.markdown('<div class="panel"><h4>Download &amp; post</h4>', unsafe_allow_html=True)
        zpath = os.path.join(WORK, "output.zip")
        if os.path.exists(zpath):
            with open(zpath, "rb") as f:
                st.download_button("Download output.zip", f, file_name="output.zip")
        st.markdown("**Title / description / hashtags (copy karke paste karo)**")
        for x in st.session_state.get("details", []):
            st.markdown(f"`{x['file']}`")
            st.code(f"{x['title']}\n\n{x['desc']}\n\n{x['tags']} #shorts #reels", language=None)
        st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------- youtube ---
if tab == "YouTube":
    with col_prev:
        st.markdown('<div class="panel"><h4>YouTube upload</h4>', unsafe_allow_html=True)
        SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
        token_path = os.path.join(WORK, "yt_token.json")
        if "yt_creds" not in st.session_state:
            st.session_state["yt_creds"] = None
            if os.path.exists(token_path):
                try:
                    from google.oauth2.credentials import Credentials
                    from google.auth.transport.requests import Request
                    c = Credentials.from_authorized_user_file(token_path, SCOPES)
                    if c.expired and c.refresh_token:
                        c.refresh(Request())
                    if c.valid:
                        st.session_state["yt_creds"] = c
                except Exception:
                    pass
        creds = st.session_state["yt_creds"]
        if creds:
            st.success("Connected (saved login reuse ho raha hai).")
            privacy = st.selectbox("Privacy", ["private", "unlisted", "public"])
            if st.button("Upload generated videos"):
                try:
                    from googleapiclient.discovery import build
                    from googleapiclient.http import MediaFileUpload
                    yt = build("youtube", "v3", credentials=creds)
                    files = [p for p in st.session_state.get("results", []) if os.path.exists(p)]
                    meta = {x["file"]: x for x in st.session_state.get("details", [])}
                    for p in files:
                        key = os.path.basename(p) if p.startswith("captioned/") else "/".join(p.split("/")[-2:])
                        m = meta.get(key, {})
                        body = {"snippet": {"title": (m.get("title") or os.path.basename(p))[:95],
                                            "description": (m.get("desc", "") + "\n\n" + m.get("tags", "")),
                                            "categoryId": "22"},
                                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
                        media = MediaFileUpload(p, chunksize=-1, resumable=True)
                        r = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
                        st.write(f"{os.path.basename(p)} -> https://youtu.be/{r['id']}")
                except Exception as e:
                    st.error(f"Upload fail: {e}")
        else:
            cs = st.file_uploader("client_secret.json (Desktop app type)", type=["json"], key="cs")
            if cs is not None:
                cp = os.path.join(WORK, "client_secret.json")
                open(cp, "wb").write(cs.getbuffer())
                st.session_state["cs_path"] = cp
            if st.button("1. Get authorization link") and st.session_state.get("cs_path"):
                from google_auth_oauthlib.flow import Flow
                flow = Flow.from_client_secrets_file(st.session_state["cs_path"], scopes=SCOPES,
                                                     redirect_uri="http://localhost:8080/")
                url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                st.session_state["yt_flow"] = flow
                st.session_state["yt_url"] = url
            if st.session_state.get("yt_url"):
                st.markdown(f"[Open and approve this link]({st.session_state['yt_url']})")
                code = st.text_input("Paste code (after 'code=', before '&')")
                if st.button("2. Connect") and code.strip():
                    try:
                        st.session_state["yt_flow"].fetch_token(code=code.strip())
                        st.session_state["yt_creds"] = st.session_state["yt_flow"].credentials
                        open(token_path, "w").write(st.session_state["yt_flow"].credentials.to_json())
                        st.rerun()
                    except Exception as e:
                        st.error(f"Connect fail: {e}")
        st.markdown("</div>", unsafe_allow_html=True)
