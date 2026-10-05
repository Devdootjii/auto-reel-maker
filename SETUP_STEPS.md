# Free Auto Reels Generator — web app (v9)

## 1) FIX THE CRASH FIRST — Python must be 3.12
Your last crash log still says **"Using Python 3.14.7"**. On 3.14 the package
`tokenizers` has no prebuilt wheel, so it tries to compile from source and fails (needs Rust).

Streamlit Cloud **cannot change the Python version after deploy**. So:

1. share.streamlit.io -> your app -> the **⋮ (three dots) menu** -> **Delete app**.
2. Click **Create app** again -> pick the same repo -> main file `app.py`.
3. **Before pressing Deploy**, open **Advanced settings** -> **Python version** -> choose **3.12**.
4. Click **Deploy**.
5. Wait ~5–10 min. It will build cleanly (no Rust needed).

Until this is done, the app will keep showing "Oh no".

## 2) UI fixes in v9
- **Panels are now real Streamlit containers** (`st.container(border=True)`). Previously I
  faked them with `<div>` tags, which Streamlit does not wrap around widgets — that is exactly
  why you saw **empty space** and **overlapping boxes** on the right. Fixed.
- **"Preview" heading removed** — the preview speaks for itself now.
- **Everything is tighter and smaller** — global spacing reduced, widget gaps cut, smaller
  inputs/sliders/buttons, so it fits one screen with no scrolling.
- Layout unchanged otherwise: header + tabs + left options + centre preview + right
  progress/other + bottom action bar.

## 3) Update
Re-upload **`app.py`** to the same repo (overwrite -> Commit). Auto-redeploys.

## Notes
- Keep **Whisper model = `small`**; for Hindi set **Language = `hi`** (auto often mis-detects).
- Settings auto-save; Reset is on the Home tab.
- If it breaks, the app prints the real error on screen — screenshot it and send it.
