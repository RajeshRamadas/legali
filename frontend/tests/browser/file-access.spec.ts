import AxeBuilder from "@axe-core/playwright";
import {test,expect,type BrowserContext} from "@playwright/test";

const record="af1251c4-0979-4c1a-86aa-601d77e75601",file="21e0044e-ea26-40f6-9793-e1088ea37289";
const row=(id:string,staff=false)=>({id,at:"2026-11-12T07:00:00Z",actor:staff?"Synthetic Administrator":"Verified customer",reader:staff?"staff":"customer",kind:staff?"preliminary_report":"document",ticket_number:"HX-FILE-FIXTURE",case_reference:record,file_reference:file});
async function fixtures(context:BrowserContext,mode="normal"){
  if(mode!=="signed-out")await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","file-access-browser-fixture-only"));
  const state={queries:[] as Record<string,string>[],writes:[] as string[],failNext:mode==="load"};
  await context.route("**/api/v1/**",route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});
    if(request.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(request.method()!=="GET")state.writes.push(path);
    if(path.endsWith("/auth/me"))return reply({id:"file-access-staff",name:"Synthetic Administrator",role:mode==="agent"?"agent":"admin",mfa_enabled:true,available_for_calls:false});
    if(path.endsWith("/admin/urgent")||path.endsWith("/case-alerts")||path.endsWith("/deadline-alerts"))return reply({items:[],unacknowledged:0});
    if(path==="/api/v1/admin/file-access"){
      const query=Object.fromEntries(url.searchParams);state.queries.push(query);
      if(state.failNext){state.failNext=false;return reply({detail:"File access lookup temporarily unavailable."},503);}
      const filtered=query.reader!=="all"||query.kind!=="all"||!!query.ticket_number;
      const items=query.ticket_number==="HX-NOBODY"?[]:query.cursor?[{...row("entry-old"),ticket_number:null,file_reference:null}]:filtered?[row("entry-filtered",true)]:[row("entry-new"),row("entry-staff",true)];
      return reply({items,next_cursor:query.cursor||filtered?null:"older-file-access-cursor",checked_at:"2026-11-12T07:01:00Z"});
    }
    return reply({detail:"No file access browser fixture"},503);
  });return state;
}

test("authorized file requests are accessible responsive and read only",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/file-access");
  const entries=page.getByRole("region",{name:"Authorized file requests",exact:true});
  await expect(entries.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
  await expect(entries.getByText("Synthetic Administrator",{exact:false})).toBeVisible();
  await entries.locator("summary").first().click();await expect(entries.getByText(file,{exact:true}).first()).toBeVisible();
  await expect(page.getByText("An entry confirms permission checks",{exact:false})).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);expect(state.queries).toHaveLength(1);expect(state.writes).toHaveLength(0);
  await page.evaluate(()=>{(document.activeElement as HTMLElement|null)?.blur();window.scrollTo(0,0);});
  await page.screenshot({path:test.info().outputPath("file-access-history.png"),fullPage:true});
});

test("reader file type case and India dates apply together after confirmation",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/file-access");await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
  await page.getByRole("combobox",{name:"Reader",exact:true}).selectOption("staff");await page.getByRole("combobox",{name:"File type",exact:true}).selectOption("preliminary_report");
  await page.getByRole("textbox",{name:"Case ticket number",exact:true}).fill(" hx-file-fixture ");await page.getByLabel("From date",{exact:true}).fill("2026-11-11");await page.getByLabel("To date",{exact:true}).fill("2026-11-12");
  expect(state.queries).toHaveLength(1);await page.getByRole("button",{name:"Apply file access filters",exact:true}).click();
  await expect.poll(()=>state.queries.length).toBe(2);expect(state.queries[1]).toEqual({reader:"staff",kind:"preliminary_report",ticket_number:"HX-FILE-FIXTURE",from_date:"2026-11-11",to_date:"2026-11-12"});
  await expect(page.locator(".activity-applied")).toContainText("Staff · Preliminary reports · Case HX-FILE-FIXTURE");await expect(page.getByRole("button",{name:"Older file access",exact:true})).toBeDisabled();
  await expect(page.getByText("Filter edits have not been applied. Refresh keeps your filter edits.",{exact:true})).toHaveCount(0);
});

