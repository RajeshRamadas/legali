"use client";

import { useEffect, useState } from "react";
import type { LawyerSlot, SlotDay } from "@homexo/shared";
import { api } from "../api";

// Morning, afternoon and evening by the hour shown on the slot (the lawyer's time zone).
function part(slot: LawyerSlot): "Morning" | "Afternoon" | "Evening" {
  const [time, meridiem] = slot.label.split(" ");
  const hour = (Number(time.split(":")[0]) % 12) + (meridiem === "pm" ? 12 : 0);
  return hour < 12 ? "Morning" : hour < 17 ? "Afternoon" : "Evening";
}

export default function SlotPicker({ slug, selected, onSelect, refreshKey = 0 }: {
  slug: string;
  selected: string | null;
  onSelect: (slot: LawyerSlot & { day: string }) => void;
  refreshKey?: number;
}) {
  const [days, setDays] = useState<SlotDay[] | null>(null);
  const [dayIndex, setDayIndex] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.lawyerSlots(slug, 7)
      .then((r) => {
        setDays(r.days);
        // Open on the first day with a free slot.
        setDayIndex(Math.max(0, r.days.findIndex((d) => d.slots.length > 0)));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load times."));
  }, [slug, refreshKey]);

  if (error) return <p className="lw-error" role="alert">{error}</p>;
  if (!days) return <p className="lw-fine">Loading open times…</p>;
  const day = days[dayIndex];
  const groups = (["Morning", "Afternoon", "Evening"] as const)
    .map((name) => ({ name, slots: day.slots.filter((s) => part(s) === name) }))
    .filter((g) => g.slots.length > 0);

  return (
    <div>
      <div className="lw-days" role="tablist" aria-label="Day">
        {days.map((d, i) => (
          <button key={d.date} role="tab" aria-selected={i === dayIndex} className={`lw-day${i === dayIndex ? " on" : ""}`} onClick={() => setDayIndex(i)}>
            {d.label}
            <small className={d.slots.length ? undefined : "none"}>{d.slots.length ? `${d.slots.length} slots` : "No slots"}</small>
          </button>
        ))}
      </div>
      {groups.length === 0 ? (
        <p className="lw-fine">No open times on {day.label.toLowerCase() === "today" ? "today" : day.label}. Try another day.</p>
      ) : groups.map((g) => (
        <div key={g.name} className="lw-slot-group">
          <span>{g.name}</span>
          <div className="lw-slots">
            {g.slots.map((s) => (
              <button key={s.starts_at} className={`lw-slot${selected === s.starts_at ? " on" : ""}`} aria-pressed={selected === s.starts_at} onClick={() => onSelect({ ...s, day: day.label })}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
