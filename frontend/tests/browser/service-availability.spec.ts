import AxeBuilder from "@axe-core/playwright";
import { test,expect,type BrowserContext } from "@playwright/test";

const service = {id:"service-fixture",slug:"title-verification",name:"Title Verification",category:"Buyers",description:"Synthetic service for browser checks.",property_types:["apartment"],active:true,paused:false,revision:1};
async function adminFixtures(context:BrowserContext,conflict=false,role="admin") {
  let current={...service}, writes=0;
  const history: {id:string;paused:boolean;revision:number;reason:string;actor:string;at:string}[]=[];
  await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","availability-browser-only"));
  await context.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname,method=route.request().method();
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,PATCH,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});
    if(method==="OPTIONS") return route.fulfill({headers,status:204});
    if(path==="/api/v1/auth/me")return reply({id:"staff-fixture",name:"Synthetic Administrator",role,mfa_enabled:true,available_for_calls:false});
    if(path==="/api/v1/admin/urgent")return reply({items:[]});
    if(path==="/api/v1/admin/case-alerts")return reply({items:[],total:0,unacknowledged:0,escalated:0});
    if(path==="/api/v1/admin/services")return reply({items:[current]});
    if(path==="/api/v1/admin/services/title-verification/history")return reply({items:history,total:history.length,page:1,page_size:20});
    if(path==="/api/v1/admin/services/title-verification"&&method==="PATCH"){
      writes++;const payload=route.request().postDataJSON();expect(payload.confirmed).toBe(true);expect(payload.revision).toBe(current.revision);
      if(conflict&&writes===1){current={...current,paused:true,revision:2};return reply({detail:"Service availability changed. Reload the catalogue before saving."},409);}
      current={...current,paused:payload.paused,revision:current.revision+1};history.unshift({id:`event-${writes}`,paused:current.paused,revision:current.revision,reason:payload.reason,actor:"Synthetic Administrator",at:"2026-11-10T05:00:00Z"});return reply(current);
    }
    return reply({detail:"No service availability fixture"},503);
  });
  return {writes:()=>writes};
}

test("administrator reviews a pause, resumes it and sees private history",async({page,context})=>{
  const state=await adminFixtures(context);await page.goto("/admin/services");
  await page.getByRole("textbox",{name:"Private operational reason"}).fill("Synthetic pilot capacity review.");
  await expect(page.getByRole("button",{name:"Pause new requests",exact:true})).toBeDisabled();expect(state.writes()).toBe(0);
  await page.getByRole("checkbox").check();await page.getByRole("button",{name:"Pause new requests",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"Service availability saved"})).toBeFocused();
  await expect(page.getByText("New requests paused",{exact:true})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Private availability history"})).toBeVisible();
  await expect(page.getByText("Synthetic pilot capacity review.",{exact:true})).toBeVisible();
  const report=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze();
  expect(report.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}))).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.getByRole("textbox",{name:"Private operational reason"}).fill("Synthetic capacity restored after review.");
  await page.getByRole("checkbox").check();await page.getByRole("button",{name:"Resume new requests",exact:true}).click();
  await expect(page.getByText("Accepting new requests",{exact:true})).toBeVisible();expect(state.writes()).toBe(2);
});

