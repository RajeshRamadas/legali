import { useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import type { BookingRef } from "@homexo/shared";

// Bookings made or found in the app, kept on the device so My bookings can list them without an account.
const KEY = "homexo.bookings";
let refs: BookingRef[] = [];
let loaded = false;
const listeners = new Set<(refs: BookingRef[]) => void>();

function emit() {
  listeners.forEach((listener) => listener(refs));
  AsyncStorage.setItem(KEY, JSON.stringify(refs)).catch(() => {
    // Kept for this session only.
  });
}

async function load() {
  if (loaded) return;
  loaded = true;
  try {
    const stored = JSON.parse((await AsyncStorage.getItem(KEY)) || "[]");
    if (Array.isArray(stored)) {
      const known = new Set(refs.map((r) => r.ticket_number));
      refs = [...refs, ...stored.filter((r) => r && typeof r.ticket_number === "string" && !known.has(r.ticket_number))];
      listeners.forEach((listener) => listener(refs));
    }
  } catch {
    // Nothing stored yet, or storage unavailable.
  }
}

export function saveBookingRef(ref: BookingRef) {
  refs = [ref, ...refs.filter((r) => r.ticket_number !== ref.ticket_number)].slice(0, 20);
  emit();
}

export function forgetBookingRef(ticketNumber: string) {
  refs = refs.filter((r) => r.ticket_number !== ticketNumber);
  emit();
}

export function useBookingRefs(): BookingRef[] {
  const [value, setValue] = useState(refs);
  useEffect(() => {
    listeners.add(setValue);
    load();
    setValue(refs);
    return () => {
      listeners.delete(setValue);
    };
  }, []);
  return value;
}
