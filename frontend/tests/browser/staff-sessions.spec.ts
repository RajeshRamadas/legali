import AxeBuilder from "@axe-core/playwright";
import {test,expect,type BrowserContext} from "@playwright/test";

const current="eb94ba02-a3c4-4948-904b-6a77a3bfb73a",other="32fc1443-7ccd-425e-a6ea-e5b04ea197fb";
const user={id:"synthetic-staff",name:"Synthetic Administrator",role:"admin",email:"synthetic@example.invalid",phone:null,mfa_enabled:true,available_for_calls:false};
const row=(id:string,is_current:boolean)=>({id,is_current,browser:is_current?"Chrome":"Safari",device:is_current?"Windows":"iPhone or iPad",created_at:"2026-11-12T07:00:00Z",last_seen_at:"2026-11-12T07:01:00Z",expires_at:"2026-11-12T15:00:00Z"});
async function fixtures(context:BrowserContext,mode="normal"){
  if(mode!=="signed-out")await context.addInitScript(()=>sessionStorage.setItem("homexo.staff.token","staff-sessions-browser-fixture-only"));
  const state={items:[row(current,true),row(other,false)],reads:0,actions:[] as string[],failRead:mode==="load",failAction:mode==="failure",rotate:false};
  await context.route("**/api/v1/**",route=>{
    const request=route.request(),path=new URL(request.url()).pathname;
    const headers={"access-control-allow-origin":"*","access-control-allow-headers":"authorization,content-type","access-control-allow-methods":"GET,POST,OPTIONS"};
    const reply=(json:unknown,status=200)=>route.fulfill({headers,json,status});
    if(request.method()==="OPTIONS")return route.fulfill({headers,status:204});
    if(path.endsWith("/auth/me"))return reply(user);
    if(path.endsWith("/auth/security"))return reply({mfa_enabled:true,mfa_required:false,recovery_codes_remaining:8});
    if(path.endsWith("/admin/urgent"))return reply({items:[]});
    if(path.endsWith("/deadline-alerts")||path.endsWith("/case-alerts"))return reply({items:[],unacknowledged:0});
    if(path.endsWith("/auth/sessions")){
      state.reads++;if(state.failRead){state.failRead=false;return reply({detail:"Synthetic staff session lookup unavailable"},503);}
      return reply({items:state.items,checked_at:"2026-11-12T07:02:00Z",max_active:20,activity_interval_seconds:300});
    }
    if(path.endsWith("/auth/password/change")){
      state.rotate=true;state.items=[row("new-current",true)];
      return reply({access_token:"rotated-staff-browser-fixture-only",user});
    }
    if(path.includes("/sessions/")||path.endsWith("/auth/logout")||path.endsWith("/auth/logout-all")){
      state.actions.push(path);expect(request.headers()["authorization"]).toBe(`Bearer ${state.rotate?"rotated-staff-browser-fixture-only":"staff-sessions-browser-fixture-only"}`);
      if(state.failAction){state.failAction=false;return reply({detail:"Synthetic staff revocation unavailable"},503);}
      if(path.endsWith("/logout-all"))return reply({message:"Signed out on all devices."});
      if(path.endsWith("/revoke-others")){const count=state.items.filter(item=>!item.is_current).length;state.items=state.items.filter(item=>item.is_current);return reply({revoked:count});}
      const id=path.endsWith("/auth/logout")?current:path.split("/").at(-2);
      state.items=state.items.filter(item=>item.id!==id);return reply({revoked:true,current:id===current});
    }
    return reply({detail:"No staff sessions browser fixture"},503);
  });return state;
}

test("staff session center is accessible responsive and only shows safe hints",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/security");await expect(page.getByText("This session",{exact:true})).toBeVisible();
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa","wcag22aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);expect(state.actions).toHaveLength(0);
  await page.screenshot({path:test.info().outputPath("staff-sessions.png"),fullPage:true});
});

test("staff explicitly confirm ending a selected session",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/security");const article=page.getByRole("article",{name:"Safari on iPhone or iPad",exact:true});
  await article.getByRole("button",{name:"End session",exact:true}).click();expect(state.actions).toHaveLength(0);
  await article.getByRole("button",{name:"Keep session",exact:true}).click();expect(state.actions).toHaveLength(0);
  await article.getByRole("button",{name:"End session",exact:true}).click();await article.getByRole("button",{name:"Confirm end session",exact:true}).click();
  await expect(page.getByRole("status").filter({hasText:"selected staff session"})).toBeFocused();await expect(article).toHaveCount(0);await expect(page.getByText("This session",{exact:true})).toBeVisible();
});

