import type { Metadata } from "next";
import { Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FutureBot — ES/NQ Trading",
  description: "Futures trading algo bot for ES and NQ",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistMono.variable} h-full antialiased dark`}>
      <body className="min-h-full flex flex-col bg-[#0f1117] text-gray-200 font-mono">
        <nav className="flex items-center gap-4 px-4 py-1.5 bg-gray-950 border-b border-gray-800 text-xs">
          <Link href="/" className="text-gray-400 hover:text-white">
            Terminal
          </Link>
          <Link href="/trades" className="text-gray-400 hover:text-white">
            Trades
          </Link>
          <Link href="/signals" className="text-gray-400 hover:text-white">
            Signals
          </Link>
          <Link href="/settings" className="text-gray-400 hover:text-white">
            Settings
          </Link>
        </nav>
        <main className="flex-1 flex flex-col">{children}</main>
      </body>
    </html>
  );
}
