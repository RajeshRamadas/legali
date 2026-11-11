import AxeBuilder from "@axe-core/playwright";
import {test,expect,type BrowserContext} from "@playwright/test";

const number="HX-AI-CONSENT-FIXTURE",profile={name:"Synthetic Customer",phone:"+919999900001",contact:"+919999900001",email:null};
async function fixtures(context:BrowserContext,mode="normal"){
  await context.addInitScript(({profile,number})=>{
    localStorage.setItem("homexo.customer.session",JSON.stringify({token:"consent-browser-fixture-only",profile}));
    sessionStorage.setItem("homexo.documents.ref",JSON.stringify({ticket_number:number,contact:profile.contact}));
  },{profile,number});
  const state={allowed:false,revision:0,canWithdraw:mode==="changed",writes:[] as Record<string,unknown>[],failNext:mode==="load",conflict:mode==="conflict",configured:mode!=="unavailable"&&mode!=="changed"};
  const ticket={ticket_number:number,service_name:"Synthetic due diligence",package:null,status:"submitted",status_label:"Received",created_at:"2026-11-12T07:00:00Z",history:[],messages:[],meetings:[],documents:[],report:null,document_request:null,can_upload:true,can_reply:true};
  await context.route("**/api/v1/**",route=>{
    const req=route.request(),path=new URL(req.url()).pathname,headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,POST,PUT,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});if(req.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path.endsWith("/account"))return reply({profile,requests:[],bookings:[],payments:[],payments_mode:"off"});
    if(path.endsWith("/support-requests/unread"))return reply({requests:0,unread_replies:0});
    if(path.endsWith("/tickets/lookup"))return reply(ticket);
    if(path.endsWith("/ai-processing")){
      if(req.method()==="GET"&&state.failNext){state.failNext=false;return reply({detail:"Synthetic consent lookup unavailable"},503);}
      if(req.method()==="PUT"){
        const body=req.postDataJSON();state.writes.push(body);
        if(state.conflict){state.conflict=false;state.revision++;return reply({detail:"The AI processing choice changed. Refresh and review again."},409);}
        if(body.revision!==state.revision)return reply({detail:"Stale revision"},409);
        state.allowed=body.allowed;state.canWithdraw=body.allowed;state.revision++;
      }
      return reply({status:state.allowed?"allowed":state.canWithdraw?"review_required":state.revision?"withdrawn":"not_allowed",allowed:state.allowed,revision:state.revision,can_withdraw:state.canWithdraw,changed_at:null,disclosure:{configured:state.configured,processor:state.configured?"Synthetic Processor":null,privacy_url:state.configured?"https://privacy.example.test/policy":null,notice_version:"external-document-ai-v1",processing_revision:state.configured?"reviewed-processor":null,paragraphs:["Document text and scanned page images may be sent to this processor. Advocate review remains required.","Withdraw permission for future requests. Requests already in progress cannot be recalled."]}});
    }
    return reply({detail:"No consent browser fixture"},503);
  });return state;
}

test("customer explicitly allows and withdraws per-case AI permission without losing an unsent reply",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/documents");const panel=page.getByRole("region",{name:"External AI processing",exact:true});
  const allow=panel.getByRole("button",{name:"Allow external AI processing",exact:true});await expect(allow).toBeDisabled();expect(state.writes).toHaveLength(0);
  await panel.getByText("Read what this permission covers",{exact:true}).click();await expect(panel).toContainText("scanned page images");
  await expect(panel.getByRole("link",{name:"Processor privacy policy",exact:true})).toHaveAttribute("href","https://privacy.example.test/policy");
  await page.getByText("Messages and case updates",{exact:true}).click();const reply=page.getByRole("textbox",{name:"Message the case team",exact:true});await reply.fill("Keep this unsent case reply.");
  await panel.getByRole("checkbox",{name:/I have read the notice/}).check();await allow.click();
  await expect(panel.getByRole("status").filter({hasText:"Permission saved"})).toBeFocused();await expect(reply).toHaveValue("Keep this unsent case reply.");
  expect(state.writes[0]).toEqual({allowed:true,revision:0,notice_version:"external-document-ai-v1",processing_revision:"reviewed-processor"});
  const withdraw=panel.getByRole("button",{name:"Withdraw AI permission",exact:true});await expect(withdraw).toBeDisabled();await panel.getByRole("checkbox",{name:/Withdraw permission for future/}).check();await withdraw.click();
  await expect(panel).toContainText("Permission withdrawn");await expect(reply).toHaveValue("Keep this unsent case reply.");expect(state.writes).toHaveLength(2);
});

test("choice view is accessible responsive and does not auto-enable processing",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/documents");const panel=page.getByRole("region",{name:"External AI processing",exact:true});
  await expect(panel.getByRole("checkbox",{name:/I have read the notice/})).not.toBeChecked();
  expect((await new AxeBuilder({page}).include(".ai-processing-choice").withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);expect(state.writes).toHaveLength(0);
  await page.screenshot({path:test.info().outputPath("case-ai-processing-choice.png"),fullPage:true});
});

test("stale confirmation is retained but cannot be resubmitted until refreshed and reviewed",async({page,context})=>{
  await fixtures(context,"conflict");await page.goto("/documents");const panel=page.getByRole("region",{name:"External AI processing",exact:true});
  const check=panel.getByRole("checkbox",{name:/I have read the notice/}),allow=panel.getByRole("button",{name:"Allow external AI processing",exact:true});
  await check.check();await allow.click();await expect(panel.getByRole("alert")).toBeFocused();await expect(check).toBeChecked();await expect(allow).toBeDisabled();
  await panel.getByRole("button",{name:"Refresh AI choice",exact:true}).click();await expect(check).not.toBeChecked();await expect(allow).toBeDisabled();
});

test("failed lookup can be retried without assuming permission",async({page,context})=>{
  await fixtures(context,"load");await page.goto("/documents");const panel=page.getByRole("region",{name:"External AI processing",exact:true});
  await expect(panel.getByRole("alert")).toBeVisible();await expect(panel.getByRole("button",{name:"Allow external AI processing",exact:true})).toHaveCount(0);
  await panel.getByRole("button",{name:"Refresh AI choice",exact:true}).click();await expect(panel).toContainText("Not allowed");
});

for(const mode of ["unavailable","changed"])test(`${mode}: incomplete processor information cannot grant and preserves withdrawal`,async({page,context})=>{
  const state=await fixtures(context,mode);await page.goto("/documents");const panel=page.getByRole("region",{name:"External AI processing",exact:true});
  await expect(panel).toContainText("Processor information is not available");await expect(panel.getByRole("button",{name:"Allow external AI processing",exact:true})).toHaveCount(0);
  if(mode==="changed"){
    await panel.getByRole("checkbox",{name:/Withdraw permission for future/}).check();await panel.getByRole("button",{name:"Withdraw AI permission",exact:true}).click();
    await expect(panel).toContainText("Permission withdrawn");expect(state.writes[0].allowed).toBe(false);
  }
});
