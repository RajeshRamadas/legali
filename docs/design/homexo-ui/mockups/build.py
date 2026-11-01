"""Builds the Homexo UI mockups from shared pieces so every screen uses the same shell and sprite."""
import pathlib
OUT = pathlib.Path(__file__).parent

ICONS = {
 "home": '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
 "case": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/>',
 "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
 "cal": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
 "law": '<path d="M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0zM8 21h8"/>',
 "rera": '<path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6"/>',
 "spark": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z"/>',
 "card": '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h4"/>',
 "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
 "inbox": '<path d="M3 13l3-8h12l3 8v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M3 13h5l1 3h6l1-3h5"/>',
 "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
 "bell": '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 0 0 4 0"/>',
 "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
 "plus": '<path d="M12 5v14M5 12h14"/>',
 "check": '<path d="M5 12l5 5L20 7"/>',
 "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "alert": '<path d="M12 3l9 16H3z"/><path d="M12 10v4M12 17v.5"/>',
 "upload": '<path d="M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
 "send": '<path d="M5 12h14M13 6l6 6-6 6"/>',
 "chev": '<path d="M9 6l6 6-6 6"/>',
 "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 0 1-4 0v-.1A1.6 1.6 0 0 0 9 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.3 14H3a2 2 0 0 1 0-4h.1A1.6 1.6 0 0 0 4.6 9a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 9 4.6V3a2 2 0 0 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9c.3.6.9 1 1.5 1H21a2 2 0 0 1 0 4h-.1c-.6 0-1.2.4-1.5 1z"/>',
 "chat": '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
 "shield": '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
 "pen": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
 "download": '<path d="M12 4v12M7 11l5 5 5-5M4 20h16"/>',
 "filter": '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
 "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
 "rupee": '<path d="M6 4h12M6 9h12M6 4h3a5 5 0 0 1 0 10H6l9 7"/>',
}
SPRITE = '<svg style="display:none"><defs>' + "".join(f'<symbol id="{k}" viewBox="0 0 24 24">{v}</symbol>' for k, v in ICONS.items()) + "</defs></svg>"

def i(name, size=None):
    s = f' style="width:{size}px;height:{size}px"' if size else ""
    return f'<svg class="i"{s}><use href="#{name}"/></svg>'

def page(title, body, theme="light", extra_css=""):
    return f"""<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="homexo-ui.css"><style>{extra_css}</style></head><body>{SPRITE}{body}</body></html>"""

def sidebar(items, active, sub, me):
    out = [f'<aside class="side"><div class="brand"><span class="mark">H</span><span>homexo<small>{sub}</small></span></div>']
    for it in items:
        if isinstance(it, str):
            out.append(f'<div class="grp">{it}</div>'); continue
        icon, label, *count = it
        cls = "nav on" if label == active else "nav"
        c = f'<span class="count">{count[0]}</span>' if count else ""
        out.append(f'<a class="{cls}">{i(icon)}{label}{c}</a>')
    out.append(f'<div class="me"><span class="avatar" style="background:{me[2]}">{me[3]}</span><div><b>{me[0]}</b><small>{me[1]}</small></div></div></aside>')
    return "".join(out)

def topbar(placeholder):
    return f"""<header class="topbar"><span class="mbrand"><span class="mark">H</span>homexo</span><div class="search">{i('search')}{placeholder}<kbd>⌘K</kbd></div><span class="sp"></span>
<span class="icon-btn">{i('sun')}</span><span class="icon-btn">{i('bell')}<span class="dot"></span></span></header>"""

# ---------------------------------------------------------------- customer portal
CUSTOMER_NAV = ["Overview", ("home", "Home"), ("case", "My requests", 2), ("file", "Documents"), ("video", "Consultations"), ("card", "Payments"),
                "Get help", ("spark", "AI assistant"), ("law", "Find a lawyer"), ("rera", "RERA check")]