test("signing out other staff sessions keeps this session",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/security");await page.getByRole("button",{name:"Sign out other sessions",exact:true}).click();expect(state.actions).toHaveLength(0);
  await page.getByRole("button",{name:"Confirm sign out other sessions",exact:true}).click();await expect(page.getByRole("heading",{name:"Safari · iPhone or iPad",exact:true})).toHaveCount(0);await expect(page.getByText("This session",{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>!!sessionStorage.getItem("homexo.staff.token"))).toBe(true);
});

for(const mode of ["current","all"]){test(`confirmed ${mode} staff logout clears storage after success`,async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/security");
  if(mode==="current"){const article=page.getByRole("article",{name:"Chrome on Windows, current session",exact:true});await article.getByRole("button",{name:"Sign out this session",exact:true}).click();await article.getByRole("button",{name:"Confirm end session",exact:true}).click();}
  else{await page.getByRole("button",{name:"Sign out all devices",exact:true}).click();expect(state.actions).toHaveLength(0);await page.getByRole("button",{name:"Confirm sign out all devices",exact:true}).click();}
  await expect(page.getByRole("button",{name:"Sign in",exact:true})).toBeVisible();expect(await page.evaluate(()=>sessionStorage.getItem("homexo.staff.token"))).toBeNull();expect(state.actions).toHaveLength(1);
});}

test("failed revocation retains sign-in and requires explicit refresh",async({page,context})=>{
  const state=await fixtures(context,"failure");await page.goto("/admin/security");const article=page.getByRole("article",{name:"Safari on iPhone or iPad",exact:true});await article.getByRole("button",{name:"End session",exact:true}).click();await article.getByRole("button",{name:"Confirm end session",exact:true}).click();
  await expect(page.getByRole("alert").filter({hasText:"Synthetic staff revocation"})).toBeFocused();await expect(article).toBeVisible();expect(await page.evaluate(()=>!!sessionStorage.getItem("homexo.staff.token"))).toBe(true);
  await page.getByRole("button",{name:"Refresh staff sessions",exact:true}).click();await expect(article.getByRole("button",{name:"End session",exact:true})).toBeEnabled();expect(state.actions).toHaveLength(1);
});

test("failed session lookup has an explicit retry",async({page,context})=>{
  await fixtures(context,"load");await page.goto("/admin/security");await expect(page.getByRole("alert").filter({hasText:"Synthetic staff session lookup"})).toBeVisible();
  await page.getByRole("button",{name:"Refresh staff sessions",exact:true}).click();await expect(page.getByText("This session",{exact:true})).toBeVisible();
});

test("ordinary shell logout waits for server confirmation",async({page,context})=>{
  const state=await fixtures(context,"failure");await page.goto("/admin/security");const button=page.getByRole("button",{name:"Sign out",exact:true}).first();
  if(test.info().project.name!=="desktop")await page.getByRole("button",{name:"Open navigation",exact:true}).click();
  await button.click();await expect.poll(()=>state.actions.length).toBe(1);
  await expect(page.getByRole("alert").filter({hasText:"Could not confirm sign-out"})).toBeVisible();expect(await page.evaluate(()=>!!sessionStorage.getItem("homexo.staff.token"))).toBe(true);expect(state.actions[0]).toBe("/api/v1/auth/logout");
  if(test.info().project.name!=="desktop")await page.getByRole("button",{name:"Open navigation",exact:true}).click();
  await page.getByRole("button",{name:"Sign out",exact:true}).first().click();
  await expect(page.getByRole("button",{name:"Sign in",exact:true})).toBeVisible();
  expect(await page.evaluate(()=>sessionStorage.getItem("homexo.staff.token"))).toBeNull();expect(state.actions).toHaveLength(2);
});

test("password rotation refreshes the session list with the replacement token",async({page,context})=>{
  const state=await fixtures(context);await page.goto("/admin/security");await expect(page.getByText("This session",{exact:true})).toBeVisible();
  const section=page.locator("section").filter({has:page.getByRole("heading",{name:"Change password",exact:true})});
  await section.getByLabel("Current password",{exact:true}).fill("synthetic-old-password");await section.getByLabel("New password",{exact:true}).fill("synthetic-new-password");await section.getByLabel("Confirm new password",{exact:true}).fill("synthetic-new-password");await section.getByLabel("Authenticator or recovery code",{exact:true}).fill("000000");await section.getByRole("button",{name:"Change password",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Safari · iPhone or iPad",exact:true})).toHaveCount(0);await expect(page.getByText("1 active session",{exact:false})).toBeVisible();expect(state.reads).toBeGreaterThan(1);
});

test("signed-out visitors do not query staff session metadata",async({page,context})=>{
  const state=await fixtures(context,"signed-out");await page.goto("/admin/security");await expect(page.getByRole("button",{name:"Sign in",exact:true})).toBeVisible();expect(state.reads).toBe(0);expect(state.actions).toHaveLength(0);
});
