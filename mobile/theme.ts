import { createApiClient, DEFAULT_API_BASE_URL } from "@homexo/shared";

// On a phone or emulator, localhost is the device itself. Set EXPO_PUBLIC_API_BASE_URL
// to your computer's LAN address (or http://10.0.2.2:8000 on the Android emulator).
export const api = createApiClient(process.env.EXPO_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL);

export const colors = {
  ink: "#17342e",
  muted: "#667771",
  green: "#1e6b50",
  greenDark: "#164c3d",
  lime: "#d5ef9b",
  cream: "#f7f7f0",
  line: "#e5e9e1",
  white: "#fff",
  danger: "#a23b2a",
};
