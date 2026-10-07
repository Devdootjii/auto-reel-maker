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

# ====================================================================================
#  ENGINE  (transcription / clips / ffmpeg rendering) — merged into this file so that
#  app and engine can never be out of sync after a deploy.
# ====================================================================================
import sys
import types

# State that must survive Streamlit re-running this script (Whisper models, probes).
_PERSIST = sys.modules.setdefault("_arc_persist", types.ModuleType("_arc_persist"))
if not hasattr(_PERSIST, "models"):
    _PERSIST.models, _PERSIST.audio, _PERSIST.lock = {}, {}, threading.Lock()

import os
import re
import glob
import json
import threading
import subprocess
import concurrent.futures
from collections import Counter

import numpy as np

# ---------------------------------------------------------------- fonts ----
FONT_URLS = {
    "Poppins-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Bold.ttf",
    "Anton-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
    "Montserrat.ttf": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "BebasNeue-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
    "NotoSansDevanagari.ttf": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth,wght%5D.ttf",
}
FONT_CHOICES = ["Poppins", "Anton", "Montserrat", "Bebas Neue", "Noto Sans Devanagari", "DejaVu Sans"]


def _download_font(item):
    name, url, font_dir = item
    dest = os.path.join(font_dir, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 10_000:
        return
    try:
        subprocess.run(["curl", "-sLf", "--retry", "2", "-o", dest, url], check=False, timeout=90)
        if os.path.exists(dest) and os.path.getsize(dest) <= 10_000:
            os.remove(dest)          # failed / error page -> retry next start
    except Exception:
        pass


def ensure_fonts(font_dir):
    """Download caption fonts (in parallel) AND point fontconfig at them.

    Streamlit Cloud has no fontconfig config, so libass cannot find any font unless
    we hand it one via FONTCONFIG_FILE.
    """
    font_dir = os.path.abspath(font_dir)
    os.makedirs(font_dir, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(_download_font, [(n, u, font_dir) for n, u in FONT_URLS.items()]))

    root = os.path.dirname(font_dir)
    cache = os.path.join(root, "fontcache")
    os.makedirs(cache, exist_ok=True)
    conf = os.path.join(root, "fonts.conf")
    text = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        f"  <dir>{font_dir}</dir>\n"
        f"  <cachedir>{cache}</cachedir>\n"
        "</fontconfig>\n"
    )
    if not os.path.exists(conf) or open(conf, encoding="utf-8").read() != text:
        with open(conf, "w", encoding="utf-8") as f:
            f.write(text)
    os.environ["FONTCONFIG_FILE"] = conf
    return font_dir


