DJ Kyoko — Automatic Mix Builder (Windows)
===========================================

How to use:
1. Unzip this folder if you haven't already.
2. Double-click "DJ Kyoko.bat". A black window (Command Prompt) will pop up
   for a second, then a blue-ish PowerShell window — that's normal, just
   leave it open in the background.
3. Windows will probably show a blue "Windows protected your PC" screen the
   very first time (SmartScreen) — this happens to any downloaded script
   that isn't from the Microsoft Store, it's not a virus warning. Click
   "More info", then "Run anyway".
4. First run only: it installs a few things it needs (ffmpeg, deno, Python,
   rubberband). This can take several minutes — you may see a few more
   installer windows pop up, that's expected.
5. A page opens in your browser at http://127.0.0.1:8934 — that's the app.
   First time, it'll ask whether to use Louis's shared API key or your own.
   Louis's key works out of the box but is capped at $25/month shared
   across everyone using this app — if it runs out, the app will tell you
   and let you switch to your own free key from console.anthropic.com.
6. Type what you want your mix to sound like (e.g. "solomun meets madonna",
   "90s hip hop", "deep house sunset"), set how many minutes, hit Build.
   You can queue up several at once — they build in parallel with live
   progress bars, showing which tracks it picked, download %, and
   beat-matching progress.
7. When a mix finishes, play it right there in the browser or click
   "Show file" to reveal the MP3 in File Explorer.

Every run after the first is much faster since setup only happens once.
Closing the PowerShell window stops the app — just re-run "DJ Kyoko.bat"
to start it again.

Note: downloads work best if you have Google Chrome installed (even if you
don't use it as your main browser) — it's used to help get past YouTube's
download restrictions. Close Chrome before the first run if downloads fail
with a permission error — Chrome locks its own cookie file while it's open.

Note: this needs "winget" (the Windows Package Manager), which comes
built into Windows 10/11 already. If step 4 says it's missing, search
the Microsoft Store for "App Installer", install that, then re-run
"DJ Kyoko.bat".

Questions or something breaks? Ask Louis — the "Details / log" section on
each mix card shows exactly what happened and will help him debug it fast.
