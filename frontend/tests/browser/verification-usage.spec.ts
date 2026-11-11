import AxeBuilder from "@axe-core/playwright";
import {test,expect,type BrowserContext} from "@playwright/test";

const reference="af1251c4-0979-4c1a-86aa-601d77e75601";
const summary={attempts:26,succeeded:24,failed:1,unfinished:1,usage_reported:25,input_tokens:1000,output_tokens:50,known_estimated_usd:"0.000000000001",unpriced_attempts:1,average_duration_ms:1250};
const row={id:reference,job_id:reference,service_request_id:reference,provider:"anthropic",model:"fixture-model",step:"extract",status:"started",started_at:"2026-11-11T07:00:00Z",finished_at:null,duration_ms:null,input_tokens:null,output_tokens:null,cache_tokens:null,usage_complete:false,estimated_usd:null,estimate_reason:"attempt_unfinished",rate_version:"reviewed-fixture",error_category:null};
async function fixtures(context:BrowserContext,role="admin",empty=false,failInitial=false){
  await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","usage-browser-fixture-only"));
  const state={queries:[] as Record<string,string>[],writes:[] as string[],failNext:failInitial};
  await context.route("**/api/v1/**",route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});
    if(request.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(request.method()!=="GET")state.writes.push(path);
    if(path.endsWith("/auth/me"))return reply({id:"fixture-staff",name:"Fixture Administrator",role,mfa_enabled:true,available_for_calls:false});
    if(path.endsWith("/admin/urgent")||path.endsWith("/admin/case-alerts")||path.endsWith("/support-requests/deadline-alerts"))return reply({items:[],unacknowledged:0});
    if(path.endsWith("/admin/verification-usage")){
      const query=Object.fromEntries(url.searchParams);state.queries.push(query);
      if(state.failNext){state.failNext=false;return reply({detail:"Synthetic usage unavailable"},503);}
      return reply({items:empty?[]:[{...row,model:query.page==="2"?"older-fixture-model":"fixture-model"}],summary:empty?{...summary,attempts:0,known_estimated_usd:null}:summary,page:Number(query.page),page_size:25,checked_at:"2026-11-11T07:01:00Z",from_at:"2026-10-12T18:30:00Z",pricing:{status:"not_configured",version:null,models:0}});
    }
    return reply({detail:"No usage fixture"},503);
  });return state;
}

test("accessible usage view distinguishes known estimates and unfinished billing",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/ai-usage");
  const totals=page.getByRole("region",{name:"Usage totals",exact:true});
  await expect(totals).toContainText("< $0.000001 USD");await expect(totals).toContainText("1 attempt has no estimate");
  await expect(page.getByText("Unfinished · billing unknown",{exact:true})).toBeVisible();
  await page.getByText("Attempt references and estimate detail",{exact:true}).click();
  await expect(page.getByRole("region",{name:"Provider attempts",exact:true}).getByText(reference,{exact:true})).toHaveCount(3);
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect(state.queries).toHaveLength(1);expect(state.writes).toHaveLength(0);
  await page.screenshot({path:test.info().outputPath("verification-usage.png"),fullPage:true});
});

test("filters apply together and paging refresh retain unsaved filter edits",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/ai-usage");
  await expect(page.getByRole("button",{name:"Apply usage filters",exact:true})).toBeEnabled();
  await page.getByRole("combobox",{name:"Provider",exact:true}).selectOption("openai");
  await page.getByRole("combobox",{name:"Stage",exact:true}).selectOption("compare");
  await page.getByRole("combobox",{name:"Outcome",exact:true}).selectOption("failed");
  await page.getByRole("combobox",{name:"Window",exact:true}).selectOption("7");
  await page.getByText("Find a background job",{exact:true}).click();await page.getByRole("textbox",{name:"Job reference",exact:true}).fill(reference);
  expect(state.queries).toHaveLength(1);await page.getByRole("button",{name:"Apply usage filters",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"Usage refreshed"})).toBeFocused();
  expect(state.queries[1]).toEqual({provider:"openai",step:"compare",status:"failed",days:"7",job_id:reference,page:"1"});
  await page.getByRole("combobox",{name:"Provider",exact:true}).selectOption("anthropic");
  await page.getByRole("button",{name:"Next attempts",exact:true}).click();
  await expect(page.getByText("older-fixture-model",{exact:false})).toBeVisible();expect(state.queries[2]).toMatchObject({provider:"openai",page:"2"});
  await expect(page.getByRole("combobox",{name:"Provider",exact:true})).toHaveValue("anthropic");
  await page.getByRole("button",{name:"Refresh usage",exact:true}).click();await expect.poll(()=>state.queries.length).toBe(4);expect(state.queries[3]).toMatchObject({provider:"openai",page:"2"});
  await page.getByRole("button",{name:"Clear usage filters",exact:true}).click();await expect(page.getByRole("combobox",{name:"Provider",exact:true})).toHaveValue("all");
});

test("failed filter changes preserve labelled old totals and edits",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/ai-usage");
  await expect(page.getByRole("button",{name:"Apply usage filters",exact:true})).toBeEnabled();
  await page.getByRole("combobox",{name:"Provider",exact:true}).selectOption("openai");state.failNext=true;
  await page.getByRole("button",{name:"Apply usage filters",exact:true}).click();
  const alert=page.getByRole("alert").filter({hasText:"Could not load provider usage"});await expect(alert).toBeFocused();await expect(alert).toContainText("may be out of date");
  await expect(page.getByRole("region",{name:"Usage totals",exact:true})).toContainText("All providers");
  await expect(page.getByRole("combobox",{name:"Provider",exact:true})).toHaveValue("openai");
  await page.getByRole("button",{name:"Apply usage filters",exact:true}).click();await expect(alert).toHaveCount(0);
});

test("empty history has no guessed zero cost",async({page,context})=>{
  await fixtures(context,"admin",true);await page.goto("/admin/ai-usage");
  await expect(page.getByText("No provider attempts recorded.",{exact:true})).toBeVisible();
  await expect(page.getByText("No recorded provider attempts match these filters.",{exact:true})).toBeVisible();
  await expect(page.getByText("$0.00 USD",{exact:true})).toHaveCount(0);
});

test("initial lookup failure can be retried",async({page,context})=>{
  await fixtures(context,"admin",false,true);await page.goto("/admin/ai-usage");
  await expect(page.getByRole("alert").filter({hasText:"Could not load provider usage"})).toBeVisible();
  await page.getByRole("button",{name:"Refresh usage",exact:true}).click();await expect(page.getByRole("region",{name:"Usage totals",exact:true})).toBeVisible();
});

test("agents have no usage navigation or cross-case lookup",async({page,context})=>{
  const state=await fixtures(context,"agent");await page.goto("/admin/ai-usage");
  await expect(page.getByRole("heading",{name:"Administrator access required",exact:true})).toBeVisible();
  await expect(page.getByRole("link",{name:"Provider usage",exact:true})).toHaveCount(0);expect(state.queries).toHaveLength(0);
});
