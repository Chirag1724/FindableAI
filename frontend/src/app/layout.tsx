import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

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
      className={`dark ${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="min-h-screen bg-background text-[#EDEDED] antialiased selection:bg-violet-700 selection:text-white">
        {children}
      </body>
    </html>
  );
}