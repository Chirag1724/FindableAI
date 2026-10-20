import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Initialize Machine Audit",
  description:
    "Configure crawl scope, synthetic buyer personas, and GitHub integration to audit your site for AI search discoverability.",
  alternates: {
    canonical: "/audit",
  },
  openGraph: {
    title: "Initialize Machine Audit | FindableAI",
    description:
      "Configure crawl scope, synthetic buyer personas, and GitHub integration to audit your site for AI search discoverability.",
    url: "/audit",
  },
};

export default function AuditLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
