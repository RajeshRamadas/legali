"use client";
import Link from "next/link";
import {useEffect,useRef,useState} from "react";
import type {AccountSummaryManifest} from "@homexo/shared";
import {api} from "../../api";
import MainContent from "../../ui/MainContent";
import useRetryDelay from "../../ui/useRetryDelay";
import CustomerAccess from "../CustomerAccess";
import {readSession} from "../session";
import "../../ui/privacy.css";
import "./data.css";

export default function AccountDataPage(){
  return <MainContent className="privacy-center account-data"><header className="privacy-heading"><div className="eyebrow">Your records</div><h1>Download your account summary</h1><p>Keep a JSON copy of your current profile, preferences and request activity.</p></header>
    <CustomerAccess intro="Sign in with your verified phone to download a summary of your own account."><SummaryDownload/></CustomerAccess>
  </MainContent>;
}

function SummaryDownload(){
  const [value,setValue]=useState<AccountSummaryManifest|null>(null),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const guard=useRef(false),mounted=useRef(false),failure=useRef<HTMLDivElement>(null),feedback=useRef<HTMLParagraphElement>(null),retry=useRetryDelay();
  const recordRetry=useRef(retry.record);recordRetry.current=retry.record;
  useEffect(()=>{let alive=true;mounted.current=true;api.accountSummary().then(result=>{if(alive)setValue(result);}).catch(error=>{if(alive){setError(error instanceof Error?error.message:"Could not load the summary information.");recordRetry.current(error);}}).finally(()=>{if(alive)setLoading(false);});return()=>{alive=false;mounted.current=false;};},[]);
  useEffect(()=>{if(error)failure.current?.focus();},[error]);useEffect(()=>{if(notice)feedback.current?.focus();},[notice]);
  async function refresh(){
    if(guard.current)return;guard.current=true;setLoading(true);setError("");setNotice("");const token=readSession()?.token;
    try{const result=await api.accountSummary();if(mounted.current&&readSession()?.token===token){setValue(result);setNotice("Summary information refreshed. Download when you are ready.");}}
    catch(error){if(mounted.current){setError(error instanceof Error?error.message:"Could not load summary information.");retry.record(error);}}
    finally{guard.current=false;if(mounted.current)setLoading(false);}
  }
  async function download(){
    if(guard.current||!value?.ready)return;const token=readSession()?.token;if(!token)return;
    guard.current=true;setBusy(true);setError("");setNotice("");
    let objectUrl:string|null=null;
    try{
      const result=await api.downloadAccountSummary();
      if(!mounted.current)return;
      if(readSession()?.token!==token){setError("Your sign-in changed. Refresh the summary before trying again.");return;}
      objectUrl=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+"\n"],{type:"application/json;charset=utf-8"}));
      const link=document.createElement("a");link.href=objectUrl;link.download="homexo-account-summary.json";document.body.appendChild(link);link.click();link.remove();
      // Give the browser time to claim the download, then discard the object URL.
      const pendingUrl=objectUrl;window.setTimeout(()=>URL.revokeObjectURL(pendingUrl),1000);objectUrl=null;
      setNotice("Your account summary download has started. Keep the file somewhere private.");
    }catch(error){if(mounted.current){setError(error instanceof Error?error.message:"Your summary could not be downloaded.");retry.record(error);}}
    finally{if(objectUrl)URL.revokeObjectURL(objectUrl);guard.current=false;if(mounted.current)setBusy(false);}
  }
  const disabled=loading||busy||retry.seconds>0;
  return <section className="privacy-sections" aria-label="Account summary download">
    <section className="privacy-card"><h2>What your summary contains</h2><p>Your current account profile and notification preferences, request status and document counts, meeting dates, and payment records with known refund amounts.</p><p>Case document AI choices and file-preservation status appear with each request. Money amounts use paise and include a currency code.</p><p>File contents, case reports and messages need a reviewed access copy. <Link href="/account/privacy">Use Privacy requests</Link> for a fuller copy, corrections or deletion enquiries.</p></section>
    {loading&&<p role="status">Loading summary information…</p>}
    {error&&<div className="privacy-error" role="alert" tabIndex={-1} ref={failure}><p>Could not prepare the account summary. {error}</p><p>{value?"The last loaded counts may be out of date. Refresh the information before retrying.":"Refresh the information to try again."}</p></div>}
    {notice&&<p className="privacy-success" role="status" tabIndex={-1} ref={feedback}>{notice}</p>}
    {value&&<section className="privacy-card" aria-label="Summary coverage"><h2>Current coverage</h2><dl className="summary-counts">{([['requests','Requests'],['meetings','Meeting records'],['payments','Payment records']] as const).map(([key,label])=><div key={key}><dt>{label}</dt><dd>{value.counts[key].toLocaleString("en-IN")}</dd></div>)}</dl>
      <p className="privacy-muted">Checked {new Date(value.checked_at).toLocaleString("en-IN",{timeZone:"Asia/Kolkata"})} IST. Your download uses the records observed when it is prepared.</p>
      {!value.ready&&<p>This account exceeds the self-service summary limits. Use Privacy requests for a reviewed copy; no shortened download will be substituted.</p>}
      <button type="button" className="btn" disabled={disabled||!!error||!value.ready} onClick={download}>{busy?"Preparing account summary…":"Download account summary (JSON)"}</button>
    </section>}
    <div className="privacy-actions"><button type="button" className="btn light" disabled={disabled} onClick={refresh}>{retry.seconds>0?`Try again in ${retry.seconds}s`:"Refresh summary information"}</button><Link className="text-link" href="/account">Back to your account</Link></div>
    <p className="privacy-muted">This is an activity summary. It does not complete a formal privacy request or certify a payment, refund or legal opinion. The download is prepared for your signed-in account and is not stored as a public link.</p>
  </section>;
}
