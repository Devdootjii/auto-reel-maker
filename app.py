"""
app.py — Auto Reel Maker (Streamlit)  ·  v4

- Ribbon-style top tabs (Word jaisa). Tab pe click karo -> uske options left me khulte hain.
- Live preview turant (koi video render nahi) — ek frame + CSS overlay.
- No emojis. Panels ke peeche background. Animated gradient page background.
- Parallel rendering, copy-ready descriptions, YouTube upload.
- Defensive: purane engine.py pe bhi chalta hai.
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

# ------------------------------------------------------------------ CSS ----
st.markdown("""
<style>
  .stApp {
    background: linear-gradient(135deg,#080910,#131024,#0b0d18,#0e1224);
    background-size: 300% 300%;
    animation: bgmove 24s ease infinite;
  }
  @keyframes bgmove {0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
  .block-container {padding: 1.1rem 1.6rem 2rem 1.6rem; max-width: 1500px;}
  header[data-testid="stHeader"] {background: transparent;}
  section[data-testid="stSidebar"] {display:none;}

  .topbar {display:flex; align-items:baseline; gap:14px;}
  .brand {font-size:1.7rem; font-weight:800; letter-spacing:.2px;
          background:linear-gradient(90deg,#8b5cf6,#e879a6,#f0b429);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent;}
  .sub {color:#8b90a8; font-size:.86rem;}

  .panel {background:rgba(19,21,36,.86); border:1px solid #272b48; border-radius:16px;
          padding:16px 18px; box-shadow:0 6px 24px rgba(0,0,0,.28); backdrop-filter:blur(6px);}
  .panel h4 {margin:2px 0 10px 0; color:#e8eaf5; font-size:1.0rem;}
  .label {color:#aab0c8; font-size:.8rem; margin-bottom:2px;}

  .stButton>button, .stDownloadButton>button {
      border-radius:11px; font-weight:600; border:1px solid #3a2f66;
      background:linear-gradient(90deg,#7c4dff,#e0559b); color:#fff;}
  .stButton>button:hover, .stDownloadButton>button:hover {color:#fff; opacity:.93;}

  /* ribbon tabs */
  div[data-testid="stSegmentedControl"] {background:rgba(19,21,36,.86); border:1px solid #272b48;
      border-radius:14px; padding:6px; }
  div[data-testid="stSegmentedControl"] label {font-weight:600;}
  .ribbon-note {color:#7b8199; font-size:.78rem; margin-top:4px;}
</style>
""", unsafe_allow_html=True)

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))

TABS = ["Home", "Captions", "Animation", "Framing", "Audio", "Clips", "YouTube"]


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


def grab_frame(video_path, t, out, width=420):
    """Works whether or not engine has the newer extract_frame."""
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
    """Works with or without the progress kwarg."""
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
        return ""   # heavy font -> system fallback keeps the preview instant
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    return "@font-face{font-family:'PV';src:url(data:font/ttf;base64," + b64 + ");font-weight:700;}"


SAMPLE = {"hi": (["आज", "हम", "बात", "करेंगे", "क्रिकेट", "की"], 2),
          "default": (["Here", "is", "how", "it", "works", "for", "you"], 2)}


def preview_html(frame, S, lang, box_w=300):
    box_h = int(box_w * 16 / 9)
    words, hl = SAMPLE["hi"] if lang in ("hi", "mr", "ne") else SAMPLE["default"]

    if S["frame_mode"] == "fit_blur":
        bg = ("background-image:url('" + frame + "');background-size:cover;background-position:center;"
              "filter:blur(16px) brightness(.72);")
        fg = ("background-image:url('" + frame + "');background-size:contain;background-position:center;"
              "background-repeat:no-repeat;")
    elif S["frame_mode"] == "fit_color":
        bg = "background:" + S["bg_color"] + ";"
        fg = ("background-image:url('" + frame + "');background-size:contain;background-position:center;"
              "background-repeat:no-repeat;")
    else:
        bg = "background:#000;"
        fg = "background-image:url('" + frame + "');background-size:cover;background-position:center;"

    fs = max(9, round(S["caption_size"] * box_w / 1080 * 2.1))
    outline = ("text-shadow:-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000,"
               "0 0 6px rgba(0,0,0,.85);")
    cap_box = "background:rgba(0,0,0,.62);padding:3px 10px;border-radius:8px;" if S["caption_box"] else ""

    cap = ""
    if S["caption_style"] != "none":
        if S["caption_style"] == "karaoke":
            body = " ".join(("<span style='color:" + S["highlight_color"] + "'>" + w + "</span>")
                            if i == hl else w for i, w in enumerate(words))
        else:
            body = " ".join(words)
        cap = ("<div style='position:absolute;left:7%;right:7%;bottom:11%;text-align:center;"
               "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:" + str(fs) + "px;"
               "color:" + S["caption_color"] + ";" + outline + "'>"
               "<span style='" + cap_box + "'>" + body + "</span></div>")

    ov = ""
    if S["overlay_text"].strip():
        pos = "top:9%;" if S["overlay_pos"] == "top" else "bottom:24%;"
        ov = ("<div style='position:absolute;left:6%;right:6%;" + pos + "text-align:center;"
              "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:" + str(max(8, round(fs*0.8))) + "px;"
              "color:" + S["overlay_color"] + ";" + outline + "'>" + S["overlay_text"] + "</div>")

    prog = ("<div style='position:absolute;top:0;left:0;height:6px;width:42%;background:"
            + S["border_color"] + ";'></div>") if S["progress_bar"] else ""
    bw = S["border_width"] if S["border"] else 0

    frame_css = ("position:relative;width:" + str(box_w) + "px;height:" + str(box_h) + "px;margin:0 auto;"
                 "border-radius:18px;overflow:hidden;border:" + str(bw) + "px solid " + S["border_color"] + ";"
                 "box-shadow:0 14px 44px rgba(0,0,0,.55);")

    return ("<style>" + font_face(S["caption_font"]) + "</style>"
            "<div style='" + frame_css + "'>"
            "<div style='position:absolute;inset:0;" + bg + "'></div>"
            "<div style='position:absolute;inset:0;" + fg + "'></div>"
            + prog + ov + cap + "</div>")


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
st.markdown('<div class="topbar"><span class="brand">Auto Reel Maker</span>'
            '<span class="sub">Option chuno, turant preview dekho, phir process karo.</span></div>',
            unsafe_allow_html=True)

uploads = st.file_uploader("Upload video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                           accept_multiple_files=True, label_visibility="collapsed")
if not uploads:
    st.markdown('<div class="panel">Shuru karne ke liye apni video upload karo.<br>'
                '<span class="ribbon-note">Upload hote waqt: preview turant banega, koi video '
                'process nahi hoti jab tak tum Generate na dabao.</span></div>', unsafe_allow_html=True)
    st.stop()

paths = [save_upload(u) for u in uploads]
primary = paths[0]
dur_total = get_duration(primary)

# -------------------------------------------------------------- ribbon -----
try:
    tab = st.segmented_control("Section", TABS, default="Home", label_visibility="collapsed") or "Home"
except Exception:
    tab = st.radio("Section", TABS, horizontal=True, label_visibility="collapsed")

col_set, col_prev = st.columns([1, 1.15], gap="large")

# ------------------------------------------------------------- settings ----
with col_set:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f"<h4>{tab}</h4>", unsafe_allow_html=True)

    if tab == "Home":
        st.selectbox("Mode", ["reels", "full_video", "transcribe_only"], 0, key="mode")
        st.selectbox("Language", ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"], 0, key="language")
        st.selectbox("Whisper model", ["tiny", "base", "small", "medium"], 2, key="model_size",
                     help="CPU pe 'small' best.")
        st.selectbox("Caption font", ["auto"] + engine.FONT_CHOICES, 0, key="FONT")
        st.markdown('<div class="ribbon-note">reels = clips, full_video = poori video pe captions, '
                    'transcribe_only = sirf text.</div>', unsafe_allow_html=True)

    elif tab == "Captions":
        st.selectbox("Caption style", ["karaoke", "plain", "none"], 0, key="caption_style")
        st.checkbox("Box behind text", False, key="caption_box")
        st.slider("Caption size", 30, 100, 62, key="caption_size")
        st.color_picker("Text colour", "#FFFFFF", key="caption_color")
        st.color_picker("Karaoke highlight", "#FFD400", key="highlight_color")

    elif tab == "Animation":
        st.selectbox("Caption animation", ["pop", "fade", "none"], 0, key="caption_anim")
        st.checkbox("Slow zoom on video", False, key="slow_zoom")
        st.checkbox("Progress bar on reel", True, key="progress_bar")
        st.markdown('<div class="ribbon-note">Pop = chhote se bade, Fade = halka aana.</div>',
                    unsafe_allow_html=True)

    elif tab == "Framing":
        st.selectbox("Frame mode", ["fit_blur", "fit_color", "crop"], 0, key="frame_mode")
        st.color_picker("Background colour", "#101020", key="bg_color")
        st.slider("Crop zoom", 1.0, 3.0, 1.0, 0.1, key="crop_zoom")
        st.slider("Crop X", 0.0, 1.0, 0.5, 0.05, key="crop_x")
        st.slider("Crop Y", 0.0, 1.0, 0.5, 0.05, key="crop_y")
        st.checkbox("Border", True, key="border")
        st.color_picker("Border colour", "#FFD400", key="border_color")
        st.slider("Border width", 0, 40, 14, key="border_width")

    elif tab == "Audio":
        st.selectbox("Original audio", ["keep", "mute"], 0, key="original_audio")
        st.file_uploader("Background music (optional)", type=["mp3", "m4a", "wav", "aac"], key="music_file")
        st.slider("Music volume", 0.0, 1.0, 0.15, 0.05, key="music_volume")
        st.text_input("Overlay text", "", placeholder="Follow for more", key="overlay_text")
        st.selectbox("Overlay position", ["top", "bottom"], 0, key="overlay_pos")
        st.color_picker("Overlay colour", "#FFD400", key="overlay_color")

    elif tab == "Clips":
        st.number_input("Min clip (seconds)", 5, 300, 20, key="min_dur")
        st.number_input("Max clip (seconds)", 10, 600, 60, key="max_dur")
        st.number_input("Parallel jobs", 1, 8, 2, key="workers",
                        help="Ek saath kitne clips render hon.")

    elif tab == "YouTube":
        st.markdown('<div class="ribbon-note">Pehle Generate karo, phir yahan se upload.</div>',
                    unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def G(k, d):
    return st.session_state.get(k, d)

mode = G("mode", "reels"); language = G("language", "auto"); model_size = G("model_size", "small")
FONT = G("FONT", "auto")
caption_style = G("caption_style", "karaoke"); caption_box = G("caption_box", False)
caption_size = G("caption_size", 62); caption_color = G("caption_color", "#FFFFFF")
highlight_color = G("highlight_color", "#FFD400"); caption_anim = G("caption_anim", "pop")
slow_zoom = G("slow_zoom", False); progress_bar = G("progress_bar", True)
frame_mode = G("frame_mode", "fit_blur"); bg_color = G("bg_color", "#101020")
crop_zoom = G("crop_zoom", 1.0); crop_x = G("crop_x", 0.5); crop_y = G("crop_y", 0.5)
border = G("border", True); border_color = G("border_color", "#FFD400"); border_width = G("border_width", 14)
original_audio = G("original_audio", "keep"); music_volume = G("music_volume", 0.15)
overlay_text = G("overlay_text", ""); overlay_pos = G("overlay_pos", "top"); overlay_color = G("overlay_color", "#FFD400")
min_dur = G("min_dur", 20); max_dur = G("max_dur", 60); workers = G("workers", 2)
music_file = st.session_state.get("music_file")

caption_font = "Noto Sans Devanagari" if language in {"hi", "mr", "ne"} else ("Poppins" if FONT == "auto" else FONT)

# keep the music file even after switching tabs
music_path = st.session_state.get("music_path_saved", "")
if music_file is not None:
    mp = os.path.join(WORK, "music_" + music_file.name)
    if not os.path.exists(mp):
        open(mp, "wb").write(music_file.getbuffer())
    st.session_state["music_path_saved"] = mp
    music_path = mp

S = dict(mode=mode, caption_font=caption_font, caption_style=caption_style, caption_anim=caption_anim,
         caption_box=caption_box, caption_size=caption_size, caption_color=caption_color,
         highlight_color=highlight_color, frame_mode=frame_mode, bg_color=bg_color, crop_zoom=crop_zoom,
         crop_x=crop_x, crop_y=crop_y, border=border, border_color=border_color, border_width=border_width,
         progress_bar=progress_bar, slow_zoom=slow_zoom, overlay_text=overlay_text, overlay_pos=overlay_pos,
         overlay_color=overlay_color, min_dur=int(min_dur), max_dur=int(max_dur), music_path=music_path,
         music_volume=music_volume, original_audio=original_audio)

# ---------------------------------------------------------------- preview --
with col_prev:
    st.markdown('<div class="panel"><h4>Live preview</h4>', unsafe_allow_html=True)
    st.markdown('<div class="ribbon-note">Turant update hota hai — video process nahi hoti. '
                'Final output bilkul aisa hi dikhega.</div>', unsafe_allow_html=True)
    t = min(10, max(0, dur_total / 2))
    try:
        st.markdown(preview_html(frame_uri(primary, t), S, language), unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Preview nahi bana: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="panel"><h4>Process</h4>', unsafe_allow_html=True)
    if st.button("Generate", type="primary", use_container_width=True):
        bar = st.progress(0.0, text="Shuru…")
        tip = st.empty()
        try:
            trans = {}
            for i, vp in enumerate(paths):
                stem = os.path.splitext(os.path.basename(vp))[0]

                def cb(frac, _s=stem, _i=i):
                    bar.progress((_i + frac) / len(paths) * 0.6, text=f"Transcribing {_s}… {int(frac*100)}%")

                trans[vp] = full_transcript(vp, model_size, None if language == "auto" else language, cb)
                os.makedirs("transcripts", exist_ok=True)
                with open(f"transcripts/{stem}.txt", "w", encoding="utf-8") as f:
                    for s in trans[vp]:
                        f.write(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text'].strip()}\n")

            tasks, details = [], []
            for vp in paths:
                stem = os.path.splitext(os.path.basename(vp))[0]
                segs = trans[vp]
                if mode == "transcribe_only":
                    continue
                if mode == "full_video":
                    os.makedirs("captioned", exist_ok=True)
                    end = max(x["end"] for x in segs) if segs else 0
                    out = f"captioned/{stem}_captioned.mp4"
                    tasks.append((vp, segs, 0.0, end, out))
                    txt = engine.clip_text(segs, 0, end)
                    details.append({"file": os.path.basename(out), "title": txt[:90] or stem,
                                    "desc": txt, "tags": engine.hashtags(txt)})
                else:
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=int(workers)) as ex:
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
            privacy = st.selectbox("Privacy", ["private", "unlisted", "public"], 0)
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
