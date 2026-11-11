"use client";
import {useEffect,useRef,useState} from "react";
import type {CaseAIProcessing} from "@homexo/shared";
import {api} from "../api";

const labels={not_allowed:"Not allowed",allowed:"Allowed for this processor",withdrawn:"Permission withdrawn",review_required:"Review the updated processor notice"};
export default function AIProcessingChoice({ticketNumber}:{ticketNumber:string}){
  const [value,setValue]=useState<CaseAIProcessing|null>(null),[confirmed,setConfirmed]=useState(false),[withdraw,setWithdraw]=useState(false),[busy,setBusy]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const guard=useRef(false),mounted=useRef(false),failure=useRef<HTMLParagraphElement>(null),feedback=useRef<HTMLParagraphElement>(null);
  useEffect(()=>{let alive=true;mounted.current=true;guard.current=true;setBusy(true);api.aiProcessing(ticketNumber).then(result=>{if(alive)setValue(result);}).catch(error=>{if(alive)setError(error instanceof Error?error.message:"Could not load the choice.");}).finally(()=>{if(alive){setBusy(false);guard.current=false;}});return()=>{alive=false;mounted.current=false;};},[ticketNumber]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  async function load(){if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");try{const result=await api.aiProcessing(ticketNumber);if(mounted.current){setValue(result);setConfirmed(false);setWithdraw(false);setNotice("AI processing choice refreshed. Review the current notice before changing it.");}}catch(error){if(mounted.current)setError(error instanceof Error?error.message:"Could not load the choice.");}finally{guard.current=false;if(mounted.current)setBusy(false);}}
  async function save(allowed:boolean){
    if(guard.current||!value)return;guard.current=true;setBusy(true);setError("");setNotice("");
    try{const result=await api.setAIProcessing(ticketNumber,{allowed,revision:value.revision,notice_version:value.disclosure.notice_version,processing_revision:value.disclosure.processing_revision??""});if(mounted.current){setValue(result);setConfirmed(false);setWithdraw(false);setNotice(allowed?"Permission saved for this case. Previous uploads are not automatically reprocessed.":"Permission withdrawn. Requests already admitted or in progress cannot be recalled.");}}
    catch(error){if(mounted.current)setError(error instanceof Error?error.message:"Could not save the choice.");}finally{guard.current=false;if(mounted.current)setBusy(false);}
  }
  return <section className="dc-card ai-processing-choice" aria-label="External AI processing">
    <h2>External AI processing</h2><p>You choose whether your case documents may be sent to an external AI processor. Uploading files and advocate review remain available.</p>
    {busy&&<p role="status">Loading AI processing choice…</p>}
    {error&&<p role="alert" tabIndex={-1} ref={failure}>{error} Refresh this choice before trying again. The last loaded information may be out of date; your confirmation is kept.</p>}
    {notice&&<p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {value&&<><p>Current choice: <strong>{labels[value.status]}</strong>.</p>
      {value.disclosure.configured?<><p>Processor: <strong>{value.disclosure.processor}</strong> · <a href={value.disclosure.privacy_url??undefined} target="_blank" rel="noopener noreferrer">Processor privacy policy</a></p><details><summary>Read what this permission covers</summary>{value.disclosure.paragraphs.map((text,index)=><p key={index}>{text}</p>)}</details></>:<p>Processor information is not available. You can withdraw an existing permission and continue working with your case team.</p>}
      {!value.allowed&&value.disclosure.configured&&<form onSubmit={event=>{event.preventDefault();save(true);}}><fieldset disabled={busy||!!error}><label><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/> I have read the notice and allow this processor to handle my case documents for AI checks and analysis.</label><button className="btn" disabled={!confirmed}>Allow external AI processing</button></fieldset></form>}
      {value.can_withdraw&&<form onSubmit={event=>{event.preventDefault();save(false);}}><fieldset disabled={busy||!!error}><label><input type="checkbox" checked={withdraw} onChange={event=>setWithdraw(event.target.checked)}/> Withdraw permission for future external AI document processing.</label><button className="btn light" disabled={!withdraw}>Withdraw AI permission</button></fieldset></form>}
    </>}
    <button type="button" className="btn light" disabled={busy} onClick={load}>Refresh AI choice</button>
  </section>;
}
