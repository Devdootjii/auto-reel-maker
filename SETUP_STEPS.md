# Auto Reel Maker — web app setup (free)

A permanent link with a real UI, a **live phone-sized preview** of every option, progress bars, and **YouTube upload** built in. No Colab, no session timeouts.

## Files (upload all three to GitHub)
- `app.py` — the UI
- `engine.py` — the rendering/transcription core
- `requirements.txt` — dependencies

## First-time setup

### 1. GitHub
1. github.com → **New repository** → name `auto-reel-maker` → **Public** → Create.
2. **Add file → Upload files** → upload `app.py`, `engine.py`, `requirements.txt` → **Commit changes**.

### 2. Deploy (free)
1. **share.streamlit.io** → sign in with GitHub.
2. **Create app → Deploy a public app from GitHub**.
3. Repository: `auto-reel-maker` · Main file path: **`app.py`** → **Deploy**.
4. First build ~5–10 min. You get a permanent URL — bookmark it.

## Updating an existing app (this is you)
When I send new versions, just **re-upload the changed files to the same GitHub repo** (Add file → Upload files → overwrite → Commit). Streamlit **auto-redeploys** in a minute or two. Nothing else to do.

## How to use
- Open the link → upload video(s).
- Left sidebar = all options. **Preview** tab renders a short sample instantly, so you can see each option's effect before committing.
- Happy → **Generate** tab → **Generate now** → download the zip (videos + `post_details.txt`).
- **YouTube** tab → one-time connect (upload `client_secret.json`, approve the link, paste the `code=` value) → upload. Login is saved and reused.

## Notes
- Host is **CPU-only** and ~2.7 GB RAM → keep **Whisper model = `small`** (default). `medium`/`large-v3` may crash.
- A 1–1.5 hour video takes a while — you'll see a live progress bar + tips while it runs.
- App **sleeps after ~12h of no visits**; opening the link wakes it in ~30–60s. Nothing is lost.
- **Fonts are bundled** and a fontconfig file is written automatically, so captions (including Hindi) render even on this bare host.

## Troubleshooting
- **Build failed** → Manage app → Logs, send me the error.
- **Out of memory** → Whisper model `base`, one video at a time.
- **Captions missing** → make sure the newest `engine.py` is uploaded (it writes the fontconfig file).
