"""
engine.py — the rendering/transcription core for the Auto Reel Maker app.

Pure functions, no UI. Kept separate from app.py so it can be tested on its own.
"""
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
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", video_path]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", out]
    subprocess.run(cmd, check=True)
    return np.fromfile(out, dtype=np.float32)


def extract_frame(video_path, t, out="frame.jpg", width=None):
    """Grab a single frame as an image (for the instant preview)."""
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(t), "-i", video_path,
           "-frames:v", "1"]
    if width:
        cmd += ["-vf", f"scale={width}:-2"]
    cmd += ["-q:v", "4", out]
    subprocess.run(cmd, check=True)
    return out


# -------------------------------------------------------- transcription ----
_MODELS = {}
_MODEL_LOCK = threading.Lock()


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
def render_segment(video_path, segments, s, e, out_path, S, font_dir, preset="veryfast"):
    """Render one output file covering [s, e] with the given settings."""
    dur = e - s
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
    cmd += [out_path]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        # last-resort fallback: no effects, original audio
        fb = [ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", str(s), "-i", video_path, "-t", str(dur)]
        if S["mode"] == "reels":
            fb += ["-vf", "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920"]
        fb += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        fb += (["-c:a", "aac"] if S["original_audio"] == "keep" else ["-an"])
        fb += [out_path]
        subprocess.run(fb, check=True)
    return out_path
