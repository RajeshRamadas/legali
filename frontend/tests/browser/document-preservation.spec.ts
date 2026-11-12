import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const number="HX-JOB-FIXTURE", person={id:"fixture-staff",name:"Fixture Administrator",role:"admin",mfa_enabled:true,available_for_calls:false};
const job=()=>({id:"job-fixture",status:"queued",phase:"queued",created_at:"2026-11-11T07:00:00Z",state:"Karnataka",use_llm:false,run_id:null as string|null,message:null as string|null,can_cancel:true,usage:{attempts:0,succeeded:0,failed:0,unfinished:0,usage_reported:0,input_tokens:null as number|null,output_tokens:null as number|null,known_estimated_usd:null as string|null,unpriced_attempts:0,average_duration_ms:null as number|null}});
async function fixtures(context:BrowserContext,mode="normal"){
  await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","verification-job-browser-fixture-only"));
  const state={hold:{held:false,revision:0,can_manage:mode!=="agent",changed_at:null as string|null,reason:null as string|null,note:"",history:[] as {id:string;held:boolean;at:string;actor:string;reason:string;note:string}[]},failHold:false,conflict:false,holdWrites:[] as Record<string,unknown>[],queueQueries:[] as Record<string,string>[],failQueue:false,job:mode==="resume"?job():null as ReturnType<typeof job>|null,posts:[] as Record<string,unknown>[],failNext:false,failPost:false,denied:mode==="denied",customerAllowed:mode!=="no-consent"};
  const ticket={ticket_number:number,title:"Synthetic verification case",service_slug:"title-verification",service_name:"Title Verification",customer_name:"Fixture Customer",phone:"+919999900001",package:null,location:"Bengaluru",status:"submitted",status_label:"Received",priority:"normal",source:"website",needs_reply:false,
    created_at:"2026-11-11T07:00:00Z",updated_at:"2026-11-11T07:00:00Z",assignee:null,description:"Synthetic verification fixture",customer:{id:"customer",name:"Fixture Customer",phone:"+919999900001",email:null},property:{type:"apartment",location:"Bengaluru"},
    documents:[{id:"file-fixture",filename:"Synthetic deed.pdf",tag:"sale-deed",size:100,at:"2026-11-11T07:00:00Z",uploaded_by:"customer",download_url:null,scan_status:"clean",checksum_sha256:"a".repeat(64),note:null,check:null}],report:null,messages:[],meetings:[],notifications:[],events:[],verification_workflow:null,guided_request:null,chat_transcript:[],
    case:{milestones:[{key:"received",label:"Received",done:true,current:true}],current_milestone:"received",owner:null,team:[],tasks:[],open_tasks:0,overdue_tasks:0,fee:{status:"none",status_label:"Not quoted",quote:null,paid:null,paid_at:null,reference:null,note:null},closure:null,closed:null,allowed_statuses:["in_progress"],outcomes:[],deadlines:{due_at:null,first_response_due_at:null,first_response_at:null,overdue:false,first_response_missed:false,paused:false,paused_at:null}}};
  const run={id:"saved-run",created_at:"2026-11-11T07:01:00Z",state:"Karnataka",stale:false,verdict:"insufficient_evidence",reason:"Synthetic completed analysis still requires advocate review.",llm_status:"not_requested",provider:null,model:null,law_version:"fixture",documents:[],facts:[],findings:[],open_checks:[],trace:[],laws:[],limitations:[]};
  await context.route("**/api/v1/**",route=>{
    const req=route.request(),path=new URL(req.url()).pathname,headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,POST,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});if(req.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path.endsWith("/auth/me"))return reply({...person,role:mode==="agent"?"agent":"admin"});
    if(path.endsWith("/admin/urgent")||path.endsWith("/admin/case-alerts")||path.endsWith("/support-requests/deadline-alerts"))return reply({items:[],unacknowledged:0});
    if(path.endsWith("/admin/staff"))return reply({items:[person]});
    if(path.endsWith("/admin/meta"))return reply({statuses:[{value:"submitted",label:"Received"}],priorities:["normal"],notifications:{},meetings:{google_calendar:false,whatsapp:false,timezone:"Asia/Kolkata",reminder_minutes:[]}});
    if(path.endsWith(`/admin/tickets/${number}`))return state.denied?reply({detail:"Ticket not found"},404):reply(ticket);
    if(path.endsWith("/document-hold")){
      if(state.failHold){state.failHold=false;return reply({detail:"Synthetic hold unavailable"},503);}
      if(req.method()==="PUT"){
        const body=req.postDataJSON();state.holdWrites.push(body);
        if(state.conflict){state.conflict=false;state.hold={...state.hold,held:true,revision:state.hold.revision+1};return reply({detail:"The preservation decision changed. Refresh before saving."},409);}
        state.hold={...state.hold,held:body.held,revision:state.hold.revision+1,changed_at:"2026-11-12T07:00:00Z",reason:body.reason,note:body.note,history:[{id:String(state.hold.revision+1),held:body.held,at:"2026-11-12T07:00:00Z",actor:"Fixture Administrator",reason:body.reason,note:body.note},...state.hold.history]};
      }
      return reply(state.hold);
    }
    if(path.endsWith("/document-holds")){
      const query=Object.fromEntries(new URL(req.url()).searchParams);state.queueQueries.push(query);
      if(state.failQueue){state.failQueue=false;return reply({detail:"Synthetic queue unavailable"},503);}
      return reply({items:[{ticket_number:query.page==="2"?"HX-OLDER-PRESERVATION":number,held:query.status!=="released",reason:"privacy_review",revision:1,changed_at:"2026-11-12T07:00:00Z"}],total:26,active_count:2,page:Number(query.page),page_size:25,checked_at:"2026-11-12T07:00:00Z"});
    }
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



test("administrator places and releases a file hold without losing an unsent case reply",async({page,context})=>{
  const state=await fixtures(context);await page.goto(`/admin/tickets/${number}`);
  const panel=page.getByRole("region",{name:"Document preservation",exact:true});
  await expect(panel).toContainText("No active preservation hold");
  const reply=page.getByRole("textbox",{name:"Message to the customer",exact:true});await reply.fill("Keep this unsent case reply.");
  const place=panel.getByRole("button",{name:"Place document hold",exact:true});await expect(place).toBeDisabled();
  await panel.getByRole("combobox",{name:"Review reason",exact:true}).selectOption("privacy_review");
  await panel.getByRole("textbox",{name:"Administrator review note",exact:true}).fill("PRIVATE synthetic review preserves these files.");
  await panel.getByRole("checkbox").check();await place.click();
  await expect(panel).toContainText("Preservation hold active");await expect(reply).toHaveValue("Keep this unsent case reply.");
  await expect(page.locator(".casefile").getByRole("button",{name:"Remove",exact:true})).toHaveCount(0);
  expect(state.holdWrites[0]).toMatchObject({held:true,revision:0,reason:"privacy_review"});
  expect((await new AxeBuilder({page}).include(".document-preservation").withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await panel.getByRole("combobox",{name:"Review reason",exact:true}).selectOption("manual_review");
  await panel.getByRole("textbox",{name:"Administrator review note",exact:true}).fill("PRIVATE reviewed release after records assessment.");
  await panel.getByRole("checkbox").check();await panel.getByRole("button",{name:"Release document hold",exact:true}).click();
  await expect(panel).toContainText("No active preservation hold");await expect(reply).toHaveValue("Keep this unsent case reply.");expect(state.holdWrites).toHaveLength(2);
});

test("stale decision preserves the review draft and requires renewed confirmation",async({page,context})=>{
  const state=await fixtures(context);await page.goto(`/admin/tickets/${number}`);const panel=page.getByRole("region",{name:"Document preservation",exact:true});
  await panel.getByRole("combobox",{name:"Review reason",exact:true}).selectOption("privacy_review");
  const note=panel.getByRole("textbox",{name:"Administrator review note",exact:true});await note.fill("Keep this preservation review draft after a conflict.");await panel.getByRole("checkbox").check();state.conflict=true;
  await panel.getByRole("button",{name:"Place document hold",exact:true}).click();await expect(panel.getByRole("alert")).toBeFocused();await expect(note).toHaveValue("Keep this preservation review draft after a conflict.");
  await panel.getByRole("button",{name:"Refresh preservation status",exact:true}).click();await expect(panel).toContainText("Preservation hold active");await expect(note).toHaveValue("Keep this preservation review draft after a conflict.");await expect(panel.getByRole("checkbox")).not.toBeChecked();
});

test("case agents have read-only preservation status and no cross-case queue",async({page,context})=>{
  const state=await fixtures(context,"agent");state.hold.held=true;await page.goto(`/admin/tickets/${number}`);
  const panel=page.getByRole("region",{name:"Document preservation",exact:true});await expect(panel).toContainText("Preservation hold active");await expect(panel.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("link",{name:"Document holds",exact:true})).toHaveCount(0);
  await page.goto("/admin/document-holds");await expect(page.getByRole("heading",{name:"Administrator access required",exact:true})).toBeVisible();expect(state.queueQueries).toHaveLength(0);expect(state.holdWrites).toHaveLength(0);
});

test("administrator queue filters apply explicitly and paging preserves edits",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/document-holds");
  await expect(page.getByRole("link",{name:number,exact:true})).toBeVisible();
  await page.getByRole("combobox",{name:"Hold status",exact:true}).selectOption("released");await page.getByRole("combobox",{name:"Review reason",exact:true}).selectOption("privacy_review");
  const query=page.getByRole("textbox",{name:"Ticket number",exact:true});await query.fill("HX-");expect(state.queueQueries).toHaveLength(1);
  await page.getByRole("button",{name:"Apply preservation filters",exact:true}).click();await expect.poll(()=>state.queueQueries.length).toBe(2);expect(state.queueQueries[1]).toEqual({status:"released",reason:"privacy_review",q:"HX-",page:"1"});
  await query.fill("Keep this filter edit");await page.getByRole("button",{name:"Next decisions",exact:true}).click();await expect(page.getByRole("link",{name:"HX-OLDER-PRESERVATION",exact:true})).toBeVisible();await expect(query).toHaveValue("Keep this filter edit");expect(state.queueQueries[2]).toMatchObject({q:"HX-",page:"2"});
});

test("failed queue refresh keeps its labelled snapshot and unapplied filters",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/document-holds");await expect(page.getByRole("link",{name:number,exact:true})).toBeVisible();
  await page.getByRole("textbox",{name:"Ticket number",exact:true}).fill("Keep this draft");state.failQueue=true;await page.getByRole("button",{name:"Refresh preservation queue",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Could not load preservation"})).toContainText("may be out of date");await expect(page.getByRole("textbox",{name:"Ticket number",exact:true})).toHaveValue("Keep this draft");await expect(page.getByRole("link",{name:number,exact:true})).toBeVisible();
});

test("preservation queue has accessible responsive navigation",async({page,context})=>{
  await fixtures(context);await page.goto("/admin/document-holds");await expect(page.getByRole("link",{name:number,exact:true})).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:test.info().outputPath("document-preservation-queue.png"),fullPage:true});
});
