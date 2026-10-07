# Auto Reels Studio — web app (v15)

## What's new in v15
- **Render sample fixed** — it crashed on videos with no audio track (screen recordings). Silent videos now work
  everywhere (sample, Generate). If a video has no speech, reels are cut evenly without captions.
- **Compact UI** — whole interface scales with the screen (smaller options), left **menu rail** instead of tabs,
  panels fill the window like a desktop app. Phone preview scales to fit.
- **Aurora background** — slow animated northern-lights glow (GPU-friendly, respects "reduce motion").
- **Upload** — big drop-zone on the start screen; after upload the file is shown in the top bar
  (no more hidden corner). **New video** (top right) removes the upload + results so you can start over.
- **Parallel processing** — clips render in parallel, and the next video is transcribed while earlier ones render.
  Clips tab → "Parallel jobs" (0 = auto).
- **Sign in to Google once** — one login covers YouTube + Drive. The token is saved and refreshed silently;
  client_secret.json is only asked once.

## Deploy
1. GitHub: upload `app.py`, `engine.py`, `requirements.txt`; put `config.toml` at `.streamlit/config.toml`.
   (`app.py` and `engine.py` must be updated together.)
2. Streamlit Cloud → **Reboot**, then Ctrl+Shift+R.

## Stay signed in to Google even after the app restarts
Streamlit Cloud deletes local files on every reboot/redeploy. To never sign in again:
1. Connect Google once (right panel → Publish).
2. Open "Stay signed in after app restarts" and copy the two lines shown.
3. Streamlit → App → Settings → **Secrets** → paste → Save.

Also in Google Cloud → OAuth consent screen: set Publishing status to **In production**.
In "Testing" mode Google expires the login every 7 days, whatever the app does.

## Reminders
- Whisper model `small`; for Hindi/Hinglish set Language = `hi`.
- Settings auto-save; Reset is in General.
