import AxeBuilder from "@axe-core/playwright";
import { test, expect, type BrowserContext } from "@playwright/test";

const firstId="416fb188-309e-4c19-94a4-e67d559219ce", secondId="516fb188-309e-4c19-94a4-e67d559219ce";
const admin={id:"8e45ea9a-e6f5-43dc-8dbf-11018d46dc21",name:"Fixture Administrator",active:true};

async function fixtures(context: BrowserContext, mode: "normal"|"failure"|"slow"|"agent"="normal") {
  await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","delivery-history-fixture-only"));
  let release=()=>{};
  const gate=new Promise<void>(resolve=>{release=resolve;});
  const state={reads:[] as string[],writes:0,release:()=>release()};
  const record=(id:string)=>({id,reference:"SR-"+id.replaceAll("-","").toUpperCase(),subject:id===firstId?"First support request":"Second support request",details:"Synthetic conversation for delivery history testing.",kind:"other",status:"in_progress",revision:4,
    customer_update_revision:1,customer_read_revision:0,unread_replies:1,ticket_number:null,created_at:"2026-11-11T06:00:00Z",updated_at:"2026-11-11T06:00:00Z",reply_due_at:null,resolved_at:null,overdue:false,assignee:admin,customer:{name:"Synthetic Customer",phone_last4:"0001"}});
  await context.route("**/api/v1/**",async route=>{
    const request=route.request(),url=new URL(request.url()),path=url.pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,status,json});
    if(request.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(request.method()!=="GET"){state.writes++;return reply({detail:"Unexpected browser fixture write"},400);}
    if(path.endsWith("/auth/me"))return reply({...admin,role:mode==="agent"?"agent":"admin",email:"fixture@example.invalid",available_for_calls:false,mfa_enabled:true});
    if(path.endsWith("/admin/urgent"))return reply({items:[]});
    if(path.endsWith("/admin/case-alerts")||path.endsWith("/support-requests/deadline-alerts"))return reply({items:[],unacknowledged:0});
    if(path.endsWith("/support-requests/owners"))return reply({items:[admin]});
    if(path.endsWith("/assignments")||path.endsWith("/messages"))return reply({items:[],total:0,page:1,page_size:20});
    if(path.endsWith("/deliveries")){
      state.reads.push(url.search);
      if(mode==="failure"&&state.reads.length===1)return reply({detail:"Delivery history unavailable"},503);
      const id=path.includes(firstId)?firstId:secondId;
      if(mode==="slow"&&id===firstId)await gate;
      const base=id===firstId?"11111111":"22222222";
      const all=Array.from({length:id===firstId?24:1},(_,index)=>({id:`${base}-0000-0000-0000-${String(index+1).padStart(12,"0")}`,event:index===0?"support_escalation":"customer_reply",recipient_kind:index===0?"administrator":"customer",recipient_name:index===0?"Fixture Administrator":"Customer",
        channel:index===0?"email":"sms",status:index===0?"failed":"cancelled",attempts:index===0?2:0,created_at:"2026-11-11T06:00:00Z",last_attempt_at:index===0?"2026-11-11T06:01:00Z":null,scheduled_for:null,delivered_at:null,reason:index===0?"Provider outcome uncertain; review before retrying":"Reply already read"}));
      const rows=all.filter(row=>(url.searchParams.get("status")==="all"||url.searchParams.get("status")===row.status)&&(url.searchParams.get("recipient")==="all"||url.searchParams.get("recipient")===row.recipient_kind)&&(url.searchParams.get("channel")==="all"||url.searchParams.get("channel")===row.channel));
      const page=Number(url.searchParams.get("page")||1);
      return reply({items:rows.slice((page-1)*20,page*20),total:rows.length,page,page_size:20,configuration:{customer_replies_enabled:false,staff_email:"unconfigured",channels:{email:false,sms:false,whatsapp:false}}});
    }
    if(path.endsWith(`/support-requests/${firstId}`))return reply(record(firstId));
    if(path.endsWith(`/support-requests/${secondId}`))return reply(record(secondId));
    if(path.endsWith("/admin/support-requests"))return reply({items:[record(firstId),record(secondId)],total:2,page:1,page_size:20,overdue:0,filtered_overdue:0});
    return reply({detail:"No delivery browser fixture"},503);
  });
  return state;
}

