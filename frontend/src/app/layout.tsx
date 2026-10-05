import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#0A0A0A",
};

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
      <body className="min-h-screen bg-background text-[#EDEDED] antialiased selection:bg-white selection:text-black">
        {children}
      </body>
    </html>
  );
}