"use client";

import { askAssistant, requestService, type ServiceRequest } from "./homeEvents";

// A button that opens the home page's callback form with a service picked.
export default function ServiceButton({ request, className = "btn", children }: { request: ServiceRequest; className?: string; children: React.ReactNode }) {
  return <button type="button" className={className} onClick={() => requestService(request)}>{children}</button>;
}

// A button that opens the chat assistant.
export function AskButton({ className, children }: { className?: string; children: React.ReactNode }) {
  return <button type="button" className={className} onClick={() => askAssistant("")}>{children}</button>;
}
