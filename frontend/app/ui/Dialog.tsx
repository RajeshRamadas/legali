"use client";

import { useEffect, useRef, type ReactNode, type RefObject } from "react";

export default function Dialog({ open, onClose, label, labelledBy, returnFocusRef, className = "", children }: {
  open: boolean;
  onClose: () => void;
  label?: string;
  labelledBy?: string;
  returnFocusRef?: RefObject<HTMLElement | null>;
  className?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const trigger = returnFocusRef?.current ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    const overflow = document.body.style.overflow;
    dialog.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = overflow;
      if (trigger?.isConnected && trigger.getClientRects().length) trigger.focus({ preventScroll: true });
    };
  }, [open, returnFocusRef]);
  return <dialog ref={ref} className={`hx-dialog ${className}`} aria-label={label} aria-labelledby={labelledBy}
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onClose={(event) => { if (!event.currentTarget.open) onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
    onKeyDown={(event) => {
      if (event.key !== "Tab" || event.defaultPrevented) return;
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
        'a[href],button,input,select,textarea,summary,[tabindex]',
      )).filter(node => node.tabIndex >= 0 && !node.matches(':disabled,[inert],[aria-hidden="true"]') && node.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }}>
    {children}
  </dialog>;
}
