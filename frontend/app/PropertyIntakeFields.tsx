"use client";
import type { PropertyIntake } from "@homexo/shared";

export const EMPTY_INTAKE: PropertyIntake = { state: "Unknown", transaction: "unknown", seller_capacity: "unknown", development: "unknown", granted_land: "unknown", survey_number: "", property_id_or_pid: "", village: "", taluk: "", district: "" };
const choices = {
  state: { label: "Property state", options: [["Unknown", "Choose state"], ["Karnataka", "Karnataka"], ["Other", "Another state · specialist review"]] },
  transaction: { label: "Transaction", options: [["unknown", "Not sure yet"], ["purchase", "Purchase"], ["inheritance", "Inheritance"], ["gift", "Gift"], ["partition", "Partition"], ["other", "Other"]] },
  seller_capacity: { label: "Seller / transferor acts as", options: [["unknown", "Not sure yet"], ["owner", "Owner"], ["power_of_attorney", "Power of attorney holder"], ["legal_heir", "Legal heir"], ["company", "Company"]] },
  development: { label: "Property transaction stage", options: [["unknown", "Not sure yet"], ["new", "New development"], ["resale", "Resale"], ["land", "Land"]] },
  granted_land: { label: "Originally government-granted land?", options: [["unknown", "Unknown · needs investigation"], ["yes", "Yes"], ["no", "No, to my knowledge"]] },
};
export default function PropertyIntakeFields({ value, onChange, identifiers = false }: { value: PropertyIntake; onChange: (value: PropertyIntake) => void; identifiers?: boolean }) {
  return <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%, 210px),1fr))", gap: 12 }}>
    {(Object.keys(choices) as (keyof typeof choices)[]).map(key => <label key={key} className="field" style={{ display: "grid", gap: 5 }}><span>{choices[key].label}</span><select aria-label={choices[key].label} style={{ width: "100%", minWidth: 0, padding: 10 }} value={value[key]} onChange={e => onChange({ ...value, [key]: e.target.value })}>{choices[key].options.map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>)}
    {identifiers && ([ ["survey_number", "Survey number"], ["property_id_or_pid", "Property ID / PID"], ["village", "Village"], ["taluk", "Taluk"], ["district", "District"] ] as const).map(([key, label]) => <label className="field" key={key} style={{ display: "grid", gap: 5 }}><span>{label} (if known)</span><input style={{ minWidth: 0, width: "100%", padding: 10 }} maxLength={key === "survey_number" || key === "property_id_or_pid" ? 60 : 100} value={value[key]} onChange={e => onChange({ ...value, [key]: e.target.value })} /></label>)}
  </div>;
}
