/** Actual guided EN/VI prep/interview/full finishing/download E2E, written before orchestration. */
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {chromium} from 'playwright';
import {execFileSync} from 'node:child_process';
const OUT=new URL('../.artifacts/guided/',import.meta.url).pathname;await mkdir(OUT,{recursive:true});
const ownershipOnly=process.env.SELF_PODCAST_E2E_OWNERSHIP_ONLY==='1';
const checks=[],languages=(process.env.SELF_PODCAST_E2E_LANGUAGES||'en,vi').split(',');
assert.ok(languages.every(x=>['en','vi'].includes(x)));
for(const language of languages){
 const wav=new URL('../.artifacts/'+(language==='vi'?'vietnamese/':'')+'synthetic-guest.wav',import.meta.url).pathname;
 // Extend only the cached synthetic fixture's silence so fake audio doesn't loop/barge in during the sourced answer.
 const padded=OUT+`guest-${language}.wav`;execFileSync(new URL('../.venv/bin/python',import.meta.url).pathname,['-c',"import wave,sys; r=wave.open(sys.argv[1]); p=r.getparams(); data=r.readframes(r.getnframes()); r.close(); w=wave.open(sys.argv[2],'wb'); w.setparams(p); w.writeframes(data+b'\\0'*(max(0,180*p.framerate-p.nframes)*p.nchannels*p.sampwidth)); w.close()",wav,padded]);
 const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+padded]});
 const context=await browser.newContext({permissions:['microphone'],viewport:{width:1440,height:1000}});await context.tracing.start({screenshots:true,snapshots:true});
 await context.addInitScript(()=>{window.micCalls=0;const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=(...a)=>{window.micCalls++;return original(...a);};});
 const page=await context.newPage();const events=[];const resumeId=process.env['SELF_PODCAST_E2E_RESUME_'+language.toUpperCase()];
 page.on('websocket',ws=>ws.on('framereceived',f=>{try{events.push(JSON.parse(f.payload.toString()));}catch{}}));
 try{
  await page.goto('http://127.0.0.1:8765');
  try{
   const expected=JSON.parse(await readFile(new URL('../.artifacts/research/real-server-identity.json',import.meta.url),'utf8'));
   assert.equal(expected.fixture,'self-podcast-owned-real-guided');assert.match(expected.nonce,/^[a-f0-9]{32}$/);
   assert.equal(expected.data_root,new URL('../.artifacts/research/real-data',import.meta.url).pathname);
   await page.request.get('http://127.0.0.1:8765/api/bootstrap');const identity=await page.request.get('http://127.0.0.1:8765/api/owned-real-fixture-identity');assert.ok(identity.ok());assert.deepEqual(await identity.json(),expected);
  }catch{throw Error('Owned real fixture required before episode operations; start the isolated real server, not the normal studio.');}
  console.log('Owned real fixture identity verified before episode operations');
  if(ownershipOnly)continue;
  if(resumeId){await page.locator(`[data-session-id="${resumeId}"]`).click();await page.locator('.workflow h2').filter({hasText:/Finishing needs attention|Preserved audio needs review|Ready to download/}).waitFor();}
  else {await page.locator('#language').selectOption(language);await page.locator('#topic').fill('Current official OpenAI API model releases, evidence and uncertainty');await page.getByLabel('Public research query').fill('Current OpenAI API models official documentation');await page.locator('.consent input').check();
  await page.getByRole('button',{name:'Start the conversation'}).click();await page.getByText('Checking web sources',{exact:false}).waitFor();assert.equal(await page.evaluate(()=>micCalls),0);
  await page.getByRole('button',{name:'Start with researched briefing',exact:true}).waitFor({timeout:65000});assert.equal(await page.evaluate(()=>micCalls),0);assert.ok(await page.locator('.research-panel a[href^="https://"]').count());
  await page.screenshot({path:OUT+`real-${language}-prep.png`,fullPage:true});await page.getByRole('button',{name:'Start with researched briefing',exact:true}).click();await page.getByRole('heading',{name:'On the record',exact:true}).waitFor();
  const until=Date.now()+30000;while(Date.now()<until&&!events.some(e=>e.type==='response.output_audio.delta'))await page.waitForTimeout(100);assert.ok(events.some(e=>e.type==='response.output_audio.delta'));const current=await page.evaluate(async()=>{const id=document.querySelector('.session.selected').dataset.sessionId;return (await fetch('/api/sessions/'+id)).json();});assert.ok(events.some(e=>e.type==='ready'&&e.preparation_id===current.preparation.id));
  await page.waitForTimeout(12000);await page.getByRole('button',{name:'Interrupt AI',exact:true}).click();
  await page.getByLabel('Live public research query').fill('Verify one current official OpenAI API model now and cite its documentation');await page.getByRole('button',{name:'Ask interviewer to check',exact:true}).click();
  const deadline=Date.now()+125000;while(Date.now()<deadline&&!events.some(e=>e.type==='research.result'&&e.result.status==='ready'))await page.waitForTimeout(200);assert.ok(events.some(e=>e.type==='research.result'&&e.result.status==='ready'));
  assert.ok(events.some(e=>e.type==='response.done'&&e.response.output?.some(i=>i.type==='function_call')));
  const resultIndex=events.findIndex(e=>e.type==='research.result'&&e.result.status==='ready');const responseDeadline=Date.now()+35000;while(Date.now()<responseDeadline&&!events.slice(resultIndex+1).some(e=>e.type==='response.done'&&e.response.status==='completed'&&e.response.output?.some(i=>i.type==='message')))await page.waitForTimeout(100);assert.ok(events.slice(resultIndex+1).some(e=>e.type==='response.done'&&e.response.status==='completed'&&e.response.output?.some(i=>i.type==='message')),'Completed actual post-tool audio response required');
  await page.waitForTimeout(15000);await page.screenshot({path:OUT+`real-${language}-live.png`,fullPage:true});
  }
  // Episode's dated primary research citations must flow to video automatically, without manual URL pasting.
  if(resumeId&&await page.getByRole('heading',{name:'Ready to download',exact:true}).count()){
   // Explicit owned immutable-audio retry verifies the final source capture code without repeating paid interview/polish.
   const response=await page.evaluate(async id=>{const current=await(await fetch('/api/sessions/'+id)).json();return await fetch(`/api/sessions/${id}/finish`,{method:'POST',headers:{'Content-Type':'application/json','X-Self-Podcast':'1'},body:JSON.stringify({version:current.export_dir,retry:true,reviewed_audio:true,sources:{public_urls:[],project_ids:[]}})}).then(r=>r.status);},resumeId);assert.equal(response,200);
  }else{
   const initialAction=resumeId?(await page.getByRole('button',{name:'Continue with preserved uncertainties',exact:true}).count()?'Continue with preserved uncertainties':'Retry finishing'):'Finish & make video';
   await Promise.all([page.waitForResponse(r=>r.url().endsWith('/finish')&&r.request().method()==='POST'),page.getByRole('button',{name:initialAction,exact:true}).click()]);
  }
  const finishDeadline=Date.now()+1800000;let finished;
  while(Date.now()<finishDeadline){
   const selectedId=await page.locator('.session.selected').getAttribute('data-session-id');finished=await page.evaluate(async id=>(await fetch('/api/sessions/'+id)).json(),selectedId);
   if(finished.workflow?.state==='review_required'){await Promise.all([page.waitForResponse(r=>r.url().endsWith('/finish')&&r.request().method()==='POST'),page.getByRole('button',{name:'Continue with preserved uncertainties',exact:true}).click()]);}
   if(finished.workflow?.state==='ready')break;
   if(['failed','interrupted','cancelled'].includes(finished.workflow?.state))throw Error(JSON.stringify(finished.workflow));
   await page.waitForTimeout(1000);
  }
  assert.equal(finished?.workflow?.state,'ready');await page.getByRole('heading',{name:'Ready to download',exact:true}).waitFor();
  const dir=OUT+language+'/';await mkdir(dir,{recursive:true});
  const base=`/api/sessions/${finished.id}/video/${finished.workflow.job_id}/files/`,suffix='?version='+finished.workflow.version;
  for(const name of ['episode.mp4','provenance.json','validation.json','captions.json','storyboard.json','source-plan.json','source-provenance.json','project.zip']){const r=await page.request.get(new URL(base+name+suffix,page.url()).href);assert.ok(r.ok());await writeFile(dir+name,await r.body());}
  for(const name of ['episode.mp3','transcript.json','edit.json','polish.json']){const r=await page.request.get(new URL(`/api/sessions/${finished.id}/files/${name}`+suffix,page.url()).href);assert.ok(r.ok());await writeFile(dir+name,await r.body());}
  assert.ok(finished.workflow.sources.public_urls.some(url=>new URL(url).hostname==='developers.openai.com'));assert.deepEqual(finished.workflow.sources.project_ids,[]);
  const download=await page.getByRole('link',{name:'Download video',exact:true}).getAttribute('href');assert.equal(download,base+'episode.mp4'+suffix);
  await page.locator('.workflow video').evaluate(async v=>{v.muted=true;await v.play();v.currentTime=Math.min(2,v.duration/3);});await page.waitForTimeout(350);await page.locator('.workflow video').evaluate(v=>v.pause());
  await page.screenshot({path:OUT+`real-${language}-ready.png`,fullPage:true,animations:'disabled'});

  const sid=await page.locator('.session.selected').getAttribute('data-session-id');const saved=await page.evaluate(async sid=>(await fetch('/api/sessions/'+sid)).json(),sid);assert.ok(saved.frames>24000*15);assert.ok(saved.epochs.every(e=>e.expected!==null));assert.equal(saved.language,language);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:OUT+`real-${language}-mobile.png`,fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const ledger=await page.evaluate(async sid=>(await fetch('/api/sessions/'+sid+'/research')).json(),sid);
  checks.push({language,sid,resumed_owned_failure:!!resumeId,frames:saved.frames,ledger,workflow:saved.workflow,export_dir:saved.export_dir});await writeFile(OUT+`real-${language}-browser-events.json`,JSON.stringify(events,null,2));
 }finally{await context.tracing.stop({path:OUT+`real-${language}-${ownershipOnly?'ownership':'browser'}-trace.zip`});await browser.close();}
}
if(!ownershipOnly){
let previous=[];try{previous=JSON.parse(await readFile(OUT+'real-guided-e2e.json','utf8')).checks.filter(x=>!languages.includes(x.language));}catch{}
await writeFile(OUT+'real-guided-e2e.json',JSON.stringify({checks:[...previous,...checks],scope:'Actual hosted EN/VI prep/Realtime tool/capture, actual conservative polish/Codex video/render/full downloadable artifacts; synthetic microphone only, no human listening approval.'},null,2));console.log(checks.map(({language,sid,frames})=>({language,sid,frames})));

}
