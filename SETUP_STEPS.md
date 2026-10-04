# Auto Reel Maker — web app (v4)

Ribbon tabs (Word jaisa) · instant preview · parallel render · copy-ready descriptions.

## IMPORTANT: upload ALL THREE code files
Your repo currently has an OLD `engine.py` — that's why the preview error said
`module 'engine' has no attribute 'extract_frame'`. Update **all** of these:
- `app.py`
- `engine.py`   <-- must be the new one
- `requirements.txt`
- and `.streamlit/config.toml` (see below)

## Updating your existing app
1. GitHub repo → **Add file → Upload files** → drop in the new `app.py`, `engine.py`,
   `requirements.txt` → **Commit** (overwrite).
2. If you haven't already: **Add file → Create new file** → filename exactly
   `.streamlit/config.toml` → paste the config content → **Commit**.
3. Streamlit redeploys in ~1–2 min. Refresh the page.

## The interface
- Top **ribbon tabs**: Home · Captions · Animation · Framing · Audio · Clips · YouTube.
  Click a tab → its options open on the left. Your choices stay saved when you switch tabs.
- Right side: **Live preview** (instant) and **Process**.
- Preview needs no rendering — it draws one real frame of your video plus the caption,
  overlay, border and progress bar with CSS, so you see exactly where everything lands.
- After **Generate**: `output.zip` + each reel's title/description/hashtags in a copy box.

## Notes
- CPU-only host, ~2.7 GB RAM → keep **Whisper model = `small`**.
- Upload limit is raised by `.streamlit/config.toml` (`maxUploadSize = 2000`).
- App sleeps after ~12h idle; opening the link wakes it in ~30–60s.

## Troubleshooting
- **`module 'engine' has no attribute ...`** → the new `engine.py` wasn't uploaded.
- **Build failed** → Manage app → Logs, send me the error.
- **Out of memory** → Whisper `base`, fewer parallel jobs.
