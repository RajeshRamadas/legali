import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const number="HX-JOB-FIXTURE", person={id:"fixture-staff",name:"Fixture Administrator",role:"admin",mfa_enabled:true,available_for_calls:false};
const job=()=>({id:"job-fixture",status:"queued",phase:"queued",created_at:"2026-11-11T07:00:00Z",state:"Karnataka",use_llm:false,run_id:null as string|null,message:null as string|null,can_cancel:true,usage:{attempts:0,succeeded:0,failed:0,unfinished:0,usage_reported:0,input_tokens:null as number|null,output_tokens:null as number|null,known_estimated_usd:null as string|null,unpriced_attempts:0,average_duration_ms:null as number|null}});
async function fixtures(context:BrowserContext,mode="normal"){
  await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","verification-job-browser-fixture-only"));
  const state={job:mode==="resume"?job():null as ReturnType<typeof job>|null,posts:[] as Record<string,unknown>[],failNext:false,failPost:false,denied:mode==="denied",customerAllowed:mode!=="no-consent"};
  const ticket={ticket_number:number,title:"Synthetic verification case",service_slug:"title-verification",service_name:"Title Verification",customer_name:"Fixture Customer",phone:"+919999900001",package:null,location:"Bengaluru",status:"submitted",status_label:"Received",priority:"normal",source:"website",needs_reply:false,
    created_at:"2026-11-11T07:00:00Z",updated_at:"2026-11-11T07:00:00Z",assignee:null,description:"Synthetic verification fixture",customer:{id:"customer",name:"Fixture Customer",phone:"+919999900001",email:null},property:{type:"apartment",location:"Bengaluru"},
    documents:[{id:"file-fixture",filename:"Synthetic deed.pdf",tag:"sale-deed",size:100,at:"2026-11-11T07:00:00Z",uploaded_by:"customer",download_url:null,scan_status:"clean",checksum_sha256:"a".repeat(64),note:null,check:null}],report:null,messages:[],meetings:[],notifications:[],events:[],verification_workflow:null,guided_request:null,chat_transcript:[],
    case:{milestones:[{key:"received",label:"Received",done:true,current:true}],current_milestone:"received",owner:null,team:[],tasks:[],open_tasks:0,overdue_tasks:0,fee:{status:"none",status_label:"Not quoted",quote:null,paid:null,paid_at:null,reference:null,note:null},closure:null,closed:null,allowed_statuses:["in_progress"],outcomes:[],deadlines:{due_at:null,first_response_due_at:null,first_response_at:null,overdue:false,first_response_missed:false,paused:false,paused_at:null}}};
  const run={id:"saved-run",created_at:"2026-11-11T07:01:00Z",state:"Karnataka",stale:false,verdict:"insufficient_evidence",reason:"Synthetic completed analysis still requires advocate review.",llm_status:"not_requested",provider:null,model:null,law_version:"fixture",documents:[],facts:[],findings:[],open_checks:[],trace:[],laws:[],limitations:[]};
  await context.route("**/api/v1/**",route=>{
    const req=route.request(),path=new URL(req.url()).pathname,headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,POST,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});if(req.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path.endsWith("/auth/me"))return reply(person);
    if(path.endsWith("/admin/urgent")||path.endsWith("/admin/case-alerts")||path.endsWith("/support-requests/deadline-alerts"))return reply({items:[],unacknowledged:0});
    if(path.endsWith("/admin/staff"))return reply({items:[person]});
    if(path.endsWith("/admin/meta"))return reply({statuses:[{value:"submitted",label:"Received"}],priorities:["normal"],notifications:{},meetings:{google_calendar:false,whatsapp:false,timezone:"Asia/Kolkata",reminder_minutes:[]}});
    if(path.endsWith(`/admin/tickets/${number}`))return state.denied?reply({detail:"Ticket not found"},404):reply(ticket);
    if(path.endsWith("/ai-processing"))return reply({allowed:state.customerAllowed,status:state.customerAllowed?"allowed":"not_allowed"});
    if(path.endsWith("/verification/config"))return reply({configured:true,provider:"synthetic-provider",model:"fixture-model",max_documents:10,max_pages_per_document:15,background_processing:true,configuration_revision:"configuration-reviewed"});
    if(path.endsWith("/verification/jobs")&&req.method()==="POST"){
      const body=req.postDataJSON();state.posts.push(body);if(state.failPost){state.failPost=false;return reply({detail:"Synthetic submission unavailable"},503);}
      state.job={...job(),state:body.state,use_llm:body.use_llm};return reply(state.job,202);
    }
    if(path.endsWith("/verification/jobs")){
      if(state.failNext){state.failNext=false;return reply({detail:"Synthetic status unavailable"},503);}return reply({items:state.job?[state.job]:[],page:1,page_size:20});
    }
    if(path.endsWith("/cancel")){if(state.job)state.job={...state.job,status:"cancelled",phase:"finished",can_cancel:false,message:"Cancelled. Any provider request already in progress cannot be recalled."};return reply(state.job);}
    if(path.endsWith("/verification"))return reply({items:state.job?.status==="completed"?[run]:[]});
    if(path.endsWith("/admin/report-template"))return reply({items:[],sources:[],disclaimer:"Synthetic fixture"});
    return reply({detail:"No background verification fixture"},503);
  });return state;
}

