/** Real UI + API E2E. Uses synthetic test microphone, never Hieu's microphone. */
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const ROOT=fileURLToPath(new URL('../',import.meta.url));
const language=process.argv.includes('--vietnamese')?'vi':'en';
const OUT=ROOT+'.artifacts/'+(language==='vi'?'vietnamese/':'');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export async function run(page,context){
 await mkdir(OUT,{recursive:true});
 const errors=[],received=[],checks=[];let recordingId;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('websocket',ws=>{recordingId=ws.url().match(/sessions\/([a-f0-9]{32})\/live/)?.[1];ws.on('framereceived',f=>{try{const e=JSON.parse(f.payload);received.push(e);}catch{}});});
 const check=(name,value)=>{assert.ok(value,name);checks.push(name);};
 const json=path=>page.evaluate(async p=>(await fetch('/api/'+p)).json(),path);
 await page.goto('http://127.0.0.1:8765');
 await page.screenshot({path:OUT+'desktop-start.png'});
 if(language==='vi'){await page.getByLabel('Podcast language',{exact:true}).selectOption('vi');await page.screenshot({path:OUT+'desktop-language.png'});}
 check('explicit consent required',await page.getByRole('button',{name:'Start the conversation'}).isDisabled());
 await page.getByLabel('Prepare with web research & allow live public lookups').uncheck();
 await page.locator('.consent input').check();
 await page.getByRole('button',{name:'Start the conversation'}).click();
 await page.getByRole('heading',{name:'On the record'}).waitFor({timeout:20000});
 for(let i=0;i<100&&!received.some(e=>e.type==='ready');i++)await sleep(200);
 check('real Realtime connected',received.some(e=>e.type==='ready'));
 check('episode language applied by actual relay',received.find(e=>e.type==='ready').language===language);
 let interrupted=false;
 for(let i=0;i<(language==='vi'?440:240);i++){
   const done=received.filter(e=>e.type==='response.output_audio_transcript.done');
   const guest=received.some(e=>e.type==='conversation.item.input_audio_transcription.completed');
   const delta=received.filter(e=>e.type==='response.output_audio.delta');
   const complete=received.filter(e=>e.type==='response.done'&&e.response.status==='completed').flatMap(e=>e.response.output.filter(i=>i.status==='completed').map(i=>i.id));
   if(guest&&done.length>=1&&(language!=='vi'||complete.length>=2)&&delta.some(e=>e.item_id!==done[0].item_id&&(language!=='vi'||!complete.includes(e.item_id)))){
     await sleep(350);await page.getByRole('button',{name:'Interrupt AI',exact:true}).click();interrupted=true;break;
   }
   await sleep(250);
 }
 check('guest transcript from actual mic audio',received.some(e=>e.type==='conversation.item.input_audio_transcription.completed'&&(language==='vi'?/toán|chứng minh|kiểm tra|giả thiết/i:/mathematics|proof|creativ/i).test(e.transcript)));
 check('one opening question',received.some(e=>e.type==='response.output_audio_transcript.done'&&e.transcript.includes('?')));
 check('responsive follow-up generated and interrupted',interrupted);
 if(language==='vi')check('complete Vietnamese follow-up before later deliberate interruption',received.filter(e=>e.type==='response.done'&&e.response.status==='completed').length>=2);
 await page.screenshot({path:OUT+'desktop-live.png'});
 // Simulated network loss: recording continues and IDB uploads recover on reconnect.
 await context.setOffline(true);await sleep(3200);
 check('offline queue visible',/queued locally/.test(await page.locator('.health').innerText()));
 await context.setOffline(false);
 await page.getByRole('button',{name:'Reconnect AI',exact:true}).click();
 for(let i=0;i<100&&received.filter(e=>e.type==='ready').length<2;i++)await sleep(200);
 check('new API connection after offline',received.filter(e=>e.type==='ready').length>=2);
 await sleep(1200);
 await page.getByRole('button',{name:'Stop & save'}).click();
 for(let i=0;i<100&&await page.getByRole('heading',{name:'Saving your conversation'}).isVisible();i++)await sleep(200);
 check('recording stopped and saved',!await page.getByRole('heading',{name:'On the record'}).isVisible()&&!await page.getByRole('heading',{name:'Saving your conversation'}).isVisible());
 const list=await json('sessions');const s=list.find(s=>s.id===recordingId);
 check('language stored per episode',s?.language===language);
 assert.ok(s);check('source chunks durable',s.frames>24000*20&&s.epochs.every(e=>e.expected!==null));
 await page.getByRole('button',{name:'Make the episode'}).click();
 let state;
 for(let i=0;i<300;i++){
   state=await json('sessions/'+s.id);
   if(state.export_dir||state.export_status?.startsWith('Export failed'))break;
   await sleep(500);
 }
 check('real FFmpeg/transcription export succeeded',state.export_dir);
 await page.locator('audio').waitFor();
 const audio=await page.locator('audio').evaluate(async a=>{await new Promise((resolve,reject)=>{if(a.readyState>=1)return resolve();a.onloadedmetadata=resolve;a.onerror=reject;});await a.play();return {duration:a.duration,playing:!a.paused};});
 check('export playable in browser',audio.playing&&audio.duration>15);
 await sleep(500);await page.locator('audio').evaluate(a=>a.pause());
 const previousVersion=state.export_dir;
 await page.getByLabel('AI audio repair (never my voice)',{exact:true}).uncheck();
 await page.getByRole('button',{name:'Make the episode'}).click();
 for(let i=0;i<300;i++){
   state=await json('sessions/'+s.id);
   if(state.export_dir!==previousVersion||state.export_status?.startsWith('Export failed'))break;
   await sleep(500);
 }
 check('same recording re-export produces a new immutable version',state.export_dir&&state.export_dir!==previousVersion);
 const currentPlayer=page.locator(`audio[src*="${state.export_dir}"]`);await currentPlayer.waitFor();
 const playerVersion=await currentPlayer.evaluate(async a=>{await new Promise((resolve,reject)=>{if(a.readyState>=1)return resolve();a.onloadedmetadata=resolve;a.onerror=reject;});return a.currentSrc;});
 check('player refreshes to new export without a page reload',playerVersion.includes(state.export_dir)&&!playerVersion.includes(previousVersion));
 check('transcript link matches new player version',(await page.getByRole('link',{name:'Final transcript',exact:true}).getAttribute('href')).includes(state.export_dir));
 const obsoleteApproval=await page.evaluate(async({sid,version})=>(await fetch('/api/sessions/'+sid+'/approve',{method:'POST',headers:{'Content-Type':'application/json','X-Self-Podcast':'1'},body:JSON.stringify({version})})).status,{sid:s.id,version:previousVersion});
 check('obsolete listening confirmation cannot approve a different export',obsoleteApproval===409);
 check('audio diagnosis links absent when review disabled',await page.getByRole('link',{name:'AI audio diagnosis',exact:true}).count()===0&&await page.getByRole('link',{name:'Validated audio plan',exact:true}).count()===0);
 await page.screenshot({path:OUT+'desktop-export.png',fullPage:true});
 const transcript=await json('sessions/'+s.id+'/files/transcript.json');
 check('export preserves episode language',transcript.language===language);
 if(language==='vi')check('Vietnamese captions for both speakers',['Hieu','AI interviewer'].every(speaker=>transcript.segments.some(s=>s.speaker===speaker&&/[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]/i.test(s.text))));
 check('audio-derived final speaker labels',transcript.segments.some(s=>s.speaker==='Hieu')&&transcript.segments.some(s=>s.speaker==='AI interviewer'));
 check('final timestamps fit exported duration',transcript.segments.every(s=>s.start>=0&&s.end>s.start&&s.end<=audio.duration+.1));
 check('no browser errors',errors.length===0);
 const report={language,checks,session_id:s.id,audio,previous_export:previousVersion,current_export:state.export_dir,playerVersion,errors,scope:'Short actual API interview using a synthetic guest fixture; not Hieu, not an hour of live API use. Re-export/player/obsolete approval checked without reload.'};
 await writeFile(OUT+'browser-e2e.json',JSON.stringify(report,null,2));
 await writeFile(OUT+'live-events.json',JSON.stringify(received));
 return report;
}
if(typeof process!=='undefined'&&import.meta.url===`file://${process.argv[1]}`){
 const {chromium}=await import('playwright');
 const browser=await chromium.launch({headless:true,args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+OUT+'synthetic-guest.wav']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['microphone']});
 await context.tracing.start({screenshots:true,snapshots:true});
 const page=await context.newPage();
 try{console.log(await run(page,context));}finally{await context.tracing.stop({path:OUT+'browser-trace.zip'});await browser.close();}
}
