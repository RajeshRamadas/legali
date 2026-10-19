"use client";

import { useState } from "react";
import { FAQS } from "./content";

export default function Faq() {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="faq-list">
      {FAQS.map((item, i) => (
        <div className={`faq-item${open === i ? " open" : ""}`} key={item.q}>
          <button className="faq-q" aria-expanded={open === i} onClick={() => setOpen(open === i ? null : i)}>{item.q}<span>+</span></button>
          <div className="faq-a">{item.a}</div>
        </div>
      ))}
    </div>
  );
}
