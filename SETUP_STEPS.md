# Auto Reel Maker — web app (v6)

## Status
- Python 3.12 fix worked — the build now succeeds.
- The app **no longer shows "Oh no"**. If anything goes wrong, it prints the real error
  **on the page**. If it breaks, screenshot that message and send it — I can fix it exactly.

## Files to upload (all)
- `app.py`   (updated)
- `engine.py` (updated)
- `requirements.txt`
- `.streamlit/config.toml`

Re-upload them to the same GitHub repo (Add file -> Upload files -> overwrite -> Commit).
Streamlit auto-redeploys in ~1-2 min.

## What's fixed / added
- **Error surfacing**: real error shown on screen instead of a blank crash.
- **Settings auto-save + validation**: your choices are saved and reloaded next time, and
  an old/invalid saved value can no longer break a widget.
- **Safety**: duration/upload reading can't crash the app.
- Ribbon tabs, compact phone preview, many more options (box opacity, UPPERCASE, words per
  line, caption position, outline width, highlight mode, blur strength, progress colour,
  original volume, fade, max clips, overlay size), parallel jobs.

## About the 2-video upload
Uploading 2 videos at once is supported (I tested it). But this host has ~2.7 GB RAM, so
for big files it's safer to do one at a time. If it crashes with two, try one.

## Reminders
- Keep **Whisper model = `small`** (CPU host).
- Upload limit is raised by `.streamlit/config.toml`.
- App sleeps after ~12h idle; the link wakes it in ~30–60s.
