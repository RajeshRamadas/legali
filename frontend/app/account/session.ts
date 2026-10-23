"use client";

import { useEffect, useState } from "react";
import type { AccountProfile, AccountSession } from "@homexo/shared";

// The signed-in customer on this browser. Storage can be unavailable (private mode, blocked site data), so every access
// is guarded; without it the customer stays signed in until the tab is closed.
export type Session = { token: string; profile: AccountProfile };
const KEY = "homexo.customer.session";
const EVENT = "homexo-session";
let memory: Session | null = null;

export function readSession(): Session | null {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "null");
    return value?.token && value?.profile?.contact ? value : memory;
  } catch {
    return memory;
  }
}

function write(session: Session | null) {
  memory = session;
  try {
    if (session) localStorage.setItem(KEY, JSON.stringify(session));
    else localStorage.removeItem(KEY);
  } catch {
    // Kept in memory only.
  }
  window.dispatchEvent(new Event(EVENT));
}

export const signIn = (session: AccountSession) => write({ token: session.access_token, profile: session.account });
export const updateProfile = (profile: AccountProfile) => {
  const current = readSession();
  if (current) write({ ...current, profile });
};
export const signOut = () => write(null);

// The session, kept in step across components and tabs. Undefined until read on the client.
export function useSession(): Session | null | undefined {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  useEffect(() => {
    const update = () => setSession(readSession());
    update();
    window.addEventListener(EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);
  return session;
}
