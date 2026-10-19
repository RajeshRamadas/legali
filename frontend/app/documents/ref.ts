// The track card hands over the ticket and contact so the customer doesn't type them twice. Kept for the browser session only.
export type Ref = { ticket_number: string; contact: string };
const REF_KEY = "homexo.documents.ref";

export function openDocuments(ref: Ref) {
  try {
    sessionStorage.setItem(REF_KEY, JSON.stringify(ref));
  } catch {
    // Storage blocked: the page asks for the ticket number instead.
  }
}

export function readRef(): Ref | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(REF_KEY) || "null");
    return value?.ticket_number && value?.contact ? value : null;
  } catch {
    return null;
  }
}
