"use client";
import {useEffect,useState} from "react";
import type {CaseAIProcessing} from "@homexo/shared";
import {adminFetch} from "./api";

export default function AIProcessingStatus({ticketNumber,onAllowed}:{ticketNumber:string;onAllowed:(allowed:boolean)=>void}){
  const [value,setValue]=useState<CaseAIProcessing|null>(null),[error,setError]=useState(""),[refresh,setRefresh]=useState(0),[busy,setBusy]=useState(true);
  useEffect(()=>{let alive=true;setBusy(true);onAllowed(false);adminFetch<CaseAIProcessing>(`/admin/tickets/${encodeURIComponent(ticketNumber)}/ai-processing`,{cache:"no-store"}).then(result=>{if(alive){setValue(result);setError("");onAllowed(result.allowed);}}).catch(error=>{if(alive){setError(error instanceof Error?error.message:"Choice unavailable.");onAllowed(false);}}).finally(()=>{if(alive)setBusy(false);});return()=>{alive=false;};},[ticketNumber,onAllowed,refresh]);
  return <section aria-label="Customer AI permission"><h3>Customer AI permission</h3>{busy?<p role="status">Loading customer choice…</p>:error?<p role="alert">{error} Refresh the customer choice before using external AI.</p>:<p>{value?.allowed?"The customer allows external AI document processing for the current processor.":"Customer permission is required or needs review. Ask the customer to review External AI processing on their Documents page. Local extraction remains available."}</p>}<p>This permission is controlled by the verified customer. Staff confirmation is still required for each full-case AI submission.</p><button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>setRefresh(value=>value+1)}>Refresh customer AI permission</button></section>;
}
