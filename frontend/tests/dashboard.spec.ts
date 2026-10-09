import { test, expect, type Page } from '@playwright/test';

const TOKEN = 'offline-fixture-token-' + 'x'.repeat(32);
const tickets = [
  { id:101,type:'customer_order',requester:'Tauhid Zaman',subject:'Bulldog tee',status:'open',sku:'CC-TEE-WHITE',size:'S',qty:1,invoice_id:501,lease_id:null,notes:'Needs a tee in size S.' },
  { id:102,type:'rent_notice',requester:'Elm City Properties',subject:'Rent due',status:'open',sku:null,size:null,qty:null,invoice_id:null,lease_id:1,notes:'Email: shop rent due in 2 days.' },
  { id:103,type:'price_override',requester:'Yale AI Club',subject:'Bulk hoodie discount',status:'open',sku:'CC-HOOD-NAVY',size:'M',qty:20,invoice_id:null,lease_id:null,notes:'Student org wants 20 hoodies, size M, asking for a bulk discount.' },
];

async function unlock(page: Page) {
  await page.getByRole('button', { name:'Unlock human actions' }).click();
  await page.getByLabel('Your name', { exact:true }).fill('Fixture Human');
  await page.getByLabel('Human access token', { exact:true }).fill(TOKEN);
  await page.getByRole('button', { name:'Unlock actions', exact:true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
}

async function fixture(page: Page, options: { approval?: boolean; offline?: boolean; refuse?: boolean; resetRefuse?: boolean } = {}) {
  const records = structuredClone(tickets);
  let running = false, balance = 3400, paid = false;
  const events: object[] = [];
  const request = { id:'fixture-request', ticket_id:101, kind:'invoice', ref_id:501, amount:'840.00', account:'checking', due_date:'2026-08-28', requested_on:'2026-08-31', status:'pending', reason:'Unblock the reprint supplier' };
  await page.route('http://localhost:8000/**', async route => {
    if (options.offline) { await route.abort(); return; }
    const url = new URL(route.request().url());
    let body: unknown = {}, status = 200;
    if (url.pathname === '/tickets') body = { tickets:records,business_date:'2026-08-31' };
    else if (url.pathname === '/cash') body = { account:{name:'checking',balance,date:'2026-08-31'},business_date:'2026-08-31',currency:null };
    else if (url.pathname === '/approvals') body = { payments:paid ? [{...request,status:'executed'}] : options.approval ? [request] : [],purchases:[] };
    else if (url.pathname === '/tickets/101/payments/prepare') { options.approval=true; body={approval_request:request,human_approval_required:true}; }
    else if (url.pathname === '/health') body = {status:'ok',active_run_id:running ? 'fixture-run' : null};
    else if (url.pathname === '/activity') {
      const after = Number(url.searchParams.get('after_sequence') || 0);
      body = { entries:events.filter((event: any) => event.sequence > after), latest_sequence:events.length,next_after_sequence:events.length || after };
    } else if (url.pathname === '/session/verify') {
      if (route.request().headers().authorization !== `Bearer ${TOKEN}`) { status=401;body={detail:'Human bearer token required'}; }
      else body={authorized:true};
    } else if (url.pathname === '/tickets/101/run') {
      const data = route.request().postDataJSON();
      expect(data).not.toHaveProperty('token');
      expect(data.agent).toBe('Boss');
      running = true;
      const base = {timestamp_utc:'2026-08-31T13:20:00-04:00',run_id:'fixture-run',ticket:101,approval_requests:[],delegation:null,tool_calls:[]};
      events.push({ ...base,sequence:1,agent:'Boss',event:'delegation_requested',results:null,delegation:{from:'Boss',to:'Inventory',topic:'stock',task:'Check exact-size tee availability.'} },
        { ...base,sequence:2,agent:'Inventory',event:'tool_result',tool_calls:[{tool:'get_customer_order_context',arguments:{ticket_id:101}}],results:{inventory:{qty:0,size:'S'}} },
        { ...base,sequence:3,agent:'Inventory',event:'agent_completed',results:{ticket_id:101,agent:'Inventory',summary:'No size-S tees are in stock. Supplier invoice needs review.',status:'blocked',next_actions:['Ask Accounting to inspect invoice 501.']} },
        { ...base,sequence:4,agent:'Boss',event:'agent_completed',results:{ticket_id:101,agent:'Boss',summary:'The order remains blocked pending supply and human review.',status:'blocked'} });
      status=202;body={run_id:'fixture-run',ticket_id:101,agent:'Boss',status:'queued'};
    } else if (url.pathname === '/runs') body={runs:events.length ? [{run_id:'fixture-run',ticket_id:101,agent:'Boss',status:running?'running':'completed',result:{status:'blocked',summary:'The order remains blocked pending supply and human review.'}}] : []};
    else if (url.pathname === '/runs/fixture-run') { running=false;body={run_id:'fixture-run',ticket_id:101,agent:'Boss',status:'completed',result:{status:'blocked',summary:'The order remains blocked pending supply and human review.'}}; }
    else if (url.pathname === '/reset') {
      expect(route.request().headers().authorization).toBe(`Bearer ${TOKEN}`);
      expect(route.request().postDataJSON()).toEqual({confirmation:'RESET_WORKING_DATABASE'});
      if (options.resetRefuse) { status=409;body={detail:'An agent run is active; wait before resetting'}; }
      else { balance=3400;paid=true;body={reset:true}; }
    }
    else if (url.pathname === '/approvals/fixture-request/approve') {
      expect(route.request().postDataJSON()).toEqual({ticket_id:101,request_type:'payment',human_name:'Fixture Human',approve:true});
      if (options.refuse) { status=409;body={detail:'Payment refused: insufficient cash'}; }
      else { balance=2560;paid=true;body={already_executed:false,payment:{id:1,amount:840}}; }
    }
    await route.fulfill({ status,json:body,headers:{'Access-Control-Allow-Origin':'http://localhost:5174','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Allow-Methods':'GET, POST, OPTIONS'} });
  });
}

test('live dashboard reads the backend without changing shop records', async ({page}) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByTestId('checking-balance')).toHaveText('160.00');
  await expect(page.getByRole('button',{name:/#101.*Bulldog tee/})).toBeVisible();
  await page.getByRole('button',{name:/#102.*Rent due/}).click();
  await expect(page.getByRole('heading',{name:'Rent due',exact:true})).toBeVisible();
  await expect(page.getByTestId('ticket-status')).toHaveText('resolved');
  await page.getByRole('button',{name:/#103.*Bulk hoodie discount/}).click();
  await expect(page.getByRole('heading',{name:'Bulk hoodie discount',exact:true})).toBeVisible();
  await page.getByRole('button',{name:/#101.*Bulldog tee/}).click();
  await page.screenshot({path:'../output/dashboard_desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByTestId('checking-balance')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({path:'../output/dashboard_mobile.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('run activity and contributions do not turn an open ticket into resolved', async ({page}) => {
  await fixture(page);
  await page.goto('/');
  await expect(page.getByTestId('checking-balance')).toHaveText('3,400.00');
  await unlock(page);
  await page.getByRole('button',{name:'Run ticket',exact:true}).click();
  await expect(page.getByTestId('current-ticket-outcome')).toContainText('Open: database confirmed');
  const history=page.locator('details.activity-card');await expect(history).not.toHaveAttribute('open','');
  await page.getByText('Earlier attempts and audit history - historical',{exact:true}).click();
  await expect(page.getByText('Asked Inventory for help',{exact:true})).toBeVisible();
  await expect(page.getByText('No size-S tees are in stock. Supplier invoice needs review.').first()).toBeVisible();
  await expect(page.getByTestId('ticket-status')).toHaveText('open');
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
});

test('human review requires credentials and updates the backend-confirmed balance', async ({page}) => {
  await fixture(page,{approval:true});
  await page.goto('/');
  await expect(page.getByText('Pending approval',{exact:true})).toBeVisible();
  await unlock(page);
  await page.getByRole('button',{name:'Review request'}).click();
  await expect(page.getByRole('dialog')).toContainText('Approving as');
  await page.getByRole('button',{name:'Approve & pay 840.00'}).click();
  await expect(page.getByTestId('checking-balance')).toHaveText('2,560.00');
  await expect(page.getByText('Pending approval',{exact:true})).toHaveCount(0);
  await expect(page.getByTestId('ticket-status')).toHaveText('open');
  await expect(page.getByRole('button',{name:'Continue ticket',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Prepare payment request',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:/#103.*Bulk hoodie/}).click();
  await expect(page.getByLabel('What should Boss work on?')).not.toHaveValue(/ticket 101|ticket 102/);
});

test('backend refusal remains visible and does not change balance', async ({page}) => {
  await fixture(page,{approval:true,refuse:true});
  await page.goto('/');
  await unlock(page);
  await page.getByRole('button',{name:'Review request'}).click();
  await page.getByRole('button',{name:'Approve & pay 840.00'}).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('insufficient cash');
  await expect(page.getByTestId('checking-balance')).toHaveText('3,400.00');
});

test('reset requires human access and confirmation, then refreshes records', async ({page}) => {
  await fixture(page,{approval:true});
  await page.goto('/');
  await page.getByRole('button',{name:'Reset working database',exact:true}).click();
  await expect(page.getByRole('button',{name:'Unlock actions to reset'})).toBeVisible();
  await page.getByRole('button',{name:'Close dialog'}).click();
  await unlock(page);
  await page.getByRole('button',{name:'Review request'}).click();
  await page.getByRole('button',{name:'Approve & pay 840.00'}).click();
  await expect(page.getByTestId('checking-balance')).toHaveText('2,560.00');
  let resets=0;
  page.on('request',request => { if (new URL(request.url()).pathname === '/reset' && request.method() === 'POST') resets++; });
  await page.getByRole('button',{name:'Reset working database',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('audit history is preserved');
  expect(resets).toBe(0);
  await page.getByRole('button',{name:'Confirm database reset'}).click();
  await expect(page.getByTestId('checking-balance')).toHaveText('3,400.00');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(resets).toBe(1);
  await expect(page.getByTestId('ticket-status')).toHaveText('open');
});

test('reset refusal stays visible without a success claim', async ({page}) => {
  await fixture(page,{resetRefuse:true});
  await page.goto('/');
  await unlock(page);
  await page.getByRole('button',{name:'Reset working database',exact:true}).click();
  await page.getByRole('button',{name:'Confirm database reset'}).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('agent run is active');
  await expect(page.getByText('Working database restored from the original.',{exact:false})).toHaveCount(0);
});

test('offline state is explicit and never presents a fake balance', async ({page}) => {
  await fixture(page,{offline:true});
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Cannot reach the backend');
  await expect(page.getByTestId('checking-balance')).toHaveText('—');
  await expect(page.getByRole('button',{name:'Retry',exact:true})).toBeVisible();
});

test('manual preparation shows real API request without spending', async ({page}) => {
  await fixture(page); await page.goto('/'); await unlock(page);
  await page.getByRole('button',{name:'Prepare payment request',exact:true}).click();
  await expect(page.getByText('Pending approval',{exact:true})).toBeVisible();
  await expect(page.getByTestId('checking-balance')).toHaveText('3,400.00');
  await expect(page.getByRole('button',{name:'Review approval first',exact:true})).toBeDisabled();
});

test('business price proposal requires explicit human scope before decision', async ({page}) => {
  await fixture(page);
  let review:any=null, decisions=0;
  await page.route('http://localhost:8000/tickets/103', async route=>route.fulfill({json:{business_date:'2026-08-31',ticket:{status:review?.status==='executed'?'resolved':'open'},resolution_reviews:review?[review]:[],quote_drafts:review?.status==='executed'?[{unit_price:'58.00',rationale:'Only 8 of the requested 20 hoodies are in stock; fulfillment is not guaranteed.',status:'draft'}]:[]}}));
  await page.route('http://localhost:8000/tickets/103/resolution/prepare',async route=>{
    expect(route.request().postDataJSON().kind).toBe('pricing_decision');
    review={id:'business-review',kind:'pricing_decision',status:'pending',payload:JSON.stringify({unit_price:'58.00',completion_rule:'Unsent conditional quote only; no fulfillment',supply_caveat:'Availability unconfirmed'})};
    await route.fulfill({json:{review}});
  });
  await page.route('http://localhost:8000/tickets/103/resolution/business-review/decision',async route=>{
    const body=route.request().postDataJSON();expect(body.acknowledge_completion_rule).toBe(true);expect(body.human_name).toBe('Fixture Human');decisions++;review.status='executed';await route.fulfill({json:{review}});
  });
  await page.goto('/');await unlock(page);
  await page.getByRole('button',{name:/#103.*Bulk hoodie/}).click();
  await page.getByRole('button',{name:'Prepare business proposal (no payment)',exact:true}).click();
  const approve=page.getByRole('button',{name:'Approve conditional quote and resolve price request',exact:true});
  await expect(approve).toBeDisabled();expect(decisions).toBe(0);
  await page.getByLabel(/I accept the displayed completion rule/).check();await approve.click();
  await expect(page.getByText('Resolved ? pricing request only',{exact:true})).toBeVisible();expect(decisions).toBe(1);
  await expect(page.getByTestId('checking-balance')).toHaveText('3,400.00');
});

test('approved simulation plan is distinct from receipt and fulfillment; details collapsed',async({page})=>{
 await fixture(page,{approval:true});
 await page.route('http://localhost:8000/tickets/101',async route=>route.fulfill({json:{business_date:'2026-08-31',ticket:{status:'open'},fulfillments:[],resolution_reviews:[{id:'plan-only',kind:'simulated_restock',status:'approved',approved_by:'Fixture Human',payload:JSON.stringify({lead_days:5,earliest_arrival:'2026-09-05',simulation:true,qty:1})}]}}));
 await page.goto('/');
 const steps=page.getByRole('region',{name:'Current completion steps'});
 // Component is shown for paid invoice; mock executed payment without submitting a live decision.
 await unlock(page);await page.getByRole('button',{name:'Review request'}).click();await page.getByRole('button',{name:'Approve & pay 840.00'}).click();
 await expect(steps.getByText('Recorded: Fixture Human',{exact:true})).toBeVisible();
 await expect(steps.getByText('Not recorded',{exact:true})).toHaveCount(2);
 await expect(steps.getByText('Open in database',{exact:true})).toBeVisible();
 await expect(steps.locator('details')).not.toHaveAttribute('open','');
 await expect(page.locator('details.activity-card')).not.toHaveAttribute('open','');
});