def customer(theme="light"):
    body = f"""<div class="shell">{sidebar(CUSTOMER_NAV, "Home", "Customer portal", ("Asha Rao", "+91 98•••• 4410", "#6d4aff", "AR"))}
<main class="main">{topbar("Search requests, documents, lawyers…")}
<div class="content">
 <div class="page-head"><div><h1>Good afternoon, Asha</h1><p>Here is where your property work stands today, Saturday 1 November.</p></div>
  <div class="acts"><a class="btn">{i('video')}Book a consultation</a><a class="btn primary">{i('plus')}New request</a></div></div>
 <div class="stats">
  <div class="stat t-violet"><span class="ic">{i('case',22)}</span><div><small>Open requests</small><b>2</b></div></div>
  <div class="stat t-amber"><span class="ic">{i('upload',22)}</span><div><small>Documents needed</small><b>3</b></div></div>
  <div class="stat t-blue"><span class="ic">{i('video',22)}</span><div><small>Consultation today</small><b style="font-size:20px">4:00 pm</b></div></div>
  <div class="stat t-green"><span class="ic">{i('check',22)}</span><div><small>Reports ready</small><b>1</b></div></div>
 </div>
 <div style="display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:20px">
  <div style="display:grid;gap:20px">
   <section class="card"><div class="card-h"><h3><span class="ic">{i('alert')}</span>Needs your attention</h3><a class="link">See all</a></div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">
     <div style="border-radius:16px;padding:16px;color:#fff;background:linear-gradient(135deg,#6d4aff,#9b7bff)"><span class="badge" style="background:rgba(255,255,255,.2);color:#fff">Due tomorrow</span><b style="display:block;font-size:16px;margin-top:22px">Upload the sale deed</b><small style="opacity:.85">Flat purchase, Whitefield · HX-261101-04</small></div>
     <div style="border-radius:16px;padding:16px;background:var(--surface-2);border:1px solid var(--line)"><span class="badge amber">Waiting on you</span><b style="display:block;font-size:16px;margin-top:22px">Confirm khata number</b><small class="muted">Asked by Adv. Ananya Rao · 2 hours ago</small></div>
     <div style="border-radius:16px;padding:16px;background:var(--surface-2);border:1px solid var(--line)"><span class="badge blue">Today</span><b style="display:block;font-size:16px;margin-top:22px">Video call at 4:00 pm</b><small class="muted">Google Meet link sent on WhatsApp</small></div>
     <div style="border-radius:16px;padding:16px;background:var(--surface-2);border:1px solid var(--line)"><span class="badge green">Ready</span><b style="display:block;font-size:16px;margin-top:22px">Download preliminary report</b><small class="muted">Title review · signed PDF</small></div>
    </div></section>
   <section class="card"><div class="card-h"><h3><span class="ic">{i('case')}</span>My requests</h3><div class="tabs"><span class="on">Active</span><span>Completed</span></div></div>
    <div style="display:grid;gap:12px">
     <div class="case"><div class="top"><span class="ic" style="background:var(--primary-50);color:var(--primary)">{i('shield',20)}</span><div><h4>Flat purchase, Whitefield <span class="badge violet">Shield Pro</span></h4><div class="sub">Adv. Ananya Rao · started 24 Oct</div></div><div class="amt">₹9,999<small>Paid</small></div></div>
      <div class="bot"><span>Stage 3 of 4 · Lawyer review</span><span class="progress"><i style="width:68%"></i></span><span class="r"><a class="btn sm">{i('file')}Documents</a><a class="btn sm">{i('chat')}Message</a></span></div></div>
     <div class="case"><div class="top"><span class="ic" style="background:var(--amber-50);color:var(--amber)">{i('pen',20)}</span><div><h4>Name change affidavit <span class="badge amber">Draft</span></h4><div class="sub">Affidavit drafting · started 30 Oct</div></div><div class="amt">₹1,200<small>Due on approval</small></div></div>
      <div class="bot"><span>Stage 2 of 3 · Drafting</span><span class="progress"><i style="width:45%;background:var(--amber)"></i></span><span class="r"><a class="btn sm">{i('file')}Documents</a><a class="btn sm">{i('chat')}Message</a></span></div></div>
    </div></section>
  </div>
  <div style="display:grid;gap:20px;align-content:start">
   <section class="card ai"><div class="card-h" style="margin:0"><h3><span class="ic">{i('spark')}</span>Legal assistant</h3><span class="badge green">● Online</span></div>
    <div class="msg me"><div class="bubble">Is Amber Enclave in Hebbal safe to book?</div></div>
    <div class="msg"><span class="bot-ic">{i('spark',16)}</span><div class="bubble"><b>Overall risk: High</b><br>Registration lapsed · 3 years late · 100% booked.<div class="riskbar" style="margin-top:8px">{''.join('<i class="on" style="height:%dpx"></i>' % h if k<14 else '<i style="height:%dpx"></i>' % h for k,h in enumerate([8,12,16,10,18,20,14,22,16,12,18,20,22,14,10,8,12,6,9,7]))}</div></div></div>
    <div style="display:flex;gap:6px;flex-wrap:wrap"><span class="chip">RERA check</span><span class="chip">Which package?</span><span class="chip">Talk to a lawyer</span></div>
    <div class="input"><span>Ask a question or paste a document…</span><b>{i('send',16)}</b></div></section>
   <section class="card"><div class="card-h"><h3><span class="ic">{i('video')}</span>Upcoming</h3><a class="link">Calendar</a></div>
    <div class="rows">
     <div class="rowi"><span class="avatar" style="background:#e04f16">AR</span><div><b>Adv. Ananya Rao</b><small>Title review call · Google Meet</small></div><div class="r"><b>4:00 pm</b><small>Today</small></div></div>
     <div class="rowi"><span class="avatar" style="background:#0d9488">SR</span><div><b>Sub-registrar visit</b><small>Registration slot, KR Puram</small></div><div class="r"><b>11:30 am</b><small>12 Nov</small></div></div>
    </div><a class="btn primary" style="width:100%;justify-content:center;margin-top:12px">{i('video')}Join today's call</a></section>
  </div>
 </div>
</div></main></div>
<nav class="mtabs"><a class="on">{i('home',20)}Home</a><a>{i('case',20)}Requests</a><a>{i('spark',20)}Ask</a><a>{i('file',20)}Docs</a><a>{i('users',20)}Account</a></nav>"""
    return page("Customer portal", body, theme, "@media(max-width:1000px){.content>div[style]{grid-template-columns:1fr!important}.card div[style*='repeat(2']{grid-template-columns:1fr!important}}")

