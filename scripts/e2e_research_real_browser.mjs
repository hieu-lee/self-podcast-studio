/** Actual EN/VI interview UI with a cached synthetic guest WAV, never a human mic. */
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {execFileSync} from 'node:child_process';
const OUT=new URL('../.artifacts/research/',import.meta.url).pathname;await mkdir(OUT,{recursive:true});
const checks=[];
for(const language of ['en','vi']){
 const wav=new URL('../.artifacts/'+(language==='vi'?'vietnamese/':'')+'synthetic-guest.wav',import.meta.url).pathname;
 // Extend only the cached synthetic fixture's silence so fake audio doesn't loop/barge in during the sourced answer.
 const padded=OUT+`guest-${language}.wav`;execFileSync(new URL('../.venv/bin/python',import.meta.url).pathname,['-c',"import wave,sys; r=wave.open(sys.argv[1]); p=r.getparams(); data=r.readframes(r.getnframes()); r.close(); w=wave.open(sys.argv[2],'wb'); w.setparams(p); w.writeframes(data+b'\\0'*(max(0,180*p.framerate-p.nframes)*p.nchannels*p.sampwidth)); w.close()",wav,padded]);
 const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+padded]});
 const context=await browser.newContext({permissions:['microphone'],viewport:{width:1440,height:1000}});await context.tracing.start({screenshots:true,snapshots:true});
 await context.addInitScript(()=>{window.micCalls=0;const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=(...a)=>{window.micCalls++;return original(...a);};});
 const page=await context.newPage();const events=[];
 page.on('websocket',ws=>ws.on('framereceived',f=>{try{events.push(JSON.parse(f.payload.toString()));}catch{}}));
 try{
  await page.goto('http://127.0.0.1:8765');await page.locator('#language').selectOption(language);await page.locator('#topic').fill('Current official OpenAI API model releases, evidence and uncertainty');await page.getByLabel('Public research query').fill('Current OpenAI API models official documentation');await page.locator('.consent input').check();
  await page.getByRole('button',{name:'Start the conversation'}).click();await page.getByText('Checking web sources',{exact:false}).waitFor();assert.equal(await page.evaluate(()=>micCalls),0);
  await page.getByRole('button',{name:'Start with researched briefing',exact:true}).waitFor({timeout:65000});assert.equal(await page.evaluate(()=>micCalls),0);assert.ok(await page.locator('.research-panel a[href^="https://"]').count());
  await page.screenshot({path:OUT+`real-${language}-prep.png`,fullPage:true});await page.getByRole('button',{name:'Start with researched briefing',exact:true}).click();await page.getByRole('heading',{name:'On the record',exact:true}).waitFor();
  const until=Date.now()+30000;while(Date.now()<until&&!events.some(e=>e.type==='response.output_audio.delta'))await page.waitForTimeout(100);assert.ok(events.some(e=>e.type==='response.output_audio.delta'));
  await page.waitForTimeout(12000);await page.getByRole('button',{name:'Interrupt AI',exact:true}).click();
  await page.getByLabel('Live public research query').fill('Verify one current official OpenAI API model now and cite its documentation');await page.getByRole('button',{name:'Ask interviewer to check',exact:true}).click();
  const deadline=Date.now()+125000;while(Date.now()<deadline&&!events.some(e=>e.type==='research.result'&&e.result.status==='ready'))await page.waitForTimeout(200);assert.ok(events.some(e=>e.type==='research.result'&&e.result.status==='ready'));
  assert.ok(events.some(e=>e.type==='response.done'&&e.response.output?.some(i=>i.type==='function_call')));
  const resultIndex=events.findIndex(e=>e.type==='research.result'&&e.result.status==='ready');const responseDeadline=Date.now()+35000;while(Date.now()<responseDeadline&&!events.slice(resultIndex+1).some(e=>e.type==='response.done'&&e.response.status==='completed'&&e.response.output?.some(i=>i.type==='message')))await page.waitForTimeout(100);assert.ok(events.slice(resultIndex+1).some(e=>e.type==='response.done'&&e.response.status==='completed'&&e.response.output?.some(i=>i.type==='message')),'Completed actual post-tool audio response required');
  await page.waitForTimeout(15000);await page.screenshot({path:OUT+`real-${language}-live.png`,fullPage:true});
  await page.getByRole('button',{name:'Stop & save',exact:false}).click();await page.getByRole('button',{name:'Resume recording',exact:true}).waitFor({timeout:30000});
  const sid=await page.locator('.session.selected').getAttribute('data-session-id');const saved=await page.evaluate(async sid=>(await fetch('/api/sessions/'+sid)).json(),sid);assert.ok(saved.frames>24000*15);assert.ok(saved.epochs.every(e=>e.expected!==null));assert.equal(saved.language,language);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:OUT+`real-${language}-mobile.png`,fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const ledger=await page.evaluate(async sid=>(await fetch('/api/sessions/'+sid+'/research')).json(),sid);
  checks.push({language,sid,frames:saved.frames,ledger});await writeFile(OUT+`real-${language}-browser-events.json`,JSON.stringify(events,null,2));
 }finally{await context.tracing.stop({path:OUT+`real-${language}-browser-trace.zip`});await browser.close();}
}
await writeFile(OUT+'real-browser-e2e.json',JSON.stringify({checks,scope:'Actual hosted prep, actual Realtime tool calls and browser worklet capture using synthetic microphone en/vi; no human microphone/listening approval.'},null,2));console.log(checks.map(({language,sid,frames})=>({language,sid,frames})));
