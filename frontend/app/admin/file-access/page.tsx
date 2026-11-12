"use client";
import {useEffect,useRef,useState} from "react";
import Link from "next/link";
import MainContent from "../../ui/MainContent";
import {useStaff} from "../AdminShell";
import {adminFetch} from "../api";
import "../services/services.css";
import "../activity/activity.css";
import "./file-access.css";

type Filters={reader:string;kind:string;ticket_number:string;from_date:string;to_date:string};
type Entry={id:string;at:string;reader:"customer"|"staff";actor:string;kind:"document"|"preliminary_report";ticket_number:string|null;case_reference:string|null;file_reference:string|null};
type History={items:Entry[];next_cursor:string|null;checked_at:string};
const blank:Filters={reader:"all",kind:"all",ticket_number:"",from_date:"",to_date:""};
const normalize=(value:Filters)=>({...value,ticket_number:value.ticket_number.trim().toUpperCase()});
const when=(value:string)=>new Date(value).toLocaleString("en-IN",{timeZone:"Asia/Kolkata",dateStyle:"medium",timeStyle:"short"});
function endpoint(filters:Filters,cursor?:string){const query=new URLSearchParams();for(const [key,value] of Object.entries(filters))if(value.trim())query.set(key,value.trim());if(cursor)query.set("cursor",cursor);return `/admin/file-access?${query}`;}

