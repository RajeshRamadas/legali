import type { PostType } from "@homexo/shared";

// Starting points for new posts. The editor fills these in; admins replace the bracketed prompts.
export type PostTemplate = { label: string; hint: string; excerpt: string; body: string; highlights: { label: string; value: string }[] };

export const TEMPLATES: Record<PostType, PostTemplate> = {
  article: {
    label: "Article",
    hint: "A guide or explainer: a document, a process, a law change.",
    excerpt: "",
    highlights: [],
    body: `[Open with the question a buyer is asking, in one or two sentences. Why does it matter before they pay?]

## What it is

[Explain the document, rule or step in plain words. Name the office that issues it.]

## Why it matters

- [Risk it protects against]
- [What can go wrong without it]

## How to check it

1. [First step]
2. [Second step]
3. [What a clean result looks like]

## Red flags

- [Warning sign and what it usually means]

> **Tip:** [One practical tip from our case team.]

## How Homexo helps

[One short paragraph on the package or service that covers this, with a link such as [Shield Pro](/#packages).]
`,
  },
  case_study: {
    label: "Case study",
    hint: "A real file: the property, what we found and how it ended.",
    excerpt: "",
    highlights: [
      { label: "Property", value: "[e.g. 3BHK apartment]" },
      { label: "Location", value: "[e.g. Whitefield, Bengaluru]" },
      { label: "Service", value: "[e.g. Shield Pro verification]" },
      { label: "Turnaround", value: "[e.g. 6 working days]" },
      { label: "Outcome", value: "[e.g. Purchase completed safely]" },
    ],
    body: `[One-paragraph summary: who the client was (anonymised unless they agreed to be named), what they were buying and the result.]

## The situation

[What the client brought us and what they were worried about. Stage of the deal, amount at stake if shareable.]

## What we checked

- [Title chain, years covered]
- [Encumbrance Certificate period]
- [Khata, tax, approvals, RERA]

## What we found

[The issue, in plain language. Quote the document or entry if helpful.]

## What we did

1. [Action taken, e.g. requested rectification deed from seller]
2. [Coordination with sub-registrar, BBMP or bank]

## The outcome

[Result for the client: money protected, deal renegotiated, safe registration.]

> "[Client quote, with permission.]"

## Lessons for buyers

- [Takeaway another buyer can act on]
`,
  },
};
