# Free Auto Reels Generator — web app (v12)

## Fixed
- **`Generate fail: name 'full_transcript' is not defined`** — I had accidentally dropped a
  helper function when rewriting. Restored. Generate works now.
  (I also ran a full static check: every function the app calls is defined.)
- **Video preview is now phone-shaped** — when you pick **Video** preview mode, the sample
  renders inside a phone-style frame (rounded, bezel), matching the Frame preview.

## Good news
The **build now succeeds on Python 3.14** — the `tokenizers>=0.22` pin in `requirements.txt`
did its job. You no longer need to juggle Python versions.

## Update
Only **`app.py`** changed. Re-upload it to the same repo (overwrite -> Commit).

## Reminders
- Keep **Whisper model = `small`**; for Hindi/Hinglish set **Language = `hi`**.
- Preview mode: **Frame** (instant, default) or **Video** (6-second real sample).
- Settings auto-save; Reset is on the Home tab.
