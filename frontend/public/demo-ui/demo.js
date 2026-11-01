/* Interactive review only: fictional data, local state, no API requests. */
(() => {
  'use strict';
  const page = location.pathname.includes('1-public') ? 'public' : location.pathname.includes('2-customer') ? 'customer' : location.pathname.includes('5-ai') ? 'assistant' : 'staff';
  const $ = selector => document.querySelector(selector);
  const $$ = selector => Array.from(document.querySelectorAll(selector));
  const el = (tag, text, className) => { const node = document.createElement(tag); if (text) node.textContent = text; if (className) node.className = className; return node; };
  const targetOrigin = location.protocol === 'file:' ? '*' : location.origin;
  function navigate(screen) {
    if (parent !== window) parent.postMessage({ type: 'homexo-demo:navigate', screen }, targetOrigin);
    else { const files = { public:'1-public-home.html', customer:'2-customer-dashboard.html', staff:'3-staff-workspace.html', assistant:'5-ai-assistant.html' }; location.href = files[screen] || files.public; }
  }
  function toggleTheme() {
    if (parent !== window) parent.postMessage({ type: 'homexo-demo:toggle-theme' }, targetOrigin);
    else { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; try { localStorage.setItem('hx-demo-theme', theme); } catch {} }
  }
  window.addEventListener('message', event => {
    if (event.origin === location.origin && event.source === parent && event.data?.type === 'homexo-demo:theme' && ['light','dark'].includes(event.data.theme)) document.documentElement.dataset.theme = event.data.theme;
  });
  const dialog = el('dialog', '', 'demo-modal');
  dialog.setAttribute('aria-labelledby', 'demo-dialog-title'); document.body.append(dialog);
  dialog.addEventListener('click', event => { if (event.target === dialog) { const rect=dialog.getBoundingClientRect(); if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) dialog.close(); } });
  function modal(title, render) {
    dialog.replaceChildren();
    const head=el('div','','demo-modal-head'), heading=el('h2',title), close=el('button','×','icon-btn'); heading.id='demo-dialog-title'; close.type='button'; close.setAttribute('aria-label','Close dialog');close.onclick=()=>dialog.close();head.append(heading,close);dialog.append(head,el('span','Fictional demo data','demo-sample-label'));render(dialog);if(!dialog.open)dialog.showModal();
  }
  let toastTimer;
  function toast(text) { $('.demo-toast')?.remove();const node=el('div',text,'demo-toast');node.setAttribute('role','status');document.body.append(node);clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.remove(),4000); }
  const action = (label, fn, className='btn primary') => { const button=el('button',label,className);button.type='button';button.onclick=fn;return button; };
  function documents() {
    modal('Your document checklist', box => {
      box.append(el('p','Whitefield flat · Shield Pro. This sample shows how requested files and review statuses will look.'));
      const list=el('ul','','demo-modal-list');
      for(const [label,status,tone] of [['Sale deed','Upload needed','amber'],['Previous title deeds','Received','blue'],['Encumbrance certificate','Case team to obtain','violet'],['Khata certificate','Under review','blue']]){
        const row=el('li');row.append(el('span',label),el('span',status,'badge '+tone));list.append(row);
      }
      box.append(list);
      const label=el('label','Try choosing a sample file'),input=el('input');input.type='file';input.accept='.pdf,.png,.jpg,.jpeg';input.setAttribute('aria-label','Choose sample document');label.append(input);box.append(label,el('small','The selected file stays in your browser. This demo does not upload or verify it.'));
      input.onchange=()=>{if(!input.files.length)return;const row=list.firstElementChild;row.replaceChildren(el('span',input.files[0].name),el('span','Received · demo','badge blue'));toast('Sample file selected. No upload was made.');};
    });
  }
  function enquiry() {
    modal('Start a property request', box => {
      box.append(el('p','Try the sample enquiry form. Submitting shows the confirmation design without creating a real case.'));
      const form=el('form');const nameLabel=el('label','Your name'),name=el('input');name.required=true;name.placeholder='e.g. Asha Rao';name.setAttribute('aria-label','Your name');nameLabel.append(name);
      const typeLabel=el('label','Property type'),select=el('select');select.setAttribute('aria-label','Property type');for(const text of ['Apartment','Residential plot','Independent house','Agricultural land'])select.append(el('option',text));typeLabel.append(select);
      form.append(nameLabel,typeLabel,action('Preview request confirmation',()=>{},'btn primary'));form.lastElementChild.type='submit';form.onsubmit=event=>{event.preventDefault();box.replaceChildren(el('span','Sample confirmation','badge green'),el('h2','Your request is ready'),el('p',`Thanks, ${name.value}. Demo request HX-DEMO-104 shows the ${select.value.toLowerCase()} checklist, case timeline and next steps.`),action('View customer dashboard',()=>{dialog.close();navigate('customer');}));};box.append(form);
    });
  }
  function generic(title, message) { modal(title,box=>{box.append(el('p',message),action('Back to preview',()=>dialog.close(),'btn'));}); }
  function rera() { generic('Sample RERA project check','Amber Enclave is fictional sample data. The preview shows a high-risk result, lapsed registration and delayed completion. Live government-record verification is outside this design demo.'); }
  function lawyer() { modal('Book a sample consultation',box=>{box.append(el('p','Adv. Ananya Rao · Property title and RERA · English, Kannada'),el('span','₹1,500 · 30 minutes','badge violet'));const actions=el('div','','demo-modal-actions');for(const time of ['3:30 pm','4:00 pm','5:00 pm'])actions.append(action(time,()=>generic('Sample booking selected',`${time} IST with Adv. Ananya Rao. This is a preview; no booking or payment was made.`),'btn'));box.append(actions);}); }
  function notify() { modal('Needs your attention',box=>{const list=el('ul','','demo-modal-list');for(const text of ['Upload the sale deed','Confirm the property khata number','Consultation at 4:00 pm IST'])list.append(el('li',text));box.append(list,action('View documents',documents));}); }
  const transcript=[];
  function exportText(name,text){const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const link=el('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function reply(question){const text=question.toLowerCase();if(/rera|project|amber/.test(text))return 'Sample RERA check: Amber Enclave is flagged high risk in this fictional dataset. In the live service, the project registration, dates and source records must be checked before drawing a conclusion.';if(/package|price|fee/.test(text))return 'The sample packages are Shield Starter ₹4,999, Shield Pro ₹9,999 and Shield Complete ₹18,999. This demo shows the presentation only; a specialist confirms scope and fees.';if(/lawyer|consult/.test(text))return 'The sample lawyer is Adv. Ananya Rao, with a consultation slot at 4:00 pm IST. Use Book a consultation to preview the booking flow.';return 'For this sample property, the checklist requests the sale deed, previous title deeds, EC, khata and approvals as applicable. Uploaded files remain “received” until reviewed. This is a scripted design demo, not document verification or legal advice.';}
  function send(question, container){const text=question.trim();if(!text)return;const user=el('div','','msg me');user.append(el('div',text,'bubble'));const answer=el('div','','msg');answer.append(el('span','H','bot-ic'),el('div',reply(text),'bubble'));container.append(user,answer);transcript.push('You: '+text,'Demo assistant: '+reply(text));answer.scrollIntoView({block:'nearest',behavior:'auto'});}
  const ai=$('.ai');let chatContainer;
  if(ai){const first=ai.querySelector('.msg');if(first&&page==='assistant')chatContainer=first.parentElement;else{chatContainer=el('div');const input=ai.querySelector('.input');input.before(chatContainer);}}
  $$('.input,.ask').forEach(original=>{
    const form=el('form','',original.className);const placeholder=original.querySelector('span')?.textContent||'Ask a question';const input=el('input');input.placeholder=placeholder;input.setAttribute('aria-label',page==='public'?'Ask the demo assistant':'Message the demo assistant');input.maxLength=2000;const sendButton=action('→',()=>{});sendButton.type='submit';sendButton.setAttribute('aria-label','Send message');form.append(input,sendButton);original.replaceWith(form);form.onsubmit=event=>{event.preventDefault();if(!input.value.trim())return;if(page==='public'){try{sessionStorage.setItem('hx-demo-question',input.value.trim());}catch{}navigate('assistant');}else{send(input.value,chatContainer);input.value='';}};
  });
  if(page==='assistant'){try{const pending=sessionStorage.getItem('hx-demo-question');if(pending){sessionStorage.removeItem('hx-demo-question');send(pending,chatContainer);}}catch{}}
  $$('.ai .chip').forEach(node=>{node.tabIndex=0;node.setAttribute('role','button');node.onclick=()=>send(node.textContent,chatContainer);node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();node.click();}};});
  $$('.icon-btn').forEach(node=>{if(node.closest('dialog'))return;const use=node.querySelector('use')?.getAttribute('href');const button=el('button','',node.className);button.type='button';button.append(...node.childNodes);button.setAttribute('aria-label',use==='#sun'?'Toggle theme':'Notifications');button.onclick=use==='#sun'?toggleTheme:notify;node.replaceWith(button);});
  if(page==='public'){const toggle=action('',toggleTheme,'icon-btn');toggle.innerHTML='<svg class="i" aria-hidden="true"><use href="#sun"/></svg>';toggle.setAttribute('aria-label','Toggle theme');$('.pnav')?.append(toggle);}
  // Convert static reference links into keyboard-operable demo actions.
  $$('a').forEach(link=>{if(link.closest('dialog'))return;link.href='#';link.onclick=event=>{event.preventDefault();const text=link.textContent.trim().toLowerCase();
    if(/clear/.test(text)){chatContainer?.replaceChildren();transcript.length=0;toast('Demo conversation cleared.');}
    else if(/export/.test(text)){if(page==='assistant')exportText('homexo-demo-chat.txt',transcript.length?transcript.join('\n\n'):$$('.msg .bubble').map(n=>n.textContent).join('\n\n'));else exportText('homexo-demo-queue.txt',$$('.case').map(n=>n.textContent).join('\n\n'));}
    else if(/sign in|^home$|overview|my requests|^requests$|^account$/.test(text))navigate('customer');
    else if(/ai assistant|^ask$/.test(text))navigate('assistant');
    else if(/^dashboard$|ticket queue|^cases$/.test(text))navigate('staff');
    else if(/document|^docs$|upload|explain/.test(text))documents();
    else if(/rera|project/.test(text))rera();
    else if(/lawyer|consultation/.test(text))lawyer();
    else if(/new request|new ticket|get started|^start$|verify a property|packages/.test(text))enquiry();
    else if(/message/.test(text)){dialog.close();navigate('assistant');}
    else if(/join/.test(text))generic('Sample consultation','Your call is scheduled for 4:00 pm IST. The demo does not open a real meeting.');
    else if(/calendar|view all/.test(text))generic('November 2026 · sample calendar','Sample calls are scheduled on 3, 5, 9, 12, 13, 17, 20, 24 and 27 November. Select a marked day on the staff calendar to inspect it.');
    else if(/filter/.test(text))generic('Filter the sample queue','Use the case tabs or the search box to filter the sample cases. In the live workspace, service, assignee and status filters remain available.');
    else if(/update/.test(text))generic('Case HX-DEMO-104','Sample stage: lawyer review. The sale deed is received; the official EC search is pending. No real case is changed.');
    else if(/payment/.test(text))generic('Sample payments','Shield Pro · ₹9,999 paid. Name change affidavit · ₹1,200 due on approval. No real payment is processed.');
    else generic(link.textContent.trim()||'Sample action','This screen is part of the design review. The production workflow will be connected after the design is approved.');
  };});
  const cases=$$('.case');let currentTab='active';let query='';
  const empty=el('p','No sample cases match this view. Try Active cases or clear your search.','demo-empty');empty.hidden=true;cases[0]?.parentElement.append(empty);
  function filter(){let visible=0;cases.forEach((node,index)=>{let match=true;if(/complet/.test(currentTab))match=false;else if(/new/.test(currentTab))match=index===cases.length-1;else if(/waiting/.test(currentTab))match=index===1;match=match&&node.textContent.toLowerCase().includes(query.toLowerCase());node.hidden=!match;if(match)visible++;});empty.hidden=visible>0;}
  $$('.tabs').forEach(tabs=>{tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Case status');const items=Array.from(tabs.children);items.forEach((node,index)=>{const button=el('button',node.textContent,node.className);button.type='button';button.setAttribute('role','tab');button.setAttribute('aria-selected',node.classList.contains('on')?'true':'false');button.tabIndex=node.classList.contains('on')?0:-1;node.replaceWith(button);button.onclick=()=>{for(const sibling of tabs.children){sibling.classList.remove('on');sibling.setAttribute('aria-selected','false');sibling.tabIndex=-1;}button.classList.add('on');button.setAttribute('aria-selected','true');button.tabIndex=0;currentTab=button.textContent.toLowerCase();filter();};button.onkeydown=event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();let target=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowRight'?1:items.length-1))%items.length;tabs.children[target].click();tabs.children[target].focus();};});});
  const search=$('.search');if(search){const input=el('input');input.placeholder=search.textContent.replace('⌘K','').trim();input.setAttribute('aria-label','Search sample cases');search.replaceChildren(input,el('kbd','⌘K'));input.oninput=()=>{query=input.value;filter();};document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();input.focus();}});}
  $$('.cal span').filter(node=>/^\d+$/.test(node.textContent)).forEach(node=>{node.tabIndex=0;node.setAttribute('role','button');node.setAttribute('aria-label','November '+node.textContent+', 2026');node.onclick=()=>generic('November '+node.textContent+' · sample calls',node.classList.contains('has')?'Sample call: consultation with Asha Rao at 4:00 pm IST. No live calendar is connected.':'No sample calls on this day.');node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();node.click();}};});
  if($('.side')){const menu=action('☰',()=>{const side=$('.side');side.classList.toggle('demo-open');menu.setAttribute('aria-expanded',String(side.classList.contains('demo-open')));if(side.classList.contains('demo-open')){const backdrop=el('div','','demo-menu-backdrop');backdrop.onclick=closeMenu;document.body.append(backdrop);side.querySelector('a')?.focus();}else closeMenu();},'icon-btn demo-menu');menu.setAttribute('aria-label','Open navigation');menu.setAttribute('aria-expanded','false');$('.topbar')?.prepend(menu);function closeMenu(){ $('.side').classList.remove('demo-open');$('.demo-menu-backdrop')?.remove();menu.setAttribute('aria-expanded','false');menu.focus();}const closeButton=action('×',closeMenu,'icon-btn demo-drawer-close');closeButton.setAttribute('aria-label','Close navigation');$('.side').prepend(closeButton);document.addEventListener('keydown',event=>{if(!$('.side.demo-open'))return;if(event.key==='Escape')closeMenu();if(event.key==='Tab'){const stops=Array.from($('.side').querySelectorAll('a,button')).filter(n=>n.offsetParent!==null);const first=stops[0],last=stops[stops.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}});}
  if($('.pnav .links')){const links=$('.pnav .links'),menu=action('☰',()=>{links.classList.toggle('demo-public-open');menu.setAttribute('aria-expanded',String(links.classList.contains('demo-public-open')));},'icon-btn demo-menu');menu.setAttribute('aria-label','Open navigation');menu.setAttribute('aria-expanded','false');$('.pnav').append(menu);document.addEventListener('keydown',event=>{if(event.key==='Escape'){links.classList.remove('demo-public-open');menu.setAttribute('aria-expanded','false');}});}
  $$('.ai .rows .rowi').forEach(node=>{node.classList.add('demo-quick');node.tabIndex=0;node.setAttribute('role','button');node.onclick=()=>/rera/i.test(node.textContent)?rera():/document/i.test(node.textContent)?documents():/lawyer/i.test(node.textContent)?lawyer():enquiry();node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();node.click();}};});
  if(page==='customer'){
    const attention=$('.content .card .card-h + div');
    if(attention)Array.from(attention.children).forEach(node=>{node.classList.add('demo-clickable');node.tabIndex=0;node.setAttribute('role','button');const title=node.querySelector('b')?.textContent||'Attention item';node.setAttribute('aria-label',title);node.onclick=()=>/upload|khata/i.test(title)?documents():/call/i.test(title)?lawyer():generic('Sample preliminary report','Report preview: the sale deed was received, official searches remain pending and advocate review is required. This is fictional demo content.');node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();node.click();}};});
  }
  $$('.stat').forEach((node,index)=>{node.classList.add('demo-clickable');node.tabIndex=0;node.setAttribute('role','button');node.onclick=()=>{if(page==='customer'){if(index===1)documents();else if(index===2)lawyer();else generic(node.querySelector('small')?.textContent||'Sample summary','These summary values come from fictional sample data for the design review.');}else{currentTab=index===2?'waiting':'active';query='';if($('.search input'))$('.search input').value='';filter();toast('Sample queue view updated.');}};node.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();node.click();}};});
  $$('.nav.on,.mtabs .on').forEach(node=>node.setAttribute('aria-current','page'));
  const note=el('div','Interactive design demo · fictional people, cases and legal responses.','demo-frame-note');document.body.append(note);
})();
