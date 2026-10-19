import { createApiClient, DEFAULT_API_BASE_URL } from "@homexo/shared";

export const api = createApiClient(process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);
