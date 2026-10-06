# Auto Reels Studio — web app (v14)

## What's new
**Speed**
- Moving a slider/option now re-runs only the settings + preview panel (Streamlit fragments), not the whole app.
- Whisper model is loaded once and reused (and pre-loaded in the background at start-up).
- Transcription defaults to **fast** (greedy decoding, ~2-3x quicker). Use **accurate** (General tab) only if needed.
- Blur background is computed on a tiny copy and scaled up (~25% faster render); slow-zoom no longer stretches the picture.
- Video preview renders only when you press **Render sample** (before, it re-rendered on every change).
- Removed the animated full-page background (it kept the GPU busy).

**UI**
- Everything fits on ONE screen — no browser scrolling. Fixed action bar at the bottom.
- Phone preview scales with the window height and reflects crop / zoom / blur / border / progress / animation.
- Options that don't apply (e.g. blur when frame mode is crop) are hidden.
- Progress bar in the output now really animates over the clip (the old filter was static).
- Output zip keeps clean names (`reels/<video>/reel_01.mp4`) and no longer mixes files from different runs.

## Deploy
1. GitHub -> upload **`app.py`, `engine.py`, `requirements.txt`** and put `config.toml`
   at `.streamlit/config.toml`. Commit.
2. Streamlit Cloud -> your app -> **Reboot**. Hard-refresh the browser (Ctrl+Shift+R).
   (`engine.py` MUST be updated together with `app.py` — they changed together.)

## Reminders
- Keep **Whisper model = small**; for Hindi/Hinglish set **Language = hi**.
- Settings auto-save; Reset is in the General section.
- First start downloads fonts + the Whisper model once; later starts are quick.
