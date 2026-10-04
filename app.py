"""
app.py — Auto Reel Maker (Streamlit UI)

- Live, phone-sized preview so you can see every option before committing.
- Progress + tips while transcribing so you're never staring at a frozen screen.
- YouTube upload built in.

Run locally:  streamlit run app.py
"""
import os
import re
import json
import time
import hashlib
import zipfile
import subprocess

import streamlit as st

import engine

st.set_page_config(page_title="Auto Reel Maker", page_icon="🎬", layout="wide")

# ----------------------------------------------------------------- theme ---
st.markdown("""
<style>
  .block-container {padding-top: 1.2rem; max-width: 1250px;}
  h1.app-title {
    background: linear-gradient(90deg,#8b5cf6,#ec4899,#f59e0b);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-weight: 800; font-size: 2.3rem; margin-bottom: 0;
  }
  .app-sub {color:#9aa0b4; margin-top:-6px; margin-bottom: 14px;}
  div[data-testid="stSidebar"] {background: #0e0f1a;}
  div[data-testid="stSidebar"] h2 {font-size: 1.05rem;}
  .stButton>button, .stDownloadButton>button {
    border-radius: 12px; font-weight: 600; border: none;
    background: linear-gradient(90deg,#8b5cf6,#ec4899); color: white;
  }
  .stButton>button:hover, .stDownloadButton>button:hover {opacity: .9; color: white;}
  /* phone-sized video preview */
  div[data-testid="stVideo"] {max-width: 360px; margin-left: auto; margin-right: auto;}
  div[data-testid="stVideo"] video {border-radius: 18px; box-shadow: 0 10px 34px rgba(0,0,0,.45);}
  .tipbox {background:#161829; border:1px solid #2a2d45; border-radius:12px; padding:12px 16px; color:#c8cbe0;}
  .pill {display:inline-block; background:#1b1e30; border:1px solid #2a2d45; border-radius:999px;
         padding:3px 12px; margin:2px; font-size:.8rem; color:#aab;}
</style>
""", unsafe_allow_html=True)

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))

TIPS = [
    "Karaoke captions (word highlight) sabse zyada scroll rok dete hain.",
    "Screen recordings ke liye 'fit_blur' best hai — poora screen dikhta hai.",
    "Border aur progress bar reels ko premium look dete hain.",
    "Hindi/Hinglish ke liye Language = 'hi' rakho, warna galat detect ho sakta hai.",
    "Lambi video pe 'small' model chuno — CPU pe time bachta hai.",
    "Overlay me 'Follow for more' likho — har reel pe chalega.",
    "Clip length 20-60s Reels ke liye sweet spot hai.",
    "Captions ke liye Poppins/Anton English me, Noto Sans Devanagari Hindi me.",
]


# ---------------------------------------------------------------- utils ----
def save_upload(uploaded):
    data = uploaded.getbuffer()
    h = hashlib.md5(data).hexdigest()[:10]
    path = os.path.join(WORK, f"{h}_{uploaded.name}")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return path


