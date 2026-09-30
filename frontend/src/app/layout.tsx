import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Fraunces, Inter } from "next/font/google";
import "./globals.css";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "FindableAI - Machine Discoverability Audit",
    template: "%s | FindableAI",
  },
  description:
    "Audit how well AI search engines can find and trust your website. Get an F-Score, detect factual contradictions, and generate automatic fixes.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`dark ${GeistSans.variable} ${GeistMono.variable} ${fraunces.variable} ${inter.variable}`}
    >
      <body className="min-h-screen bg-background text-[#EDEDED] antialiased selection:bg-[#d4af72] selection:text-black">
        {children}
      </body>
    </html>
  );
}