# Free Auto Reels Generator — web app (v8)

## What changed in v8
- **Everything fits one screen — no page scrolling.** Streamlit's own header/toolbar is hidden,
  all widgets, labels, buttons and the upload box are compacted, and the preview is smaller.
- **New animated background** — slow-moving gradient + drifting glow orbs, and panels/buttons
  react on hover (lift + glow).
- The "Title / description / hashtags" panel now lives inside the centre column as a collapsed
  expander, so it never pushes the layout down.

## Update
Only **`app.py`** changed. Re-upload it to the same GitHub repo (overwrite -> Commit).
Streamlit redeploys in ~1-2 min.

## Layout (per your wireframe)
```
[ logo + title ............................ upload video ]
[ home | frame | captions | animations | colors | audio | clips | how to use ]
[ options (left) | phone preview (centre) | progress + other options (right) ]
[ Generate video | Download | Save to Drive | Upload to YouTube ]
```
The **How to use** tab explains the whole flow inside the app.

## Notes
- CPU host -> keep **Whisper model = `small`**.
- Settings auto-save; Reset is on the Home tab.
- If anything breaks, the app prints the real error on screen — screenshot it and send it.