def get_duration(path):
    err = subprocess.run([engine.ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


@st.cache_data(show_spinner=False)
def transcript_window(video_path, ss, dur, model_size, language):
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pv.f32"))
    segs, _ = engine.transcribe(audio, model_size, language)
    for s in segs:
        s["start"] += ss; s["end"] += ss
        s["words"] = [(a + ss, b + ss, w) for (a, b, w) in s["words"]]
    return segs


@st.cache_data(show_spinner=False)
def render_preview(video_path, ss, dur, model_size, language, settings_json):
    S = json.loads(settings_json)
    segs = transcript_window(video_path, ss, dur, model_size, language)
    out = os.path.join(WORK, "preview.mp4")
    engine.render_segment(video_path, segs, ss, ss + dur, out, S, FONTS)
    return out


def full_transcript(video_path, model_size, language, progress_cb=None):
    key = f"{video_path}|{model_size}|{language}"
    store = st.session_state.setdefault("transcripts", {})
    if key in store:
        return store[key]
    audio = engine.extract_audio(video_path, out=os.path.join(WORK, "full.f32"))
    segs, _ = engine.transcribe(audio, model_size, language, progress=progress_cb)
    store[key] = segs
    return segs


# --------------------------------------------------------------- sidebar ---
st.sidebar.markdown("## ⚙️ Settings")

mode = st.sidebar.selectbox("Mode", ["reels", "full_video", "transcribe_only"], index=0,
                            help="reels = clips -> 9:16 · full_video = poori video + captions · transcribe_only = sirf text")
language = st.sidebar.selectbox("Language", ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"], index=0)
model_size = st.sidebar.selectbox("Whisper model", ["tiny", "base", "small", "medium", "large-v3"], index=2,
                                  help="CPU pe 'small' best. GPU ho to medium/large-v3.")

FONT = st.sidebar.selectbox("Caption font", ["auto"] + engine.FONT_CHOICES, index=0)
caption_font = "Noto Sans Devanagari" if language in {"hi", "mr", "ne"} else ("Poppins" if FONT == "auto" else FONT)

st.sidebar.markdown("---\n### 💬 Captions")
caption_style = st.sidebar.selectbox("Style", ["karaoke", "plain", "none"], index=0)
caption_anim = st.sidebar.selectbox("Animation", ["pop", "fade", "none"], index=0)
caption_box = st.sidebar.checkbox("Box behind text", value=False)
caption_size = st.sidebar.slider("Size", 30, 100, 62)
caption_color = st.sidebar.color_picker("Text colour", "#FFFFFF")
highlight_color = st.sidebar.color_picker("Karaoke highlight", "#FFD400")

st.sidebar.markdown("---\n### 🖼️ Framing")
frame_mode = st.sidebar.selectbox("Frame mode", ["fit_blur", "fit_color", "crop"], index=0,
                                  help="fit_blur = poora video + blurred bg · fit_color = solid colour · crop = fill")
bg_color = st.sidebar.color_picker("Background colour", "#101020")
crop_zoom = st.sidebar.slider("Crop zoom", 1.0, 3.0, 1.0, 0.1)
crop_x = st.sidebar.slider("Crop X", 0.0, 1.0, 0.5, 0.05)
crop_y = st.sidebar.slider("Crop Y", 0.0, 1.0, 0.5, 0.05)

st.sidebar.markdown("---\n### ✨ Extras")
border = st.sidebar.checkbox("Border", value=True)
border_color = st.sidebar.color_picker("Border colour", "#FFD400")
border_width = st.sidebar.slider("Border width", 0, 40, 14)
progress_bar = st.sidebar.checkbox("Progress bar", value=True)
slow_zoom = st.sidebar.checkbox("Slow zoom", value=False)
overlay_text = st.sidebar.text_input("Overlay text", "", placeholder="Follow for more")
overlay_pos = st.sidebar.selectbox("Overlay position", ["top", "bottom"], index=0)
overlay_color = st.sidebar.color_picker("Overlay colour", "#FFD400")

st.sidebar.markdown("---\n### 🎵 Audio")
original_audio = st.sidebar.selectbox("Original audio", ["keep", "mute"], index=0)
music_file = st.sidebar.file_uploader("Background music (optional)", type=["mp3", "m4a", "wav", "aac"])
music_volume = st.sidebar.slider("Music volume", 0.0, 1.0, 0.15, 0.05)

st.sidebar.markdown("---\n### ✂️ Clips")
min_dur = st.sidebar.number_input("Min clip (s)", 5, 300, 20)
max_dur = st.sidebar.number_input("Max clip (s)", 10, 600, 60)

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
SETTINGS_JSON = json.dumps(S, sort_keys=True)

# ----------------------------------------------------------------- main ----
st.markdown('<h1 class="app-title">🎬 Auto Reel Maker</h1>', unsafe_allow_html=True)
st.markdown('<p class="app-sub">Long video → reels with captions · ya poori video pe captions. Preview pehle dekho, phir banao.</p>', unsafe_allow_html=True)

uploads = st.file_uploader("Upload your video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                           accept_multiple_files=True)

if not uploads:
    st.markdown(
        '<div class="tipbox">👋 Shuru karne ke liye apni video upload karo. '
        'Upload hote-hote ye tips padh lo:<br><br>' +
        "".join(f'<span class="pill">{t}</span>' for t in TIPS[:5]) + "</div>",
        unsafe_allow_html=True)
    st.stop()

paths = [save_upload(u) for u in uploads]
primary = paths[0]
dur_total = get_duration(primary)
st.success(f"✅ {len(paths)} video ready · pehli video {dur_total/60:.1f} min")

tab_preview, tab_run, tab_yt = st.tabs(["👀 Preview", "🚀 Generate", "📤 YouTube"])

# ------------------------------------------------------------- preview ----
with tab_preview:
    st.subheader("Preview")
    st.caption("Options ka asar turant dikhega. Neeche se sample ka hissa chuno:")
    c1, c2, c3 = st.columns([1, 1, 1])
    ss = c1.number_input("Start (s)", 0, max(1, int(dur_total)), int(min(30, dur_total * 0.1)))
    pdur = c2.number_input("Length (s)", 4, 30, 10)
    if c3.button("↻ Refresh"):
        st.cache_data.clear()

    with st.spinner("Sample ban raha hai…"):
        try:
            pv = render_preview(primary, float(ss), float(pdur), model_size,
                                None if language == "auto" else language, SETTINGS_JSON)
            st.video(pv)
            st.caption("Ye sirf preview hai (is window ka transcript). Final me poori video process hogi.")
        except Exception as e:
            st.error(f"Preview fail: {e}")

# --------------------------------------------------------------- run ------
with tab_run:
    st.subheader("Generate")
    st.caption("Poori video process hogi — lambi video pe time lagega. Aapko progress dikhega.")
    if st.button("▶️ Generate now", type="primary"):
        bar = st.progress(0.0, text="Shuru…")
        tip = st.empty()
        results, details = [], []
        try:
            for vi, vp in enumerate(paths):
                stem = os.path.splitext(os.path.basename(vp))[0]

                def cb(frac, _stem=stem):
                    bar.progress(frac, text=f"Transcribing {_stem}… {int(frac*100)}%")
                    tip.markdown(f'<div class="tipbox">💡 {TIPS[int(frac*len(TIPS)) % len(TIPS)]}</div>',
                                 unsafe_allow_html=True)

                segs = full_transcript(vp, model_size, None if language == "auto" else language, cb)
                os.makedirs("transcripts", exist_ok=True)
                with open(f"transcripts/{stem}.txt", "w", encoding="utf-8") as f:
                    for s in segs:
                        f.write(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text'].strip()}\n")

                if mode == "transcribe_only":
                    continue

                if mode == "full_video":
                    os.makedirs("captioned", exist_ok=True)
                    end = max(x["end"] for x in segs) if segs else 0
                    out = f"captioned/{stem}_captioned.mp4"
                    bar.progress(0.9, text=f"Rendering {stem}…")
                    engine.render_segment(vp, segs, 0.0, end, out, S, FONTS)
                    txt = engine.clip_text(segs, 0, end)
                    results.append(out)
                    details.append({"file": os.path.basename(out), "title": txt[:90] or stem,
                                    "desc": txt, "tags": engine.hashtags(txt)})
                else:
                    clips = engine.find_clips(segs, S["min_dur"], S["max_dur"])
                    os.makedirs(f"reels/{stem}", exist_ok=True)
                    for i, (s, e) in enumerate(clips):
                        bar.progress(min(0.95, 0.5 + 0.45 * (i + 1) / max(1, len(clips))),
                                     text=f"Rendering {stem} clip {i+1}/{len(clips)}…")
                        out = f"reels/{stem}/reel_{i+1:02d}.mp4"
                        engine.render_segment(vp, segs, s, e, out, S, FONTS)
                        txt = engine.clip_text(segs, s, e)
                        results.append(out)
                        details.append({"file": f"{stem}/reel_{i+1:02d}.mp4",
                                        "title": txt[:90] or f"Reel {i+1}", "desc": txt,
                                        "tags": engine.hashtags(txt)})
                bar.progress((vi + 1) / len(paths), text=f"done: {stem}")

            with open("post_details.txt", "w", encoding="utf-8") as f:
                f.write("POST DETAILS - ready to paste into YouTube / Instagram\n" + "=" * 50 + "\n\n")
                for x in details:
                    f.write(f"FILE: {x['file']}\nTITLE: {x['title']}\nDESCRIPTION:\n{x['desc']}\n")
                    f.write(f"HASHTAGS: {x['tags']} #shorts #reels\n" + "-" * 50 + "\n")

            bar.progress(1.0, text="Packaging…")
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
            st.session_state["results"] = results
            st.session_state["details"] = details
            st.success(f"🎉 Ho gaya! {len(results)} file(s) + post_details.txt")
            with open(zpath, "rb") as f:
                st.download_button("⬇️ Download output.zip", f, file_name="output.zip")
        except Exception as e:
            st.error(f"Generate fail: {e}")

# ------------------------------------------------------------ youtube -----
with tab_yt:
    st.subheader("📤 Upload to YouTube")
    st.caption("Reels private upload honge — YouTube Studio me review karke public karo.")
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
        st.success("✅ YouTube se connected (saved login reuse ho raha hai).")
        if st.button("🔌 Disconnect"):
            st.session_state["yt_creds"] = None
            if os.path.exists(token_path):
                os.remove(token_path)
            st.rerun()
    else:
        st.write("**Ek baar ka setup:** apna OAuth `client_secret.json` (Desktop app type) upload karo,")
        st.write("phir link kholo, approve karo, aur address bar se `code=` wali value paste karo.")
        cs = st.file_uploader("client_secret.json", type=["json"], key="cs")
        if cs is not None:
            cs_path = os.path.join(WORK, "client_secret.json")
            open(cs_path, "wb").write(cs.getbuffer())
            st.session_state["cs_path"] = cs_path
        if st.button("1️⃣ Get authorization link") and st.session_state.get("cs_path"):
            from google_auth_oauthlib.flow import Flow
            flow = Flow.from_client_secrets_file(st.session_state["cs_path"], scopes=SCOPES,
                                                 redirect_uri="http://localhost:8080/")
            url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            st.session_state["yt_flow"] = flow
            st.session_state["yt_url"] = url
        if st.session_state.get("yt_url"):
            st.markdown(f"[🔗 Open this link and approve]({st.session_state['yt_url']})")
            code = st.text_input("Paste the code (only the part after 'code=', before '&')")
            if st.button("2️⃣ Connect") and code.strip():
                try:
                    flow = st.session_state["yt_flow"]
                    flow.fetch_token(code=code.strip())
                    st.session_state["yt_creds"] = flow.credentials
                    open(token_path, "w").write(flow.credentials.to_json())
                    st.success("Connected! Ab upload kar sakte ho.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Connect fail: {e}")

    if creds:
        privacy = st.selectbox("Privacy", ["private", "unlisted", "public"], index=0)
        st.write("Pehle **Generate** tab me reels banao, phir yahan upload karo.")
        if st.button("🚀 Upload generated videos", type="primary"):
            try:
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload
                yt = build("youtube", "v3", credentials=creds)
                files = sorted([p for p in st.session_state.get("results", []) if os.path.exists(p)])
                if not files:
                    st.warning("Koi file nahi mili — pehle Generate karo.")
                meta = {x["file"]: x for x in st.session_state.get("details", [])}
                for p in files:
                    key = os.path.basename(p) if p.startswith("captioned/") else "/".join(p.split("/")[-2:])
                    m = meta.get(key, {})
                    body = {"snippet": {"title": (m.get("title") or os.path.basename(p))[:95],
                                        "description": (m.get("desc", "") + "\n\n" + m.get("tags", "")),
                                        "categoryId": "22"},
                            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
                    media = MediaFileUpload(p, chunksize=-1, resumable=True)
                    resp = yt.videos().insert(part="snippet,status", body=body, media_body=media).execute()
                    st.write(f"✅ {os.path.basename(p)} → https://youtu.be/{resp['id']}")
            except Exception as e:
                st.error(f"Upload fail: {e}")
