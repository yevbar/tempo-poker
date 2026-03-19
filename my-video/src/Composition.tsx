import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface GamePlayer {
  name: string;
  model: string;
  stack: number;
  bet: number;
  folded: boolean;
  all_in: boolean;
  is_dealer: boolean;
  is_active: boolean;
  hole_cards: string[] | null;
  won?: number;
  hand_desc?: string;
  is_winner?: boolean;
}

export interface GameState {
  status: "waiting" | "playing" | "showdown";
  hand_num?: number;
  street?: string;
  pot?: number;
  board?: string[];
  players?: GamePlayer[];
  winners?: string[];
  thinking?: string;
  last_action?: { player: string; text: string };
  message?: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SUITS: Record<string, string> = { h: "♥", d: "♦", c: "♣", s: "♠" };
const RED_SUITS = new Set(["h", "d"]);

const MODEL_COLORS: Record<string, string> = {
  claude: "#7c5cbf",
  gpt: "#0fa37f",
  gemini: "#e8a020",
  llama: "#4a90d9",
  mistral: "#d95050",
  deepseek: "#3aacb8",
  grok: "#cc77cc",
  qwen: "#88b040",
};

function modelColor(model: string): string {
  const m = model.toLowerCase();
  const key = Object.keys(MODEL_COLORS).find((k) => m.includes(k));
  return key ? MODEL_COLORS[key] : "#667788";
}

// ─── Card ────────────────────────────────────────────────────────────────────

function Card({ cardStr, size = 1 }: { cardStr: string | null; size?: number }) {
  const w = Math.round(50 * size);
  const h = Math.round(70 * size);

  if (!cardStr) {
    return (
      <div
        style={{
          width: w, height: h,
          borderRadius: 6 * size,
          background: "repeating-linear-gradient(45deg,#1a2e60 0px,#1a2e60 4px,#0d1e45 4px,#0d1e45 8px)",
          border: "1px solid #334",
          flexShrink: 0,
        }}
      />
    );
  }

  const rank = cardStr[0];
  const suit = cardStr[1];
  const isRed = RED_SUITS.has(suit);
  const rankDisplay = rank === "T" ? "10" : rank;
  const suitSymbol = SUITS[suit] ?? suit;

  return (
    <div
      style={{
        width: w, height: h,
        borderRadius: 6 * size,
        background: "#fff",
        border: "1px solid #ccc",
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "space-between",
        padding: `${3 * size}px ${4 * size}px`,
        color: isRed ? "#c0392b" : "#111",
        fontFamily: "monospace",
        fontWeight: "bold",
        flexShrink: 0,
        boxShadow: `1px ${2 * size}px ${6 * size}px rgba(0,0,0,0.45)`,
      }}
    >
      <span style={{ fontSize: 14 * size, lineHeight: 1 }}>{rankDisplay}</span>
      <span style={{ fontSize: 20 * size, alignSelf: "center", lineHeight: 1 }}>{suitSymbol}</span>
      <span style={{ fontSize: 14 * size, lineHeight: 1, alignSelf: "flex-end", transform: "rotate(180deg)" }}>
        {rankDisplay}
      </span>
    </div>
  );
}

// ─── Player Seat ─────────────────────────────────────────────────────────────

function PlayerSeat({ player, x, y, frame }: { player: GamePlayer; x: number; y: number; frame: number }) {
  const color = modelColor(player.model);
  const pulse = player.is_active ? 8 + 6 * Math.sin(frame * 0.18) : 0;
  const glow = player.is_active ? `0 0 ${pulse}px ${color}99` : "none";

  return (
    <div
      style={{
        position: "absolute",
        left: x, top: y,
        transform: "translate(-50%,-50%)",
        textAlign: "center",
        width: 120,
        opacity: player.folded ? 0.3 : 1,
      }}
    >
      <div
        style={{
          width: 36, height: 36,
          borderRadius: "50%",
          background: color + "28",
          border: `2px solid ${color}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          margin: "0 auto 3px",
          color, fontWeight: "bold", fontSize: 16, fontFamily: "monospace",
          boxShadow: glow,
        }}
      >
        {player.name[0].toUpperCase()}
      </div>

      <div
        style={{
          fontSize: 11, fontWeight: "bold",
          color: player.is_winner ? "#f0c040" : "#ddd",
          fontFamily: "monospace",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          marginBottom: 1,
        }}
      >
        {player.name}
        {player.is_dealer && (
          <span
            style={{
              background: "#f0c040", color: "#111", fontSize: 8,
              fontWeight: "bold", borderRadius: "50%",
              width: 13, height: 13,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              marginLeft: 3,
            }}
          >
            D
          </span>
        )}
      </div>

      <div style={{ fontSize: 8, color: "#556", fontFamily: "monospace", marginBottom: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {player.model}
      </div>

      {!player.folded && (
        <div style={{ display: "flex", gap: 3, justifyContent: "center", marginBottom: 3 }}>
          {player.hole_cards
            ? player.hole_cards.map((c, i) => <Card key={i} cardStr={c} size={0.72} />)
            : [<Card key={0} cardStr={null} size={0.72} />, <Card key={1} cardStr={null} size={0.72} />]}
        </div>
      )}

      <div style={{ fontSize: 11, color: "#aaeeff", fontFamily: "monospace" }}>
        ${player.stack.toFixed(2)}
      </div>

      {player.bet > 0 && (
        <div style={{ fontSize: 10, color: "#f0c040", fontFamily: "monospace" }}>
          bet ${player.bet.toFixed(2)}
        </div>
      )}

      {(player.won ?? 0) > 0 && (
        <div style={{ fontSize: 12, color: "#f0c040", fontWeight: "bold", fontFamily: "monospace" }}>
          +${(player.won ?? 0).toFixed(2)}
        </div>
      )}

      {player.hand_desc && (
        <div style={{ fontSize: 9, color: "#aaa", fontFamily: "monospace" }}>{player.hand_desc}</div>
      )}

      {player.is_active && (
        <div
          style={{
            fontSize: 9, color: "#f0c040", fontFamily: "monospace",
            opacity: 0.5 + 0.5 * Math.sin(frame * 0.22),
          }}
        >
          thinking…
        </div>
      )}
    </div>
  );
}

// ─── Main Composition ────────────────────────────────────────────────────────

export const MyComposition: React.FC<GameState> = (props) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const { status, hand_num, street, pot, board = [], players = [], message } = props;

  const fadeIn = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });

  const tableW = width * 0.58;
  const tableH = height * 0.60;
  const cx = width / 2;
  const cy = height / 2 + 16;

  const n = Math.max(players.length, 1);
  const seats = players.map((_, i) => ({
    x: cx + (tableW / 2) * 0.9 * Math.cos((i / n) * 2 * Math.PI - Math.PI / 2),
    y: cy + (tableH / 2) * 0.9 * Math.sin((i / n) * 2 * Math.PI - Math.PI / 2),
  }));

  if (status === "waiting") {
    return (
      <div
        style={{
          width, height, background: "#080810",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "monospace", color: "#445", fontSize: 18, opacity: fadeIn, letterSpacing: 2,
        }}
      >
        {message ?? "Waiting for game to start…"}
      </div>
    );
  }

  return (
    <div
      style={{
        width, height,
        background: "radial-gradient(ellipse at center,#0d1520 0%,#070710 100%)",
        position: "relative", overflow: "hidden", opacity: fadeIn,
      }}
    >
      {/* Top bar */}
      <div
        style={{
          position: "absolute", top: 0, left: 0, right: 0, height: 42,
          background: "rgba(0,0,0,0.55)", borderBottom: "1px solid #1e1e30",
          display: "flex", alignItems: "center", padding: "0 22px", gap: 22,
          fontFamily: "monospace",
        }}
      >
        <span style={{ color: "#f0c040", fontSize: 13, letterSpacing: 3, fontWeight: "bold" }}>
          ♠ TEMPO POKER ♥
        </span>
        <span style={{ color: "#445", fontSize: 12 }}>
          Hand <span style={{ color: "#ddd" }}>#{hand_num}</span>
        </span>
        <span
          style={{
            background: "#14142a", border: "1px solid #2a2a40", borderRadius: 4,
            padding: "2px 10px", fontSize: 11, color: "#f0c040",
            letterSpacing: 1, textTransform: "uppercase",
          }}
        >
          {street}
        </span>
        <span style={{ color: "#445", fontSize: 12 }}>
          Pot <span style={{ color: "#f0c040" }}>${(pot ?? 0).toFixed(2)}</span>
        </span>
      </div>

      {/* Felt table */}
      <div
        style={{
          position: "absolute",
          left: cx - tableW / 2, top: cy - tableH / 2,
          width: tableW, height: tableH,
          borderRadius: "50%",
          background: "radial-gradient(ellipse at 50% 38%,#2a8060 0%,#1f6347 45%,#0f3d28 100%)",
          border: "13px solid #7a3010",
          boxShadow: "0 0 0 3px #9a4018,0 0 80px rgba(0,0,0,0.9),inset 0 0 70px rgba(0,0,0,0.35)",
        }}
      >
        <div style={{ position: "absolute", inset: 10, borderRadius: "50%", border: "1px solid rgba(255,255,255,0.05)" }} />
      </div>

      {/* Community cards + pot */}
      <div
        style={{
          position: "absolute", left: cx, top: cy,
          transform: "translate(-50%,-50%)", textAlign: "center",
        }}
      >
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: 10 }}>
          {Array.from({ length: 5 }).map((_, i) => {
            const cf = Math.max(0, frame - i * 4);
            const scale = interpolate(cf, [0, 10], [0.6, 1], { extrapolateRight: "clamp" });
            const op = interpolate(cf, [0, 8], [0, 1], { extrapolateRight: "clamp" });
            return (
              <div key={i} style={{ transform: `scale(${scale})`, opacity: op }}>
                <Card cardStr={board[i] ?? null} size={1.1} />
              </div>
            );
          })}
        </div>
        <div
          style={{
            color: "#f0c040", fontFamily: "monospace", fontSize: 13,
            letterSpacing: 1, textShadow: "0 0 8px rgba(240,192,64,0.4)",
          }}
        >
          POT &nbsp;${(pot ?? 0).toFixed(2)}
        </div>
      </div>

      {/* Players */}
      {players.map((p, i) => (
        <PlayerSeat key={p.name} player={p} x={seats[i].x} y={seats[i].y} frame={frame} />
      ))}
    </div>
  );
};
