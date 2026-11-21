import { Text, View } from "react-native";
import { formatFee, type CaseProgress } from "@homexo/shared";
import { styles } from "./LawyersScreen";
import { ui } from "./lawyerUi";

const caseDate = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric",
});

export function CaseProgressPanel({ progress }: { progress: CaseProgress }) {
  const { closed, deadline_paused, due_at, fee, milestones, next_step } = progress;
  const amount = fee?.status === "paid" ? fee.paid : fee?.quote;
  return (
    <View style={{ gap: 6 }}>
      <Text accessibilityRole="header" style={styles.cardTitle}>Case progress</Text>
      {milestones.map(step => {
        const current = step.current && !closed;
        const state = step.done ? "Complete" : current ? "Current" : closed ? "Incomplete" : "Upcoming";
        return (
          <Text key={step.key} style={current ? styles.label : ui.muted}>
            {step.label} · {state}
          </Text>
        );
      })}
      {!closed && next_step && <Text style={styles.body}>Next step: {next_step}</Text>}
      {!closed && deadline_paused && <Text style={styles.body}>On hold · target date paused</Text>}
      {!closed && !deadline_paused && due_at && (
        <Text style={styles.body}>Target date: {caseDate.format(new Date(due_at))}</Text>
      )}
      {fee && (
        <Text style={styles.body}>
          {fee.status_label}{fee.status !== "waived" && amount != null ? " · " + formatFee(amount) : ""}
        </Text>
      )}
      {closed && (
        <Text style={styles.body}>
          Case closed{closed.outcome_label ? " · " + closed.outcome_label : ""}
          {closed.at ? " · " + caseDate.format(new Date(closed.at)) : ""}
        </Text>
      )}
    </View>
  );
}