test("paging keeps draft filters and caches newer pages",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/file-access");await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
  const draft=page.getByRole("textbox",{name:"Case ticket number",exact:true});await draft.fill("HX-DRAFT");
  await page.getByRole("button",{name:"Older file access",exact:true}).click();await expect(page.getByText("Case no longer available",{exact:true})).toBeVisible();await expect(draft).toHaveValue("HX-DRAFT");expect(state.queries[1]).toEqual({reader:"all",kind:"all",cursor:"older-file-access-cursor"});
  await page.getByRole("button",{name:"Newer file access",exact:true}).click();await expect(page.getByRole("heading",{name:"Preliminary report access authorized",exact:true})).toBeVisible();expect(state.queries).toHaveLength(2);
  await page.getByRole("button",{name:"Refresh file access history",exact:true}).click();await expect.poll(()=>state.queries.length).toBe(3);await expect(draft).toHaveValue("HX-DRAFT");expect(state.queries[2]).toEqual({reader:"all",kind:"all"});
});

test("failed refresh keeps previous results and draft edits until retry",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/file-access");await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
  const draft=page.getByRole("textbox",{name:"Case ticket number",exact:true});await draft.fill("HX-DRAFT");state.failNext=true;
  await page.getByRole("button",{name:"Refresh file access history",exact:true}).click();await expect(page.getByRole("alert").filter({hasText:"Could not load file access history"}).filter({hasText:"Could not load file access history"})).toBeFocused();
  await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();await expect(draft).toHaveValue("HX-DRAFT");
  await page.getByRole("button",{name:"Refresh file access history",exact:true}).click();await expect(page.getByRole("alert").filter({hasText:"Could not load file access history"})).toHaveCount(0);await expect(draft).toHaveValue("HX-DRAFT");
});

test("failed filter application retains the last applied scope",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/file-access");await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
  await page.getByRole("combobox",{name:"Reader",exact:true}).selectOption("staff");state.failNext=true;
  await page.getByRole("button",{name:"Apply file access filters",exact:true}).click();await expect(page.getByRole("alert").filter({hasText:"Could not load file access history"})).toBeVisible();await expect(page.locator(".activity-applied")).toContainText("All readers");
  await page.getByRole("button",{name:"Apply file access filters",exact:true}).click();await expect(page.locator(".activity-applied")).toContainText("Staff");
});

test("initial failure can be retried and empty results can be cleared",async({page,context})=>{
  await fixtures(context,"load");await page.goto("/admin/file-access");await expect(page.getByRole("alert").filter({hasText:"Could not load file access history"})).toBeVisible();
  await page.getByRole("button",{name:"Refresh file access history",exact:true}).click();await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
  await page.getByRole("textbox",{name:"Case ticket number",exact:true}).fill("HX-NOBODY");await page.getByRole("button",{name:"Apply file access filters",exact:true}).click();await expect(page.getByText("No recorded file access matches these filters.",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"Older file access",exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"Clear file access filters",exact:true}).click();await expect(page.getByRole("heading",{name:"Stored case file access authorized",exact:true})).toBeVisible();
});

for(const mode of ["agent","signed-out"]){test(`${mode} visitors do not query file access history`,async({page,context})=>{
  const state=await fixtures(context,mode);await page.goto("/admin/file-access");
  if(mode==="agent"){await expect(page.getByRole("heading",{name:"Administrator access required",exact:true})).toBeVisible();await expect(page.getByRole("link",{name:"File access history",exact:true})).toHaveCount(0);}
  else await expect(page.getByRole("button",{name:"Sign in",exact:true})).toBeVisible();
  expect(state.queries).toHaveLength(0);expect(state.writes).toHaveLength(0);
});}