test("conflicting pause retains the private draft until explicit reload",async({page,context})=>{
  await adminFixtures(context,true);await page.goto("/admin/services");
  const reason=page.getByRole("textbox",{name:"Private operational reason"});await reason.fill("Synthetic unsaved operational reason.");await page.getByRole("checkbox").check();await page.getByRole("button",{name:"Pause new requests",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Service availability changed"})).toBeVisible();await expect(reason).toHaveValue("Synthetic unsaved operational reason.");
  await page.getByRole("button",{name:"Reload catalogue (replaces draft)",exact:true}).click();await expect(page.getByRole("button",{name:"Resume new requests",exact:true})).toBeVisible();await expect(reason).toHaveValue("");
});

test("agents cannot open availability controls",async({page,context})=>{
  await adminFixtures(context,false,"agent");await page.goto("/admin/services");await expect(page.getByRole("heading",{name:"Administrator access required"})).toBeVisible();await expect(page.getByRole("textbox",{name:"Private operational reason"})).toHaveCount(0);
});

test("callback preserves details and blocks an unavailable linked service",async({page,context})=>{
  await context.route("**/api/v1/**",route=>{
    const path=new URL(route.request().url()).pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type"};
    if(route.request().method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path==="/api/v1/services")return route.fulfill({headers,json:{items:[{...service,slug:"general-guidance",name:"General guidance"}]}});
    return route.fulfill({headers,status:503,json:{detail:"No callback availability fixture"}});
  });
  await page.goto("/?service=title-verification#callback");
  await page.getByRole("textbox",{name:"Full name",exact:true}).fill("Synthetic Customer");
  await expect(page.getByRole("button",{name:"Request free callback ↗",exact:true})).toBeDisabled();
  await expect(page.getByText(/This service is not accepting new requests/)).toBeVisible();
  await page.getByLabel("Service needed",{exact:true}).selectOption("general-guidance");
  await expect(page.getByRole("button",{name:"Request free callback ↗",exact:true})).toBeEnabled();
  await expect(page.getByRole("textbox",{name:"Full name",exact:true})).toHaveValue("Synthetic Customer");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test("paused consultations keep the profile visible without a new booking form",async({page,context})=>{
  let slotReads=0;
  await context.route("**/api/v1/**",route=>{
    const path=new URL(route.request().url()).pathname,headers={"access-control-allow-origin":"*"};
    if(path.endsWith("/slots"))slotReads++;
    if(path==="/api/v1/lawyers/fixture")return route.fulfill({headers,json:{id:"advocate-fixture",slug:"fixture",name:"Synthetic Advocate",initials:"SA",headline:"Property law",specialisations:[],experience_years:12,locality:null,city:"Bengaluru",languages:["English"],consultations:0,rating:null,review_count:0,bio:"",education:null,bar_enrolment:null,courts:[],hours:[],reviews:[],consultation_fee:1500,consultation_minutes:30,pay_online:false,next_available:null,booking_paused:true}});
    return route.fulfill({headers,status:503,json:{detail:"No consultation availability fixture"}});
  });
  await page.goto("/lawyers/fixture");await expect(page.getByRole("heading",{name:"Synthetic Advocate",exact:true})).toBeVisible();
  await expect(page.getByRole("status").filter({hasText:"New consultations are temporarily paused"})).toBeVisible();
  await expect(page.getByRole("button",{name:/Confirm booking/})).toHaveCount(0);expect(slotReads).toBe(0);
});

test("paused saved intake retains its answers and blocks submission until availability returns",async({page,context})=>{
  const profile={name:"Synthetic Customer",phone:"+919999900001",contact:"+919999900001",email:null};
  await context.addInitScript(profile=>localStorage.setItem("homexo.customer.session",JSON.stringify({token:"availability-customer-fixture",profile})),profile);
  await context.route("**/api/v1/**",route=>{
    const path=new URL(route.request().url()).pathname,headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type"};
    if(route.request().method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path==="/api/v1/account")return route.fulfill({headers,json:{profile,requests:[],bookings:[],payments:[],payments_mode:"off"}});
    if(path==="/api/v1/intake/drafts/draft-fixture")return route.fulfill({headers,json:{id:"draft-fixture",status:"draft",revision:2,service_available:false,answers:{service_slug:"title-verification",goal:"Keep my original property review details."},questions:[{key:"service_slug",prompt:"Service",kind:"select",required:true,help:"",options:[{value:"title-verification",label:"Title Verification"}]},{key:"goal",prompt:"Your goal",kind:"textarea",required:true,help:"",options:[]}],next_question:null,completed:2,total:2,updated_at:"2026-11-10T05:00:00Z",expires_at:"2026-12-10T05:00:00Z",ticket:null,notice:{version:"fixture-v1",submission:"I reviewed this synthetic submission notice."}}});
    return route.fulfill({headers,status:503,json:{detail:"No intake availability fixture"}});
  });
  await page.goto("/request?draft=draft-fixture");await expect(page.getByRole("status").filter({hasText:"Your saved answers are kept"})).toBeVisible();
  await expect(page.getByText("Keep my original property review details.",{exact:true})).toBeVisible();
  await page.getByRole("checkbox").check();await expect(page.getByRole("button",{name:"Create my request",exact:true})).toBeDisabled();
});
