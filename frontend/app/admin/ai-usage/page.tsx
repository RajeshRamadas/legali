"use client";
import {useEffect,useRef,useState} from "react";
import MainContent from "../../ui/MainContent";
import {useStaff} from "../AdminShell";
import {adminFetch} from "../api";
import UsageSummaryView,{estimatedCost,type UsageSummary} from "../VerificationUsageSummary";
import "../services/services.css";
import "../activity/activity.css";
import "./usage.css";

type Filters={provider:string;step:string;status:string;days:string;job_id:string};
type Attempt={id:string;job_id:string;service_request_id:string;provider:string;model:string;step:string;status:string;started_at:string;finished_at:string|null;duration_ms:number|null;input_tokens:number|null;output_tokens:number|null;cache_tokens:number|null;usage_complete:boolean;estimated_usd:string|null;estimate_reason:string;rate_version:string|null;error_category:string|null};
type History={items:Attempt[];summary:UsageSummary;page:number;page_size:number;checked_at:string;from_at:string;pricing:{status:string;version:string|null;models:number}};
const blank:Filters={provider:"all",step:"all",status:"all",days:"30",job_id:""};
const when=(value:string)=>new Date(value).toLocaleString("en-IN",{timeZone:"Asia/Kolkata",dateStyle:"medium",timeStyle:"short"});
const outcomes:Record<string,string>={started:"Unfinished · billing unknown",succeeded:"Succeeded",failed:"Failed"};
const reasons:Record<string,string>={priced:"Configured rate estimate",attempt_unfinished:"Outcome and billing unknown",rates_not_configured:"Rates not configured",invalid_rate_configuration:"Rate configuration needs attention",model_not_priced:"No configured rate for this model",usage_unavailable:"Provider usage unavailable",cache_usage_unpriced:"Cache usage has no configured price"};
function endpoint(filters:Filters,page=1){const query=new URLSearchParams({...filters,page:String(page)});if(!filters.job_id)query.delete("job_id");return `/admin/verification-usage?${query}`;}

