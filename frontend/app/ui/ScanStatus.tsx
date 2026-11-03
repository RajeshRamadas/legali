export default function ScanStatus({ status }: { status: "pending" | "clean" | "infected" | "failed" }) {
  const labels = { clean: "Security scan passed", pending: "Quarantined · awaiting security scan", failed: "Quarantined · security scan unavailable, ask the case team to retry", infected: "Blocked · a threat was detected; upload a safe replacement" };
  return <small className={`hx-security-status ${status}`} role={status === "clean" ? undefined : "status"}>{labels[status]}</small>;
}
