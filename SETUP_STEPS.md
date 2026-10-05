# Free Auto Reels Generator — web app (v7)

New layout (your wireframe): header + tab bar + left options + centre phone preview +
right progress/other options + bottom action bar. Plus a **How to use** tab.

## Just update app.py
Only **`app.py`** changed. Re-upload it to the same GitHub repo
(Add file -> Upload files -> overwrite -> Commit). Streamlit redeploys in ~1-2 min.

(Your repo already has `engine.py`, `requirements.txt`, `.streamlit/config.toml` from before.)

## The interface
- **Top**: logo + title, and the video uploader on the right.
- **Tab bar**: Home · Frame · Captions · Animations · Colors · Audio · Clips · **How to use**.
  Click a tab -> its options open on the left.
- **Left**: options for the selected tab.
- **Centre**: phone-shaped **live preview** — one real frame of your video with your settings
  drawn on top. Updates instantly; no video processing.
- **Right**: **Progress** (live) and **Other options** (YouTube + Google Drive connect).
- **Bottom**: **Generate video · Download · Save to Drive · Upload to YouTube**.
- **How to use** tab: a step-by-step guide inside the app, so any user knows what to do.

## Notes
- CPU host, ~2.7 GB RAM -> keep **Whisper model = `small`**.
- Settings auto-save; **Reset settings** is on the Home tab.
- If anything breaks, the app now prints the real error on screen — screenshot it and send it.
