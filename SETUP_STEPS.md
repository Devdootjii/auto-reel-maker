# Auto Reels Studio — v17

## Deploy (3 files changed)
1. GitHub: replace `app.py` and `requirements.txt` (new: `yt-dlp`, `gdown`), and `.streamlit/config.toml`.
2. Streamlit Cloud -> app -> Reboot. Hard-refresh (Ctrl+Shift+R).
   (`engine.py` is not used any more — safe to delete.)

## New in v17
- **Upload from a link** (start screen): `Upload file` | `YouTube / link` | `Google Drive`.
  - YouTube / Instagram / X / Vimeo / direct .mp4 -> yt-dlp (up to 1080p, 4 h).
  - Google Drive -> file must be shared as "Anyone with the link".
  - Links download straight to the server's disk, so big files do not use RAM.
  - If YouTube answers "sign in / bot": upload a cookies.txt (expander on the same screen).
- **Crash fixes** (server overload):
  - Cores/RAM are now read from the container (`os.cpu_count()` reported the whole host -> dozens of threads).
  - Only 1-2 heavy jobs (transcribe/render) run at once for ALL visitors; others wait in a queue.
  - Parallel renders are capped by RAM. Whisper "medium" is hidden on servers under 4 GB.
  - Every visitor gets their own folder (no more shared `output.zip` / preview files). Old folders auto-clean after 6 h.
  - Download button no longer holds the whole zip in RAM (newer Streamlit reads it only on click).
  - Upload limit is now 1000 MB (a 2 GB upload lives fully in RAM and crashed the server). Use a link for bigger files.
- **Layout**: header is one line (no overlap), 7 tabs in one row, panels measure the window and stop 12 px above the
  action bar on any screen/zoom.

## Security tip (important)
Anyone who opens a public Streamlit app can use the connected Google login. To lock publishing, add to Secrets:
`PUBLISH_PIN = "your-pin"`  (the Publish tab then asks for it).
