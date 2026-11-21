import { useRef, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { getDocumentAsync, type DocumentPickerAsset } from "expo-document-picker";
import { type CustomerDocument, type TicketStatus } from "@homexo/shared";
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

export function CaseDocuments({ ticket, contact, onUpdate }: {
  ticket: TicketStatus; contact: string; onUpdate: (next: TicketStatus) => void;
}) {
  const [selected, setSelected] = useState<{ asset: DocumentPickerAsset; tag: string; label: string; mime: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const locked = useRef(false);
  const open = ticket.can_upload && (!ticket.report || ticket.report.status === "issued");
  const items = (ticket.report?.items ?? ticket.document_request?.items ?? []).filter(
    item => item.fetch_by === "customer" && item.status !== "verified" && item.status !== "waived",
  );

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
          <Text style={ui.muted}>Choose the document you want to upload.</Text>
          {items.map(item => (
            <Pressable key={item.tag} accessibilityRole="button" disabled={busy} onPress={() => choose(item.tag, item.label)}>
              <Text style={styles.link}>{item.label}</Text>
            </Pressable>
          ))}
          <Pressable accessibilityRole="button" disabled={busy} onPress={() => choose("", "Other document")}>
            <Text style={styles.link}>Other document</Text>
          </Pressable>
        </>
      ))}
      {message ? <Text accessibilityLiveRegion="polite" style={styles.body}>{message}</Text> : null}
    </View>
  );
}
