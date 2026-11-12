import AxeBuilder from "@axe-core/playwright";
import {test,expect,type BrowserContext} from "@playwright/test";
import {readFile} from "node:fs/promises";

const profile={name:"Synthetic Customer",phone:"+919999900001",contact:"9999900001",email:"customer@example.test"};
const counts={requests:2,meetings:0,payments:0};
const manifest={format_version:"homexo-account-summary-v1",counts,limits:{requests:1000,meetings:2000,payments:2000},ready:true,sections:["profile","notification_preferences","requests","meetings","payments"],excluded:["internal_notes","document_contents"],checked_at:"2026-11-12T07:00:00Z"};
const summary={format_version:manifest.format_version,generated_at:manifest.checked_at,scope:"current_account_activity_summary",counts,sections:manifest.sections,excluded:manifest.excluded,
  profile:{name:profile.name,email:profile.email,verified_phone:profile.contact,account_created_at:manifest.checked_at,profile_updated_at:manifest.checked_at},
  notification_preferences:{email:true,sms:false,whatsapp:true,revision:1,updated_at:manifest.checked_at},
  requests:["HX-SUMMARY-ONE","HX-SUMMARY-TWO"].map(ticket_number=>({ticket_number,title:"Synthetic request",service_name:"Synthetic due diligence",package:null,status:"submitted",status_label:"Received",created_at:manifest.checked_at,updated_at:manifest.checked_at,document_count:0,document_preservation_active:false,external_document_ai:{status:"not_allowed",changed_at:null}})),meetings:[],payments:[]};

async function fixtures(context:BrowserContext,mode="normal"){
  if(mode!=="signed-out")await context.addInitScript(profile=>localStorage.setItem("homexo.customer.session",JSON.stringify({token:"summary-browser-fixture-only",profile})),profile);
  let release:(()=>void)|null=null;const held=new Promise<void>(resolve=>{release=resolve;});
  const state={downloads:0,reads:0,failRead:mode==="load",failDownload:mode==="download",slow:mode==="slow",release:()=>release?.()};
  await context.route("**/api/v1/**",async route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,OPTIONS","access-control-expose-headers":"retry-after"};
    const reply=(json:unknown,status=200,extra={})=>route.fulfill({headers:{...headers,...extra},status,json});
    if(request.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path.endsWith("/account"))return reply({profile,requests:[],bookings:[],payments:[],payments_mode:"off"});
    if(path.endsWith("/support-requests/unread"))return reply({requests:0,unread_replies:0});
    if(path.endsWith("/data-summary/download")){
      state.downloads++;expect(request.headers()["authorization"]).toBe("Bearer summary-browser-fixture-only");
      if(state.slow)await held;
      if(state.failDownload){state.failDownload=false;return reply({detail:"Synthetic summary preparation unavailable"},503);}
      if(mode==="rate")return reply({detail:"Please wait before preparing another summary"},429,{"retry-after":"2"});
      return reply(summary,200,{"content-disposition":"attachment; filename=homexo-account-summary.json","cache-control":"private, no-store"});
    }
    if(path.endsWith("/data-summary")){
      state.reads++;if(state.failRead){state.failRead=false;return reply({detail:"Synthetic summary counts unavailable"},503);}
      return reply(mode==="over-limit"?{...manifest,ready:false,counts:{...counts,requests:1001}}:manifest);
    }
    return reply({detail:"No account summary browser fixture"},503);
  });return state;
}

test("verified customer explicitly downloads a private JSON summary",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/account/data");
  const download=page.getByRole("button",{name:"Download account summary (JSON)",exact:true});await expect(download).toBeEnabled();expect(state.downloads).toBe(0);
  const received=page.waitForEvent("download");await download.click();const file=await received;
  expect(file.suggestedFilename()).toBe("homexo-account-summary.json");const saved=await file.path();expect(saved).not.toBeNull();const data=JSON.parse(await readFile(saved!,"utf8"));
  expect(data.profile.verified_phone).toBe(profile.contact);expect(data.requests).toHaveLength(2);expect(data.excluded).toContain("internal_notes");
  await expect(page.getByRole("status").filter({hasText:"download has started"})).toBeFocused();expect(state.downloads).toBe(1);
});