# ------------------------------------------------------------- ffmpeg -----
def ffmpeg_exe():
    """Prefer a bundled ffmpeg (imageio-ffmpeg) so no system install is needed."""
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run(cmd):
    """Run ffmpeg; on failure raise an error that shows ffmpeg's real message."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        lines = [l for l in (r.stderr or "").strip().splitlines() if l.strip()]
        raise RuntimeError("ffmpeg: " + " | ".join(lines[-3:])[-350:])
    return r


_AUDIO_CACHE = _PERSIST.audio


def has_audio(path):
    if path not in _AUDIO_CACHE:
        try:
            err = subprocess.run([ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
            _AUDIO_CACHE[path] = bool(re.search(r"Stream #\d+:\d+.*?: Audio:", err))
        except Exception:
            _AUDIO_CACHE[path] = True
    return _AUDIO_CACHE[path]


def duration(path):
    try:
        err = subprocess.run([ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def even_clips(total, min_dur=20, max_dur=60):
    """Fallback when there is no speech (e.g. silent screen recordings): cut evenly."""
    if total <= 0:
        return []
    if total <= max_dur:
        return [(0.0, round(total, 1))]
    n = int(-(-total // max_dur))
    step = total / n
    out = [(round(i * step, 1), round((i + 1) * step, 1)) for i in range(n)]
    return [c for c in out if c[1] - c[0] >= min(min_dur, 5)]


def get_dim(path):
    """(width, height) of a video."""
    try:
        err = subprocess.run([ffmpeg_exe(), "-i", path], capture_output=True, text=True).stderr
        m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 1080, 1920


def extract_audio(video_path, ss=None, dur=None, out="audio.f32"):
    """float32 mono @16k. Videos with no audio track give an empty array (no crash)."""
    if not has_audio(video_path):
        return np.zeros(0, dtype=np.float32)
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", video_path]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", out]
    _run(cmd)
    return np.fromfile(out, dtype=np.float32)


def extract_frame(video_path, t, out="frame.jpg", width=None):
    """Grab a single frame as an image (for the instant preview)."""
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(t), "-i", video_path,
           "-frames:v", "1"]
    if width:
        cmd += ["-vf", f"scale={width}:-2"]
    cmd += ["-q:v", "4", out]
    _run(cmd)
    return out


# -------------------------------------------------------- transcription ----
_MODELS = _PERSIST.models
_MODEL_LOCK = _PERSIST.lock


def get_model(model_size="small"):
    """Load a Whisper model ONCE per process and reuse it (loading is the slow part)."""
    with _MODEL_LOCK:
        if model_size not in _MODELS:
            from faster_whisper import WhisperModel
            _MODELS[model_size] = WhisperModel(
                model_size, device="cpu", compute_type="int8",
                cpu_threads=os.cpu_count() or 4, num_workers=1)
        return _MODELS[model_size]


def transcribe(audio, model_size="small", language=None, model=None, progress=None, beam_size=1):
    """audio: float32 mono @16k. Returns (segments, info).

    beam_size=1 (greedy) is ~2-3x faster than the default 5 with very little quality loss.
    progress: optional callable(fraction 0..1) fired as segments arrive.
    """
    if audio is None or len(audio) < 1600:          # < 0.1 s -> nothing to transcribe
        return [], None
    model = model or get_model(model_size)
    segs, info = model.transcribe(
        audio, language=language, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True, beam_size=int(beam_size), best_of=1, temperature=0.0,
        condition_on_previous_text=False)
    total = (len(audio) / 16000.0) or 1.0
    out = []
    for s in segs:
        out.append({
            "start": s.start, "end": s.end, "text": s.text,
            "words": [(w.start, w.end, w.word) for w in (s.words or [])],
        })
        if progress:
            try:
                progress(min(1.0, s.end / total))
            except Exception:
                pass
    return out, info


# --------------------------------------------------------------- clips -----
def find_clips(segments, min_dur=20, max_dur=60, k=2, smooth=2, cutoff=0.5, max_clips=0):
    from sklearn.feature_extraction.text import TfidfVectorizer
    segs = [s for s in segments if s["text"].strip()]
    if len(segs) < 4:
        return [(segs[0]["start"], segs[-1]["end"])] if segs else []
    texts = [s["text"].strip() for s in segs]
    try:
        X = TfidfVectorizer(token_pattern=r"(?u)\b\w\w+\b").fit_transform(texts).toarray()
    except ValueError:                      # empty vocabulary -> just cut evenly
        X = np.eye(len(segs))
    n = X.shape[0]

    def pool(idx):
        sub = X[idx]
        return sub.mean(axis=0) if sub.shape[0] else np.zeros(X.shape[1])

    gap = np.ones(n - 1)
    for g in range(n - 1):
        left = pool(range(max(0, g - k + 1), g + 1))
        right = pool(range(g + 1, min(g + 1 + k, n)))
        d = np.linalg.norm(left) * np.linalg.norm(right)
        gap[g] = float(left @ right / d) if d else 0.0
    if smooth >= 2:
        gap = np.convolve(gap, np.ones(smooth) / smooth, mode="same")
    depth = np.zeros_like(gap)
    for g in range(len(gap)):
        lp = gap[max(0, g - k):g + 1].max()
        rp = gap[g:min(g + k, len(gap))].max()
        depth[g] = (lp - gap[g]) + (rp - gap[g])
    thresh = depth.mean() + cutoff * depth.std()
    cut = sorted(set([0] + [g + 1 for g in range(len(depth)) if depth[g] > thresh] + [n]))
    spans = [(segs[a]["start"], segs[b - 1]["end"]) for a, b in zip(cut[:-1], cut[1:]) if b > a]
    out = []
    for s, e in spans:
        if out and (e - s) < min_dur:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    final = []
    for s, e in out:
        while (e - s) > max_dur:
            final.append((s, s + max_dur)); s += max_dur
        final.append((s, e))
    out2 = [(round(s, 1), round(e, 1)) for s, e in final if (e - s) >= min_dur]
    return out2[:max_clips] if max_clips else out2


def hashtags(text, n=6):
    words = re.findall(r"[A-Za-z\u0900-\u097F]{4,}", text.lower())
    stop = set("this that with from have your will they what when where which about there their them then than been being were are was the and for you not but his her she him our out off over under again also into more very just karenge karega karte".split())
    words = [w for w in words if w not in stop]
    return " ".join("#" + w for w, _ in Counter(words).most_common(n))


def clip_text(segments, s, e):
    return " ".join(x["text"].strip() for x in segments if x["end"] > s and x["start"] < e).strip()


# ----------------------------------------------------------------- ASS -----
def _ass_ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_col(hexstr):
    h = hexstr.lstrip("#"); r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _group_words(words, max_words=4, gap=0.7):
    lines, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[0] - cur[-1][1] > gap):
            lines.append(cur); cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


ANIMS = {"pop": "{\\fscx80\\fscy80\\t(0,160,\\fscx100\\fscy100)}",
         "fade": "{\\fad(140,140)}",
         "none": ""}


def ass_head(W, H, S):
    fs = max(16, round(S.get("caption_size", 62) * H / 1920))
    ovfs = max(14, round(S.get("overlay_size", 54) * H / 1920))
    pos = S.get("caption_pos", "bottom")
    align = 5 if pos == "middle" else 2
    mcapv = round(S.get("caption_margin", 230) * H / 1920) if pos != "middle" else 0
    mlr = round(80 * W / 1080)
    ov_align = 8 if S.get("overlay_pos", "top") == "top" else 2
    ov_margin = round((130 if S.get("overlay_pos", "top") == "top" else 300) * H / 1920)
    ov_lr = round(60 * W / 1080)

    outline = int(S.get("caption_outline", 4))
    if S.get("caption_box", False):
        alpha = int(round((1.0 - float(S.get("caption_box_opacity", 0.6))) * 255))
        cap_back = "&H%02X000000" % alpha
        cap_border, cap_outline, cap_shadow = 3, max(6, outline + 6), 0
    else:
        cap_border, cap_outline, cap_shadow, cap_back = 1, outline, 2, "&H64000000"

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{S['caption_font']},{fs},{_ass_col(S['caption_color'])},&H000000FF,&H00000000,{cap_back},-1,0,0,0,100,100,0,0,{cap_border},{cap_outline},{cap_shadow},{align},{mlr},{mlr},{mcapv},1
Style: Overlay,{S['caption_font']},{ovfs},{_ass_col(S['overlay_color'])},&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,2,{ov_align},{ov_lr},{ov_lr},{ov_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(path, segments, s, e, W, H, S):
    anim = ANIMS.get(S["caption_anim"], "")
    body = ""
    if S["overlay_text"].strip():
        ov = S["overlay_text"].strip().replace("{", "(").replace("}", ")").replace("\n", "\\N")
        body += f"Dialogue: 0,0:00:00.00,{_ass_ts(e - s)},Overlay,,0,0,0,,{ov}\n"
    if S["caption_style"] != "none":
        clip_segs = [x for x in segments if x["end"] > s and x["start"] < e]
        words = []
        for seg in clip_segs:
            for (ws, we, wt) in seg["words"]:
                if ws >= s and ws < e:
                    words.append((ws - s, min(we, e) - s, wt.strip()))
        if S["caption_style"] == "karaoke" and words:
            hl, base = _ass_col(S["highlight_color"]), _ass_col(S["caption_color"])
            for line in _group_words(words, max_words=int(S.get("caption_max_words", 4))):
                for j, w in enumerate(line):
                    st = w[0]
                    en = line[j + 1][0] if j + 1 < len(line) else w[1] + 0.2
                    if S.get("highlight_mode", "color") == "box":
                        txt = " ".join((f"{{\\c{base}\\3c&H000000&\\bord6}}" + x[2] + "{\\r}" if k == j else x[2])
                                       for k, x in enumerate(line))
                    else:
                        txt = " ".join((f"{{\\c{hl}}}{x[2]}{{\\c{base}}}" if k == j else x[2])
                                       for k, x in enumerate(line))
                    if S.get("caption_uppercase", False):
                        txt = txt.upper()
                    body += f"Dialogue: 0,{_ass_ts(st)},{_ass_ts(en)},Caption,,0,0,0,,{anim}{txt}\n"
        else:
            for seg in clip_segs:
                st = max(seg["start"], s); en = min(seg["end"], e)
                txt = seg["text"].strip().replace("{", "(").replace("}", ")")
                if S.get("caption_uppercase", False):
                    txt = txt.upper()
                body += f"Dialogue: 0,{_ass_ts(st - s)},{_ass_ts(en - s)},Caption,,0,0,0,,{anim}{txt}\n"
    open(path, "w", encoding="utf-8").write(ass_head(W, H, S) + body)


# ------------------------------------------------------------- filters ----
def frame_graph(S):
    if S["mode"] == "full_video":
        return "[0:v]null[o]"
    if S["slow_zoom"]:
        # cover-crop to 9:16 first (old code stretched the picture), then zoom slowly
        return ("[0:v]scale=1296:2304:force_original_aspect_ratio=increase,crop=1296:2304,"
                "zoompan=z='min(1.10,1+0.0006*on)':d=1:"
                "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[o]")
    if S["frame_mode"] == "fit_blur":
        # blur a tiny copy and scale it up: looks the same, ~10x cheaper than blurring 1080x1920
        sigma = max(0.5, float(S.get("blur_strength", 30)) / 4.0)
        return ("[0:v]split=2[v1][v2];"
                "[v1]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
                f"gblur=sigma={sigma:.2f},scale=1080:1920[bg];"
                "[v2]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2[o]")
    if S["frame_mode"] == "fit_color":
        col = S["bg_color"].replace("#", "0x")
        return (f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={col}[o]")
    w = "min(iw,ih*9/16)"; h = "min(ih,iw*16/9)"
    return (f"[0:v]crop='{w}/{S['crop_zoom']}':'{h}/{S['crop_zoom']}':"
            f"(iw-ow)*{S['crop_x']}:(ih-oh)*{S['crop_y']},scale=1080:1920[o]")


def audio_graph(fc, S):
    maps = ["-map", "[vout]"]; acodec = []
    music = S.get("music_path") or ""
    if music and S["original_audio"] == "keep":
        fc += f";[0:a]volume={S.get('original_volume',1.0)}[a0];[1:a]volume={S['music_volume']}[a1];[a0][a1]amix=inputs=2:duration=first[aout]"
        maps += ["-map", "[aout]"]; acodec = ["-c:a", "aac"]
    elif music:
        fc += f";[1:a]volume={S['music_volume']}[aout]"
        maps += ["-map", "[aout]"]; acodec = ["-c:a", "aac"]
    elif S["original_audio"] == "keep":
        if float(S.get("original_volume", 1.0)) != 1.0:
            fc += f";[0:a]volume={S.get('original_volume',1.0)}[aout]"
            maps += ["-map", "[aout]"]
        else:
            maps += ["-map", "0:a?"]
        acodec = ["-c:a", "aac"]
    return fc, maps, acodec


# ------------------------------------------------------------- render -----
def render_segment(video_path, segments, s, e, out_path, S, font_dir, preset="veryfast", threads=None):
    """Render one output file covering [s, e] with the given settings."""
    dur = e - s
    S = dict(S)
    if not has_audio(video_path):
        S["original_audio"] = "mute"
    W, H = (1080, 1920) if S["mode"] == "reels" else get_dim(video_path)
    fc = frame_graph(S)
    if S["caption_style"] != "none" or S["overlay_text"].strip():
        ass = out_path + ".ass"
        write_ass(ass, segments, s, e, W, H, S)
        fc += f";[o]ass={ass}:fontsdir={font_dir}[o]"
    if S["mode"] == "reels":
        if S["progress_bar"]:
            # drawbox cannot animate (its `t` means thickness); slide a coloured strip instead
            pc = S.get("progress_color", S["border_color"]).replace("#", "0x")
            fc += (f";color=c={pc}:s=1080x18:r=30:d={dur:.2f}[bar]"
                   f";[o][bar]overlay=x='-w+w*t/{dur:.2f}':y=0:shortest=1[o]")
        if S["border"]:
            fc += f";[o]drawbox=x=0:y=0:w=iw:h=ih:color={S['border_color'].replace('#','0x')}@1:t={S['border_width']}[o]"
    if S.get("fade", False) and dur > 2:
        fo = max(0.0, dur - 0.4)
        fc += f";[o]fade=t=in:st=0:d=0.4,fade=t=out:st={fo:.2f}:d=0.4[o]"
    fc += ";[o]null[vout]"
    fc, maps, acodec = audio_graph(fc, S)

    music = S.get("music_path") or ""
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(s), "-i", video_path]
    if music:
        cmd += ["-ss", str(s), "-stream_loop", "-1", "-i", music]
    cmd += ["-t", str(dur), "-filter_complex", fc] + maps + \
           ["-c:v", "libx264", "-preset", preset, "-crf", "23", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart"] + acodec
    if music and S["mode"] == "full_video":
        cmd += ["-shortest"]
    if threads:
        cmd += ["-threads", str(int(threads))]
    cmd += [out_path]
    try:
        _run(cmd)
    except RuntimeError:
        # last-resort fallback: no effects, original audio
        fb = [ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(s), "-i", video_path, "-t", str(dur)]
        if S["mode"] == "reels":
            fb += ["-vf", "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920"]
        fb += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        fb += (["-c:a", "aac"] if S["original_audio"] == "keep" else ["-an"])
        fb += [out_path]
        _run(fb)
    return out_path


# `engine.xxx(...)` keeps working everywhere in the app
engine = types.SimpleNamespace(**{k: v for k, v in list(globals().items()) if not k.startswith("__")})

st.set_page_config(page_title="Auto Reels Studio", page_icon="🎬", layout="wide",
                   initial_sidebar_state="collapsed")

# ===================================================================== CSS ====
CSS = """
:root{--bg:#07090e;--panel:rgba(14,17,25,.62);--panel2:#181c26;--field:#0e1117;--line:#232836;--line2:#323a50;
  --text:#e8eaf0;--muted:#8d95aa;--accent:#7c5cf0;--accent2:#9279ff;--ok:#34c38f;--bad:#ef5b5b;}

/* full-window app: root font scales with the screen so options stay compact */
html{font-size:clamp(11.5px,.92vw,14.5px) !important;}
html,body,.stApp{height:100vh;overflow:hidden !important;background:var(--bg) !important;}
[data-testid="stAppViewContainer"],[data-testid="stMain"]{height:100vh;overflow:hidden !important;
  background:transparent !important;position:relative;z-index:1;}
.stApp{font-family:Inter,"Segoe UI",system-ui,-apple-system,sans-serif;color:var(--text);}
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
#MainMenu,footer{display:none !important;}
.block-container{padding:10px 16px 0 16px !important;max-width:1700px !important;margin:0 auto !important;}
[data-testid="stVerticalBlock"]{gap:.45rem !important;}
[data-testid="stHorizontalBlock"]{gap:.7rem !important;}
@media (max-width:900px){html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]
  {height:auto;overflow:auto !important;}}

