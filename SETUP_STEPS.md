# Auto Reel Maker — web app (v3)

One page. Instant preview. Parallel rendering. Copy-ready descriptions.

## Files to upload to GitHub
- `app.py`
- `engine.py`
- `requirements.txt`
- `config.toml`  → **must live at `.streamlit/config.toml`** (see step 3)

## First-time setup
1. github.com → **New repository** → name `auto-reel-maker` → **Public** → Create.
2. **Add file → Upload files** → upload `app.py`, `engine.py`, `requirements.txt` → Commit.
3. **Add file → Create new file** → in the filename box type exactly:
   `.streamlit/config.toml`
   → paste the contents of the `config.toml` I gave you → Commit.
   (This raises the upload limit above 200 MB and sets the theme.)
4. **share.streamlit.io** → sign in with GitHub → **Create app → Deploy a public app from GitHub**
   → repo `auto-reel-maker`, main file `app.py` → **Deploy**. First build ~5–10 min.

## Updating (this is you)
Re-upload the changed files to the same repo (Add file → Upload files → overwrite → Commit).
Streamlit **auto-redeploys** in ~1–2 min. Refresh the page.

## How it works now
- **Left column** = all settings. **Right column** = live preview.
- **Preview is instant** — it does NOT render a video. It draws one real frame of your video and
  overlays the caption / overlay text / border / progress bar with CSS, so you see exactly where
  everything lands and how it looks. Change any option → it updates immediately.
- When it looks right → **Generate**. Videos render in parallel (see "Parallel jobs").
- When done you get: **output.zip**, and each reel's **title / description / hashtags** in a box
  with a **copy button** — paste straight into YouTube/Instagram. A `post_details.txt` is also
  inside the zip if you'd rather keep the file.

## Notes
- Host is CPU-only, ~2.7 GB RAM → keep **Whisper model = `small`**.
- **Upload limit:** default is 200 MB; the `config.toml` raises it. If a video is still too big,
  compress it or trim it before uploading.
- App **sleeps after ~12h idle**; opening the link wakes it in ~30–60s.
- Fonts are bundled and a fontconfig file is written automatically, so captions (incl. Hindi) render.

## Troubleshooting
- **Build failed** → Manage app → Logs, send me the error.
- **Out of memory** → Whisper model `base`, fewer parallel jobs.
- **Captions missing** → make sure the latest `engine.py` is uploaded.
- **Upload still capped at 200 MB** → check that `.streamlit/config.toml` exists with
  `[server]` `maxUploadSize = 2000`.
