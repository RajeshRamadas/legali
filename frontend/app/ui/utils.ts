export const IST = "Asia/Kolkata";
export const dateLabel = (value: Date | string = new Date()) =>
  new Intl.DateTimeFormat("en-IN", {
    timeZone: IST,
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(value));
export const timeLabel = (value: Date | string) =>
  new Intl.DateTimeFormat("en-IN", {
    timeZone: IST,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(value));
export const dayKey = (value: Date | string) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: IST,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
export function greeting(name: string, now = new Date()) {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: IST,
      hour: "2-digit",
      hourCycle: "h23",
    }).format(now),
  );
  return `${hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening"}, ${name.split(" ")[0] || "there"}`;
}
export function joinable(
  meeting: {
    status: string;
    starts_at: string;
    ends_at: string;
    meet_link: string | null;
  },
  now = Date.now(),
) {
  return (
    meeting.status === "scheduled" &&
    !!meeting.meet_link &&
    now >= new Date(meeting.starts_at).getTime() - 15 * 60000 &&
    now <= new Date(meeting.ends_at).getTime()
  );
}
export const initials = (name: string) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0])
    .join("")
    .toUpperCase();
export function maskedPhone(phone: string) {
  const digits = phone.replace(/\D/g, "");
  return digits.length > 6
    ? `+${digits.slice(0, 2)} ${digits.slice(2, 4)}•••• ${digits.slice(-4)}`
    : "Your account";
}