/* ---------- aurora background (transform-only animation = cheap on the GPU) ---------- */
.stApp::before,.stApp::after{content:"";position:fixed;z-index:0;pointer-events:none;will-change:transform;}
.stApp::before{inset:-30%;background:
  radial-gradient(32% 28% at 20% 30%,rgba(124,92,240,.58),transparent 70%),
  radial-gradient(28% 24% at 78% 22%,rgba(34,211,238,.40),transparent 70%),
  radial-gradient(32% 28% at 60% 80%,rgba(52,211,153,.36),transparent 70%);
  animation:aur1 16s ease-in-out infinite alternate;}
.stApp::after{inset:-35%;background:linear-gradient(115deg,transparent 26%,rgba(52,211,153,.24) 38%,
  rgba(124,92,240,.30) 50%,rgba(34,211,238,.22) 62%,transparent 74%);filter:blur(30px);
  animation:aur2 22s ease-in-out infinite alternate;}
@keyframes aur1{0%{transform:translate3d(-9%,-6%,0) rotate(-6deg) scale(1)}
  50%{transform:translate3d(10%,6%,0) rotate(5deg) scale(1.16)}100%{transform:translate3d(-4%,11%,0) rotate(-3deg) scale(1.05)}}
@keyframes aur2{from{transform:translate3d(-15%,2%,0) skewX(-12deg) scale(1)}
  to{transform:translate3d(15%,-5%,0) skewX(12deg) scale(1.1)}}

