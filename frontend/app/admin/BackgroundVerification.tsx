"use client";
import { useEffect, useRef, useState } from "react";
import { useStaff } from "./AdminShell";
import { adminFetch, formatDate } from "./api";
import VerificationUsageSummary, { type UsageSummary } from "./VerificationUsageSummary";

type Job = { id:string; status:string; phase:string; created_at:string; state:string; use_llm:boolean; run_id:string|null; message:string|null; can_cancel:boolean; usage?:UsageSummary };
type Request = { state:string; use_llm:boolean; consent_to_external_processing:boolean };
const active = (job:Job) => job.status === "queued" || job.status === "running";
const labels:Record<string,string> = { queued:"Queued · waiting for a worker", running:"Analysis in progress", completed:"Analysis saved", failed:"Analysis failed", cancelled:"Cancelled", stale:"Evidence changed", interrupted:"Worker interrupted" };
const phases:Record<string,string> = { queued:"Waiting", extracting:"Reading documents", analysing:"Analysing evidence", finalizing:"Checking and saving", finished:"Finished" };

export default function BackgroundVerification({ ticketNumber, request, configurationRevision, disabled, refreshKey, onCompleted, onReview }: {
  ticketNumber:string; request:Request; configurationRevision:string; disabled:boolean; refreshKey:string;
  onCompleted:()=>Promise<void>; onReview:()=>void;
}) {
  const { onError } = useStaff();
  const base=`/admin/tickets/${encodeURIComponent(ticketNumber)}/verification/jobs`;
  const [jobs,setJobs]=useState<Job[]>([]), [loading,setLoading]=useState(true), [busy,setBusy]=useState(false), [error,setError]=useState(""), [notice,setNotice]=useState("");
  const saved = useRef(new Set<string>()), latest=useRef<Job[]>([]), mounted=useRef(false), guard=useRef(false);
  const submission=useRef<{signature:string;key:string}|null>(null), refresh=useRef<()=>Promise<void>>(async()=>{}), completed=useRef(onCompleted);
  const feedback=useRef<HTMLParagraphElement>(null), failure=useRef<HTMLParagraphElement>(null);
  completed.current=onCompleted;
  useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);
  useEffect(()=>{
    let alive=true;mounted.current=true;setLoading(true);
    let inFlight=false;
    async function load(){
      if(inFlight)return;inFlight=true;
      try{
        const result=await adminFetch<{items:Job[]}>(base,{cache:"no-store"});
        if(!alive)return;
        latest.current=result.items;setJobs(result.items);setError("");
        const unseen=result.items.filter(job=>job.status==="completed"&&job.run_id&&!saved.current.has(job.run_id));
        if(unseen.length){await completed.current();if(alive)unseen.forEach(job=>saved.current.add(job.run_id!));}
      }catch(error){if(alive)setError(onError(error));}
      finally{inFlight=false;if(alive)setLoading(false);}
    }
    refresh.current=load;load();
    const timer=setInterval(()=>{if(!document.hidden&&latest.current.some(active))load();},5000);
    const visible=()=>{if(!document.hidden)load();};document.addEventListener("visibilitychange",visible);
    return()=>{alive=false;mounted.current=false;clearInterval(timer);document.removeEventListener("visibilitychange",visible);};
  },[base,refreshKey,onError]);
  async function queue(){
    if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");
    const body={...request,state:request.state.trim(),configuration_revision:configurationRevision};const signature=JSON.stringify(body);
    if(submission.current?.signature!==signature)submission.current={signature,key:crypto.randomUUID()};
    try{
      const job=await adminFetch<Job>(base,{method:"POST",body:JSON.stringify({...body,submission_key:submission.current.key})});
      if(mounted.current){submission.current=null;latest.current=[job,...latest.current.filter(row=>row.id!==job.id)];setJobs(latest.current);setNotice("Analysis queued. You can leave this case and return to its saved status.");await refresh.current();}
    }catch(error){if(mounted.current)setError(onError(error));}
    finally{guard.current=false;if(mounted.current)setBusy(false);}
  }
  async function cancel(job:Job){
    if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");
    try{await adminFetch(`${base}/${job.id}/cancel`,{method:"POST"});if(mounted.current){setNotice("Analysis cancelled. A provider request already in progress cannot be recalled.");await refresh.current();}}
    catch(error){if(mounted.current)setError(onError(error));}
    finally{guard.current=false;if(mounted.current)setBusy(false);}
  }
  return <section className="verification-background" aria-label="Background analysis">
    <button type="button" className="btn btn-primary" onClick={queue} disabled={disabled||busy||loading||jobs.some(active)||!!error}>{busy?"Saving analysis request…":"Queue verification"}</button>
    <p>Progress is saved when you leave. A dedicated background worker processes the queue. Changes to evidence or processing settings can invalidate a request.</p>
    <button type="button" className="btn btn-secondary" disabled={busy||loading} onClick={()=>refresh.current()}>Refresh analysis jobs</button>
    {loading&&<p role="status">Loading saved analysis jobs…</p>}
    {error&&<p className="admin-error" role="alert" tabIndex={-1} ref={failure}>{error} The last loaded jobs may be out of date. Your analysis settings are kept; refresh before trying again.</p>}
    {notice&&<p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {!loading&&!jobs.length&&!error&&<p>No saved background analysis requests.</p>}
    {!!jobs.length&&<details open><summary>Recent analysis jobs (latest 20)</summary><ol>{jobs.map(job=><li key={job.id}>
      <h3>{labels[job.status]??"Analysis status unavailable"}</h3><p>{job.state} · {job.use_llm?"LLM analysis":"Local extraction"} · {formatDate(job.created_at)}</p><p>{phases[job.phase]??"Status unavailable"}</p>
      {job.usage&&<VerificationUsageSummary usage={job.usage}/>}
      {job.message&&<p>{job.message}</p>}{job.can_cancel&&<button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>cancel(job)}>Cancel analysis</button>}
      {["failed","interrupted","stale","cancelled"].includes(job.status)&&<button type="button" className="btn btn-secondary" disabled={busy||jobs.some(active)} onClick={()=>{onReview();setNotice("Review the current settings and confirm provider consent again before queuing a fresh analysis.");}}>Review a new analysis</button>}
    </li>)}</ol></details>}
  </section>;
}
