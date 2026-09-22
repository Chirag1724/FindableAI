import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FindableAI — Machine-Discoverability Optimization Platform",
  description: "Evidence-Grounded Autonomous Generative Engine & Machine Discoverability Optimization Platform",
  icons: {
    icon: "/logo.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-gray-100 antialiased selection:bg-brandIndigo selection:text-white">
        {children}
      </body>
    </html>
  );
}
