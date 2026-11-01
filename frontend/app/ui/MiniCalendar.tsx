"use client";
import { dayKey } from "./utils";
export default function MiniCalendar({
  month = new Date(),
  marked,
  onSelect,
}: {
  month?: Date;
  marked: Set<string>;
  onSelect: (day: string) => void;
}) {
  const [year, number] = dayKey(month).split("-").map(Number),
    m = number - 1,
    start = new Date(Date.UTC(year, m, 1)).getUTCDay(),
    count = new Date(Date.UTC(year, m + 1, 0)).getUTCDate(),
    today = dayKey(new Date());
  return (
    <div className="hx-calendar">
      <strong>
        {new Intl.DateTimeFormat("en-IN", {
          timeZone: "Asia/Kolkata",
          month: "long",
          year: "numeric",
        }).format(month)}
      </strong>
      <div className="hx-calendar-grid">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
          <small key={d}>{d}</small>
        ))}
        {Array.from({ length: start }, (_, i) => (
          <span key={`blank-${i}`} />
        ))}
        {Array.from({ length: count }, (_, i) => {
          const date = `${year}-${String(m + 1).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`;
          return (
            <button
              key={date}
              type="button"
              aria-label={date}
              aria-current={date === today ? "date" : undefined}
              className={`${marked.has(date) ? "marked" : ""} ${date === today ? "today" : ""}`}
              onClick={() => onSelect(date)}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
    </div>
  );
}
