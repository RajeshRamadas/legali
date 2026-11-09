"use client";
export default function FormTrap({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <div className="hx-form-trap" aria-hidden="true"><label>Website<input type="text" name="website_url" autoComplete="off" tabIndex={-1} value={value} onChange={event => onChange(event.target.value)} /></label></div>;
}
