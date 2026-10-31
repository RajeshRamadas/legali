import { useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { AccountProfile, AccountSession } from "@homexo/shared";

// The customer signed in on this device. Undefined until storage has been read.
export type Session = { token: string; profile: AccountProfile };
const KEY = "homexo.customer.session";
let session: Session | null | undefined;
const listeners = new Set<(value: Session | null | undefined) => void>();

function emit() {
  listeners.forEach((listener) => listener(session));
  const write = session ? AsyncStorage.setItem(KEY, JSON.stringify(session)) : AsyncStorage.removeItem(KEY);
  write.catch(() => {
    // Signed in for this session only.
  });
}

async function load() {
  if (session !== undefined) return;
  try {
    const stored = JSON.parse((await AsyncStorage.getItem(KEY)) || "null");
    // Signed in or out while storage was being read: that wins.
    if (session !== undefined) return;
    session = stored?.token && stored?.profile?.contact ? stored : null;
  } catch {
    session ??= null;
  }
  listeners.forEach((listener) => listener(session));
}

export function signIn(value: AccountSession) {
  session = { token: value.access_token, profile: value.account };
  emit();
}

export function updateProfile(profile: AccountProfile) {
  if (!session) return;
  session = { ...session, profile };
  emit();
}

export function signOut() {
  session = null;
  emit();
}

export function useSession(): Session | null | undefined {
  const [value, setValue] = useState(session);
  useEffect(() => {
    listeners.add(setValue);
    load();
    setValue(session);
    return () => {
      listeners.delete(setValue);
    };
  }, []);
  return value;
}
