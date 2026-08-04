import type { Metadata } from "next";
import { WerewolfActivity } from "./werewolf-activity";

export const metadata: Metadata = {
  title: "月影狼蹤｜Discord 狼人殺",
  description: "在 Discord 裡直接玩的多人視覺化狼人殺 Activity。",
  other: {
    "codex-preview": "ready",
  },
};

export default function Home() {
  return <WerewolfActivity />;
}