test("queues local analysis without a long request and shows accessible saved status",async({page,context})=>{
  const state=await fixtures(context);await page.goto(`/admin/tickets/${number}`);const panel=page.getByRole("region",{name:"Background analysis",exact:true});
  await expect(panel.getByRole("button",{name:"Queue verification",exact:true})).toBeEnabled();await panel.getByRole("button",{name:"Queue verification",exact:true}).click();
  await expect(panel.getByRole("heading",{name:"Queued · waiting for a worker",exact:true})).toBeVisible();expect(state.posts).toHaveLength(1);expect(state.posts[0].use_llm).toBe(false);
  await expect(panel.getByRole("button",{name:"Queue verification",exact:true})).toBeDisabled();
  expect((await new AxeBuilder({page}).include(".verification-panel").withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.evaluate(()=>{(document.activeElement as HTMLElement|null)?.blur();window.scrollTo(0,0);});
  await page.screenshot({path:test.info().outputPath("background-verification.png"),fullPage:true});
});

test("queued analysis survives navigation without resubmission",async({page,context})=>{
  const state=await fixtures(context,"resume");await page.goto(`/admin/tickets/${number}`);await expect(page.getByRole("heading",{name:"Queued · waiting for a worker",exact:true})).toBeVisible();
  await page.reload();await expect(page.getByRole("heading",{name:"Queued · waiting for a worker",exact:true})).toBeVisible();expect(state.posts).toHaveLength(0);
});

test("completion refreshes saved evidence without overwriting review notes",async({page,context})=>{
  const state=await fixtures(context,"resume");await page.goto(`/admin/tickets/${number}`);await expect(page.getByRole("button",{name:"Cancel analysis",exact:true})).toBeVisible();
  const reply=page.getByRole("textbox",{name:"Message to the customer",exact:true});await reply.fill("Keep this unsent case reply.");
  state.job={...job(),status:"completed",phase:"finished",run_id:"saved-run",can_cancel:false,usage:{attempts:2,succeeded:1,failed:1,unfinished:0,usage_reported:1,input_tokens:100,output_tokens:20,known_estimated_usd:"0.000320000000",unpriced_attempts:1,average_duration_ms:1200}};await page.getByRole("button",{name:"Refresh analysis jobs",exact:true}).click();
  await expect(page.getByText("Synthetic completed analysis still requires advocate review.",{exact:true})).toBeVisible();await expect(reply).toHaveValue("Keep this unsent case reply.");
  await expect(page.getByRole("region",{name:"Background analysis",exact:true})).toContainText("100 input · 20 output");
  await expect(page.getByRole("region",{name:"Background analysis",exact:true})).toContainText("$0.00032 USD");
});

test("cancellation stops active job status and retry only reviews settings",async({page,context})=>{
  const state=await fixtures(context,"resume");await page.goto(`/admin/tickets/${number}`);await page.getByRole("button",{name:"Cancel analysis",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Cancelled",exact:true})).toBeVisible();await page.getByRole("button",{name:"Review a new analysis",exact:true}).click();expect(state.posts).toHaveLength(0);
  await expect(page.getByRole("checkbox",{name:/I am authorised/})).toHaveCount(0);
});

test("LLM submission requires current explicit consent",async({page,context})=>{
  const state=await fixtures(context);await page.goto(`/admin/tickets/${number}`);await page.getByRole("checkbox",{name:/Use LLM evidence analysis/}).check();
  const queue=page.getByRole("button",{name:"Queue verification",exact:true});await expect(queue).toBeDisabled();await page.getByRole("checkbox",{name:/I am authorised/}).check();await queue.click();
  await expect(page.getByRole("heading",{name:"Queued · waiting for a worker",exact:true})).toBeVisible();expect(state.posts[0]).toMatchObject({use_llm:true,consent_to_external_processing:true,configuration_revision:"configuration-reviewed"});
});

test("failed submission keeps settings and reuses its idempotency reference",async({page,context})=>{
  const state=await fixtures(context);await page.goto(`/admin/tickets/${number}`);state.failPost=true;await page.getByRole("button",{name:"Queue verification",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Synthetic submission unavailable"})).toBeVisible();await page.getByRole("button",{name:"Refresh analysis jobs",exact:true}).click();await page.getByRole("button",{name:"Queue verification",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Queued · waiting for a worker",exact:true})).toBeVisible();expect(state.posts).toHaveLength(2);expect(state.posts[0].submission_key).toBe(state.posts[1].submission_key);
});

test("status refresh failure retains settings and labels old jobs",async({page,context})=>{
  const state=await fixtures(context,"resume");await page.goto(`/admin/tickets/${number}`);const field=page.getByRole("textbox",{name:"Property state / union territory",exact:true});await field.fill("Kerala");state.failNext=true;
  await page.getByRole("button",{name:"Refresh analysis jobs",exact:true}).click();await expect(page.getByRole("alert").filter({hasText:"Synthetic status unavailable"})).toContainText("may be out of date");await expect(field).toHaveValue("Kerala");
});

test("inaccessible cases show no background analysis controls",async({page,context})=>{
  await fixtures(context,"denied");await page.goto(`/admin/tickets/${number}`);await expect(page.getByRole("region",{name:"Background analysis",exact:true})).toHaveCount(0);await expect(page.getByText("Ticket not found",{exact:false}).first()).toBeVisible();
});


test("customer permission blocks LLM selection and refreshing it keeps case reply drafts",async({page,context})=>{
  const state=await fixtures(context,"no-consent");await page.goto(`/admin/tickets/${number}`);
  const llm=page.getByRole("checkbox",{name:/Use LLM evidence analysis/});
  await expect(llm).toBeDisabled();await expect(page.getByRole("region",{name:"Customer AI permission",exact:true})).toContainText("Customer permission is required");
  const reply=page.getByRole("textbox",{name:"Message to the customer",exact:true});await reply.fill("Keep this unsent case reply.");
  state.customerAllowed=true;await page.getByRole("button",{name:"Refresh customer AI permission",exact:true}).click();
  await expect(llm).toBeEnabled();await expect(reply).toHaveValue("Keep this unsent case reply.");expect(state.posts).toHaveLength(0);
});
