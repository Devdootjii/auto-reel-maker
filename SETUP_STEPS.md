# Free Auto Reels Generator — web app (v11)

## The big fix: settings no longer reset
Root cause found. Streamlit **deletes the state of any widget that isn't rendered on the current
run**. Because each ribbon tab only renders its own widgets, switching tabs wiped the earlier
choices — that's why "jo pehle kiya wo default ho jata hai".

Fix: all settings now live in **one plain dict** (`st.session_state["S"]`) that is *not* tied to
widget keys. Widgets read their value from that dict and write back into it. Switching tabs can
no longer reset anything.

## Other changes in v11
- **iPhone-style phone preview** — rounded bezel + dynamic island. Shows a **real frame of your
  video** with your settings drawn on top, and uses the **real caption words** (from a short
  window of your video) so the preview matches the output.
- **Preview mode toggle** (right column): **Frame** (instant, default) or **Video** (renders a
  short 6-second sample with sound). Switch any time.
- **Border is OFF by default** now (add it if you want it).
- **Description / hashtags moved to the right column** (no longer under the preview).
- **Tighter layout** — wasted gaps removed, uploaded video shown as a small badge, smaller widgets.

## Update
Only **`app.py`** changed. Re-upload it to the same repo (overwrite → Commit). Auto-redeploys.

## Notes
- First preview does a 6-second transcription to get real caption words (once, then cached).
- Keep **Whisper model = `small`**; for Hindi/Hinglish set **Language = `hi`**.
- Settings auto-save; Reset is on the Home tab.
