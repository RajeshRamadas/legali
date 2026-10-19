// Lets separate parts of the home page work together: any button can open the callback form with a service picked,
// or put a question to the chat assistant.
export const SERVICE_EVENT = "homexo:service";
export const ASK_EVENT = "homexo:ask";

export type ServiceRequest = { slug: string; message: string; pkg?: string | null; description?: string };

export function requestService(detail: ServiceRequest) {
  window.dispatchEvent(new CustomEvent<ServiceRequest>(SERVICE_EVENT, { detail }));
}

export function askAssistant(question: string) {
  window.dispatchEvent(new CustomEvent<string>(ASK_EVENT, { detail: question }));
}