# ---------------------------------------------------------------- staff workspace
STAFF_NAV = ["Workspace", ("home", "Dashboard"), ("inbox", "Ticket queue", 7), ("case", "Cases"), ("cal", "Calendar"), ("file", "Verification"),
             "Clients & team", ("users", "Customers"), ("law", "Lawyer profile"), ("video", "Team calls"),
             "Content", ("pen", "Blog"), ("download", "Government fetches"), ("settings", "Settings")]

def staff(theme="light"):
    rows = [
      ("Asha Rao", "Full legal due diligence · Shield Pro", "HX-261101-04", "Whitefield", "red", "Urgent", "₹9,999", "Lawyer review", 68, "#6d4aff", "shield"),
      ("Farhan Ali", "Khata / tax / BESCOM transfer", "HX-261031-B9", "HSR Layout", "amber", "Medium", "₹3,500", "Gathering documents", 35, "#f59e0b", "file"),
      ("Lakshmi N", "Certified copy, Encumbrance Certificate", "HX-261030-63", "Devanahalli", "blue", "Normal", "₹1,800", "Fetching from Kaveri", 52, "#2563eb", "download"),
    ]
    cases = "".join(f"""<div class="case"><div class="top"><span class="ic" style="background:color-mix(in srgb,{c} 14%,transparent);color:{c}">{i(ic,20)}</span><div><h4>{n} <span class="badge {b}">{bl}</span></h4><div class="sub">{s}</div></div><div class="amt">{amt}<small>{t} · {loc}</small></div></div>
<div class="bot"><span>{i('clock',15)} {st}</span><span class="progress"><i style="width:{p}%;background:{c}"></i></span><span class="r"><a class="btn sm">{i('file')}Documents</a><a class="btn sm">{i('pen')}Update</a></span></div></div>""" for n,s,t,loc,b,bl,amt,st,p,c,ic in rows)
    days = ['<span class="h">%s</span>' % d for d in "SMTWTFS"]
    cal = "".join(days) + '<span class="dim">26</span><span class="dim">27</span><span class="dim">28</span><span class="dim">29</span><span class="dim">30</span><span class="dim">31</span><span class="today">1</span>' + "".join(f'<span class="{"has" if d in (3,4,6,10,12,13,17,20) else ""}">{d}</span>' for d in range(2, 30))
    body = f"""<div class="shell">{sidebar(STAFF_NAV, "Dashboard", "Staff workspace", ("Ananya Rao", "Lawyer · Admin", "#e04f16", "AR"))}
<main class="main">{topbar("Search tickets, customers, phone or area…")}
<div class="content">
 <div class="page-head"><div><span class="badge violet">Property legal</span><h1 style="margin-top:8px">Good afternoon, Ananya</h1><p>Your case overview for Saturday, 1 November 2026.</p></div>
  <div class="acts"><a class="btn">{i('download')}Export</a><a class="btn">{i('filter')}Filter</a><a class="btn primary">{i('plus')}New ticket</a></div></div>
 <div class="tabs"><span class="on">Active cases</span><span>New requests</span><span>Waiting on customer</span><span>Completed</span><span>Analytics</span></div>
 <div class="stats">
  <div class="stat t-violet"><span class="ic">{i('inbox',22)}</span><div><small>Open tickets</small><b>24</b><span class="delta">+5 this week</span></div></div>
  <div class="stat t-blue"><span class="ic">{i('rupee',22)}</span><div><small>Collected this month</small><b>₹1.86L</b><span class="delta">+12%</span></div></div>
  <div class="stat t-amber"><span class="ic">{i('cal',22)}</span><div><small>Calls next 7 days</small><b>12</b></div></div>
  <div class="stat t-pink"><span class="ic">{i('file',22)}</span><div><small>Documents to review</small><b>8</b></div></div>
 </div>
 <div style="display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:20px">
  <section class="card"><div class="card-h"><h3><span class="ic">{i('case')}</span>Active cases</h3><a class="link">Open queue →</a></div><div style="display:grid;gap:12px">{cases}</div></section>
  <div style="display:grid;gap:20px;align-content:start">
   <section class="card"><div class="card-h"><h3><span class="ic">{i('cal')}</span>November 2026</h3><a class="link">View all</a></div><div class="cal">{cal}</div>
    <div style="display:flex;justify-content:space-between;margin-top:12px;padding:10px 12px;border-radius:12px;background:var(--surface-2);font-weight:600"><span class="ink2">{i('clock',15)} This month</span><span>13 calls</span></div></section>
   <section class="card"><div class="card-h"><h3><span class="ic">{i('video')}</span>Today's timeline</h3></div>
    <div class="rows">
     <div class="rowi"><span class="badge blue">11:00</span><div><b>Client call · Farhan Ali</b><small>Khata transfer scope</small></div></div>
     <div class="rowi"><span class="badge violet">14:00</span><div><b>Document review · HX-261101-04</b><small>Sale deed, EC 30 years</small></div></div>
     <div class="rowi"><span class="badge green">16:00</span><div><b>Consultation · Asha Rao</b><small>Google Meet</small></div><div class="r"><a class="btn sm primary">Join</a></div></div>
    </div></section>
  </div>
 </div>
</div></main></div>"""
    return page("Staff workspace" + (" dark" if theme == "dark" else ""), body, theme, "@media(max-width:1000px){.content>div[style]{grid-template-columns:1fr!important}}")

