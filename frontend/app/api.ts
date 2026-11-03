import { createApiClient, DEFAULT_API_BASE_URL } from "@homexo/shared";

import { readSession, signOut } from "./account/session";

export const api = createApiClient(process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL, {
  getToken: () => readSession()?.token,
  onUnauthorized: (token) => { if (readSession()?.token === token) signOut(); },
});
