"use client";
import {useEffect,useRef,useState} from "react";
import Link from "next/link";
import type {CustomerSessions} from "@homexo/shared";
import {api} from "../../api";
import MainContent from "../../ui/MainContent";
import CustomerAccess from "../CustomerAccess";
import {readSession,signOut} from "../session";
import "../../ui/privacy.css";
import "./security.css";

const when=(value:string)=>new Date(value).toLocaleString("en-IN",{timeZone:"Asia/Kolkata",dateStyle:"medium",timeStyle:"short"});
export default function CustomerSecurity(){return <MainContent className="privacy-center customer-security"><header className="privacy-heading"><div className="eyebrow">Account security</div><h1>Your signed-in sessions</h1><p>Review where you are signed in and end sessions you no longer need.</p></header><CustomerAccess intro="Sign in with your verified phone to manage your account sessions."><Sessions/></CustomerAccess></MainContent>;}

function Sessions(){
  const [data,setData]=useState<CustomerSessions|null>(null),[busy,setBusy]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState(""),[confirm,setConfirm]=useState("");
  const guard=useRef(false),mounted=useRef(false),feedback=useRef<HTMLParagraphElement>(null),failure=useRef<HTMLDivElement>(null);
  useEffect(()=>{let alive=true;mounted.current=true;const token=readSession()?.token;if(token)api.customerSessions(token).then(value=>{if(alive&&readSession()?.token===token)setData(value);}).catch(error=>{if(alive)setError(error instanceof Error?error.message:"Could not load sessions.");}).finally(()=>{if(alive)setBusy(false);});return()=>{alive=false;mounted.current=false;};},[]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  async function refresh(){const token=readSession()?.token;if(guard.current||!token)return;guard.current=true;setBusy(true);setError("");setNotice("");try{const value=await api.customerSessions(token);if(mounted.current&&readSession()?.token===token){setData(value);setConfirm("");setNotice("Your active sessions have been refreshed.");}}catch(error){if(mounted.current)setError(error instanceof Error?error.message:"Could not load sessions.");}finally{guard.current=false;if(mounted.current)setBusy(false);}}
  async function revoke(id:string){
    const token=readSession()?.token;if(guard.current||!token)return;guard.current=true;setBusy(true);setError("");setNotice("");
    try{
      const result=id==="others"?await api.revokeOtherCustomerSessions(token):await api.revokeCustomerSession(id,token);
      if(!mounted.current||readSession()?.token!==token)return;
      if("current" in result&&result.current){signOut();return;}
      const value=await api.customerSessions(token);if(mounted.current&&readSession()?.token===token){setData(value);setConfirm("");setNotice(id==="others"?"Other active sessions have been ended.":"The selected session has been ended.");}
    }catch(error){if(mounted.current)setError(error instanceof Error?error.message:"Could not end the session. Refresh before trying again.");}
    finally{guard.current=false;if(mounted.current)setBusy(false);}
  }
  return <section className="privacy-sections" aria-label="Account sessions"><section className="privacy-card"><h2>Active sign-ins</h2><p>Browser and device labels are approximate. Activity times update about every five minutes. Ending a session blocks its next authenticated request; information already downloaded remains on that device.</p><p>Signing out does not withdraw your case AI permission or cancel requests already in progress.</p><button className="btn light" disabled={busy} onClick={refresh}>Refresh signed-in sessions</button></section>
    {busy&&<p role="status">Loading session information…</p>}{error&&<div role="alert" className="privacy-error" tabIndex={-1} ref={failure}><p>{error}</p><p>The last loaded sessions may be out of date. Refresh before trying again.</p></div>}{notice&&<p role="status" className="privacy-success" tabIndex={-1} ref={feedback}>{notice}</p>}
    {data&&<><p>{data.items.length} active {data.items.length===1?"session":"sessions"} · Checked {when(data.checked_at)} IST</p><ol className="session-list">{data.items.map(item=><li key={item.id}><article className="privacy-card" aria-label={`${item.browser} on ${item.device}${item.is_current?", current session":""}`}><h2>{item.browser} · {item.device}</h2>{item.is_current&&<span className="privacy-badge">This session</span>}<dl><div><dt>Signed in</dt><dd>{when(item.created_at)} IST</dd></div><div><dt>Last activity</dt><dd>{when(item.last_seen_at)} IST</dd></div><div><dt>Expires</dt><dd>{when(item.expires_at)} IST</dd></div></dl>
      {confirm===item.id?<div className="privacy-confirm"><p>{item.is_current?"End this session and return to sign-in?":"End this session? It will need phone verification to sign in again."}</p><button className="btn small" disabled={busy||!!error} onClick={()=>revoke(item.id)}>Confirm end session</button><button className="btn small light" disabled={busy} onClick={()=>setConfirm("")}>Keep session</button></div>:<button className="btn small light" disabled={busy||!!error} onClick={()=>setConfirm(item.id)}>{item.is_current?"Sign out this session":"End session"}</button>}
    </article></li>)}</ol>
      {data.items.some(item=>!item.is_current)&&(confirm==="others"?<section className="privacy-card"><h2>End every other session?</h2><p>This session stays signed in. Other sessions will need phone verification.</p><div className="privacy-actions"><button className="btn" disabled={busy||!!error} onClick={()=>revoke("others")}>Confirm sign out other sessions</button><button className="btn light" disabled={busy} onClick={()=>setConfirm("")}>Keep other sessions</button></div></section>:<button className="btn light" disabled={busy||!!error} onClick={()=>setConfirm("others")}>Sign out other sessions</button>)}
      <p className="privacy-muted">Up to {data.max_active} sessions can remain active. A new sign-in beyond that limit ends the oldest active session.</p>
    </>}<Link className="text-link" href="/account">Back to your account</Link>
  </section>;
}