export default function FileAccessHistory(){
  const {user,onError}=useStaff();
  const [draft,setDraft]=useState<Filters>(blank),[applied,setApplied]=useState<Filters>(blank);
  const [pages,setPages]=useState<History[]>([]),[index,setIndex]=useState(0);
  const [busy,setBusy]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const guard=useRef(false),feedback=useRef<HTMLParagraphElement>(null),failure=useRef<HTMLDivElement>(null);
  useEffect(()=>{if(user.role!=="admin")return;let alive=true;guard.current=true;setBusy(true);
    adminFetch<History>(endpoint(blank),{cache:"no-store"}).then(result=>{if(alive){setPages([result]);setIndex(0);setApplied(blank);setError("");}})
      .catch(error=>{if(alive)setError(onError(error));}).finally(()=>{if(alive){guard.current=false;setBusy(false);}});
    return()=>{alive=false;};},[user.role,onError]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  if(user.role!=="admin")return <MainContent><h1>Administrator access required</h1><p>Only administrators can review file access history.</p></MainContent>;
  const current=pages[index],changed=JSON.stringify(normalize(draft))!==JSON.stringify(applied);
  const summary=[applied.reader==="all"?"All readers":applied.reader==="staff"?"Staff":"Customers",applied.kind==="all"?"All file types":applied.kind==="document"?"Stored case files":"Preliminary reports",applied.ticket_number?`Case ${applied.ticket_number}`:"All cases",applied.from_date?`From ${applied.from_date}`:"",applied.to_date?`Through ${applied.to_date}`:""].filter(Boolean).join(" · ");
  async function load(filters:Filters,older=false){
    if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");
    const normalized=normalize(filters);
    try{const result=await adminFetch<History>(endpoint(normalized,older?current?.next_cursor??undefined:undefined),{cache:"no-store"});
      if(older){setPages(values=>[...values,result]);setIndex(index+1);}else{setPages([result]);setIndex(0);setApplied(normalized);}
      setNotice(`${older?`Page ${index+2} loaded`:"File access history refreshed"}. ${result.items.length} recorded ${result.items.length===1?"entry":"entries"} shown.`);
    }catch(error){setError(onError(error));}finally{guard.current=false;setBusy(false);}
  }
  function navigate(next:number){setIndex(next);setError("");setNotice(`Page ${next+1} loaded. ${pages[next].items.length} recorded entries shown.`);}
  return <MainContent className="service-availability activity-page file-access-page">
    <header><div className="eyebrow">Administrator workspace</div><h1>File access history</h1><p>Review who was authorized to request private case files. An entry confirms permission checks, not that a download finished or the person read the file.</p></header>
    <section className="service-availability-card"><h2>Find authorized file requests</h2><form aria-label="File access filters" onSubmit={event=>{event.preventDefault();load(draft);}}><fieldset disabled={busy}><div className="activity-filters">
      <label>Reader<select value={draft.reader} onChange={event=>setDraft({...draft,reader:event.target.value})}><option value="all">All readers</option><option value="customer">Customers</option><option value="staff">Staff</option></select></label>
      <label>File type<select value={draft.kind} onChange={event=>setDraft({...draft,kind:event.target.value})}><option value="all">All file types</option><option value="document">Stored case files</option><option value="preliminary_report">Preliminary reports</option></select></label>
      <label>Case ticket number<input maxLength={60} pattern="[A-Za-z0-9 -]*" value={draft.ticket_number} onChange={event=>setDraft({...draft,ticket_number:event.target.value})} placeholder="Exact ticket number" /></label>
      <label>From date<input type="date" value={draft.from_date} onChange={event=>setDraft({...draft,from_date:event.target.value})}/></label>
      <label>To date<input type="date" min={draft.from_date||undefined} value={draft.to_date} onChange={event=>setDraft({...draft,to_date:event.target.value})}/></label>
    </div><p className="activity-hint">Dates use India Standard Time. Staff names are current display names. Customer identity and file contents are kept out of this view.</p><div className="activity-actions"><button className="btn">Apply file access filters</button><button type="button" className="btn light" onClick={()=>{setDraft(blank);load(blank);}}>Clear file access filters</button><button type="button" className="btn light" onClick={()=>load(applied)}>Refresh file access history</button></div></fieldset></form>{changed&&<p>Filter edits have not been applied. Refresh keeps your filter edits.</p>}</section>
    {busy&&<p role="status">Loading file access history…</p>}{error&&<div role="alert" tabIndex={-1} ref={failure}><p>Could not load file access history. {error}</p><p>{current?"The last successful page is still shown and may be out of date. Your filter edits are kept.":"Use Refresh file access history to try again. Your filter edits are kept."}</p></div>}{notice&&<p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {current&&<section className="service-availability-card" aria-label="Authorized file requests"><h2>Authorized file requests</h2><p className="activity-applied">Showing: {summary}</p><p>Loaded <time dateTime={current.checked_at}>{when(current.checked_at)}</time> IST · Page {index+1}</p>
      {!current.items.length?<p>No recorded file access matches these filters.</p>:<ol className="activity-entries">{current.items.map(item=><li key={item.id}><article aria-label={`${item.actor}: ${item.kind==="document"?"stored case file":"preliminary report"}`}><div className="activity-entry-head"><h3>{item.kind==="document"?"Stored case file":"Preliminary report"} access authorized</h3><span>{item.reader==="customer"?"Customer":"Staff"}</span></div><p>{item.actor} · <time dateTime={item.at}>{when(item.at)}</time> IST</p>
        {item.ticket_number?<Link className="text-link" href={`/admin/tickets/${encodeURIComponent(item.ticket_number)}`}>Open case {item.ticket_number}</Link>:<p>Case no longer available</p>}
        <details><summary>Entry references</summary><dl><div><dt>Entry reference</dt><dd>{item.id}</dd></div>{item.case_reference&&<div><dt>Case reference</dt><dd>{item.case_reference}</dd></div>}{item.file_reference&&<div><dt>File reference</dt><dd>{item.file_reference}</dd></div>}</dl></details>
      </article></li>)}</ol>}
      <nav aria-label="File access history pages"><button className="btn light" disabled={busy||index===0} onClick={()=>navigate(index-1)}>Newer file access</button><span>Page {index+1}</span><button className="btn light" disabled={busy||(!pages[index+1]&&!current.next_cursor)} onClick={()=>pages[index+1]?navigate(index+1):load(applied,true)}>Older file access</button></nav>
    </section>}
    <p>Only retained records captured by this feature appear; earlier access is unavailable. A permitted request may fail later. Repeated previews or range requests may create multiple entries.</p>
  </MainContent>;
}
