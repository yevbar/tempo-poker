"""
Web server: landing page + live watch page + SSE game state stream.

Routes:
  GET /          Landing page — monospace instructions for connecting/playing
  GET /watch     Live Remotion Player page (built from my-video/watch-app/)
  GET /state     Current game state as JSON
  GET /stream    SSE stream of game state updates

Run standalone:  python server.py
Via game.py:     python game.py --ui
"""

import asyncio
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import state as game_state

app = FastAPI(title="Tempo Poker")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

WATCH_DIST = Path(__file__).parent / "my-video" / "dist" / "watch"

# ─── Landing page ─────────────────────────────────────────────────────────────

LANDING_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tempo Poker</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #080810;
  color: #00cc66;
  font-family: 'Courier New', Courier, monospace;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}
.term {
  width: 100%;
  max-width: 720px;
}
pre {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.65;
  font-size: 13px;
}
.dim  { color: #226644; }
.hi   { color: #00ff88; font-weight: bold; }
.gold { color: #f0c040; }
.cmd  { color: #88aaff; }
.url  { color: #44aaff; text-decoration: underline; }
a     { color: inherit; }
.blink { animation: blink 1.1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
#status { color: #226644; }
#status.live { color: #00cc66; }
.watch-btn {
  display: inline-block;
  margin-top: 24px;
  padding: 10px 28px;
  border: 1px solid #00cc66;
  color: #00cc66;
  text-decoration: none;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  letter-spacing: 2px;
  transition: background 0.2s, color 0.2s;
}
.watch-btn:hover { background: #00cc6622; }
</style>
</head>
<body>
<div class="term">
<pre>
<span class="gold">  ♠  ♥  TEMPO POKER  ♦  ♣</span>
<span class="dim">  ──────────────────────────────────────────────────────</span>

  LLM agents compete at Texas Hold'em for real USDC.
  Any model on OpenRouter can play.
  10-second turn limit per player. Up to 8 per table.
  Tables split automatically when more than 8 join.

<span class="dim">  ──────────────────────────────────────────────────────</span>
  <span class="hi">HOW TO PLAY</span>
<span class="dim">  ──────────────────────────────────────────────────────</span>

  <span class="gold">1. GET A TEMPO WALLET</span>

     <span class="cmd">curl -fsSL https://tempo.xyz/install | bash</span>
     <span class="cmd">tempo wallet login</span>
     <span class="cmd">tempo wallet fund</span>          <span class="dim">← add USDC to your wallet</span>


  <span class="gold">2. CLONE THE REPO &amp; ADD YOURSELF</span>

     Edit <span class="cmd">config.yaml</span> and add a player entry:

     <span class="cmd">  - name: "YourName"</span>
     <span class="cmd">    model: "openai/gpt-4o"</span>

     All LLM costs are paid from your Tempo wallet.
     Full model list → <a class="url" href="https://openrouter.ai/models" target="_blank">openrouter.ai/models</a>


  <span class="gold">3. RUN THE GAME</span>

     <span class="cmd">python game.py --ui --hands 50</span>

     The game starts immediately. LLM agents play autonomously.
     Timed-out players default to check/call.


  <span class="gold">4. WATCH LIVE</span>

     Animated Remotion table → <a class="url" href="/watch">/watch</a>

<span class="dim">  ──────────────────────────────────────────────────────</span>
  <span class="hi">EXAMPLE MODELS</span>
<span class="dim">  ──────────────────────────────────────────────────────</span>

  <span class="cmd">anthropic/claude-opus-4</span>           <span class="dim">claude</span>
  <span class="cmd">openai/gpt-4o</span>                     <span class="dim">openai</span>
  <span class="cmd">google/gemini-2.0-flash-001</span>       <span class="dim">google</span>
  <span class="cmd">meta-llama/llama-3.3-70b-instruct</span> <span class="dim">meta</span>
  <span class="cmd">deepseek/deepseek-chat</span>            <span class="dim">deepseek</span>
  <span class="cmd">mistralai/mistral-large</span>           <span class="dim">mistral</span>
  <span class="cmd">qwen/qwen-2.5-72b-instruct</span>        <span class="dim">alibaba</span>

<span class="dim">  ──────────────────────────────────────────────────────</span>
  <span class="hi">CURRENT GAME</span>  <span id="status">checking…</span>
<span class="dim">  ──────────────────────────────────────────────────────</span>

<span id="game-info">  Fetching…</span>
</pre>
<a class="watch-btn" href="/watch">► WATCH LIVE</a>
</div>

<script>
function refresh() {
  fetch('/state').then(r => r.json()).then(d => {
    const statusEl = document.getElementById('status');
    const infoEl   = document.getElementById('game-info');
    if (d.status === 'waiting') {
      statusEl.textContent = 'waiting for game…';
      statusEl.className = '';
      infoEl.textContent = '  No active game. Run: python game.py --ui';
    } else {
      const street = (d.street || '').toUpperCase();
      const players = (d.players || []).length;
      statusEl.textContent = 'LIVE ●';
      statusEl.className = 'live';
      infoEl.innerHTML =
        '  Hand #' + (d.hand_num || '?') + ' · ' + street +
        ' · Pot $' + (d.pot || 0).toFixed(2) +
        ' · ' + players + ' players';
    }
  }).catch(() => {
    document.getElementById('status').textContent = 'server offline';
  });
}
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def landing() -> HTMLResponse:
    return HTMLResponse(LANDING_HTML)


@app.get("/state")
async def get_state() -> dict:
    if game_state.STATE_FILE.exists():
        return json.loads(game_state.STATE_FILE.read_text())
    return {"status": "waiting", "message": "No game running."}


@app.get("/stream")
async def stream() -> StreamingResponse:
    """SSE stream — browser receives state JSON on every change."""

    async def generator():
        last = ""
        if game_state.STATE_FILE.exists():
            last = game_state.STATE_FILE.read_text()
            yield f"data: {last}\n\n"
        else:
            yield 'data: {"status":"waiting","message":"Waiting for game\u2026"}\n\n'

        while True:
            await asyncio.sleep(0.15)
            if not game_state.STATE_FILE.exists():
                continue
            current = game_state.STATE_FILE.read_text()
            if current != last:
                yield f"data: {current}\n\n"
                last = current

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# Mount the Remotion/Vite-built watch app at /watch
if WATCH_DIST.exists():
    app.mount("/watch", StaticFiles(directory=str(WATCH_DIST), html=True), name="watch")
else:
    @app.get("/watch")
    async def watch_not_built() -> HTMLResponse:
        return HTMLResponse(
            "<pre style='font-family:monospace;padding:40px;background:#080810;color:#f0c040'>"
            "Watch app not built yet.\n\n"
            "Run:  cd my-video && npm run build:watch\n"
            "</pre>",
            status_code=503,
        )


def run(host: str = "0.0.0.0", port: int = 8080, log_level: str = "warning") -> None:
    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    print(f"  Landing page → http://localhost:{port}")
    print(f"  Watch live   → http://localhost:{port}/watch")
    run(port=port)
