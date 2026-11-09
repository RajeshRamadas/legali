"use client";
import { useEffect, useState } from "react";
import { ApiError } from "@homexo/shared";

export default function useRetryDelay() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (seconds <= 0) return;
    const timer = window.setTimeout(() => setSeconds(value => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [seconds]);
  function record(error: unknown) {
    if (error instanceof ApiError && error.status === 429 && error.retryAfterSeconds) setSeconds(error.retryAfterSeconds);
  }
  return { seconds, record };
}