# ---------------------------------------------------------------- AI assistant page
def assistant(theme="light"):
    body = f"""<div class="shell">{sidebar(CUSTOMER_NAV, "AI assistant", "Customer portal", ("Asha Rao", "+91 98•••• 4410", "#6d4aff", "AR"))}
<main class="main">{topbar("Search requests, documents, lawyers…")}
<div class="content" style="grid-template-columns:minmax(0,1fr) 320px;align-items:start">
 <section class="card ai" style="min-height:640px;padding:0;gap:0">
  <div style="display:flex;align-items:center;gap:12px;padding:18px 20px;border-bottom:1px solid var(--line)"><span class="bot-ic" style="width:42px;height:42px;border-radius:12px">{i('spark',20)}</span><div><h3 style="font-size:18px">Legal assistant</h3><small class="muted hide-m">Answers from Homexo guides and RERA records · a lawyer can take over any time</small></div><span class="hide-m" style="margin-left:auto;display:flex;gap:8px"><a class="btn sm">{i('download')}Export</a><a class="btn sm">Clear</a></span></div>
  <div style="flex:1;display:grid;gap:16px;padding:20px;align-content:start">
   <div class="msg me"><div class="bubble" style="max-width:70%">I'm buying a resale 2BHK in Whitefield. Which documents should I ask the seller for?</div></div>
   <div class="msg"><span class="bot-ic">{i('spark',16)}</span><div class="bubble" style="max-width:78%;background:var(--surface)">For a resale flat in Bangalore, ask for these before you pay an advance:
    <ol style="margin:8px 0;padding-left:18px;line-height:1.7"><li><b>Sale deed</b> of the seller, plus the earlier deeds (mother deed chain)</li><li><b>Encumbrance Certificate</b> for 30 years</li><li><b>Khata certificate and extract</b>, and the latest tax receipts</li><li><b>Occupancy certificate</b> and approved building plan</li><li><b>Society NOC</b> and the share certificate</li></ol>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px"><span class="badge gray">Guide: resale checks</span><span class="badge gray">Karnataka RERA</span></div></div></div>
   <div class="msg"><span class="bot-ic" style="opacity:0">.</span><div style="display:flex;gap:12px;align-items:center;padding:12px 14px;border-radius:14px;background:var(--primary-50);max-width:78%"><span class="avatar" style="background:#e04f16">AR</span><div><b>Want a lawyer to check them?</b><br><small class="ink2">Shield Pro covers all five, with a video call. ₹9,999 fixed.</small></div><a class="btn sm primary" style="margin-left:auto">Start</a></div></div>
  </div>
  <div style="padding:16px 20px;border-top:1px solid var(--line)"><div class="input"><span>Ask anything about a property, a document or a law…</span><b>{i('send',16)}</b></div></div>
 </section>
 <div style="display:grid;gap:20px">
  <section class="card"><div class="card-h"><h3>Quick actions</h3></div><div class="rows">
   <div class="rowi"><span class="card-h" style="margin:0"><span class="ic">{i('rera')}</span></span><div><b>Check a RERA project</b><small>Warning signs in seconds</small></div><span class="r">{i('chev')}</span></div>
   <div class="rowi"><span class="card-h" style="margin:0"><span class="ic">{i('file')}</span></span><div><b>Explain a document</b><small>Upload a deed or EC</small></div><span class="r">{i('chev')}</span></div>
   <div class="rowi"><span class="card-h" style="margin:0"><span class="ic">{i('pen')}</span></span><div><b>Draft an affidavit</b><small>Reviewed by an advocate</small></div><span class="r">{i('chev')}</span></div>
   <div class="rowi"><span class="card-h" style="margin:0"><span class="ic">{i('law')}</span></span><div><b>Talk to a lawyer</b><small>Free slots today</small></div><span class="r">{i('chev')}</span></div>
  </div></section>
  <section class="card"><div class="card-h"><h3>Tips</h3></div><ul style="margin:0;padding-left:18px;line-height:1.8;color:var(--ink-2)"><li>Mention the area and property type</li><li>Paste a RERA number for exact records</li><li>Answers are guidance, not legal advice</li></ul></section>
 </div>
</div></main></div>
<nav class="mtabs"><a>{i('home',20)}Home</a><a>{i('case',20)}Requests</a><a class="on">{i('spark',20)}Ask</a><a>{i('file',20)}Docs</a><a>{i('users',20)}Account</a></nav>"""
    return page("AI assistant", body, theme, "@media(max-width:1000px){.content[style]{grid-template-columns:1fr!important}}")