/* ---------- top app bar ---------- */
.brand{display:flex;align-items:center;gap:.8rem;}
.logo{width:2.5rem;height:2.5rem;border-radius:.7rem;background:linear-gradient(135deg,#7c5cf0,#3ec6a8);
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:.9rem;
  box-shadow:0 6px 18px rgba(124,92,240,.35);}
.bt{font-size:1.1rem;font-weight:650;line-height:1.15;}
.bs{font-size:.76rem;color:var(--muted);line-height:1.3;margin-top:2px;}
.chip{display:inline-block;background:rgba(24,28,38,.9);border:1px solid var(--line);border-radius:.45rem;
  padding:1px .55rem;margin-right:.3rem;font-size:.72rem;color:#c5cadb;}

/* ---------- panels: equal height, fill the window ---------- */
.st-key-p_left,.st-key-p_center,.st-key-p_right{background:var(--panel);border:1px solid var(--line);
  border-radius:.9rem;padding:.8rem .9rem;flex:0 0 auto !important;height:calc(100vh - 150px) !important;
  max-height:calc(100vh - 150px) !important;overflow-y:auto;box-shadow:0 10px 30px rgba(0,0,0,.28);}
.st-key-p_center{overflow:hidden;container-type:inline-size;}
[class*="st-key-p_"]::-webkit-scrollbar{width:6px;}
[class*="st-key-p_"]::-webkit-scrollbar-thumb{background:var(--line2);border-radius:6px;}
.ptitle{font-size:.95rem;font-weight:650;margin:0 0 .15rem 0;}
.hint{font-size:.72rem;color:var(--muted);line-height:1.4;}

/* ---------- widgets (compact) ---------- */
[data-testid="stWidgetLabel"]{min-height:0 !important;margin-bottom:1px !important;}
[data-testid="stWidgetLabel"] p,label p{font-size:.72rem !important;color:var(--muted) !important;font-weight:500 !important;}
div[data-baseweb="select"]>div{min-height:2rem !important;background:var(--field) !important;
  border-color:var(--line) !important;font-size:.8rem !important;border-radius:.55rem !important;}
.stTextInput input,.stNumberInput input{min-height:2rem !important;font-size:.8rem !important;
  background:var(--field) !important;border-radius:.55rem !important;}
[data-testid="stSlider"]{padding-top:0 !important;}
[data-testid="stSliderTickBarMin"],[data-testid="stSliderTickBarMax"]{display:none !important;}
[data-testid="stSliderThumbValue"]{font-size:.7rem !important;}
.stCheckbox{padding:.35rem 0 0 0;}
.stCheckbox p{font-size:.8rem !important;color:var(--text) !important;}
[data-testid="stExpander"]{border:1px solid var(--line) !important;border-radius:.6rem !important;background:rgba(24,28,38,.7);}
[data-testid="stExpander"] summary{font-size:.8rem !important;padding:.35rem .6rem !important;}
code{font-size:.72rem !important;}

.stButton,.stDownloadButton,[data-testid="stPopover"]{width:100%;}
.stButton>button,.stDownloadButton>button,[data-testid="stPopover"] button{width:100%;min-height:2.2rem;
  padding:.15rem .6rem;border-radius:.6rem;font-size:.8rem;font-weight:600;border:1px solid var(--line2);
  background:rgba(24,28,38,.9);color:var(--text);transition:border-color .15s,background .15s;}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stPopover"] button:hover{
  border-color:var(--accent);color:#fff;background:#1e2331;}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{
  background:linear-gradient(135deg,#7c5cf0,#5b6cf0);border-color:transparent;color:#fff;
  box-shadow:0 6px 18px rgba(124,92,240,.35);}
.stButton>button[kind="primary"]:hover,.stButton>button[data-testid="stBaseButton-primary"]:hover{filter:brightness(1.12);}
.stButton>button:disabled,.stDownloadButton>button:disabled{opacity:.38;}

[data-testid="stSegmentedControl"]{width:100%;}
.st-key-p_left [data-testid="stSegmentedControl"] [role="group"],
.st-key-p_left [data-testid="stSegmentedControl"]>div{flex-wrap:nowrap !important;}
.st-key-p_left [data-testid="stSegmentedControl"] button{flex:1 1 auto;padding:.15rem .3rem !important;}
.empty{border:1px dashed var(--line2);border-radius:.8rem;padding:1.4rem 1rem;text-align:center;margin-top:.5rem;}
.empty b{display:block;font-size:.88rem;margin-bottom:.2rem;}
.empty span{font-size:.76rem;color:var(--muted);}
[data-testid="stSegmentedControl"] button{font-size:.76rem !important;padding:.15rem .6rem !important;min-height:1.9rem !important;}
[data-baseweb="tab-list"]{gap:.25rem;}
[data-baseweb="tab"]{height:2.1rem;font-size:.8rem;}

/* ---------- fixed action bar ---------- */
.st-key-actionbar{position:fixed;left:0;right:0;bottom:0;z-index:60;background:rgba(9,11,16,.92);
  border-top:1px solid var(--line);padding:.55rem 16px .6rem 16px;}
@media (min-width:900px){.st-key-actionbar{padding-right:190px;}}   /* room for the host's "Manage app" badge */
.st-key-actionbar [data-testid="stHorizontalBlock"]{max-width:1700px;margin:0 auto;}
.stat{font-size:.78rem;color:var(--muted);}
.stat.ok{color:var(--ok);} .stat.bad{color:var(--bad);}
.st-key-actionbar [data-testid="stProgress"] p{font-size:.74rem;}

/* ---------- empty state ---------- */
.hero{margin:5vh auto 1rem auto;max-width:720px;text-align:center;}
.hero h1{font-size:1.9rem;font-weight:680;margin:0 0 .35rem 0;letter-spacing:-.01em;}
.hero p{color:var(--muted);font-size:.95rem;margin:0;}
.st-key-herobox{max-width:640px;margin:0 auto;}
.st-key-herobox [data-testid="stFileUploaderDropzone"]{padding:1.6rem 1rem !important;
  background:rgba(14,17,23,.75);border:1.5px dashed var(--line2);border-radius:1rem;}
.st-key-herobox [data-testid="stFileUploaderDropzone"]:hover{border-color:var(--accent);}
.steps{display:flex;gap:.8rem;justify-content:center;flex-wrap:wrap;max-width:760px;margin:1.2rem auto 0 auto;}
.step{flex:1 1 190px;max-width:240px;background:var(--panel);border:1px solid var(--line);border-radius:.8rem;
  padding:.8rem 1rem;text-align:left;}
.step b{display:block;font-size:.88rem;margin-bottom:.15rem;}
.step span{font-size:.78rem;color:var(--muted);}
.guide h4{color:#c9b8ff;margin:.5rem 0 .2rem 0;font-size:.88rem;}
.guide li,.guide p{color:#c3c7db;font-size:.8rem;margin-bottom:2px;}

/* ---------- phone preview (scales with window height) ---------- */
.phone{--ph:clamp(240px,min(calc(100vh - 234px),calc((100cqw - 1.8rem) / .573)),780px);position:relative;height:var(--ph);
  width:calc(var(--ph)*.573);margin:.5rem auto 0 auto;border-radius:calc(var(--ph)*.075);
  background:#1b1e29;border:1px solid #38405a;box-shadow:0 18px 50px rgba(0,0,0,.6),0 0 0 1px rgba(124,92,240,.12);}
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
                max_clips=0, workers=0, preview_mode="frame", privacy="private", aurora=True)

SETTINGS_FILE = os.path.join(WORK, "settings.json")
FONT_FILES = {"Poppins": "Poppins-Bold.ttf", "Anton": "Anton-Regular.ttf", "Montserrat": "Montserrat.ttf",
              "Bebas Neue": "BebasNeue-Regular.ttf", "Noto Sans Devanagari": "NotoSansDevanagari.ttf"}

GUIDE = """
<div class="guide">
<h4>How to use</h4>
<ol>
<li><b>Upload</b> one or more videos on the start screen.</li>
<li><b>Tune</b> it — pick a section in the left menu (Frame, Captions, Motion, Colors, Audio, Clips).</li>
<li><b>Preview</b> in the phone. It shows a real frame of your video with your settings.
Use <i>Sample</i> + <i>Render</i> for a real 5-second clip.</li>
<li><b>Generate</b> (bottom bar) — transcribes and renders. Then <b>Download</b> or publish.</li>
</ol>
<h4>Good defaults</h4>
<ul>
<li><b>Mode</b>: <code>reels</code> = auto clips in 9:16 · <code>full_video</code> = whole video + captions.</li>
<li><b>Language</b>: set <code>hi</code> for Hindi / Hinglish (auto often mis-detects).</li>
<li><b>Whisper model</b>: <code>small</code>. <b>Transcription</b>: <code>fast</code> (use <code>accurate</code> only if needed).</li>
<li><b>Frame mode</b>: <code>fit_blur</code> for screen recordings.</li>
</ul>
<p>Settings save automatically. <b>New video</b> (top right) removes the current upload and results so you can start again.</p>
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


# ============================================================== google login ====
G_YT = "https://www.googleapis.com/auth/youtube.upload"
G_DR = "https://www.googleapis.com/auth/drive.file"
G_SCOPES = [G_YT, G_DR]                       # ONE login covers YouTube + Drive
G_TOKEN = os.path.join(WORK, "google_token.json")
G_LEGACY = [os.path.join(WORK, "yt_token.json"), os.path.join(WORK, "drive_token.json")]
CS_PATH = os.path.join(WORK, "client_secret.json")


def _secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def client_secret_path():
    """Saved file -> or Streamlit secret GOOGLE_CLIENT_SECRET -> or None. Never asks twice."""
    if os.path.exists(CS_PATH):
        return CS_PATH
    v = _secret("GOOGLE_CLIENT_SECRET")
    if v:
        try:
            with open(CS_PATH, "w") as f:
                f.write(v if isinstance(v, str) else json.dumps(v.to_dict()))
            return CS_PATH
        except Exception:
            return None
    return None


def load_google_creds():
    """Saved token file -> or secret GOOGLE_TOKEN -> or old yt/drive token. Refreshes silently."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        return None
    sources = []
    if os.path.exists(G_TOKEN):
        sources.append(("file", G_TOKEN))
    if _secret("GOOGLE_TOKEN"):
        sources.append(("secret", None))
    sources += [("file", p) for p in G_LEGACY if os.path.exists(p)]
    for kind, path in sources:
        try:
            if kind == "file":
                c = Credentials.from_authorized_user_file(path)
            else:
                v = _secret("GOOGLE_TOKEN")
                c = Credentials.from_authorized_user_info(json.loads(v) if isinstance(v, str) else v.to_dict())
            if c.refresh_token and not c.valid:
                c.refresh(Request())
            if c.valid:
                if path != G_TOKEN:
                    with open(G_TOKEN, "w") as f:
                        f.write(c.to_json())
                return c
        except Exception:
            continue
    return None


def google_creds():
    if st.session_state.get("g_creds") is None:
        st.session_state["g_creds"] = load_google_creds()
    return st.session_state["g_creds"]


def extract_code(text):
    text = text.strip()
    m = re.search(r"[?&]?code=([^&\s]+)", text)
    return unquote(m.group(1)) if m else text


def _make_flow():
    from google_auth_oauthlib.flow import Flow
    try:
        return Flow.from_client_secrets_file(client_secret_path(), scopes=G_SCOPES,
                                             redirect_uri="http://localhost:8080/",
                                             autogenerate_code_verifier=False)
    except TypeError:
        return Flow.from_client_secrets_file(client_secret_path(), scopes=G_SCOPES,
                                             redirect_uri="http://localhost:8080/")


def google_disconnect():
    for p in [G_TOKEN] + G_LEGACY:
        try:
            os.remove(p)
        except OSError:
            pass
    st.session_state["g_creds"] = None
    st.session_state.pop("g_url", None)


def publish_panel():
    creds = google_creds()
    if creds:
        yt_ok, dr_ok = creds.has_scopes([G_YT]), creds.has_scopes([G_DR])
        st.markdown("<span class='stat ok'>Google connected</span> &nbsp;<span class='chip'>YouTube %s</span>"
                    "<span class='chip'>Drive %s</span>" % ("✓" if yt_ok else "–", "✓" if dr_ok else "–"),
                    unsafe_allow_html=True)
        _seed("privacy")
        S["privacy"] = st.selectbox("YouTube privacy", ALLOWED["privacy"], key="w_privacy")
        st.markdown("<span class='hint'>You stay signed in — no secret or code needed again.</span>",
                    unsafe_allow_html=True)
        if not (yt_ok and dr_ok):
            st.markdown("<span class='hint'>Some access is missing. Disconnect and connect again to grant both.</span>",
                        unsafe_allow_html=True)
        with st.expander("Stay signed in after app restarts"):
            st.markdown("<span class='hint'>Hosted apps wipe local files on reboot. To never sign in again, open "
                        "<b>App → Settings → Secrets</b> and paste the two lines below.</span>",
                        unsafe_allow_html=True)
            cs = client_secret_path()
            secret_text = ("GOOGLE_TOKEN = '''" + creds.to_json() + "'''\n"
                           "GOOGLE_CLIENT_SECRET = '''" + (open(cs).read().strip() if cs else "<paste client_secret.json>")
                           + "'''")
            st.code(secret_text, language="toml")
        st.button("Disconnect Google", on_click=google_disconnect)
        return

    cs = client_secret_path()
    if not cs:
        up = st.file_uploader("client_secret.json (one time only)", type=["json"], key="cs")
        if up is not None:
            with open(CS_PATH, "wb") as f:
                f.write(up.getbuffer())
            st.rerun(scope="fragment")
        st.markdown("<span class='hint'>Google Cloud → APIs → Credentials → OAuth client. Add "
                    "<code>http://localhost:8080/</code> as redirect URI. Enable YouTube Data API + Drive API.</span>",
                    unsafe_allow_html=True)
        return
    st.markdown("<span class='hint'>client_secret.json is saved. Sign in once:</span>", unsafe_allow_html=True)
    if st.button("Get Google sign-in link"):
        flow = _make_flow()
        st.session_state["g_url"], _ = flow.authorization_url(prompt="consent", access_type="offline")
    if st.session_state.get("g_url"):
        st.markdown(f"**1.** [Open Google & approve]({st.session_state['g_url']})  \n"
                    "<span class='hint'>**2.** The page may say 'can't connect' — that's fine. Copy the whole "
                    "address from the browser bar and paste below.</span>", unsafe_allow_html=True)
        code = st.text_input("Code or full URL", key="g_code", placeholder="http://localhost:8080/?code=…")
        if st.button("Connect", key="g_connect") and code.strip():
            try:
                flow = _make_flow()
                flow.fetch_token(code=extract_code(code))
                with open(G_TOKEN, "w") as f:
                    f.write(flow.credentials.to_json())
                st.session_state["g_creds"] = flow.credentials
                st.session_state.pop("g_url", None)
            except Exception as e:
                st.error(f"Connect failed: {str(e)[:160]}. Press 'Get sign-in link' again.")
                return
            st.rerun(scope="fragment")


# =================================================================== panels ====
def tab_general():
    c1, c2 = st.columns(2)
    sel("mode", "Mode", c1)
    sel("language", "Language", c2)
    sel("model_size", "Whisper model", c1)
    sel("accuracy", "Transcription", c2, help="fast = greedy decoding (2-3x faster). accurate = beam 5.")
    sel("FONT", "Caption font")
    chk("aurora", "Animated aurora background")
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
    st.markdown("<div class='hint' style='margin-top:.4rem'>Border</div>", unsafe_allow_html=True)
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
    num("workers", "Parallel jobs (0 = auto)", 0, 8, c2)
    cpu = os.cpu_count() or 2
    st.markdown(f"<span class='hint'>Clips render in parallel, and the next video is transcribed while earlier "
                f"ones render. Auto uses {max(1, min(4, cpu))} job(s) on this server "
                f"({cpu} CPU core{'s' if cpu != 1 else ''}).</span>", unsafe_allow_html=True)


TAB_FN = {"General": tab_general, "Frame": tab_frame, "Captions": tab_captions, "Motion": tab_motion,
          "Colors": tab_colors, "Audio": tab_audio, "Clips": tab_clips}


def panel_preview(primary, dur_total):
    Sx = build_settings()
    _seed("preview_mode")
    top = st.columns([1.25, 1], vertical_alignment="center")
    with top[0]:
        pm = st.segmented_control("Preview", ALLOWED["preview_mode"], key="w_preview_mode",
                                  format_func=lambda x: "Frame" if x == "frame" else "Sample",
                                  label_visibility="collapsed")
    S["preview_mode"] = pm or S["preview_mode"]

    slot = st.empty()
    t = min(8.0, max(0.0, dur_total / 2))
    try:
        frame = frame_uri(primary, t)
    except Exception as e:
        st.warning(f"Could not read a frame: {str(e)[:120]}")
        return
    hindi = S["language"] in ("hi", "mr", "ne")
    fallback = ["आज", "हम", "बात", "करेंगे"] if hindi else ["Here", "is", "how", "it", "works"]

    if S["preview_mode"] == "video":
        sig = json.dumps({**{k: v for k, v in Sx.items() if k not in ("preview_mode", "privacy")},
                          "mode": "reels"}, sort_keys=True)
        with top[1]:
            go = st.button("Render", key="btn_pv")
        if go:
            st.session_state.pop("pv_err", None)
            with st.spinner("Rendering 5 s sample…"):
                try:
                    st.session_state["pv"] = (sig, preview_video_b64(primary, 0.0, 5.0, sig))
                except Exception as e:
                    st.session_state["pv_err"] = str(e)[:240]
        pv = st.session_state.get("pv")
        slot.markdown(phone_html(Sx, video=pv[1]) if pv else phone_html(Sx, frame, fallback),
                      unsafe_allow_html=True)
        if st.session_state.get("pv_err"):
            st.markdown("<span class='stat bad'>Sample failed: %s</span>" % st.session_state["pv_err"],
                        unsafe_allow_html=True)
        elif pv and pv[0] != sig:
            st.markdown("<span class='hint'>Settings changed — press Render to refresh.</span>", unsafe_allow_html=True)
        elif not pv:
            st.markdown("<span class='hint'>Press Render for a real 5-second clip.</span>", unsafe_allow_html=True)
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
            st.markdown("<div class='empty'><b>Nothing generated yet</b><span>Titles, descriptions and hashtags "
                        "for every reel appear here after you press Generate.</span></div>", unsafe_allow_html=True)
    with t2:
        publish_panel()


@st.fragment
def studio():
    """Options (tabs) · phone · details. Reruns on its own — fast."""
    primary = st.session_state["primary"]
    dur_total = media_info(primary)["dur"]
    left, center, right = st.columns([1.25, 0.95, 1.0], gap="small")
    with left:
        with st.container(key="p_left"):
            st.session_state.setdefault("w_tab", "General")
            try:
                st.segmented_control("Section", TABS, key="w_tab", label_visibility="collapsed")
            except AttributeError:                      # very old Streamlit
                st.radio("Section", TABS, key="w_tab", horizontal=True, label_visibility="collapsed")
            tab = st.session_state.get("w_tab") or st.session_state.get("_tab") or "General"
            st.session_state["_tab"] = tab
            TAB_FN[tab]()
            if not S["aurora"]:
                st.markdown("<style>.stApp::before,.stApp::after{animation:none !important}</style>",
                            unsafe_allow_html=True)
    with center:
        with st.container(key="p_center"):
            panel_preview(primary, dur_total)
    with right:
        with st.container(key="p_right"):
            panel_right()
    persist()


# ============================================================ generate/publish ====
def run_generate(paths, slot):
    """Pipeline: video N+1 is transcribed WHILE the clips of video N render, and clips render in parallel."""
    Sfull = build_settings()
    cpu = os.cpu_count() or 2
    workers = int(Sfull["workers"]) or max(1, min(4, cpu))
    threads = max(1, cpu // workers)                    # don't let N ffmpegs fight over the same cores
    fonts = st.session_state["fonts"]
    lang, beam = _lang(S), _beam(S)

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "transcripts"), exist_ok=True)
    prog = slot.progress(0.0, text="Starting…")

    n = len(paths)
    pending, results, details, notes = {}, [], [], []
    total, done, best = 0, 0, 0.0
    store = st.session_state.setdefault("tr", {})

    def reap():
        nonlocal done
        for f in [f for f in pending if f.done()]:
            results.append(f.result())                  # re-raises render errors
            pending.pop(f)
            done += 1

    def show(tf, what):
        nonlocal best
        rp = (done / total) if total else tf
        best = max(best, min(1.0, 0.55 * tf + 0.45 * rp))
        prog.progress(best, text=f"{what} · rendered {done}/{total}" if total else what)

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        for i, vp in enumerate(paths):
            stem = clean_stem(vp)
            key = f"{vp}|{S['model_size']}|{lang}|{beam}"
            if key not in store:
                def cb(frac, _s=stem, _i=i):
                    reap()
                    show((_i + frac) / n, f"Transcribing {_s} {int(frac * 100)}%")
                audio = engine.extract_audio(vp, out=os.path.join(WORK, f"full_{i}.f32"))
                store[key], _ = engine.transcribe(audio, S["model_size"], lang, progress=cb, beam_size=beam)
            segs = store[key]
            with open(os.path.join(OUT, "transcripts", f"{stem}.txt"), "w", encoding="utf-8") as f:
                for s_ in segs:
                    f.write(f"[{s_['start']:.1f} - {s_['end']:.1f}] {s_['text'].strip()}\n")
            show((i + 1) / n, f"Transcribed {i + 1}/{n}")

            if S["mode"] == "transcribe_only":
                continue
            vdur = media_info(vp)["dur"] or max((x["end"] for x in segs), default=0)
            jobs = []
            if S["mode"] == "full_video":
                os.makedirs(os.path.join(OUT, "captioned"), exist_ok=True)
                out = os.path.join(OUT, "captioned", f"{stem}_captioned.mp4")
                jobs.append((0.0, vdur, out, f"{stem}_captioned.mp4"))
            else:
                clips = engine.find_clips(segs, Sfull["min_dur"], Sfull["max_dur"], max_clips=Sfull["max_clips"]) \
                    if segs else []
                if not clips:
                    clips = engine.even_clips(vdur, Sfull["min_dur"], Sfull["max_dur"])
                    if Sfull["max_clips"]:
                        clips = clips[:Sfull["max_clips"]]
                    if not segs:
                        notes.append("no speech found, clips cut evenly without captions")
                os.makedirs(os.path.join(OUT, "reels", stem), exist_ok=True)
                for k, (s0, e0) in enumerate(clips):
                    jobs.append((s0, e0, os.path.join(OUT, "reels", stem, f"reel_{k + 1:02d}.mp4"),
                                 f"{stem}/reel_{k + 1:02d}.mp4"))
            for (s0, e0, out, label) in jobs:
                txt = engine.clip_text(segs, s0, e0)
                details.append({"file": label, "path": out, "title": txt[:90] or stem, "desc": txt,
                                "tags": engine.hashtags(txt)})
                pending[ex.submit(engine.render_segment, vp, segs, s0, e0, out, Sfull, fonts, "veryfast",
                                  threads)] = out
                total += 1
            reap()

        while pending:
            concurrent.futures.wait(list(pending), timeout=0.6, return_when=concurrent.futures.FIRST_COMPLETED)
            reap()
            show(1.0, "Rendering")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    results.sort()
    with open(os.path.join(OUT, "post_details.txt"), "w", encoding="utf-8") as f:
        f.write("POST DETAILS\n" + "=" * 40 + "\n\n")
        for x in details:
            f.write(f"FILE: {x['file']}\nTITLE: {x['title']}\nDESCRIPTION:\n{x['desc']}\n"
                    f"HASHTAGS: {x['tags']} #shorts #reels\n" + "-" * 40 + "\n")
    with zipfile.ZipFile(os.path.join(WORK, "output.zip"), "w") as z:     # videos already compressed -> store
        for root, _, files in os.walk(OUT):
            for fn in files:
                if not fn.endswith(".ass"):
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, OUT))
    st.session_state["results"], st.session_state["details"] = results, details
    extra = f" ({'; '.join(sorted(set(notes)))})" if notes else ""
    st.session_state["last_msg"] = ("ok", f"Done — {len(results)} file(s) ready{extra}. Download or publish.")


def run_drive():
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = google_creds()
    if not creds.has_scopes([G_DR]):
        raise RuntimeError("Drive access not granted — Disconnect Google and connect again.")
    svc = build("drive", "v3", credentials=creds)
    media = MediaFileUpload(os.path.join(WORK, "output.zip"), resumable=True)
    f = svc.files().create(body={"name": "auto_reels_output.zip"}, media_body=media,
                           fields="id,webViewLink").execute()
    st.session_state["last_msg"] = ("ok", "Saved to Drive: " + f.get("webViewLink", ""))


def run_youtube(slot):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = google_creds()
    if not creds.has_scopes([G_YT]):
        raise RuntimeError("YouTube access not granted — Disconnect Google and connect again.")
    yt = build("youtube", "v3", credentials=creds)
    meta = {x["path"]: x for x in st.session_state.get("details", [])}
    files = [p for p in st.session_state["results"] if os.path.exists(p)]
    links = []
    for n_, p in enumerate(files, 1):
        slot.progress(n_ / len(files), text=f"Uploading {n_}/{len(files)} to YouTube…")
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
        c1, c2, c3, c4, c5 = st.columns([1.1, 1, 1, 1.2, 3], vertical_alignment="center")
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
            if drive or yt:
                if not google_creds():
                    st.session_state["last_msg"] = ("bad", "Connect Google first: right panel → Publish.")
                elif drive:
                    slot.markdown("<span class='stat'>Uploading to Drive…</span>", unsafe_allow_html=True)
                    run_drive()
                else:
                    run_youtube(slot)
                st.rerun()
        except Exception as e:
            if type(e).__name__ in ("RerunException", "StopException"):
                raise
            st.session_state["last_msg"] = ("bad", f"Failed: {str(e)[:200]}")
            st.rerun()


# ===================================================================== main ====
def new_video():
    st.session_state["ukey"] = st.session_state.get("ukey", 0) + 1
    for k in ("paths", "primary", "results", "details", "pv", "pv_err", "last_msg", "tr"):
        st.session_state.pop(k, None)


def main():
    fonts = init_engine()
    st.session_state["fonts"] = fonts
    st.markdown(f"<style>{CSS}{font_css(fonts)}</style>", unsafe_allow_html=True)
    brand = ('<div class="brand"><div class="logo">AR</div><div><div class="bt">Auto Reels Studio</div>'
             '<div class="bs">%s</div></div></div>')
    paths = st.session_state.get("paths")

    # ---------- start screen: big uploader (files are copied to disk, so the widget can go away) ----------
    if not paths:
        st.markdown(brand % "Upload, tune, preview, generate.", unsafe_allow_html=True)
        st.markdown('<div class="hero"><h1>Turn long videos into captioned reels</h1>'
                    '<p>Drop one or more videos below to begin.</p></div>', unsafe_allow_html=True)
        with st.container(key="herobox"):
            uploads = st.file_uploader("Upload video(s)", type=["mp4", "mov", "mkv", "webm", "avi"],
                                       accept_multiple_files=True, label_visibility="collapsed",
                                       key=f"up_{st.session_state.get('ukey', 0)}")
        st.markdown('<div class="steps">'
                    '<div class="step"><b>1 · Upload</b><span>MP4, MOV, MKV, WebM or AVI up to 2 GB each.</span></div>'
                    '<div class="step"><b>2 · Tune</b><span>Frame, captions, colours, audio and clip length.</span></div>'
                    '<div class="step"><b>3 · Generate</b><span>Auto-cut clips with word-by-word captions.</span></div>'
                    '</div>', unsafe_allow_html=True)
        if uploads:
            with st.spinner("Saving…"):
                st.session_state["paths"] = [save_upload(u) for u in uploads]
                st.session_state["primary"] = st.session_state["paths"][0]
            st.rerun()
        return

    # ---------- app bar ----------
    mi = media_info(paths[0])
    chips = (f'<span class="chip">{clean_stem(paths[0])[:32]}</span><span class="chip">{human(mi["size"])}</span>'
             f'<span class="chip">{mi["dur"] / 60:.1f} min</span>')
    if len(paths) > 1:
        chips += f'<span class="chip">+{len(paths) - 1} more</span>'
    h1, h2, h3 = st.columns([9, 0.8, 1.1], vertical_alignment="center")
    h1.markdown(brand % chips, unsafe_allow_html=True)
    with h2.popover("Help"):
        st.markdown(GUIDE, unsafe_allow_html=True)
    h3.button("New video", on_click=new_video, help="Remove the current upload and results, then pick another video.")

    studio()
    action_bar()


try:
    main()
except Exception as _e:
    if type(_e).__name__ in ("StopException", "RerunException"):
        raise
    st.error("App error — please send this message:")
    st.exception(_e)
