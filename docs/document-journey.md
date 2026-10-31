# Document journey: guided uploads, relationship map and checklist

The customer Documents page (`/documents`) and the staff ticket page show the same plain-language view of a case,
built by `backend/app/document_journey.py` and returned as `document_request.journey` on every ticket view.

- **Stages**: property details → your documents → official records → documents read (latest verification run;
  out of date when files changed since) → advocate review → signed report. Uploads and official records run side by
  side, so more than one stage can be current.
- **Groups and links** (the "How your documents fit together" map): each requested document belongs to one question
  (who is selling, how they came to own it, loans and charges, government records, approvals, court and government
  searches, other). Identity feeds the title chain, which feeds the other checks, which feed the advocate's opinion.
  Tags map to groups in `GROUPS`; tags a lawyer adds go to "other".
- **Checks**: one per group plus the advocate's opinion. Status comes only from checklist item statuses:
  `problem` if any item is rejected, `passed` when all are verified/waived, `in_review` when nothing is still needed,
  else `waiting` (naming what the customer and the case team still owe). `flags` lists problems the automatic upload
  check (`documents.ai_check`) noticed; they are advice and never change a status.
- **next_upload**: the item the page asks for next, a rejected upload first, then the first one still needed.

The customer page asks for one document at a time (drag and drop, several files, or a phone photo), lets the customer
skip one they don't have yet, and files uploads by document name rather than tag.