# ---------------------------------------------------------------- public home
def public():
    css = """
.pub{background:#f7f5f0;min-height:100vh}
[data-theme] .pub{--surface-2:#efece5}
.pnav{display:flex;align-items:center;gap:28px;height:78px;width:min(1200px,calc(100% - 40px));margin:auto}
.pnav .links{display:flex;gap:26px;font-weight:600;color:var(--ink-2);margin:0 auto}
.phero{width:min(1200px,calc(100% - 40px));margin:auto;display:grid;grid-template-columns:1fr 1fr;gap:30px;align-items:center;padding:40px 0 30px;position:relative}
.phero h1{font-size:clamp(44px,6vw,76px);line-height:1.02;font-weight:700;letter-spacing:-.045em}
.phero h1 em{font-style:normal;color:var(--primary);position:relative}
.phero h1 em::after{content:"";position:absolute;left:4%;right:4%;bottom:-6px;height:12px;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 14'%3E%3Cpath d='M2 9 C 60 2, 140 2, 198 7 M 20 12 C 80 7, 140 8, 180 11' fill='none' stroke='%236d4aff' stroke-width='3' stroke-linecap='round'/%3E%3C/svg%3E") center/100% 100% no-repeat}
.phero p.lead{font-size:18px;line-height:1.6;color:var(--ink-2);max-width:520px;margin:22px 0 26px}
.ask{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid var(--line);border-radius:18px;padding:8px 8px 8px 16px;box-shadow:var(--shadow-lg);max-width:560px;color:var(--ink-3)}
.ask span{flex:1}
.collage{position:relative;height:520px}
.collage::before{content:"";position:absolute;inset:10% 0 5% 10%;border-radius:50%;background:radial-gradient(closest-side,rgba(109,74,255,.25),rgba(56,189,248,.18) 55%,transparent);filter:blur(30px)}
.ph{position:absolute;border-radius:24px;display:grid;place-items:end center;overflow:hidden;font-size:120px;font-weight:700;color:rgba(255,255,255,.9);letter-spacing:-.05em}
.flt{position:absolute;background:#fff;border-radius:16px;padding:12px 14px;box-shadow:var(--shadow-lg);font-size:13px;display:grid;gap:4px}
.flt b{font-size:14px}
.strip{width:min(1200px,calc(100% - 40px));margin:30px auto 0;display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;padding:26px 0;border-top:1px solid var(--line);color:var(--ink-3);font-weight:700;font-size:15px}
.strip span{display:flex;align-items:center;gap:8px}
.sec{width:min(1200px,calc(100% - 40px));margin:auto;padding:60px 0}
.sec h2{font-size:40px;font-weight:700;letter-spacing:-.04em}
.svc{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:26px}
.svc .card{display:grid;gap:10px;align-content:start}
.svc .card .ic{width:46px;height:46px;border-radius:14px;display:grid;place-items:center}
.svc .card b{font-size:17px}.svc .card p{margin:0;color:var(--ink-2);line-height:1.55}
@media(max-width:1000px){.pnav .links{display:none}.phero{grid-template-columns:1fr}.collage{height:400px}.svc{grid-template-columns:1fr 1fr}.pnav{justify-content:space-between}}
@media(max-width:560px){.svc{grid-template-columns:1fr}.collage{height:360px;transform:scale(.8);transform-origin:top left;width:125%}.sec h2{font-size:30px}}
"""
    body = f"""<div class="pub">
<nav class="pnav"><div class="brand" style="padding:0"><span class="mark">H</span><span>homexo legal</span></div>
 <div class="links"><a>RERA check</a><a>Find a lawyer</a><a>Verify a property</a><a>Documents</a><a>For developers</a></div>
 <a class="btn" style="border-radius:999px">Sign in</a><a class="btn dark" style="border-radius:999px">Get started</a></nav>
<section class="phero">
 <div><span class="badge violet">Bangalore · property law online</span>
  <h1 style="margin-top:16px">Property lawyers,<br>on <em>demand.</em></h1>
  <p class="lead">Check a RERA project, book a verified advocate and verify a property, all for one fixed fee. Follow every step from your phone.</p>
  <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px"><a class="btn dark pill">Book a lawyer</a><a class="btn pill">Check a RERA project</a></div>
  <div class="ask">{i('spark')}<span>Ask: is this flat safe to buy?</span><a class="btn primary sm" style="height:38px">{i('send',16)}</a></div>
 </div>
 <div class="collage">
  <div class="ph" style="left:16%;top:4%;width:44%;height:52%;background:linear-gradient(160deg,#b9e3ff,#7cc4f2)"><svg viewBox="0 0 100 100" style="width:78%;height:auto;display:block"><circle cx="50" cy="38" r="19" fill="rgba(255,255,255,.55)"/><path d="M12 100c2-24 18-36 38-36s36 12 38 36z" fill="rgba(255,255,255,.55)"/></svg></div>
  <div class="ph" style="left:52%;top:40%;width:42%;height:48%;background:linear-gradient(160deg,#ffb4a2,#f07b63)"><svg viewBox="0 0 100 100" style="width:78%;height:auto;display:block"><circle cx="50" cy="38" r="19" fill="rgba(255,255,255,.55)"/><path d="M12 100c2-24 18-36 38-36s36 12 38 36z" fill="rgba(255,255,255,.55)"/></svg></div>
  <div class="flt" style="left:54%;top:8%"><b>Adv. Ananya Rao</b><span class="muted">Title & RERA disputes</span><span class="badge green">● Free today 3:30 pm</span></div>
  <div class="flt" style="left:0;top:50%"><b>Shield Pro</b><span><span class="badge violet">₹9,999 fixed</span> <span class="badge gray">5 days</span></span></div>
  <div class="flt" style="left:6%;top:74%;grid-template-columns:auto 1fr;align-items:center;gap:4px 10px"><span class="avatar" style="background:#16a34a">{i('check',16)}</span><div><b>Title review done</b><br><span class="muted">HX-261101-04 · Stage 3 of 4</span></div></div>
  <div class="flt" style="right:0;top:84%;grid-template-columns:1fr auto;align-items:center;gap:10px"><div><b>Amber Enclave</b><br><span class="muted">RERA check</span></div><span class="badge red">High risk</span></div>
 </div>
</section>
<div class="strip"><span>{i('shield')}Verified advocates</span><span>{i('rupee')}Fixed fees</span><span>{i('video')}Google Meet calls</span><span>{i('chat')}WhatsApp updates</span><span>{i('card')}UPI & cards</span><span>{i('rera')}Karnataka RERA data</span></div>
<section class="sec"><span class="badge violet">What we do</span><h2 style="margin-top:12px">Start anywhere. It all lands on one case.</h2>
 <div class="svc">
  <div class="card"><span class="ic" style="background:var(--primary-50);color:var(--primary)">{i('rera',22)}</span><b>Check a RERA project</b><p>Free warning-sign check on any registered project and developer.</p><a class="link">Check a project →</a></div>
  <div class="card"><span class="ic" style="background:var(--blue-50);color:var(--blue)">{i('law',22)}</span><b>Talk to a lawyer</b><p>Compare advocates by speciality, language, fee and next free slot.</p><a class="link">Browse lawyers →</a></div>
  <div class="card"><span class="ic" style="background:var(--green-50);color:var(--green)">{i('shield',22)}</span><b>Verify a property</b><p>Title, EC, approvals and khata, ending in a plain verdict.</p><a class="link">See packages →</a></div>
  <div class="card"><span class="ic" style="background:var(--amber-50);color:var(--amber)">{i('file',22)}</span><b>Documents & affidavits</b><p>EC, RTC, certified copies, deeds and affidavits, couriered.</p><a class="link">Request a document →</a></div>
 </div></section>
</div>"""
    return page("Public home", body, "light", css)

files = {
 "1-public-home.html": public(),
 "2-customer-dashboard.html": customer(),
 "3-staff-workspace.html": staff(),
 "4-staff-workspace-dark.html": staff("dark"),
 "5-ai-assistant.html": assistant(),
}
for name, html in files.items():
    (OUT / name).write_text(html)
print("built", len(files))
