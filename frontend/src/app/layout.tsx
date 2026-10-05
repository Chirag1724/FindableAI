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
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "https://findableai.vercel.app"),
  title: {
    default: "FindableAI - Machine Discoverability & AI Search Optimization",
    template: "%s | FindableAI",
  },
  description:
    "Audit how well AI search engines can find and trust your website. Get an F-Score, detect factual contradictions, and generate automatic fixes.",
  applicationName: "FindableAI",
  authors: [{ name: "FindableAI Team", url: "https://findableai.vercel.app" }],
  generator: "Next.js",
  keywords: [
    "Machine Discoverability Optimization",
    "Generative Engine Optimization",
    "GEO",
    "MDO",
    "AI Search Audit",
    "SearchGPT",
    "Perplexity AI",
    "Google AI Overviews",
    "Schema.org JSON-LD",
    "Findability F-Score",
    "NLI Entailment",
    "Autonomous Code Remediation",
  ],
  referrer: "origin-when-cross-origin",
  creator: "FindableAI",
  publisher: "FindableAI",
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/icon1.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [
      { url: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },
  manifest: "/manifest.json",
  openGraph: {
    title: "FindableAI - Machine Discoverability & AI Search Optimization",
    description:
      "Audit how well AI search engines (SearchGPT, Perplexity, Gemini) find and trust your website. Get an evidence-grounded F-Score and automated PR code fixes.",
    url: "https://findableai.vercel.app",
    siteName: "FindableAI",
    images: [
      {
        url: "/logo.png",
        width: 1200,
        height: 630,
        alt: "FindableAI - Machine Discoverability Platform",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "FindableAI - Machine Discoverability & AI Search Optimization",
    description:
      "Audit how well AI search engines find and trust your website. Calculate your F-Score, detect contradictions, and open automated remediation PRs.",
    images: ["/logo.png"],
    creator: "@FindableAI",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
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