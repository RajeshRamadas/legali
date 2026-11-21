import { useRef, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { getDocumentAsync, type DocumentPickerAsset } from "expo-document-picker";
import { type CustomerDocument, type JourneyCheck, type TicketStatus } from "@homexo/shared";
import { styles } from "./LawyersScreen";
import { ui } from "./lawyerUi";
import { api } from "./theme";

const mimeTypes: Record<string, string> = {
  pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
  webp: "image/webp", heic: "image/heic", doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};
const scanLabels: Record<CustomerDocument["scan_status"], string> = {
  pending: "Security scan pending", clean: "Security scan passed",
  infected: "Blocked by security scan", failed: "Security scan failed",
};

const checkLabels: Record<JourneyCheck["status"], string> = {
  passed: "Verified", in_review: "Being checked", waiting: "Waiting for documents", problem: "Needs attention",
};

function VerificationCheck({ check }: { check: JourneyCheck }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={{ gap: 4 }}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(!expanded)}>
        <Text style={styles.link}>{check.question}</Text>
        <Text style={ui.muted}>{checkLabels[check.status]}</Text>
      </Pressable>
      {expanded && (
        <View style={{ gap: 4 }}>
          <Text style={styles.body}>{check.detail}</Text>
          {check.total > 0 && check.key !== "opinion" && (
            <Text style={ui.muted}>{check.accepted} of {check.total} documents accepted</Text>
          )}
          {!!check.flags?.length && (
            <>
              <Text style={styles.label}>Flagged by the automatic upload check</Text>
              {check.flags.map((flag, index) => <Text key={index} style={ui.muted}>{flag}</Text>)}
            </>
          )}
        </View>
      )}
    </View>
  );
}

export function CaseDocuments({ ticket, contact, onUpdate }: {
  ticket: TicketStatus; contact: string; onUpdate: (next: TicketStatus) => void;
}) {
  const [selected, setSelected] = useState<{ asset: DocumentPickerAsset; tag: string; label: string; mime: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const locked = useRef(false);
  const checks = ticket.document_request?.journey?.checks ?? [];
  const open = ticket.can_upload && (!ticket.report || ticket.report.status === "issued");
  const items = ticket.report?.items ?? ticket.document_request?.items ?? [];

  async function choose(tag: string, label: string) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setMessage("");
    try {
      const result = await getDocumentAsync({ multiple: false, copyToCacheDirectory: true, base64: false });
      if (result.canceled) return;
      const asset = result.assets[0];
      const mime = mimeTypes[asset.name.split(".").pop()?.toLowerCase() ?? ""];
      if (!mime || !asset.name.includes(".")) {
        setMessage("Choose a PDF, Word document, JPG, PNG, WEBP or HEIC image.");
        return;
      }
      setSelected({ asset, tag, label, mime });
    } catch {
      setMessage("Could not open the file picker. Please try again.");
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  async function upload() {
    if (!selected || locked.current || !open) return;
    locked.current = true;
    setBusy(true);
    setMessage("");
    const { asset, tag, mime } = selected;
    try {
      const file = asset.file ?? { uri: asset.uri, name: asset.name, type: mime };
      const next = await api.uploadDocument({ ticket_number: ticket.ticket_number, contact }, file, { tag });
      onUpdate(next);
      setSelected(null);
      setMessage("File uploaded.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload could not be confirmed. Check the file list before retrying.");
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  return (
    <View style={{ gap: 8 }}>
      <Text style={styles.label}>Case documents</Text>
      {ticket.documents.map(doc => (
        <Text key={doc.id} style={ui.muted}>{doc.filename} · {scanLabels[doc.scan_status]}</Text>
      ))}
      {checks.length > 0 && (
        <>
          <Text accessibilityRole="header" style={styles.label}>Verification checks</Text>
          {checks.map(check => <VerificationCheck key={check.key} check={check} />)}
        </>
      )}
      {items.length > 0 && <Text accessibilityRole="header" style={styles.label}>Document checklist</Text>}
      {items.map(item => (
        <View key={item.id} style={{ gap: 4 }}>
          <Text style={styles.label}>{item.label} · {item.status_label}</Text>
          {item.guidance ? <Text style={ui.muted}>{item.guidance}</Text> : null}
          {item.fetch_by === "homexo" && (
            <Text style={ui.muted}>Handled by the case team{item.source ? ` · ${item.source.name}` : ""}</Text>
          )}
          {item.status === "rejected" && item.note ? (
            <Text style={styles.body}>Advocate feedback: {item.note}</Text>
          ) : null}
          {open && !selected && item.fetch_by === "customer" && item.status !== "verified" && item.status !== "waived" && (
            <Pressable accessibilityRole="button" accessibilityLabel={`Upload file for ${item.label}`} disabled={busy} onPress={() => choose(item.tag, item.label)}>
              <Text style={styles.link}>{item.status === "rejected" ? "Upload replacement" : "Choose file"}</Text>
            </Pressable>
          )}
        </View>
      ))}
      {open && (selected ? (
        <>
          <Text style={styles.body}>{selected.label} · {selected.asset.name}</Text>
          <Pressable accessibilityRole="button" disabled={busy} onPress={upload} style={styles.button}>
            <Text style={styles.buttonText}>{busy ? "Uploading…" : "Upload to case"}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => { setSelected(null); setMessage(""); }}>
            <Text style={styles.link}>Cancel</Text>
          </Pressable>
        </>
      ) : (
        <>
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => choose("", "Other document")}>
            <Text style={styles.link}>Upload another document</Text>
          </Pressable>
        </>
      ))}
      {message ? <Text accessibilityLiveRegion="polite" style={styles.body}>{message}</Text> : null}
    </View>
  );
}
