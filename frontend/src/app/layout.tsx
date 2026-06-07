import type { Metadata } from "next";
import { Inter, Sora } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  weight: ["600", "700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Basketball IQ — AI-Powered Analytics Platform",
  description: "Video analysis, scouting reports, and game simulation for basketball coaches",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${sora.variable}`}>
      <body className="min-h-screen bg-surface text-slate-900 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
