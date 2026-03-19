import "./index.css";
import { Composition } from "remotion";
import { MyComposition } from "./Composition";
import type { GameState } from "./Composition";

const defaultProps: GameState = {
  status: "waiting",
  message: "Waiting for game to start…",
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="PokerTable"
      component={MyComposition}
      durationInFrames={150}
      fps={30}
      width={1280}
      height={720}
      defaultProps={defaultProps}
    />
  );
};
