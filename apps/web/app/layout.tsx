import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "APOLO LangDock",
  description: "Open AI workspace for models, agents, workflows and MCP."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
