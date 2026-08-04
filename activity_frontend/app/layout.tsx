import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "月影狼蹤｜Discord 狼人殺",
  description: "6–12 人多人視覺化狼人殺，直接在 Discord 裡開局。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    title: "月影狼蹤｜Discord 狼人殺",
    description: "召集朋友，在月色下找出藏在人群中的狼人。",
    images: ["/werewolf-social-card.png"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#090b12",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
