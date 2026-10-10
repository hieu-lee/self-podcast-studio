/** Actual UI + saved HTTP sessions. No microphone or model API calls. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const OUT=fileURLToPath(new URL('../.artifacts/',import.meta.url));
await mkdir(OUT,{recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
await context.tracing.start({screenshots:true,snapshots:true});
const page=await context.newPage(),checks=[];
try{
 await page.goto('http://127.0.0.1:8765');
 const sessions=await page.evaluate(async()=>(await fetch('/api/sessions')).json());
 const [a,b]=sessions.filter(s=>s.frames&&s.export_dir&&!s.epochs.some(e=>e.expected===null));
 assert.ok(a&&b,'Need two saved exported synthetic sessions; run the audio/browser E2Es first.');
 const selected=()=>page.locator('.session.selected').getAttribute('data-session-id');
 await page.locator(`[data-session-id="${a.id}"]`).click();
 let release,heldResolve,holding=false;const held=new Promise(r=>heldResolve=r);
 await page.route(`**/api/sessions/${a.id}`,async route=>{
  if(holding)return route.continue();holding=true;
  const response=await route.fetch();await new Promise(r=>{release=r;heldResolve();});await route.fulfill({response});
 });
 await held;
 await page.locator(`[data-session-id="${b.id}"]`).click();
 await page.locator(`[data-session-id="${b.id}"].selected`).waitFor();assert.equal(await selected(),b.id);release();
 await page.waitForTimeout(400);
 assert.equal(await selected(),b.id,'Obsolete A poll must not replace current B selection');
 checks.push('delayed poll cannot switch selected recording');await page.unroute(`**/api/sessions/${a.id}`);
 // Same-id older snapshot must not roll back a newer export/status view.
 await page.locator(`[data-session-id="${a.id}"]`).click();
 const url=`**/api/sessions/${a.id}`;let count=0,oldRelease,newResolve;
 const newer=new Promise(r=>newResolve=r);
 await page.route(url,async route=>{
  const response=await route.fetch();const body=await response.json();
  if(++count===1){body.export_status='obsolete polling snapshot';await new Promise(r=>oldRelease=r);}
  else{body.export_status='newest polling snapshot';newResolve();}
  await route.fulfill({response,json:body});
 });
 await newer;await page.getByText('newest polling snapshot',{exact:true}).waitFor();
 oldRelease();await page.waitForTimeout(400);
 assert.equal(await page.locator('.export-status').innerText(),'newest polling snapshot','Older same-id response must not replace newer status');
 checks.push('out-of-order same-session poll cannot roll back newer snapshot');
 await page.unroute(url);
 await page.screenshot({path:OUT+'polling-regression.png',fullPage:true});
 const report={checks,sessions:[a.id,b.id],scope:'Actual browser and saved session HTTP reads; no microphone or paid API calls.'};
 await writeFile(OUT+'polling-e2e.json',JSON.stringify(report,null,2));console.log(report);
}finally{await context.tracing.stop({path:OUT+'polling-trace.zip'});await browser.close();}
