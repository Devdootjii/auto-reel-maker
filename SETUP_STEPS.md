# Auto Reel Maker — web app (v5)

## FIX THE CRASH FIRST (important)
The "Oh no / Error running app" crash was: your app is running on **Python 3.14**, and
`tokenizers` / `av` have no wheels for it, so it tried to build from source and failed
(needs Rust).

**Streamlit Cloud cannot change the Python version after deploy** — you must delete and
redeploy:
1. In share.streamlit.io, open your app -> **Manage app** -> **Delete app**.
2. Click **Create app** again, pick the same repo, main file `app.py`.
3. Open **Advanced settings** -> **Python version** -> choose **3.12**.
4. **Deploy**. (You can reuse the same subdomain.)
It will then build cleanly — no Rust needed.

## Files (upload all)
- `app.py`
- `engine.py`
- `requirements.txt`
- `.streamlit/config.toml` (create it via GitHub: Add file -> Create new file ->
  filename `.streamlit/config.toml` -> paste the config content)

## What's new in v5
- **Ribbon tabs** at the top: Home · Captions · Animation · Framing · Overlay · Audio ·
  Clips · YouTube. Click a tab -> its options open on the left.
- **Compact phone-sized preview** (no more scrolling to see it), still instant.
- **Many more options**: box + box opacity, UPPERCASE, words-per-line, caption position,
  bottom margin, outline width, highlight mode (colour/box), blur strength, progress-bar
  colour, original volume, fade in/out, max clips, overlay size, and more.
- **Settings auto-save** — your choices are stored and reloaded, so you don't set them
  again on the next visit. "Reset settings" button on the Home tab if you want to start over.

## How to use
1. Upload video(s).
2. Pick a ribbon tab, set options (watch the live preview).
3. **Generate** -> download `output.zip`, or copy the title/description/hashtags from the
   copy boxes, or use the YouTube tab.

## Notes
- CPU-only host, ~2.7 GB RAM -> keep **Whisper model = `small`**.
- Upload limit raised by `.streamlit/config.toml` (`maxUploadSize = 2000`).
- App sleeps after ~12h idle; opening the link wakes it in ~30–60s.
