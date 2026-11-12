"use client";
import {useEffect,useRef,useState} from "react";
import {adminFetch,formatDate} from "./api";
import {useStaff} from "./AdminShell";
import "../ui/views/admin-verification.css";

type Hold={held:boolean;revision:number;changed_at:string|null;can_manage:boolean;reason?:string|null;note?:string;history?:{id:string;held:boolean;at:string;actor:string;reason:string|null;note:string}[]};
const reasons:Record<string,string>={privacy_review:"Privacy review",legal_obligation:"Legal obligation review",manual_review:"Manual records review"};
export default function DocumentPreservation({ticketNumber,onHeld}:{ticketNumber:string;onHeld:(held:boolean)=>void}){
  const {onError}=useStaff();const [value,setValue]=useState<Hold|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const [reason,setReason]=useState(""),[note,setNote]=useState(""),[confirmed,setConfirmed]=useState(false);
  const guard=useRef(false),failure=useRef<HTMLParagraphElement>(null),feedback=useRef<HTMLParagraphElement>(null);
  const base=`/admin/tickets/${encodeURIComponent(ticketNumber)}/document-hold`;
  const currentBase=useRef(base);currentBase.current=base;
  useEffect(()=>{let alive=true;guard.current=true;setBusy(true);setValue(null);setReason("");setNote("");setConfirmed(false);setNotice("");setError("");onHeld(true);adminFetch<Hold>(base,{cache:"no-store"}).then(result=>{if(alive){setValue(result);onHeld(result.held);setError("");}}).catch(error=>{if(alive)setError(onError(error));}).finally(()=>{if(alive){setBusy(false);guard.current=false;}});return()=>{alive=false;};},[base,onHeld,onError]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  async function load(){if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");try{const result=await adminFetch<Hold>(base,{cache:"no-store"});if(currentBase.current!==base)return;setValue(result);onHeld(result.held);setConfirmed(false);setNotice("Preservation status refreshed. Your review note is kept; confirm the current decision again before saving.");}catch(error){if(currentBase.current===base)setError(onError(error));}finally{if(currentBase.current===base){setBusy(false);guard.current=false;}}}
  async function save(){if(guard.current||!value)return;guard.current=true;setBusy(true);setError("");setNotice("");try{const result=await adminFetch<Hold>(base,{method:"PUT",body:JSON.stringify({held:!value.held,revision:value.revision,reason,note:note.trim()})});if(currentBase.current!==base)return;setValue(result);onHeld(result.held);setConfirmed(false);setReason("");setNote("");setNotice(result.held?"Preservation hold saved. File deletion and replacement are blocked.":"Preservation hold released. Existing file access and deletion rules still apply.");}catch(error){if(currentBase.current===base)setError(onError(error));}finally{if(currentBase.current===base){setBusy(false);guard.current=false;}}}
  return <section className="document-preservation" aria-label="Document preservation"><h3>Document preservation</h3><p>Place a case hold to block deletion and replacement of stored files. Uploads, downloads permitted by file-security rules, and case review continue.</p>
    {busy&&<p role="status">Loading preservation status…</p>}{error&&<p role="alert" tabIndex={-1} ref={failure}>{error} Refresh the status before trying again. The last loaded status may be out of date; your note is kept.</p>}{notice&&<p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {value&&<><p>Current status: <strong>{value.held?"Preservation hold active":"No active preservation hold"}</strong>{value.changed_at?` · ${formatDate(value.changed_at)}`:""}</p>
      {value.can_manage?<><details><summary>Administrator decision and recent history</summary>{value.note&&<p className="preservation-note">{value.note}</p>}<ol>{value.history?.map(item=><li key={item.id}><p>{item.held?"Hold placed":"Hold released"} · {formatDate(item.at)} · {item.actor} · {item.reason?reasons[item.reason]:"Recorded review"}</p><p className="preservation-note">{item.note}</p></li>)}</ol></details>
        <form aria-label="Preservation decision" onSubmit={event=>{event.preventDefault();save();}}><fieldset disabled={busy||!!error}>
          <label>Review reason<select required value={reason} onChange={event=>setReason(event.target.value)}><option value="">Choose a reason</option>{Object.entries(reasons).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
          <label>Administrator review note<textarea required minLength={20} maxLength={2000} rows={3} value={note} onChange={event=>setNote(event.target.value)}/></label>
          <label className="preservation-confirm"><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/>{value.held?"I have reviewed the preservation requirements and confirm release of this case's file hold.":"I confirm that file deletion and replacement should be blocked for this case."}</label>
          <button className="btn btn-secondary" disabled={!reason||note.trim().length<20||!confirmed}>{value.held?"Release document hold":"Place document hold"}</button>
        </fieldset></form></>:<p>Administrators manage preservation decisions. Private review notes are restricted to administrators.</p>}
    </>}<button type="button" className="btn btn-secondary" disabled={busy} onClick={load}>Refresh preservation status</button>
  </section>;
}
