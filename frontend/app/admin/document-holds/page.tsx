"use client";
import Link from "next/link";
import {useEffect,useRef,useState} from "react";
import MainContent from "../../ui/MainContent";
import {useStaff} from "../AdminShell";
import {adminFetch,formatDate} from "../api";
import "../services/services.css";
import "../activity/activity.css";

type Filters={status:string;reason:string;q:string};
type Queue={items:{ticket_number:string;held:boolean;reason:string;changed_at:string;revision:number}[];total:number;active_count:number;page:number;page_size:number;checked_at:string};
const blank:Filters={status:"active",reason:"all",q:""};
const reasons:Record<string,string>={privacy_review:"Privacy review",legal_obligation:"Legal obligation review",manual_review:"Manual records review"};
const endpoint=(filters:Filters,page=1)=>`/admin/document-holds?${new URLSearchParams({...filters,page:String(page)})}`;

export default function DocumentHolds(){
  const {user,onError}=useStaff();const [draft,setDraft]=useState(blank),[applied,setApplied]=useState(blank),[data,setData]=useState<Queue|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const guard=useRef(false),failure=useRef<HTMLDivElement>(null),feedback=useRef<HTMLParagraphElement>(null);
  useEffect(()=>{if(user.role!=="admin")return;let alive=true;guard.current=true;setBusy(true);adminFetch<Queue>(endpoint(blank),{cache:"no-store"}).then(value=>{if(alive)setData(value);}).catch(error=>{if(alive)setError(onError(error));}).finally(()=>{if(alive){setBusy(false);guard.current=false;}});return()=>{alive=false;};},[user.role,onError]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  if(user.role!=="admin")return <MainContent><h1>Administrator access required</h1><p>Only administrators can review preservation holds across cases.</p></MainContent>;
  async function load(filters:Filters,page=1){if(guard.current)return;guard.current=true;setBusy(true);setError("");setNotice("");const normalized={...filters,q:filters.q.trim()};try{const value=await adminFetch<Queue>(endpoint(normalized,page),{cache:"no-store"});setData(value);setApplied(normalized);setNotice(`Preservation queue refreshed. Page ${value.page}, ${value.items.length} decisions shown.`);}catch(error){setError(onError(error));}finally{guard.current=false;setBusy(false);}}
  return <MainContent className="service-availability activity-page"><header><div className="eyebrow">Administrator workspace</div><h1>Document preservation holds</h1><p>Review file-preservation decisions and open a case to place or release a hold. A hold blocks file deletion and replacement through the application.</p></header>
    <section className="service-availability-card"><h2>Find preservation decisions</h2><form aria-label="Preservation filters" onSubmit={event=>{event.preventDefault();load(draft);}}><fieldset disabled={busy}><div className="activity-filters">
      <label>Hold status<select value={draft.status} onChange={event=>setDraft({...draft,status:event.target.value})}><option value="active">Active holds</option><option value="released">Released holds</option><option value="all">All retained decisions</option></select></label>
      <label>Review reason<select value={draft.reason} onChange={event=>setDraft({...draft,reason:event.target.value})}><option value="all">All reasons</option>{Object.entries(reasons).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      <label>Ticket number<input maxLength={40} value={draft.q} onChange={event=>setDraft({...draft,q:event.target.value})}/></label>
    </div><div className="activity-actions"><button className="btn">Apply preservation filters</button><button type="button" className="btn light" onClick={()=>{setDraft(blank);load(blank);}}>Clear preservation filters</button><button type="button" className="btn light" onClick={()=>load(applied,data?.page??1)}>Refresh preservation queue</button></div></fieldset></form>{JSON.stringify(draft)!==JSON.stringify(applied)&&<p>Filter edits have not been applied. Refresh and paging keep your edits.</p>}</section>
    {busy&&<p role="status">Loading preservation decisions…</p>}{error&&<div role="alert" tabIndex={-1} ref={failure}><p>Could not load preservation decisions. {error}</p><p>{data?"The last successful snapshot is shown and may be out of date. Your filter edits are kept.":"Use Refresh preservation queue to retry."}</p></div>}{notice&&<p role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {data&&<section className="service-availability-card" aria-label="Preservation decisions"><h2>Recorded preservation decisions</h2><p>{data.active_count} active holds across all cases · {data.total} matching decisions</p><p>Showing: {applied.status} · {applied.reason==="all"?"All reasons":reasons[applied.reason]}{applied.q?` · Ticket contains ${applied.q}`:""}. Checked {formatDate(data.checked_at)}.</p>
      {!data.items.length?<p>No preservation decisions match these filters.</p>:<ol className="activity-entries">{data.items.map(item=><li key={item.ticket_number}><article><h3><Link href={`/admin/tickets/${encodeURIComponent(item.ticket_number)}#documents`}>{item.ticket_number}</Link></h3><p>{item.held?"Hold active":"Hold released"} · {reasons[item.reason]} · {formatDate(item.changed_at)}</p><p>Private review notes are available to administrators in the case.</p></article></li>)}</ol>}
      <nav aria-label="Preservation queue pages"><button className="btn light" disabled={busy||data.page<=1} onClick={()=>load(applied,data.page-1)}>Previous decisions</button><span>Page {data.page}</span><button className="btn light" disabled={busy||data.page>=10000||data.page*data.page_size>=data.total} onClick={()=>load(applied,data.page+1)}>Next decisions</button></nav>
    </section>}<p>Uploads, authorized downloads, security scanning and case review can continue. Retention periods, deletion approval, backups and storage-provider retention controls require their own reviewed procedures.</p>
  </MainContent>;
}