test("summary page is accessible responsive and explains its coverage",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/account/data");await expect(page.getByRole("region",{name:"Summary coverage",exact:true})).toBeVisible();
  await expect(page.getByRole("link",{name:"Use Privacy requests",exact:true})).toHaveAttribute("href","/account/privacy");
  await expect(page.getByText(/IST\. Your download uses/)).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);expect(state.downloads).toBe(0);
  await page.screenshot({path:test.info().outputPath("account-summary.png"),fullPage:true});
});

test("failed download keeps counts and requires refresh before deliberate retry",async({page,context})=>{
  const state=await fixtures(context,"download");await page.goto("/account/data");const button=page.getByRole("button",{name:"Download account summary (JSON)",exact:true});await expect(button).toBeEnabled();await button.click();
  await expect(page.getByRole("alert").filter({hasText:"Could not prepare"})).toBeFocused();await expect(page.getByRole("region",{name:"Summary coverage",exact:true})).toBeVisible();await expect(button).toBeDisabled();
  await page.getByRole("button",{name:"Refresh summary information",exact:true}).click();await expect(button).toBeEnabled();
  const received=page.waitForEvent("download");await button.click();await received;expect(state.downloads).toBe(2);
});

test("initial failure can be refreshed and large accounts do not receive shortened files",async({page,context})=>{
  await fixtures(context,"load");await page.goto("/account/data");await expect(page.getByRole("alert").filter({hasText:"Could not prepare"})).toBeVisible();
  await page.getByRole("button",{name:"Refresh summary information",exact:true}).click();await expect(page.getByRole("button",{name:"Download account summary (JSON)",exact:true})).toBeEnabled();
});

test("over-limit accounts are directed to reviewed access without downloading",async({page,context})=>{
  const state=await fixtures(context,"over-limit");await page.goto("/account/data");await expect(page.getByText(/no shortened download will be substituted/)).toBeVisible();
  await expect(page.getByRole("button",{name:"Download account summary (JSON)",exact:true})).toBeDisabled();expect(state.downloads).toBe(0);
});

test("rate limits delay refresh and never start a file download",async({page,context})=>{
  const state=await fixtures(context,"rate");await page.goto("/account/data");const button=page.getByRole("button",{name:"Download account summary (JSON)",exact:true});await expect(button).toBeEnabled();await button.click();
  await expect(page.getByRole("alert").filter({hasText:"Could not prepare"})).toBeVisible();await expect(button).toBeDisabled();await expect(page.getByRole("button",{name:/Try again in \d+s/})).toBeDisabled();expect(state.downloads).toBe(1);
});

test("a session change during preparation discards the summary",async({page,context})=>{
  const state=await fixtures(context,"slow");const files:string[]=[];page.on("download",file=>files.push(file.suggestedFilename()));await page.goto("/account/data");
  const button=page.getByRole("button",{name:"Download account summary (JSON)",exact:true});await expect(button).toBeEnabled();await button.click();await expect.poll(()=>state.downloads).toBe(1);
  await page.evaluate(()=>localStorage.setItem("homexo.customer.session",JSON.stringify({token:"changed-session-token",profile:{name:"Changed session",contact:"9999900001"}})));
  state.release();await expect(page.getByRole("alert").filter({hasText:"Your sign-in changed"})).toBeVisible();expect(files).toEqual([]);
});

test("signed-out visitors are asked to verify without reading summary records",async({page,context})=>{
  const state=await fixtures(context,"signed-out");await page.goto("/account/data");await expect(page.getByRole("button",{name:"Download account summary (JSON)",exact:true})).toHaveCount(0);
  await expect(page.getByText("Sign in with your verified phone to download a summary of your own account.",{exact:true})).toBeVisible();expect(state.reads).toBe(0);expect(state.downloads).toBe(0);
});
