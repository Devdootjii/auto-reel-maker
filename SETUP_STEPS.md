# Auto Reel Maker — web app setup (free)

You get a **permanent link** with a real UI, and a **live preview** of every option.
No more Colab, no session timeouts, no re-uploading.

## What you need
- A free **GitHub** account
- A free **Streamlit Community Cloud** account (sign in with GitHub)

## Steps

### 1. Put the files on GitHub
1. Go to github.com -> **New repository**. Name it `auto-reel-maker`, keep it **Public**, Create.
2. In the repo click **Add file -> Upload files**.
3. Upload these three files:
   - `app.py`
   - `engine.py`
   - `requirements.txt`
4. Click **Commit changes**.

### 2. Deploy on Streamlit Community Cloud
1. Go to **share.streamlit.io** -> sign in with GitHub (authorise it).
2. Click **Create app** -> **Deploy a public app from GitHub**.
3. Repository: pick `auto-reel-maker`. Main file path: **`app.py`**.
4. Click **Deploy**. First build takes ~5-10 minutes (it installs Whisper).
5. You get a URL like `https://<your-name>-auto-reel-maker.streamlit.app` — that's your tool. Bookmark it.

### 3. Use it
- Open the link -> upload a video -> tweak options in the left sidebar.
- The **Preview** tab renders a short sample instantly, so you can see exactly what each option does before committing.
- Happy? Go to the **Generate** tab -> **Generate now** -> download the zip (videos + `post_details.txt`).

## Important notes
- **This host is CPU-only.** No GPU. So:
  - Use **Whisper model = `small`** (default) or `base` for long videos.
  - A 1-1.5 hour video may take a while. Start it and let it run.
- **Memory limit ~2.7 GB.** `medium`/`large-v3` may crash — stick to `small`.
- The app **sleeps after ~12 hours of no visits**; opening the link wakes it in a few seconds. Nothing is lost.
- First visit after a sleep takes ~30-60s to boot.

## Want a GPU (10x faster)?
- **Hugging Face Spaces** gives a free **16 GB RAM** CPU box, and free personal accounts can run Gradio Spaces on **ZeroGPU** (free GPU bursts). Streamlit on HF now needs a paid PRO plan, so on HF use **Gradio**.
- Or rent a cheap GPU (HF Spaces T4 ~$0.40/hour) if you process long videos often.
- For now, CPU + `small` works fine — just slower.

## Troubleshooting
- **Build failed**: open the app's logs (Manage app -> Logs) and send me the error.
- **Out of memory**: lower the Whisper model to `base`, and process one video at a time.
- **Hindi text shows boxes**: tell me — the Devanagari font may not have loaded; I'll switch it to the bundled one.
