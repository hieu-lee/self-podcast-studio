import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const ROOT=fileURLToPath(new URL('../',import.meta.url));
const OUT=ROOT+'.artifacts/';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export async function runFailures(browser){
 const checks=[];
 const check=(name,value)=>{assert.ok(value,name);checks.push(name);};
 const denied=await browser.newContext({viewport:{width:1440,height:900}});
 await denied.addInitScript(()=>{navigator.mediaDevices.getUserMedia=()=>Promise.reject(new DOMException('Test microphone permission denied','NotAllowedError'));});
 const d=await denied.newPage();await d.goto('http://127.0.0.1:8765');await d.locator('#topic').fill('E2E microphone-denial fixture');await d.getByLabel('Prepare with web research & allow live public lookups').uncheck();await d.locator('.consent input').check();await d.getByRole('button',{name:'Start the conversation'}).click();
 await d.getByRole('alert').waitFor();check('mic denial visible, no false live state',!await d.getByRole('heading',{name:'On the record'}).isVisible());
 await d.screenshot({path:OUT+'microphone-denied.png'});await denied.close();
 const c=await browser.newContext({viewport:{width:1440,height:900},permissions:['microphone']});
 let p=await c.newPage();await p.goto('http://127.0.0.1:8765');await p.locator('#topic').fill('E2E browser crash/offline recovery fixture — synthetic microphone');await p.getByLabel('Prepare with web research & allow live public lookups').uncheck();await p.locator('.consent input').check();
 await p.getByRole('button',{name:'Start the conversation'}).click();await p.getByRole('heading',{name:'On the record'}).waitFor();
 await sleep(1500);
 await p.route('**/chunks',route=>route.abort());await sleep(3200);
 check('durable browser queue grows during upload outage',/queued locally/.test(await p.locator('.health').innerText()));
 const sid=await p.evaluate(async()=>{const sessions=await(await fetch('/api/sessions')).json();return sessions.find(s=>s.topic.startsWith('E2E browser crash/')).id;});
 await p.close();await sleep(500);p=await c.newPage();await p.goto('http://127.0.0.1:8765');
 await sleep(1500);await p.locator('.session').filter({hasText:'E2E browser crash/'}).first().click();
 // Hosted WebSocket close can outlast tab closure; don't race the recording lock.
 for(let i=0;i<100;i++){const state=await p.evaluate(async sid=>(await fetch('/api/sessions/'+sid)).json(),sid);if(!state.connected)break;await sleep(200);}
 await p.getByRole('button',{name:'Recover committed audio',exact:true}).click();
 for(let i=0;i<100;i++){const state=await p.evaluate(async sid=>(await fetch('/api/sessions/'+sid)).json(),sid);if(state.epochs.every(e=>e.expected!==null))break;await sleep(100);}
 const m=await p.evaluate(async sid=>(await fetch('/api/sessions/'+sid)).json(),sid);
 check('tab close recovery keeps ordered committed chunks',m.frames>=24000*3&&m.epochs.every(e=>e.expected!==null));
 check('lost tail explicitly recorded',m.events.some(e=>e.type==='recovery_warning'));
 const exp=await p.evaluate(async sid=>{const r=await fetch('/api/sessions/'+sid+'/export',{method:'POST',headers:{'Content-Type':'application/json','X-Self-Podcast':'1'},body:'{}'});return r.status;},sid);
 check('unacknowledged lost tail blocks export',exp===409);
 await p.screenshot({path:OUT+'recovered-capture.png'});await c.close();
 const suspended=await browser.newContext({permissions:['microphone'],viewport:{width:1440,height:900}});
 await suspended.addInitScript(()=>{const Base=window.AudioContext;window.AudioContext=class extends Base{constructor(...args){super(...args);window.testAudioContext=this;}};});
 const sp=await suspended.newPage();await sp.goto('http://127.0.0.1:8765');await sp.locator('#topic').fill('E2E suspended audio engine — synthetic microphone');await sp.getByLabel('Prepare with web research & allow live public lookups').uncheck();await sp.locator('.consent input').check();await sp.getByRole('button',{name:'Start the conversation'}).click();await sp.getByRole('heading',{name:'On the record'}).waitFor();
 await sleep(1500);await sp.evaluate(()=>window.testAudioContext.suspend());
 await sp.getByRole('heading',{name:'On the record'}).waitFor({state:'hidden',timeout:10000});await sp.getByRole('heading',{name:'Saving your conversation'}).waitFor({state:'hidden',timeout:10000});
 check('suspended engine stops without hang and preserves lost-audio warning',(await sp.locator('.notice').allTextContents()).some(t=>/unsaved tail|suspended/.test(t)));
 await sp.screenshot({path:OUT+'audio-suspended.png',fullPage:true});await suspended.close();
 const report={checks,session_id:sid,scope:'Real browser durability/permission failure cases using synthetic test microphone.'};
 await writeFile(OUT+'failure-e2e.json',JSON.stringify(report,null,2));return report;
}
if(import.meta.url===`file://${process.argv[1]}`){
 const {chromium}=await import('playwright');
 const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+OUT+'synthetic-guest.wav']});
 try{console.log(await runFailures(browser));}finally{await browser.close();}
}
