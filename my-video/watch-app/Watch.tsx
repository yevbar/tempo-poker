import { useEffect, useRef, useState } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import { MyComposition, type GameState } from "../src/Composition";

const COMPOSITION_FRAMES = 150; // 5s at 30fps — loops on each new state
const FPS = 30;
const W = 1280;
const H = 720;

const WAITING: GameState = {
  status: "waiting",
  message: "Connecting to game server…",
};

// Read backend URL from ?server=https://... query param, default to same origin
const API_BASE = new URLSearchParams(window.location.search).get("server") ?? "";

function LogEntry({ text, kind }: { text: string; kind: string }) {
  const colors: Record<string, string> = {
    win: "#f0c040",
    deal: "#7ecfff",
    street: "#8888cc",
    system: "#445566",
    action: "#aaa",
  };
  return (
    <div
      style={{
        fontSize: 11,
        fontFamily: "monospace",
        color: colors[kind] ?? "#aaa",
        padding: "3px 0",
        borderBottom: "1px solid rgba(255,255,255,0.03)",
        lineHeight: 1.4,
      }}
    >
      {text}
    </div>
  );
}

function Standings({ players }: { players: GameState["players"] }) {
  if (!players?.length) return null;
  const sorted = [...players].sort((a, b) => b.stack - a.stack);
  return (
    <div>
      {sorted.map((p, i) => (
        <div
          key={p.name}
          style={{
            display: "grid",
            gridTemplateColumns: "18px 1fr auto",
            gap: 6,
            fontSize: 11,
            fontFamily: "monospace",
            padding: "4px 0",
            borderBottom: "1px solid rgba(255,255,255,0.03)",
            color: i === 0 ? "#f0c040" : "#ccc",
          }}
        >
          <span style={{ color: "#445" }}>{i + 1}</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {p.name}
          </span>
          <span style={{ color: "#aaeeff" }}>${p.stack.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export function Watch() {
  const [state, setState] = useState<GameState>(WAITING);
  const [log, setLog] = useState<Array<{ text: string; kind: string }>>([]);
  const [connected, setConnected] = useState(false);
  const [age, setAge] = useState(0);
  const lastUpdateRef = useRef<number>(Date.now());
  const playerRef = useRef<PlayerRef>(null);

  // SSE connection — reconnects automatically
  useEffect(() => {
    let es: EventSource;

    const connect = () => {
      es = new EventSource(`${API_BASE}/stream`);

      es.onopen = () => setConnected(true);

      es.onmessage = (evt) => {
        try {
          const incoming = JSON.parse(evt.data) as GameState & {
            action_log?: Array<{ text: string; kind: string }>;
          };
          const { action_log, ...gameState } = incoming;
          setState(gameState);
          if (action_log) setLog(action_log);
          lastUpdateRef.current = Date.now();

          // Restart animation from frame 0 on each new event
          playerRef.current?.seekTo(0);
        } catch {
          // ignore parse errors
        }
      };

      es.onerror = () => {
        setConnected(false);
        es.close();
        setTimeout(connect, 3000);
      };
    };

    connect();
    return () => es?.close();
  }, []);

  // Age ticker
  useEffect(() => {
    const t = setInterval(() => {
      setAge(Math.round((Date.now() - lastUpdateRef.current) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div
      style={{
        background: "#08080f",
        minHeight: "100vh",
        display: "grid",
        gridTemplateRows: "42px 1fr 28px",
        fontFamily: "monospace",
        color: "#ddd",
      }}
    >
      {/* Header */}
      <div
        style={{
          background: "#050508",
          borderBottom: "1px solid #1a1a28",
          display: "flex",
          alignItems: "center",
          padding: "0 20px",
          gap: 20,
        }}
      >
        <span style={{ color: "#f0c040", letterSpacing: 3, fontSize: 13, fontWeight: "bold" }}>
          ♠ TEMPO POKER ♥
        </span>
        <span style={{ color: "#334", fontSize: 12 }}>
          Hand{" "}
          <span style={{ color: "#bbb" }}>#{state.hand_num ?? "—"}</span>
        </span>
        {state.street && (
          <span
            style={{
              background: "#14142a",
              border: "1px solid #2a2a40",
              borderRadius: 4,
              padding: "2px 10px",
              fontSize: 10,
              color: "#f0c040",
              letterSpacing: 1,
              textTransform: "uppercase",
            }}
          >
            {state.street}
          </span>
        )}
        <span style={{ flex: 1 }} />
        <a
          href="/"
          style={{ color: "#334", fontSize: 11, textDecoration: "none" }}
        >
          ← how to play
        </a>
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: connected ? "#2ecc71" : "#e74c3c",
            boxShadow: connected ? "0 0 6px #2ecc71" : "none",
          }}
        />
      </div>

      {/* Main: player + sidebar */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 260px",
          overflow: "hidden",
        }}
      >
        {/* Remotion Player */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
            background: "#070710",
          }}
        >
          <Player
            ref={playerRef}
            component={MyComposition}
            inputProps={state}
            durationInFrames={COMPOSITION_FRAMES}
            fps={FPS}
            compositionWidth={W}
            compositionHeight={H}
            style={{ width: "100%", maxWidth: "100%", aspectRatio: "16/9" }}
            loop
            autoPlay
            controls={false}
            clickToPlay={false}
          />
        </div>

        {/* Sidebar */}
        <div
          style={{
            borderLeft: "1px solid #1a1a28",
            display: "grid",
            gridTemplateRows: "1fr 1fr",
            overflow: "hidden",
          }}
        >
          {/* Action log */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              padding: 12,
              overflow: "hidden",
              borderBottom: "1px solid #1a1a28",
            }}
          >
            <div
              style={{
                fontSize: 9,
                letterSpacing: 2,
                color: "#334",
                textTransform: "uppercase",
                marginBottom: 8,
                paddingBottom: 6,
                borderBottom: "1px solid #1a1a28",
              }}
            >
              Action Log
            </div>
            <div
              style={{
                flex: 1,
                overflowY: "auto",
                scrollbarWidth: "thin",
                scrollbarColor: "#222 transparent",
              }}
            >
              {[...log].reverse().map((e, i) => (
                <LogEntry key={i} text={e.text} kind={e.kind} />
              ))}
            </div>
          </div>

          {/* Standings */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              padding: 12,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                fontSize: 9,
                letterSpacing: 2,
                color: "#334",
                textTransform: "uppercase",
                marginBottom: 8,
                paddingBottom: 6,
                borderBottom: "1px solid #1a1a28",
              }}
            >
              Standings
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
              <Standings players={state.players} />
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div
        style={{
          background: "#040407",
          borderTop: "1px solid #1a1a28",
          display: "flex",
          alignItems: "center",
          padding: "0 16px",
          gap: 12,
          fontSize: 11,
          color: "#334",
        }}
      >
        <span style={{ color: connected ? "#2ecc71" : "#e74c3c" }}>
          {connected ? "● live" : "○ reconnecting…"}
        </span>
        <span>·</span>
        <span>Last update: {age < 2 ? "now" : `${age}s ago`}</span>
        {state.players && (
          <>
            <span>·</span>
            <span>{state.players.length} players</span>
          </>
        )}
      </div>
    </div>
  );
}