test("delivery filters, paging and refresh preserve unsent reply and private note",async({page,context})=>{
  const state=await fixtures(context);await page.goto(`/admin/support?request=${firstId}`);
  await page.getByLabel("Reply shown to customer").fill("Keep my unsent reply");
  await page.getByLabel("Internal note (administrators only)").fill("Keep my private draft");
  expect(state.reads).toHaveLength(0);
  await page.locator("summary").filter({hasText:"Delivery history"}).click();
  const history=page.getByRole("region",{name:"Support delivery history"});
  await expect(history.getByText("Provider outcome uncertain; review before retrying")).toBeVisible();
  await expect(history.getByText(/Staff email notices: not configured/)).toBeVisible();
  await history.getByRole("button",{name:"Next deliveries"}).click();
  await expect(history.getByText("Page 2 · 24 records")).toBeVisible();
  await history.getByLabel("Delivery status").selectOption("failed");
  await expect(history.getByRole("listitem")).toHaveCount(1);
  await history.getByLabel("Delivery recipient").selectOption("administrator");
  await history.getByLabel("Delivery channel").selectOption("email");
  await expect(history.getByText("Response target escalated",{exact:true})).toBeVisible();
  await history.getByRole("button",{name:"Refresh delivery history"}).click();
  await expect(history.getByRole("listitem")).toHaveCount(1);
  expect(state.reads.some(value=>value.includes("page=2"))).toBe(true);
  expect(state.reads.at(-1)).toContain("status=failed");
  await expect(page.getByLabel("Reply shown to customer")).toHaveValue("Keep my unsent reply");
  await expect(page.getByLabel("Internal note (administrators only)")).toHaveValue("Keep my private draft");
  expect(state.writes).toBe(0);
  const scan=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze();
  expect(scan.violations.map(row=>({id:row.id,nodes:row.nodes.map(node=>node.target)}))).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await history.screenshot({path:test.info().outputPath("support-delivery-history.png")});
  await history.getByLabel("Delivery status").selectOption("delivered");
  await expect(history.getByText("No delivery records match this view.")).toBeVisible();
});

test("history failure and explicit retry leave the conversation draft untouched",async({page,context})=>{
  const state=await fixtures(context,"failure");await page.goto(`/admin/support?request=${firstId}`);
  await page.getByLabel("Reply shown to customer").fill("A draft retained after a history error");
  await page.locator("summary").filter({hasText:"Delivery history"}).click();
  const history=page.getByRole("region",{name:"Support delivery history"});
  await expect(history.getByRole("alert")).toContainText("Delivery history unavailable");
  await history.getByRole("button",{name:"Refresh delivery history"}).click();
  await expect(history.getByText("Provider outcome uncertain; review before retrying")).toBeVisible();
  await expect(page.getByLabel("Reply shown to customer")).toHaveValue("A draft retained after a history error");
  expect(state.writes).toBe(0);expect(state.reads).toHaveLength(2);
});

test("a late response cannot replace another support request's delivery history",async({page,context})=>{
  const state=await fixtures(context,"slow");await page.goto(`/admin/support?request=${firstId}`);
  await page.locator("summary").filter({hasText:"Delivery history"}).click();
  await expect(page.getByText("Loading delivery history…")).toBeVisible();
  await page.getByRole("button",{name:/Second support request/}).click();
  await expect(page.getByRole("heading",{name:"Second support request",exact:true})).toBeVisible();
  await page.locator("summary").filter({hasText:"Delivery history"}).click();
  const history=page.getByRole("region",{name:"Support delivery history"});
  await expect(history.getByText(/22222222-0000-0000-0000-/)).toBeVisible();
  const old=page.waitForResponse(response=>response.url().includes(`${firstId}/deliveries`));
  state.release();await old;
  await expect(history.getByText(/11111111-0000-0000-0000-/)).toHaveCount(0);
  await expect(history.getByText(/22222222-0000-0000-0000-/)).toBeVisible();
  expect(state.writes).toBe(0);
});

test("agents cannot open administrator delivery controls",async({page,context})=>{
  const state=await fixtures(context,"agent");await page.goto("/admin/support");
  await expect(page.getByText(/Administrator access is required/)).toBeVisible();
  await expect(page.locator("summary").filter({hasText:"Delivery history"})).toHaveCount(0);
  expect(state.reads).toHaveLength(0);
});
