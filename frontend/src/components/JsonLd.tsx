/**
 * Machine-generated Schema.org JSON-LD component by FindableAI.
 * Enhances discoverability for LLMs and AI Search Engines (SearchGPT, Perplexity, Google AI Overviews).
 */
export function JsonLd() {
  const schema = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "FindableAI",
        "url": "https://findableai.vercel.app/"
      },
      {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
          {
            "@type": "Question",
            "name": "How does FindableAI differ from traditional SEO tools?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Traditional SEO tools optimize for keyword density, backlinks, and search crawlers. Modern searchers rely on AI answer engines. FindableAI audits machine discoverability: whether an LLM can retrieve, verify, and cite your factual claims without hallucinating."
            }
          },
          {
            "@type": "Question",
            "name": "What exactly is the Findability F-Score?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "The F-Score is a deterministic 0 to 100 metric evaluated across four mathematically grounded pillars: Query Intent Coverage (40%), Fact Consistency / Contradiction Penalty (30%), DOM & Schema Structure (20%), and Machine Extractability & Accessibility (10%). It pinpoints exactly where search engines lose confidence in your site."
            }
          },
          {
            "@type": "Question",
            "name": "How do autonomous GitHub Pull Requests work?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "When FindableAI identifies ungrounded queries or structural ambiguities, it traces the exact CSS selector path in your DOM. It then writes unified diffs with content patches and Schema.org JSON-LD microdata, proposing a pull request with these fixes for your team to review and merge."
            }
          },
          {
            "@type": "Question",
            "name": "Can I run audits on local or staging URLs?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "For live public URLs, audits execute immediately. For local or private staging environments, you can run our CLI crawler or provide a private GitHub repository URL to audit source files and templates directly."
            }
          },
          {
            "@type": "Question",
            "name": "Do I need to install an SDK or grant write access to production?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "No. Discoverability scans run non-invasively using headless browsers crawling your public URLs. For automatic code fixes, we only need repository write permissions for the designated remediation branch you authorize."
            }
          },
          {
            "@type": "Question",
            "name": "What are findableai.vercel.app's eligibility options and terms (query #1)?",
            "acceptedAnswer": {
              "@type": "Answer",
              "text": "Automated entailment analysis for eligibility intent from developer perspective."
            }
          }
        ]
      }
    ]
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

export default JsonLd;