export default function VerificationUsagePage(){
  const {user,onError}=useStaff();
  const [draft,setDraft]=useState<Filters>(blank),[applied,setApplied]=useState<Filters>(blank);
  const [data,setData]=useState<History|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const guard=useRef(false),failure=useRef<HTMLDivElement>(null),feedback=useRef<HTMLParagraphElement>(null);
  useEffect(()=>{
    if(user.role!=="admin")return;
    let alive=true;guard.current=true;setBusy(true);
    adminFetch<History>(endpoint(blank),{cache:"no-store"}).then(value=>{if(alive){setData(value);setApplied(blank);setError("");}}).catch(error=>{if(alive)setError(onError(error));}).finally(()=>{if(alive){setBusy(false);guard.current=false;}});
    return()=>{alive=false;};
  },[user.role,onError]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);
  useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  if(user.role!=="admin")return <MainContent><h1>Administrator access required</h1><p>Only administrators can review provider usage across cases.</p></MainContent>;
  async function load(filters:Filters,page=1){
    if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");
    const normalized={...filters,job_id:filters.job_id.trim()};
    try{const value=await adminFetch<History>(endpoint(normalized,page),{cache:"no-store"});setData(value);setApplied(normalized);setNotice(`Usage refreshed. Page ${value.page}, ${value.items.length} attempts shown.`);}
    catch(error){setError(onError(error));}finally{guard.current=false;setBusy(false);}
  }
  const changed=JSON.stringify(draft)!==JSON.stringify(applied);
  return <MainContent className="service-availability activity-page usage-page">
    <header><div className="eyebrow">Administrator workspace</div><h1>Verification provider usage</h1><p>Review provider attempts, reported tokens, response times and estimated costs for background verification.</p></header>
    <p>Scope: background verification calls recorded after this feature was enabled. Synchronous analysis, upload checks, chat and historical calls are outside this view.</p>
    <section className="service-availability-card"><h2>Find provider attempts</h2>
      <form aria-label="Provider usage filters" onSubmit={event=>{event.preventDefault();load(draft);}}><fieldset disabled={busy}>
        <div className="activity-filters">
          <label>Provider<select value={draft.provider} onChange={event=>setDraft({...draft,provider:event.target.value})}><option value="all">All providers</option><option value="anthropic">Anthropic</option><option value="openai">OpenAI adapter</option></select></label>
          <label>Stage<select value={draft.step} onChange={event=>setDraft({...draft,step:event.target.value})}><option value="all">All stages</option><option value="extract">Extraction</option><option value="compare">Comparison</option></select></label>
          <label>Outcome<select value={draft.status} onChange={event=>setDraft({...draft,status:event.target.value})}><option value="all">All outcomes</option><option value="started">Unfinished</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option></select></label>
          <label>Window<select value={draft.days} onChange={event=>setDraft({...draft,days:event.target.value})}>{[1,7,30,90].map(days=><option key={days} value={days}>{days===1?"Today":`Last ${days} calendar days`}</option>)}</select></label>
        </div><details><summary>Find a background job</summary><label>Job reference<input value={draft.job_id} onChange={event=>setDraft({...draft,job_id:event.target.value})} maxLength={36} pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}" /></label></details>
        <p>Windows start at midnight in India Standard Time and end when refreshed.</p>
        <div className="activity-actions"><button className="btn">Apply usage filters</button><button type="button" className="btn light" onClick={()=>{setDraft(blank);load(blank);}}>Clear usage filters</button><button type="button" className="btn light" onClick={()=>load(applied,data?.page??1)}>Refresh usage</button></div>
      </fieldset></form>{changed&&<p>Filter edits have not been applied. Refresh keeps your filter edits.</p>}
    </section>
    {busy&&<p role="status">Loading provider usage…</p>}
    {error&&<div role="alert" tabIndex={-1} ref={failure}><p>Could not load provider usage. {error}</p><p>{data?"The last successful snapshot is still shown and may be out of date. Your filter edits are kept.":"Use Refresh usage to try again. Your filter edits are kept."}</p></div>}
    {notice&&<p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {data&&<>
      <section className="service-availability-card" aria-label="Usage totals"><h2>Recorded usage</h2>
        <p>Showing: {applied.provider==="all"?"All providers":applied.provider} · {applied.step==="all"?"All stages":applied.step} · {applied.status==="all"?"All outcomes":outcomes[applied.status]}{applied.job_id?` · Job ${applied.job_id}`:""}</p>
        <p>From {when(data.from_at)} IST through <time dateTime={data.checked_at}>{when(data.checked_at)}</time> IST. Totals cover all matching attempts.</p>
        <UsageSummaryView usage={data.summary}/>
        <p>Current pricing: {data.pricing.status==="configured"?`${data.pricing.models} configured model rates · ${data.pricing.version}`:data.pricing.status==="invalid"?"Configuration needs attention; new estimates are unavailable.":"Rates not configured; new estimates are unavailable."} Each estimate retains the rates used at the time of the attempt.</p>
      </section>
      <section className="service-availability-card" aria-label="Provider attempts"><h2>Provider attempts</h2><p>Page {data.page} · Most recent first</p>
        {!data.items.length?<p>No recorded provider attempts match these filters.</p>:<ol className="activity-entries">{data.items.map(item=><li key={item.id}><article aria-label={`${item.provider} ${item.step} attempt`}>
          <div className="activity-entry-head"><h3>{item.provider==="openai"?"OpenAI adapter":"Anthropic"} · {item.step==="extract"?"Extraction":"Comparison"}</h3><span>{outcomes[item.status]??"Outcome unavailable"}</span></div>
          <p>{item.model} · <time dateTime={item.started_at}>{when(item.started_at)}</time> IST</p>
          <dl className="usage-details"><div><dt>Reported tokens</dt><dd>{item.usage_complete?`${item.input_tokens?.toLocaleString("en-IN")} input · ${item.output_tokens?.toLocaleString("en-IN")} output · ${item.cache_tokens?.toLocaleString("en-IN")} cached`:"Unavailable"}</dd></div>
            <div><dt>Elapsed time</dt><dd>{item.duration_ms===null?"Unfinished":`${(item.duration_ms/1000).toLocaleString("en-IN",{maximumFractionDigits:2})} seconds`}</dd></div>
            <div><dt>Estimated cost</dt><dd>{estimatedCost(item.estimated_usd)} · {reasons[item.estimate_reason]??"Estimate unavailable"}</dd></div></dl>
          <details><summary>Attempt references and estimate detail</summary><dl>{[["Attempt reference",item.id],["Job reference",item.job_id],["Case reference",item.service_request_id],["Rate version",item.rate_version??"Unavailable"],["Exact estimate USD",item.estimated_usd??"Unavailable"],["Failure category",item.error_category??"None recorded"]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></details>
        </article></li>)}</ol>}
        <nav aria-label="Provider usage pages"><button className="btn light" disabled={busy||data.page<=1} onClick={()=>load(applied,data.page-1)}>Previous attempts</button><span>Page {data.page}</span><button className="btn light" disabled={busy||data.page>=10000||data.page*data.page_size>=data.summary.attempts} onClick={()=>load(applied,data.page+1)}>Next attempts</button></nav>
      </section>
    </>}
    <p>This view contains operational metadata, without document content. Provider billing can differ from these estimates. Unfinished, missing and cached usage may have charges that are absent from the known subtotal.</p>
  </MainContent>;
}
