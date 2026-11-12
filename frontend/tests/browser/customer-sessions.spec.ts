import AxeBuilder from "@axe-core/playwright";
import {test,expect,type BrowserContext} from "@playwright/test";

const current="eb94ba02-a3c4-4948-904b-6a77a3bfb73a",other="32fc1443-7ccd-425e-a6ea-e5b04ea197fb";
const profile={name:"Synthetic Customer",phone:"+919999900001",contact:"9999900001",email:null};
const row=(id:string,is_current:boolean)=>({id,is_current,browser:is_current?"Chrome":"Safari",device:is_current?"Windows":"iPhone or iPad",created_at:"2026-11-12T07:00:00Z",last_seen_at:"2026-11-12T07:01:00Z",expires_at:"2026-12-12T07:00:00Z"});
async function fixtures(context:BrowserContext,mode="normal"){
  if(mode!=="signed-out")await context.addInitScript(profile=>localStorage.setItem("homexo.customer.session",JSON.stringify({token:"sessions-browser-fixture-only",profile})),profile);
  const state={items:[row(current,true),row(other,false)],reads:0,actions:[] as string[],failRead:mode==="load",failAction:mode==="failure"};
  await context.route("**/api/v1/**",route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,POST,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});
    if(request.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path.endsWith("/account"))return reply({profile,requests:[],bookings:[],payments:[],payments_mode:"off"});
    if(path.endsWith("/support-requests/unread"))return reply({requests:0,unread_replies:0});
    if(path.endsWith("/account/sessions")){
      state.reads++;if(state.failRead){state.failRead=false;return reply({detail:"Synthetic session lookup unavailable"},503);}
      return reply({items:state.items,checked_at:"2026-11-12T07:02:00Z",max_active:20,activity_interval_seconds:300});
    }
    if(path.includes("/sessions/")||path.endsWith("/account/logout")){
      state.actions.push(path);expect(request.headers()["authorization"]).toBe("Bearer sessions-browser-fixture-only");
      if(state.failAction){state.failAction=false;return reply({detail:"Synthetic session revocation unavailable"},503);}
      if(path.endsWith("/revoke-others")){const count=state.items.filter(item=>!item.is_current).length;state.items=state.items.filter(item=>item.is_current);return reply({revoked:count});}
      const id=path.endsWith("/account/logout")?current:path.split("/").at(-2);
      state.items=state.items.filter(item=>item.id!==id);return reply({revoked:true,current:id===current});
    }
    return reply({detail:"No customer sessions browser fixture"},503);
  });return state;
}

test("session page is accessible responsive and only shows safe sign-in hints",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/account/security");await expect(page.getByText("This session",{exact:true})).toBeVisible();await expect(page.getByRole("heading",{name:"Safari · iPhone or iPad",exact:true})).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);expect(state.actions).toHaveLength(0);
  await page.screenshot({path:test.info().outputPath("customer-sessions.png"),fullPage:true});
});

test("customer explicitly confirms ending another session",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/account/security");const article=page.getByRole("article",{name:"Safari on iPhone or iPad",exact:true});
  await article.getByRole("button",{name:"End session",exact:true}).click();expect(state.actions).toHaveLength(0);
  await article.getByRole("button",{name:"Keep session",exact:true}).click();expect(state.actions).toHaveLength(0);
  await article.getByRole("button",{name:"End session",exact:true}).click();await article.getByRole("button",{name:"Confirm end session",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"selected session has been ended"})).toBeFocused();await expect(article).toHaveCount(0);await expect(page.getByText("This session",{exact:true})).toBeVisible();expect(state.actions[0]).toContain(other);
});

test("ending all other sessions keeps the current session",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/account/security");await page.getByRole("button",{name:"Sign out other sessions",exact:true}).click();expect(state.actions).toHaveLength(0);
  await page.getByRole("button",{name:"Confirm sign out other sessions",exact:true}).click();await expect(page.getByRole("heading",{name:"Safari · iPhone or iPad",exact:true})).toHaveCount(0);await expect(page.getByText("This session",{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>!!localStorage.getItem("homexo.customer.session"))).toBe(true);
});

test("ending this session clears the local sign-in only after success",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/account/security");const article=page.getByRole("article",{name:"Chrome on Windows, current session",exact:true});
  await article.getByRole("button",{name:"Sign out this session",exact:true}).click();await article.getByRole("button",{name:"Confirm end session",exact:true}).click();
  await expect(page.getByText("Sign in with your verified phone to manage your account sessions.",{exact:true})).toBeVisible();expect(await page.evaluate(()=>localStorage.getItem("homexo.customer.session"))).toBeNull();expect(state.actions).toHaveLength(1);
});

test("failed revocation keeps sign-in and requires explicit refresh",async({page,context})=>{
  const state=await fixtures(context,"failure");await page.goto("/account/security");const article=page.getByRole("article",{name:"Safari on iPhone or iPad",exact:true});await article.getByRole("button",{name:"End session",exact:true}).click();await article.getByRole("button",{name:"Confirm end session",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Synthetic session revocation"})).toBeVisible();await expect(article).toBeVisible();expect(await page.evaluate(()=>!!localStorage.getItem("homexo.customer.session"))).toBe(true);
  await page.getByRole("button",{name:"Refresh signed-in sessions",exact:true}).click();await expect(article.getByRole("button",{name:"End session",exact:true})).toBeEnabled();expect(state.actions).toHaveLength(1);
});

test("lookup failures can be refreshed without inventing an empty active list",async({page,context})=>{
  await fixtures(context,"load");await page.goto("/account/security");await expect(page.getByRole("alert").filter({hasText:"Synthetic session lookup"})).toBeVisible();
  await page.getByRole("button",{name:"Refresh signed-in sessions",exact:true}).click();await expect(page.getByText("This session",{exact:true})).toBeVisible();
});

test("ordinary profile sign-out waits for server revocation",async({page,context})=>{
  const state=await fixtures(context,"failure");await page.goto("/account#profile");const button=page.getByRole("button",{name:"Sign out",exact:true}).first();await expect(button).toBeVisible();await button.click();
  await expect(page.getByRole("alert").filter({hasText:"Could not confirm sign-out"})).toBeVisible();expect(await page.evaluate(()=>!!localStorage.getItem("homexo.customer.session"))).toBe(true);expect(state.actions[0]).toBe("/api/v1/account/logout");
});

test("signed-out visitors do not query session metadata",async({page,context})=>{
  const state=await fixtures(context,"signed-out");await page.goto("/account/security");await expect(page.getByText("Sign in with your verified phone to manage your account sessions.",{exact:true})).toBeVisible();expect(state.reads).toBe(0);expect(state.actions).toHaveLength(0);
});
