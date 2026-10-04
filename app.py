"""
app.py — Streamlit UI for the Auto Reel Maker.

Live preview: jab bhi tum koi option badalte ho, ek chhota sample turant ban ke
dikh jaata hai -- taaki blindly kuch na chunna pade.

Run locally:   streamlit run app.py
"""
import os
import re
import json
import hashlib
import zipfile
import subprocess

import streamlit as st

import engine

st.set_page_config(page_title="Auto Reel Maker", page_icon="🎬", layout="wide")

WORK = "work"
os.makedirs(WORK, exist_ok=True)
FONTS = engine.ensure_fonts(os.path.join(WORK, "fonts"))


# ---------------------------------------------------------------- utils ----
def save_upload(uploaded):
    data = uploaded.getbuffer()
    h = hashlib.md5(data).hexdigest()[:10]
    name = f"{h}_{uploaded.name}"
    path = os.path.join(WORK, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return path


def get_duration(path):
    err = subprocess.run([engine.ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


@st.cache_data(show_spinner=False)
def transcript_window(video_path, ss, dur, model_size, language):
    audio = engine.extract_audio(video_path, ss=ss, dur=dur, out=os.path.join(WORK, "pv.f32"))
    segs, _ = engine.transcribe(audio, model_size, language)
    for s in segs:                                   # shift to absolute time
        s["start"] += ss; s["end"] += ss
        s["words"] = [(a + ss, b + ss, w) for (a, b, w) in s["words"]]
    return segs


@st.cache_data(show_spinner=False)
def transcript_full(video_path, model_size, language):
    audio = engine.extract_audio(video_path, out=os.path.join(WORK, "full.f32"))
    segs, _ = engine.transcribe(audio, model_size, language)
    return segs


@st.cache_data(show_spinner=False)
def render_preview(video_path, ss, dur, model_size, language, settings_json):
    S = json.loads(settings_json)
    segs = transcript_window(video_path, ss, dur, model_size, language)
    out = os.path.join(WORK, "preview.mp4")
    engine.render_segment(video_path, segs, ss, ss + dur, out, S, FONTS)
    return out


# --------------------------------------------------------------- sidebar ---
st.sidebar.title("⚙️ Settings")

mode = st.sidebar.selectbox("Mode", ["reels", "full_video", "transcribe_only"], index=0,
                            help="reels = clips banake 9:16 · full_video = poori video + captions · transcribe_only = sirf text")

LANG = ["auto", "hi", "en", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"]
language = st.sidebar.selectbox("Language", LANG, index=0)
model_size = st.sidebar.selectbox("Whisper model", ["tiny", "base", "small", "medium", "large-v3"], index=2,
                                  help="CPU pe: small/medium. GPU ho to medium/large-v3.")

DEVANAGARI = {"hi", "mr", "ne"}
FONT = st.sidebar.selectbox("Caption font", ["auto"] + engine.FONT_CHOICES, index=0)
if language in DEVANAGARI:
    caption_font = "Noto Sans Devanagari"
elif FONT == "auto":
    caption_font = "Poppins"
else:
    caption_font = FONT

st.sidebar.markdown("---")
st.sidebar.subheader("Captions")
caption_style = st.sidebar.selectbox("Caption style", ["karaoke", "plain", "none"], index=0)
caption_anim = st.sidebar.selectbox("Animation", ["pop", "fade", "none"], index=0)
caption_box = st.sidebar.checkbox("Box behind text", value=False)
caption_size = st.sidebar.slider("Caption size", 30, 100, 62)
caption_color = st.sidebar.color_picker("Caption colour", "#FFFFFF")
highlight_color = st.sidebar.color_picker("Highlight colour (karaoke)", "#FFD400")

st.sidebar.markdown("---")
st.sidebar.subheader("Framing")
frame_mode = st.sidebar.selectbox("Frame mode", ["fit_blur", "fit_color", "crop"], index=0,
                                  help="fit_blur = poora video + blurred bg · fit_color = solid colour · crop = fill (kaat do)")
bg_color = st.sidebar.color_picker("Background colour (fit_color)", "#101020")
crop_zoom = st.sidebar.slider("Crop zoom", 1.0, 3.0, 1.0, 0.1)
crop_x = st.sidebar.slider("Crop X", 0.0, 1.0, 0.5, 0.05)
crop_y = st.sidebar.slider("Crop Y", 0.0, 1.0, 0.5, 0.05)

st.sidebar.markdown("---")
st.sidebar.subheader("Extras")
border = st.sidebar.checkbox("Border", value=True)
border_color = st.sidebar.color_picker("Border colour", "#FFD400")
border_width = st.sidebar.slider("Border width", 0, 40, 14)
progress_bar = st.sidebar.checkbox("Progress bar", value=True)
slow_zoom = st.sidebar.checkbox("Slow zoom", value=False)
overlay_text = st.sidebar.text_input("Overlay text", "")
overlay_pos = st.sidebar.selectbox("Overlay position", ["top", "bottom"], index=0)
overlay_color = st.sidebar.color_picker("Overlay colour", "#FFD400")

st.sidebar.markdown("---")
st.sidebar.subheader("Audio")
original_audio = st.sidebar.selectbox("Original audio", ["keep", "mute"], index=0)
music_file = st.sidebar.file_uploader("Background music (optional)", type=["mp3", "m4a", "wav", "aac"])
music_volume = st.sidebar.slider("Music volume", 0.0, 1.0, 0.15, 0.05)

st.sidebar.markdown("---")
st.sidebar.subheader("Clips")
min_dur = st.sidebar.number_input("Min clip seconds", 5, 300, 20)
max_dur = st.sidebar.number_input("Max clip seconds", 10, 600, 60)

music_path = ""
if music_file is not None:
    music_path = os.path.join(WORK, "music_" + music_file.name)
    if not os.path.exists(music_path):
        open(music_path, "wb").write(music_file.getbuffer())

S = dict(
    mode=mode, caption_font=caption_font, caption_style=caption_style, caption_anim=caption_anim,
    caption_box=caption_box, caption_size=caption_size, caption_color=caption_color,
    highlight_color=highlight_color, frame_mode=frame_mode, bg_color=bg_color,
    crop_zoom=crop_zoom, crop_x=crop_x, crop_y=crop_y, border=border, border_color=border_color,
    border_width=border_width, progress_bar=progress_bar, slow_zoom=slow_zoom,
    overlay_text=overlay_text, overlay_pos=overlay_pos, overlay_color=overlay_color,
    min_dur=int(min_dur), max_dur=int(max_dur), music_path=music_path,
    music_volume=music_volume, original_audio=original_audio,
)
SETTINGS_JSON = json.dumps(S, sort_keys=True)

# ----------------------------------------------------------------- main ----
st.title("🎬 Auto Reel Maker")
st.caption("Long video → reels with captions · ya poori video pe captions. Preview pehle dekho, phir banao.")

uploads = st.file_uploader("Upload your video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                           accept_multiple_files=True)

if not uploads:
    st.info("Pehle apni video upload karo. Uske baad preview aur generate options aa jaayenge.")
    st.stop()

paths = [save_upload(u) for u in uploads]
primary = paths[0]
dur_total = get_duration(primary)
st.success(f"{len(paths)} video(s) ready. Pehli video: {dur_total/60:.1f} min")

tab_preview, tab_run = st.tabs(["👀 Preview", "🚀 Generate"])

# ------------------------------------------------------------- preview ----
with tab_preview:
    st.subheader("Preview")
    st.write("Yahan options ka asar turant dikhega. Sample ke liye ek chhota hissa chuno:")
    c1, c2, c3 = st.columns(3)
    ss = c1.number_input("Start (seconds)", 0, max(1, int(dur_total)), int(min(30, dur_total * 0.1)))
    pdur = c2.number_input("Preview length (seconds)", 4, 30, 10)
    c3.write("")
    c3.write("")
    if c3.button("↻ Refresh preview"):
        st.cache_data.clear()

    with st.spinner("Sample ban raha hai…"):
        try:
            pv = render_preview(primary, float(ss), float(pdur), model_size, None if language == "auto" else language, SETTINGS_JSON)
            st.video(pv)
            st.caption("Ye sample sirf preview ke liye hai (is window ka transcript). Final output me poori video process hogi.")
        except Exception as e:
            st.error(f"Preview fail hua: {e}")

# --------------------------------------------------------------- run ------
with tab_run:
    st.subheader("Generate")
    if mode == "transcribe_only":
        st.write("Sirf transcript milega.")
    else:
        st.write("Poori video process hogi. Lambi video pe thoda time lagega.")
    if st.button("▶️ Generate now", type="primary"):
        progress = st.progress(0.0, text="Transcribing…")
        results, details = [], []
        try:
            for vi, vp in enumerate(paths):
                stem = os.path.splitext(os.path.basename(vp))[0]
                segs = transcript_full(vp, model_size, None if language == "auto" else language)
                os.makedirs("transcripts", exist_ok=True)
                with open(f"transcripts/{stem}.txt", "w", encoding="utf-8") as f:
                    for s in segs:
                        f.write(f"[{s['start']:.1f} - {s['end']:.1f}] {s['text'].strip()}\n")

                if mode == "transcribe_only":
                    progress.progress((vi + 1) / len(paths), text=f"done: {stem}")
                    continue

                if mode == "full_video":
                    os.makedirs("captioned", exist_ok=True)
                    end = max(x["end"] for x in segs) if segs else 0
                    out = f"captioned/{stem}_captioned.mp4"
                    engine.render_segment(vp, segs, 0.0, end, out, S, FONTS)
                    txt = engine.clip_text(segs, 0, end)
                    results.append(out)
                    details.append({"file": os.path.basename(out), "title": txt[:90] or stem,
                                    "desc": txt, "tags": engine.hashtags(txt)})
                else:
                    clips = engine.find_clips(segs, S["min_dur"], S["max_dur"])
                    os.makedirs(f"reels/{stem}", exist_ok=True)
                    for i, (s, e) in enumerate(clips):
                        out = f"reels/{stem}/reel_{i+1:02d}.mp4"
                        engine.render_segment(vp, segs, s, e, out, S, FONTS)
                        txt = engine.clip_text(segs, s, e)
                        results.append(out)
                        details.append({"file": f"{stem}/reel_{i+1:02d}.mp4", "title": txt[:90] or f"Reel {i+1}",
                                        "desc": txt, "tags": engine.hashtags(txt)})
                progress.progress((vi + 1) / len(paths), text=f"done: {stem}")

            # post_details.txt — title / description / hashtags per output
            with open("post_details.txt", "w", encoding="utf-8") as f:
                f.write("POST DETAILS - ready to paste into YouTube / Instagram\n")
                f.write("=" * 50 + "\n\n")
                for x in details:
                    f.write(f"FILE: {x['file']}\nTITLE: {x['title']}\n")
                    f.write(f"DESCRIPTION:\n{x['desc']}\nHASHTAGS: {x['tags']} #shorts #reels\n")
                    f.write("-" * 50 + "\n")

            progress.progress(1.0, text="Packaging…")
            zpath = os.path.join(WORK, "output.zip")
            with zipfile.ZipFile(zpath, "w") as z:
                for rp in results:
                    z.write(rp, os.path.basename(rp))
                if os.path.exists("post_details.txt"):
                    z.write("post_details.txt", "post_details.txt")
                for tp in ("transcripts",):
                    if os.path.isdir(tp):
                        for root, _, files in os.walk(tp):
                            for fn in files:
                                full = os.path.join(root, fn)
                                z.write(full, os.path.relpath(full, "."))
            st.success(f"Ho gaya! {len(results)} file(s) + post_details.txt taiyaar.")
            with open(zpath, "rb") as f:
                st.download_button("⬇️ Download output.zip", f, file_name="output.zip")
        except Exception as e:
            st.error(f"Generate fail hua: {e}")
