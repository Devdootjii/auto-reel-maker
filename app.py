"""
app.py — Auto Reel Maker (Streamlit)

Design goals (v3):
- ONE page, no tab-hopping. Settings left, live preview right.
- INSTANT preview: no video rendering. A single frame + CSS overlay shows exactly
  where every element will sit and how it will look. Changes appear immediately.
- Parallel rendering of clips/videos.
- When done: download, YouTube upload, and the title/description/hashtags with
  one-click copy.
"""
import os
import re
import json
import base64
import hashlib
import zipfile
import subprocess
import concurrent.futures

import streamlit as st

import engine

st.set_page_config(page_title="Auto Reel Maker", page_icon="🎬", layout="wide")

# ------------------------------------------------------------------ CSS ----
st.markdown("""
<style>
  .block-container {padding: 1rem 1.4rem 2rem 1.4rem; max-width: 1500px;}
  header[data-testid="stHeader"] {background: transparent;}
  .brand {font-size:1.6rem; font-weight:800; letter-spacing:.3px;
          background:linear-gradient(90deg,#8b5cf6,#ec4899,#f59e0b);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent;}
  .sub {color:#8b90a8; font-size:.9rem; margin-top:-4px;}
  .panel {background:#141626; border:1px solid #232742; border-radius:16px; padding:14px 16px;}
  .stButton>button, .stDownloadButton>button {
      border-radius:11px; font-weight:600; border:0;
      background:linear-gradient(90deg,#8b5cf6,#ec4899); color:#fff;}
  .stButton>button:hover, .stDownloadButton>button:hover {color:#fff; opacity:.92;}
  section[data-testid="stSidebar"] {display:none;}
  label, .stMarkdown p {font-size:.86rem;}
  .smallhint {color:#7b8199; font-size:.78rem;}
</style>
""", unsafe_allow_html=True)

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))

TIPS = [
    "Karaoke captions scroll rok dete hain.",
    "Screen recordings ke liye fit_blur best hai.",
    "20–60s clip Reels ka sweet spot hai.",
    "Hindi ke liye Language = 'hi' rakho.",
    "Lambi video pe 'small' model chuno.",
    "Overlay me 'Follow for more' likho.",
]


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


@st.cache_data(show_spinner=False)
def frame_uri(video_path, t):
    out = os.path.join(WORK, f"frame_{hashlib.md5((video_path+str(t)).encode()).hexdigest()[:8]}.jpg")
    engine.extract_frame(video_path, t, out, width=420)
    return "data:image/jpeg;base64," + base64.b64encode(open(out, "rb").read()).decode()


@st.cache_data(show_spinner=False)
def font_face(font_name):
    fname = engine.FONT_URLS and {
        "Poppins": "Poppins-Bold.ttf", "Anton": "Anton-Regular.ttf", "Montserrat": "Montserrat.ttf",
        "Bebas Neue": "BebasNeue-Regular.ttf", "Noto Sans Devanagari": "NotoSansDevanagari.ttf",
    }.get(font_name)
    if not fname:
        return ""
    p = os.path.join(FONTS, fname)
    if not os.path.exists(p) or os.path.getsize(p) > 300_000:
        return ""   # heavy fonts -> use the system font in the preview (keeps it instant)
    b64 = base64.b64encode(open(p, "rb").read()).decode()
    return "@font-face{font-family:'PV';src:url(data:font/ttf;base64," + b64 + ");font-weight:700;}"


SAMPLE = {
    "hi": (["आज", "हम", "बात", "करेंगे", "क्रिकेट", "की"], 2),
    "default": (["Here", "is", "how", "it", "works", "for", "you"], 2),
}


