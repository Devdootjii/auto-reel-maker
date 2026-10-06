# Free Auto Reels Generator — web app (v13)

## Fixed
- **Video preview now plays INSIDE the iPhone frame.** Earlier it appeared as a separate
  rectangular player. Now the sample is embedded in the phone screen, so both preview modes
  (Frame and Video) look the same phone.
- (previous fix) `full_transcript` helper restored — Generate works.
- The build now succeeds on Python 3.14 (`tokenizers>=0.22` pin) — no Python juggling.

## IMPORTANT — make sure you are running the new file
Your last screenshot showed the plain "Oh no" crash page. That is the OLD app. The new app
shows a friendly message with the real error instead. So please:
1. GitHub -> re-upload **`app.py`** (overwrite -> Commit).
2. Streamlit -> your app -> **Reboot** (or wait for auto-redeploy).
3. Hard-refresh the browser (Ctrl+Shift+R).

If it still shows "Oh no", the deployed file is not the new one — check the repo's `app.py`
timestamp / commit.

## Reminders
- Keep **Whisper model = `small`**; for Hindi/Hinglish set **Language = `hi`**.
- Right column has the **Preview** switch: Frame (instant) or Video (5s real sample).
- Settings auto-save; Reset is on the Home tab.
