DJ Kyoko — Automatic Mix Builder
================================

How to use:
1. Unzip this folder if you haven't already.
2. Double-click "DJ Kyoko.command". It'll open a Terminal window — that's
   normal, just leave it open in the background.
3. First run only: it installs a few things it needs (Homebrew, ffmpeg,
   Python packages). This can take several minutes and may ask for your Mac
   password once (to install Homebrew, if you don't already have it).
4. A page opens in your browser at http://127.0.0.1:8934 — that's the app.
   First time, it'll ask whether to use Louis's shared API key or your own.
   Louis's key works out of the box but is capped at $25/month shared
   across everyone using this app — if it runs out, the app will tell you
   and let you switch to your own free key from console.anthropic.com.
5. Type what you want your mix to sound like (e.g. "solomun meets madonna",
   "90s hip hop", "deep house sunset"), set how many minutes, hit Build.
   You can queue up several at once — they build in parallel with live
   progress bars, showing which tracks it picked, download %, and
   beat-matching progress.
6. When a mix finishes, play it right there in the browser or click
   "Finder" to reveal the MP3 file.

Every run after the first is much faster since setup only happens once.
Closing the Terminal window stops the app — just re-run the .command file
to start it again.

Note: downloads work best if you have Google Chrome installed (even if you
don't use it as your main browser) — it's used to help get past YouTube's
download restrictions.

Questions or something breaks? Ask Louis — the "story" log on each mix
card shows exactly what happened and will help him debug it fast.