def preview_html(frame, S, lang, box_w=300):
    """Instant CSS mockup — no ffmpeg. Shows where each element lands."""
    box_h = int(box_w * 16 / 9)
    words, hl = SAMPLE["hi"] if lang in ("hi", "mr", "ne") else SAMPLE["default"]

    if S["frame_mode"] == "fit_blur":
        bg = ("background-image:url('" + frame + "');background-size:cover;background-position:center;"
              "filter:blur(16px) brightness(.75);")
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
    cap_box = ("background:rgba(0,0,0,.62);padding:3px 10px;border-radius:8px;"
               if S["caption_box"] else "")
    hlcol = S["highlight_color"]

    cap = ""
    if S["caption_style"] != "none":
        if S["caption_style"] == "karaoke":
            html_words = " ".join(
                ("<span style='color:" + hlcol + "'>" + w + "</span>") if i == hl else w
                for i, w in enumerate(words))
        else:
            html_words = " ".join(words)
        cap = ("<div style='position:absolute;left:7%;right:7%;bottom:11%;text-align:center;"
               "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:" + str(fs) + "px;"
               "color:" + S["caption_color"] + ";" + outline + "'>"
               "<span style='" + cap_box + "'>" + html_words + "</span></div>")

    ov = ""
    if S["overlay_text"].strip():
        pos = "top:9%;" if S["overlay_pos"] == "top" else "bottom:24%;"
        ov = ("<div style='position:absolute;left:6%;right:6%;" + pos + "text-align:center;"
              "font-family:\"PV\",system-ui,sans-serif;font-weight:700;font-size:" + str(max(8, round(fs*0.8))) + "px;"
              "color:" + S["overlay_color"] + ";" + outline + "'>" + S["overlay_text"] + "</div>")

    prog = ("<div style='position:absolute;top:0;left:0;height:6px;width:42%;"
            "background:" + S["border_color"] + ";'></div>") if S["progress_bar"] else ""

    bw = S["border_width"] if S["border"] else 0
    frame_css = ("position:relative;width:" + str(box_w) + "px;height:" + str(box_h) + "px;margin:0 auto;"
                 "border-radius:18px;overflow:hidden;border:" + str(bw) + "px solid " + S["border_color"] + ";"
                 "box-shadow:0 12px 40px rgba(0,0,0,.5);")

    return ("<style>" + font_face(S["caption_font"]) + "</style>"
            "<div style='" + frame_css + "'>"
            "<div style='position:absolute;inset:0;" + bg + "'></div>"
            "<div style='position:absolute;inset:0;" + fg + "'></div>"
            + prog + ov + cap + "</div>")


@st.cache_data(show_spinner=False)
def transcript_window(video_path, ss, dur, model_size, language):
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pv.f32"))
    segs, _ = engine.transcribe(audio, model_size, language)
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
    segs, _ = engine.transcribe(audio, model_size, language, progress=progress_cb)
    store[key] = segs
    return segs


# ----------------------------------------------------------------- header --
c_head, c_up = st.columns([1, 1.3])
with c_head:
    st.markdown('<div class="brand">🎬 Auto Reel Maker</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Option chuno → turant preview dekho → process karo.</div>', unsafe_allow_html=True)
with c_up:
    uploads = st.file_uploader("Video(s) upload karo", type=["mp4", "mov", "mkv", "webm", "avi"],
                               accept_multiple_files=True, label_visibility="collapsed")

if not uploads:
    st.markdown('<div class="panel">👋 Shuru karne ke liye video upload karo.<br><br>' +
                "".join(f"<span class='smallhint'>• {t}&nbsp;&nbsp;</span>" for t in TIPS) + "</div>",
                unsafe_allow_html=True)
    st.stop()

paths = [save_upload(u) for u in uploads]
primary = paths[0]
dur_total = get_duration(primary)

col_set, col_prev = st.columns([1, 1.15], gap="large")

