/** Intended redesign contract and retained controls. Written before UI integration. */
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {chromium} from 'playwright';
const root=new URL('../',import.meta.url).pathname,out=root+'.artifacts/research/';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},colorScheme:'light'});
await context.addInitScript(()=>{window.micCalls=0;navigator.mediaDevices.getUserMedia=()=>{window.micCalls++;throw new Error('UI inspection must not capture audio');};});
await context.tracing.start({screenshots:true,snapshots:true});
const page=await context.newPage(),checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
const fixture=id=>({id,topic:'Owned UI fixture — never a human recording',language:'vi',frames:24000*30,epochs:[{epoch:0,expected:30}],research_enabled:'yes',export_dir:'owned-export-v1',polished_audio:true,export_audio_review:'yes',research:[{id:'owned-evidence',status:'ready',query:'Official public topic',summary:'A public sourced fact.',retrieved_at:'2026-10-11T12:00:00Z',model:'owned-ui-fixture',web_searches:1,parts:[{text:'A public fact. '},{text:'Official source',url:'https://openai.com/'}],sources:[{title:'Official source',url:'https://openai.com/',published_at:null}]}],video:{state:'completed',progress:100,message:'Owned UI fixture only',job_id:'owned-job',approved:false}});
const sessions=[fixture('owned-ui-one'),{...fixture('owned-ui-two'),export_audio_review:'no'}];
await page.route('**/api/sessions**',async route=>{const url=new URL(route.request().url());if(route.request().method()!=='GET')throw new Error('UI inspection must not mutate episodes');if(url.pathname==='/api/sessions')return route.fulfill({json:sessions});const s=sessions.find(s=>url.pathname==='/api/sessions/'+s.id);if(s)return route.fulfill({json:s});return route.fulfill({status:404,body:'Owned UI fixture has no real media'});});
await page.route('**/api/video-sources',route=>route.fulfill({json:{projects:[{id:'owned-app',kind:'application',label:'Trusted application fixture'}]}}));
try{
 const response=await page.goto('http://127.0.0.1:8765');
 const served=await response.text(),built=await readFile(root+'frontend/dist/index.html','utf8');assert.equal(served,built);assert.match(response.headers()['cache-control'],/no-store/);checks.push('served HTML exactly matches worktree build; no-store');
 await page.getByRole('link',{name:'Self Podcast',exact:true}).waitFor();assert.equal(await page.locator('.heading,.eyebrow,.grid,.studio').count(),0);
 assert.equal(await page.locator('.stage').count(),1);assert.equal(await page.locator('textarea.topic').count(),1);assert.ok((await page.locator('#topic').evaluate(e=>getComputedStyle(e).fontFamily)).includes('Georgia'));
 assert.equal(await page.getByRole('button',{name:'Start the conversation',exact:true}).evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(210, 47, 38)');
 await page.getByLabel('Podcast language').selectOption('vi');await page.getByLabel('Public research query').fill('Only a short public query');assert.equal(await page.evaluate(()=>micCalls),0);
 await page.screenshot({path:out+'redesign-setup-light.png',fullPage:true,animations:'disabled'});checks.push('intended topic-first serif/red CTA, language and public-query controls; setup never opens mic');
 await page.locator('[data-session-id="owned-ui-one"]').click();await page.getByLabel('Public visual sources').waitFor();
 for(const name of ['Resume recording','Retry upload','Make the episode',"I've listened and checked the episode",'Make a new video attempt','I have watched and checked this video'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),1,name);
 for(const name of ['AI audio repair (never my voice)','Speaker balance & cautious noise/cough cleanup','Accept capture gaps or lost audio'])assert.equal(await page.getByLabel(name,{exact:true}).count(),1,name);
 await page.getByText('Startup has full machine execution, not an OS sandbox:',{exact:false}).waitFor();
 assert.equal(await page.locator('audio').getAttribute('src'),'/api/sessions/owned-ui-one/files/episode.mp3?version=owned-export-v1');assert.match(await page.locator('video').getAttribute('src'),/owned-job\/files\/episode.mp4\?version=owned-export-v1$/);
 assert.equal(await page.getByRole('link',{name:'Noise & volume audit',exact:true}).count(),1);assert.equal(await page.getByRole('link',{name:'AI audio diagnosis',exact:true}).count(),1);assert.equal(await page.getByRole('link',{name:'Original guest',exact:true}).count(),1);assert.ok(await page.locator('.research-panel a[href="https://openai.com/"]').count());
 await page.getByLabel('Public visual sources').fill('https://example.com/');await page.getByLabel('Application runtime · Trusted application fixture',{exact:true}).check();await page.locator('[data-session-id="owned-ui-two"]').click();await page.locator('.session.selected[data-session-id="owned-ui-two"]').waitFor();await page.waitForFunction(()=>document.querySelector('[aria-label="Public visual sources"]').value==='');assert.equal(await page.getByLabel('Public visual sources').inputValue(),'');assert.equal(await page.getByLabel('Application runtime · Trusted application fixture',{exact:true}).isChecked(),false);assert.equal(await page.evaluate(()=>micCalls),0);for(const name of ['AI audio diagnosis','Validated audio plan'])assert.equal(await page.getByRole('link',{name,exact:true}).count(),0,'no-repair export excludes '+name);checks.push('audio/research/video controls and version binding retained; no-repair version excludes diagnosis/plan; episode selection resets visual consent without mic');
 for(const scheme of ['light','dark']){await page.emulateMedia({colorScheme:scheme});assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).colorScheme),scheme);for(const [label,width,height] of [['desktop',1440,1000],['mobile',390,844]]){await page.setViewportSize({width,height});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow '+scheme+label);await page.screenshot({path:out+`redesign-saved-${scheme}-${label}.png`,fullPage:true,animations:'disabled'});}}
 checks.push('desktop/mobile/light/dark screenshot artifacts, no overflow');assert.deepEqual(errors,[]);
 await writeFile(out+'ui-restore-e2e.json',JSON.stringify({checks,scope:'Real built frontend; owned mocked saved export/video metadata only. Not paid export/video-job validation or human listening approval.'},null,2));console.log(checks);
}finally{await context.tracing.stop({path:out+'ui-restore-trace.zip'});await browser.close();}
