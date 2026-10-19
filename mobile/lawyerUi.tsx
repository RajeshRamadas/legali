import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import type { LawyerCard, LawyerSlot, SlotDay } from "@homexo/shared";
import { api, colors } from "./theme";

export const gold = "#d6ad66";
export const forest = "#123b35";

export function Avatar({ initials, size = 56 }: { initials: string; size?: number }) {
  return (
    <View style={[ui.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      <Text style={[ui.avatarText, { fontSize: size * 0.36 }]}>{initials}</Text>
    </View>
  );
}

export function Rating({ lawyer }: { lawyer: Pick<LawyerCard, "rating" | "review_count"> }) {
  if (lawyer.rating === null) return <Text style={ui.muted}>New on Homexo</Text>;
  return (
    <View style={ui.row}>
      <Text style={ui.star}>★ {lawyer.rating.toFixed(1)}</Text>
      <Text style={ui.muted}>{lawyer.review_count} review{lawyer.review_count === 1 ? "" : "s"}</Text>
    </View>
  );
}

export function Tags({ items }: { items: string[] }) {
  return <View style={ui.tags}>{items.map((t) => <Text key={t} style={ui.tagText}>{t}</Text>)}</View>;
}

// Morning, afternoon and evening by the hour shown on the slot (the lawyer's time zone).
function part(slot: LawyerSlot): string {
  const [time, meridiem] = slot.label.split(" ");
  const hour = (Number(time.split(":")[0]) % 12) + (meridiem === "pm" ? 12 : 0);
  return hour < 12 ? "Morning" : hour < 17 ? "Afternoon" : "Evening";
}

export function SlotPicker({ slug, selected, onSelect, refreshKey = 0 }: {
  slug: string;
  selected: string | null;
  onSelect: (slot: LawyerSlot & { day: string }) => void;
  refreshKey?: number;
}) {
  const [days, setDays] = useState<SlotDay[] | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.lawyerSlots(slug, 7)
      .then((r) => {
        setDays(r.days);
        setIndex(Math.max(0, r.days.findIndex((d) => d.slots.length > 0)));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load times."));
  }, [slug, refreshKey]);

  if (error) return <Text style={ui.error}>{error}</Text>;
  if (!days) return <ActivityIndicator color={colors.green} />;
  const day = days[index];
  const groups = ["Morning", "Afternoon", "Evening"].map((name) => ({ name, slots: day.slots.filter((s) => part(s) === name) })).filter((g) => g.slots.length);

  return (
    <View style={{ gap: 10 }}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
        {days.map((d, i) => (
          <Pressable key={d.date} onPress={() => setIndex(i)} style={[ui.day, i === index && ui.dayOn]} accessibilityRole="tab" accessibilityState={{ selected: i === index }}>
            <Text style={[ui.dayLabel, i === index && { color: colors.white }]}>{d.label}</Text>
            <Text style={[ui.daySlots, i === index && { color: "#c9ddd4" }, !d.slots.length && { color: colors.muted }]}>{d.slots.length ? `${d.slots.length} slots` : "No slots"}</Text>
          </Pressable>
        ))}
      </ScrollView>
      {groups.length === 0 ? <Text style={ui.muted}>No open times this day. Try another day.</Text> : groups.map((g) => (
        <View key={g.name} style={{ gap: 6 }}>
          <Text style={ui.groupLabel}>{g.name.toUpperCase()}</Text>
          <View style={ui.slots}>
            {g.slots.map((s) => (
              <Pressable key={s.starts_at} onPress={() => onSelect({ ...s, day: day.label })} style={[ui.slot, selected === s.starts_at && ui.slotOn]} accessibilityState={{ selected: selected === s.starts_at }}>
                <Text style={[ui.slotText, selected === s.starts_at && { color: colors.white }]}>{s.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ))}
    </View>
  );
}

export const ui = StyleSheet.create({
  avatar: { backgroundColor: forest, alignItems: "center", justifyContent: "center" },
  avatarText: { color: gold, fontWeight: "600", fontFamily: Platform.select({ ios: "Georgia", default: "serif" }) },
  row: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" },
  star: { backgroundColor: "#24734d", color: colors.white, fontSize: 11, fontWeight: "800", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 5, overflow: "hidden" },
  muted: { fontSize: 12, color: colors.muted },
  error: { fontSize: 13, color: colors.danger },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 5 },
  tagText: { fontSize: 10, fontWeight: "800", color: colors.green, backgroundColor: "#eef7f2", paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5, overflow: "hidden" },
  day: { minWidth: 84, alignItems: "center", borderWidth: 1, borderColor: "#d3e0d8", backgroundColor: colors.white, borderRadius: 10, paddingVertical: 8, paddingHorizontal: 10 },
  dayOn: { backgroundColor: forest, borderColor: forest },
  dayLabel: { fontSize: 13, fontWeight: "800", color: forest },
  daySlots: { fontSize: 10, color: "#24734d", marginTop: 2 },
  groupLabel: { fontSize: 10, fontWeight: "800", letterSpacing: 0.8, color: colors.muted },
  slots: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  slot: { width: "23%", minWidth: 76, borderWidth: 1, borderColor: "#b9d1c3", borderRadius: 8, paddingVertical: 9, alignItems: "center", backgroundColor: colors.white },
  slotOn: { backgroundColor: colors.green, borderColor: colors.green },
  slotText: { fontSize: 12, fontWeight: "800", color: colors.green },
});