# --------------------------------------------------------------- settings --
with col_set:
    st.markdown("#### ⚙️ Settings")
    a, b = st.columns(2)
    mode = a.selectbox("Mode", ["reels", "full_video", "transcribe_only"], 0)
    language = b.selectbox("Language", ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"], 0)
    model_size = a.selectbox("Whisper model", ["tiny", "base", "small", "medium"], 2,
                             help="CPU pe 'small' best.")
    FONT = b.selectbox("Caption font", ["auto"] + engine.FONT_CHOICES, 0)
    caption_font = "Noto Sans Devanagari" if language in {"hi", "mr", "ne"} else ("Poppins" if FONT == "auto" else FONT)

    a, b = st.columns(2)
    caption_style = a.selectbox("Caption style", ["karaoke", "plain", "none"], 0)
    caption_anim = b.selectbox("Animation", ["pop", "fade", "none"], 0)
    caption_box = a.checkbox("Box behind text", False)
    caption_size = b.slider("Caption size", 30, 100, 62)
    a, b = st.columns(2)
    caption_color = a.color_picker("Text colour", "#FFFFFF")
    highlight_color = b.color_picker("Karaoke highlight", "#FFD400")

    a, b = st.columns(2)
    frame_mode = a.selectbox("Frame mode", ["fit_blur", "fit_color", "crop"], 0)
    bg_color = b.color_picker("Background", "#101020")
    a, b, c = st.columns(3)
    crop_zoom = a.slider("Crop zoom", 1.0, 3.0, 1.0, 0.1)
    crop_x = b.slider("Crop X", 0.0, 1.0, 0.5, 0.05)
    crop_y = c.slider("Crop Y", 0.0, 1.0, 0.5, 0.05)

    a, b = st.columns(2)
    border = a.checkbox("Border", True)
    border_color = b.color_picker("Border colour", "#FFD400")
    a, b = st.columns(2)
    border_width = a.slider("Border width", 0, 40, 14)
    progress_bar = b.checkbox("Progress bar", True)
    a, b = st.columns(2)
    slow_zoom = a.checkbox("Slow zoom", False)
    overlay_pos = b.selectbox("Overlay position", ["top", "bottom"], 0)
    overlay_text = a.text_input("Overlay text", "", placeholder="Follow for more")
    overlay_color = b.color_picker("Overlay colour", "#FFD400")

    a, b = st.columns(2)
    original_audio = a.selectbox("Original audio", ["keep", "mute"], 0)
    music_volume = b.slider("Music volume", 0.0, 1.0, 0.15, 0.05)
    music_file = st.file_uploader("Background music (optional)", type=["mp3", "m4a", "wav", "aac"])

    a, b, c = st.columns(3)
    min_dur = a.number_input("Min clip (s)", 5, 300, 20)
    max_dur = b.number_input("Max clip (s)", 10, 600, 60)
    workers = c.number_input("Parallel jobs", 1, 8, 2, help="Ek saath kitne clips render hon.")

music_path = ""
if music_file is not None:
    music_path = os.path.join(WORK, "music_" + music_file.name)
    if not os.path.exists(music_path):
        open(music_path, "wb").write(music_file.getbuffer())

S = dict(mode=mode, caption_font=caption_font, caption_style=caption_style, caption_anim=caption_anim,
         caption_box=caption_box, caption_size=caption_size, caption_color=caption_color,
         highlight_color=highlight_color, frame_mode=frame_mode, bg_color=bg_color, crop_zoom=crop_zoom,
         crop_x=crop_x, crop_y=crop_y, border=border, border_color=border_color, border_width=border_width,
         progress_bar=progress_bar, slow_zoom=slow_zoom, overlay_text=overlay_text, overlay_pos=overlay_pos,
         overlay_color=overlay_color, min_dur=int(min_dur), max_dur=int(max_dur), music_path=music_path,
         music_volume=music_volume, original_audio=original_audio)

# ---------------------------------------------------------------- preview --
with col_prev:
    st.markdown("#### 👀 Live preview")
    st.markdown('<div class="smallhint">Ye turant update hota hai — video process nahi hoti. '
                'Final output bilkul aisa hi dikhega.</div>', unsafe_allow_html=True)
    t = min(10, max(0, dur_total / 2))
    try:
        fr = frame_uri(primary, t)
        st.markdown(preview_html(fr, S, language), unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Preview nahi bana: {e}")

    st.markdown("---")
    st.markdown("#### 🚀 Process")
    if st.button("▶️ Generate", type="primary", use_container_width=True):
        bar = st.progress(0.0, text="Shuru…")
        tip = st.empty()
        try:
            # 1) transcribe all videos
            trans = {}
            for i, vp in enumerate(paths):
                stem = os.path.splitext(os.path.basename(vp))[0]

                def cb(frac, _s=stem, _i=i):
                    overall = (_i + frac) / len(paths)
                    bar.progress(overall * 0.6, text=f"Transcribing {_s}… {int(frac*100)}%")
                    tip.markdown('<div class="panel">💡 ' + TIPS[int(frac * len(TIPS)) % len(TIPS)] + '</div>',
                                 unsafe_allow_html=True)

                trans[vp] = full_transcript(vp, model_size, None if language == "auto" else language, cb)
                os.makedirs("transcripts", exist_ok=True)
                with open(f"transcripts/{stem}.txt", "w", encoding="utf-8") as f:
                    for s in trans[vp]:
                        f.write(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text'].strip()}\n")

            # 2) build render tasks
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
                        details.append({"file": f"{stem}/reel_{i+1:02d}.mp4", "title": txt[:90] or f"Reel {i+1}",
                                        "desc": txt, "tags": engine.hashtags(txt)})

            # 3) render in parallel
            results = []
            if tasks:
                done = 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=int(workers)) as ex:
                    futs = {ex.submit(engine.render_segment, vp, segs, s, e, out, S, FONTS): out
                            for (vp, segs, s, e, out) in tasks}
                    for f in concurrent.futures.as_completed(futs):
                        out = f.result()
                        results.append(out)
                        done += 1
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

            bar.progress(1.0, text="Ho gaya!")
            st.session_state["results"] = results
            st.session_state["details"] = details
            st.success(f"🎉 {len(results)} file(s) ready")
        except Exception as e:
            st.error(f"Fail: {e}")

# --------------------------------------------------------------- results ---
if st.session_state.get("results"):
    st.markdown("---")
    st.markdown("### ⬇️ Download & post")
    zpath = os.path.join(WORK, "output.zip")
    if os.path.exists(zpath):
        with open(zpath, "rb") as f:
            st.download_button("⬇️ Download output.zip", f, file_name="output.zip")
    st.markdown("#### 📝 Title / description / hashtags (copy karke paste karo)")
    for x in st.session_state.get("details", []):
        st.markdown(f"**{x['file']}**")
        st.code(f"{x['title']}\n\n{x['desc']}\n\n{x['tags']} #shorts #reels", language=None)

# --------------------------------------------------------------- youtube ---
with st.expander("📤 Upload to YouTube (optional)"):
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
        if st.button("🚀 Upload generated videos"):
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
                    st.write(f"✅ {os.path.basename(p)} → https://youtu.be/{r['id']}")
            except Exception as e:
                st.error(f"Upload fail: {e}")
    else:
        cs = st.file_uploader("client_secret.json (Desktop app type)", type=["json"], key="cs")
        if cs is not None:
            cp = os.path.join(WORK, "client_secret.json")
            open(cp, "wb").write(cs.getbuffer())
            st.session_state["cs_path"] = cp
        if st.button("1️⃣ Get authorization link") and st.session_state.get("cs_path"):
            from google_auth_oauthlib.flow import Flow
            flow = Flow.from_client_secrets_file(st.session_state["cs_path"], scopes=SCOPES,
                                                 redirect_uri="http://localhost:8080/")
            url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            st.session_state["yt_flow"] = flow
            st.session_state["yt_url"] = url
        if st.session_state.get("yt_url"):
            st.markdown(f"[🔗 Open & approve]({st.session_state['yt_url']})")
            code = st.text_input("Paste code (after 'code=', before '&')")
            if st.button("2️⃣ Connect") and code.strip():
                try:
                    st.session_state["yt_flow"].fetch_token(code=code.strip())
                    st.session_state["yt_creds"] = st.session_state["yt_flow"].credentials
                    open(token_path, "w").write(st.session_state["yt_flow"].credentials.to_json())
                    st.rerun()
                except Exception as e:
                    st.error(f"Connect fail: {e}")
