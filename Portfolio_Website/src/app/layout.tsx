import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Abhishek Suman — Network & GenAI Engineer",
  description: "Enterprise network engineering and applied GenAI/LLM portfolio of Abhishek Suman.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
