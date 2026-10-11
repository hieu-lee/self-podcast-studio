// Scoped runtime browser bridge, never a private profile or general local proxy.
import fs from 'node:fs/promises';import path from 'node:path';import http from 'node:http';import crypto from 'node:crypto';import os from 'node:os';import {execFileSync,execFile} from 'node:child_process';import {promisify} from 'node:util';
if(typeof WebSocket!=='function')throw Error('Node WebSocket unavailable; start runtime capture with --experimental-websocket');
// Resolve all installed tool binaries (including recorder FFmpeg), never a profile.
process.env.PLAYWRIGHT_BROWSERS_PATH??=path.join(os.userInfo().homedir,process.platform==='darwin'?'Library/Caches/ms-playwright':'.cache/ms-playwright');
const {chromium}=await import('playwright');
const out=await fs.realpath(process.argv[2]),spec=JSON.parse(await fs.readFile(process.argv[3],'utf8'));
if(!/^s[0-3]$/.test(spec.id))throw Error('Invalid source asset');
const endpoints=new Map(spec.endpoints.map(e=>[String(e.port),e])),active=new Set(),sockets=new Set(),requests=[],blocked=[];let browser,frames=0,total=0,mainError;
const deny=http.createServer((_q,s)=>{s.writeHead(403);s.end()});deny.on('connect',(_q,s)=>s.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'));await new Promise(r=>deny.listen(0,'127.0.0.1',r));
const sensitive=/(?:sk-(?:proj-|svcacct-)?[\w-]{16,}|gh[pousr]_[\w]{20,}|-----BEGIN .*PRIVATE KEY|(?:password|secret|api[_ -]?key|access[_ -]?token|authorization|database_url)\s*[:=]\s*\S+)/i;
const privateView=/\/(?:Users|home|private|etc)\/|file:\/\/|[A-Z]:\\(?:Users|Windows)\\/i;let unsafeView=false;
function canonical(value){
 for(let i=0;i<4;i++){const next=decodeURIComponent(value);if(next===value)break;value=next;}
 if(value.includes('%')||/[\x00-\x1f\x7f]/.test(value))throw Error('Ambiguous app encoding refused');return value;
}
function privateQueryTarget(value){
 if(privateView.test(value)||/\.(?:env|pem|key|(?:sqlite3?|db3?|duckdb)(?:[-.].*)?)(?:$|[\\/])/i.test(value))return true;
 const fileLike=/[\\/]/.test(value)||/^[^\\/]+\.[A-Za-z0-9_-]+$/.test(value);
 return value.split(/[\\/]/).some(p=>/secret|credential|password|auth\.json|^auth$/i.test(p)||fileLike&&p.startsWith('.'));
}
function guardPayload(data){
 if(data==null)return;const bytes=Buffer.from(data);if(bytes.length>64000)throw Error('Runtime request body limit');
 let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes)}catch{throw Error('Opaque app payload refused')}
 let examined=0;
 function check(value,depth=0){
  if(++examined>1000||depth>10)throw Error('App payload complexity limit');
  if(value&&typeof value==='object'){for(const [key,item] of Object.entries(value)){if(/token|secret|password|auth|cookie|key|signature|credential/i.test(canonical(key)))throw Error('Private app payload refused');check(item,depth+1);}return;}
  if(typeof value!=='string')return;const decoded=canonical(value);if(sensitive.test(decoded)||privateQueryTarget(decoded)||/^[a-z][a-z0-9+.-]*:/i.test(decoded)||decoded.startsWith('//'))throw Error('Private app payload refused');
 }
 const trimmed=text.trim();if(!trimmed)return;
 if(/^[{["]/.test(trimmed)){let parsed;try{parsed=JSON.parse(trimmed)}catch{throw Error('Ambiguous app payload refused')}check(parsed);}
 else if(trimmed.includes('=')){for(const [key,value] of new URLSearchParams(trimmed)){if(/token|secret|password|auth|cookie|key|signature|credential/i.test(canonical(key)))throw Error('Private app payload refused');check(value);}}
 else check(trimmed);
}
function permitted(value,method){
 const u=new URL(value);if(!['http:','ws:'].includes(u.protocol)||u.hostname!=='127.0.0.1'||u.username||u.password||u.hash||!endpoints.has(u.port))throw Error('Unapproved app destination');
 const pathname=canonical(u.pathname);
 if(sensitive.test(pathname)||privateQueryTarget(pathname))throw Error('Credential/private app pathname refused');
 if(pathname.includes('\\')||pathname.split('/').some(p=>p.startsWith('.')||/^(?:admin|account|accounts|login|logout|profile|credentials|secrets|keys|etc|proc)$/i.test(p))||/\.(?:env|pem|key|(?:sqlite3?|db3?|duckdb)(?:[-.].*)?)(?:$|\/)/i.test(pathname))throw Error('Private app path refused');
 for(const [rawKey,rawValue] of u.searchParams){const key=canonical(rawKey),value=canonical(rawValue);if(/token|secret|password|auth|cookie|key|signature|credential/i.test(key)||sensitive.test(value)||privateQueryTarget(value)||/^[a-z][a-z0-9+.-]*:/i.test(value)||value.startsWith('//'))throw Error('Credential/private/nested app query refused');}
 const endpoint=endpoints.get(u.port);if(!endpoint.routes.some(r=>(r.prefix==='/'||pathname===r.prefix||pathname.startsWith(r.prefix.endsWith('/')?r.prefix:r.prefix+'/'))&&r.methods.includes(method)))throw Error('Unapproved app route/method');
 if(endpoint.reuse_pid&&!['GET','WS'].includes(method))throw Error('Reused application is read-only');verifyListener(u.port);return u;
}
function verifyListener(port){
 try{
  const listeners=execFileSync('/usr/sbin/lsof',['-nP','-iTCP:'+port,'-sTCP:LISTEN','-Fpn'],{encoding:'utf8'}).split('\n');const names=listeners.filter(s=>s.startsWith('n'));if(!names.length||names.some(s=>s!=='n127.0.0.1:'+port))throw Error('Nonloopback listener');
  const pids=listeners.filter(s=>s.startsWith('p')).map(s=>Number(s.slice(1)));
  if(!pids.length)throw Error('No listener');
  for(const pid of pids){const binding=spec.bindings?.find(b=>String(b.port)===port&&b.pid===pid);if(!binding||execFileSync('ps',['-p',String(pid),'-o','lstart='],{encoding:'utf8'}).trim()!==binding.birth)throw Error('Wrong identity');}
 }catch{throw Error('Runtime listener identity changed')}
}
async function get(value,method='GET',body,headers={},follow=false,depth=0){
 if(++total>300||depth>4)throw Error('Runtime request budget');const u=permitted(value,method);guardPayload(body);
 return await new Promise((resolve,reject)=>{
  const q=http.request({hostname:'127.0.0.1',port:u.port,path:u.pathname+u.search,method,agent:false,headers:{Accept:'*/*',...(headers['content-type']?{'Content-Type':headers['content-type']}:{})}},r=>{
   let size=0,chunks=[];r.on('error',reject);r.on('data',b=>{size+=b.length;if(size>8_000_000)q.destroy(Error('Runtime response body limit'));else chunks.push(b)});r.on('end',async()=>{
    try{if([301,302,303,307,308].includes(r.statusCode)){if(!follow||!r.headers.location)throw Error('App redirect unsupported here');const next=permitted(new URL(r.headers.location,u).href,'GET');resolve(await get(next.href,'GET',undefined,{},true,depth+1));return;}
     requests.push({port_role:endpoints.get(u.port).role,path:u.pathname,method,status:r.statusCode});resolve({url:u.href,status:r.statusCode,body:Buffer.concat(chunks),headers:{...(r.headers['content-type']?{'content-type':r.headers['content-type']}:{}),'Access-Control-Allow-Origin':'*'}});
    }catch(e){reject(e)}
   });
  });active.add(q);q.on('close',()=>active.delete(q));q.on('error',reject);q.setTimeout(8000,()=>q.destroy(Error('Runtime request timeout')));q.end(body);
 });
}
function safeText(text){if(unsafeView||sensitive.test(text)||privateView.test(text))throw Error('Sensitive application view withheld');return text.slice(0,5000)}
async function inspectText(page){
 for(const port of endpoints.keys())verifyListener(port);
 await page.locator('input[type=password]').evaluateAll(elements=>elements.forEach(el=>{el.value='';el.style.visibility='hidden'}));
 const view=await page.evaluate(()=>window.__selfPodcastReadView());safeText(view.values);return safeText(view.text);
}
try{
 const document=await get(`http://127.0.0.1:${spec.page_port}${spec.page_path}`,'GET',undefined,{},true);if(document.status!==200)throw Error('App page not ready');let initial=document;
 browser=await chromium.launch({headless:true,chromiumSandbox:true,proxy:{server:`http://127.0.0.1:${deny.address().port}`,bypass:'<-loopback>'},args:['--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 const context=await browser.newContext({viewport:{width:1280,height:720},serviceWorkers:'block',acceptDownloads:false,...(!spec.inspect?{recordVideo:{dir:path.join(out,'runtime-capture'),size:{width:1280,height:720}}}:{})});
 await context.exposeBinding('__selfPodcastUnsafeView',()=>{unsafeView=true});
 await context.addInitScript(({sensitiveSource,privateSource})=>{
  const secret=new RegExp(sensitiveSource,'i'),privatePath=new RegExp(privateSource,'i'),roots=new Set();let flagged=false,dirty=true;
  function flag(){if(!flagged){flagged=true;window.__selfPodcastUnsafeView().catch(()=>{})}}
  function track(root){if(roots.has(root))return;if(roots.size>=1000){flag();return;}roots.add(root);dirty=true;new MutationObserver(()=>{dirty=true;scan()}).observe(root,{subtree:true,childList:true,attributes:true,characterData:true});}
  function readView(){
   if(dirty){dirty=false;for(const root of roots)for(const el of root.querySelectorAll('*'))if(el.shadowRoot)track(el.shadowRoot);}
   const text=[document.body?.innerText??'',document.title],values=[];let examined=0;
   for(const root of roots){
    if(root.host&&!root.host.isConnected)continue;
    for(const el of root.querySelectorAll('*')){
     if(++examined>10000){flag();break;}const box=el.getBoundingClientRect();if(!box.width||!box.height)continue;
     if(el.matches('input:not([type=password]),textarea'))values.push(el.value);
     if(el.matches('select'))text.push([...el.selectedOptions].map(option=>option.label).join(' '));
     for(const name of ['placeholder','alt','title','aria-label'])text.push(el.getAttribute(name)??'');
     const generated=['::before','::after'].map(pseudo=>{const style=getComputedStyle(el,pseudo);if(style.display==='none'||style.visibility!=='visible'||['none','normal'].includes(style.content))return '';return style.content.startsWith('"')&&style.content.endsWith('"')?style.content.slice(1,-1):style.content;});
     if(generated.some(Boolean))text.push(generated[0]+(el.innerText??el.textContent??'')+generated[1]);
    }
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),rendered=[];let node;
    while(node=walker.nextNode()){if(++examined>10000){flag();break;}const range=document.createRange();range.selectNodeContents(node);const box=range.getBoundingClientRect();if(box.width&&box.height&&(!node.parentElement||getComputedStyle(node.parentElement).visibility==='visible'))rendered.push(node.textContent);}
    text.push(rendered.join(''));
   }
   return {text:text.join('\n'),values:values.join('\n')};
  }
  function scan(){if(flagged)return;const view=readView(),text=view.text+'\n'+view.values;if(secret.test(text)||privatePath.test(text))flag();}
  // Observe open components before app scripts run; inaccessible views fail closed.
  const attach=Element.prototype.attachShadow;Element.prototype.attachShadow=function(...args){const root=attach.apply(this,args);if(root.mode==='open')track(root);else flag();return root;};
  for(const owner of [Element.prototype,ShadowRoot.prototype,Document])for(const name of ['setHTMLUnsafe','parseHTMLUnsafe','parseHTML'])if(typeof owner[name]==='function'){const original=owner[name];owner[name]=function(...args){if(/shadowrootmode/i.test(String(args[0])))flag();return original.apply(this,args);};}
  Object.defineProperty(window,'__selfPodcastReadView',{value:readView,writable:false,configurable:false});track(document);
  // Value setters do not emit DOM mutations; monitor them before the next paint.
  for(const prototype of [HTMLInputElement.prototype,HTMLTextAreaElement.prototype]){const descriptor=Object.getOwnPropertyDescriptor(prototype,'value');Object.defineProperty(prototype,'value',{...descriptor,set(value){descriptor.set.call(this,value);scan()}})}
  document.addEventListener('input',scan,true);
  const tick=()=>{scan();requestAnimationFrame(tick)};tick();
 },{sensitiveSource:sensitive.source,privateSource:privateView.source});
 const origins=spec.endpoints.map(e=>`http://127.0.0.1:${e.port}`),wsOrigins=spec.endpoints.map(e=>`ws://127.0.0.1:${e.port}`);
 const csp=`default-src 'self' data: blob:; connect-src ${[...origins,...wsOrigins].join(' ')}; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: ${origins.join(' ')}; frame-src 'none'; object-src 'none'; form-action 'self'; base-uri 'none'; worker-src 'self' blob:; sandbox allow-scripts allow-same-origin`;
 await context.route('**/*',async route=>{
  const req=route.request();try{
   if(req.headers()['authorization']||req.headers()['cookie'])throw Error('App credential headers refused');
   if(req.method()==='OPTIONS'){
    const method=req.headers()['access-control-request-method'];permitted(req.url(),method);await route.fulfill({status:204,headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':method,'Access-Control-Allow-Headers':'content-type'}});return;
   }
   permitted(req.url(),req.method());const main=req.isNavigationRequest()&&req.frame()===page.mainFrame();let response;
   if(main&&initial&&req.url()===initial.url){response=initial;initial=undefined}else response=await get(req.url(),req.method(),req.postDataBuffer(),req.headers());
   if(req.isNavigationRequest()&&/<template\b[\s\S]*\bshadowrootmode\b/i.test(response.body.toString('utf8'))){unsafeView=true;throw Error('Uninspectable declarative Shadow DOM withheld');}
   await route.fulfill({status:response.status,body:response.body,headers:{...response.headers,'Content-Security-Policy':csp}});
   }catch(e){blocked.push({kind:'http',reason:e.message});if(req.isNavigationRequest()||e.message==='Runtime listener identity changed')mainError=e.message;await route.abort()}
 });
 const socketErrors=[];
 await context.routeWebSocket('**/*',route=>{
  let peer;
  try{
   permitted(route.url(),'WS');peer=new WebSocket(route.url());sockets.add(peer);const queue=[];
   const checkFrame=data=>{verifyListener(new URL(route.url()).port);if(++frames>200||Buffer.byteLength(data)>64000)throw Error('Runtime WebSocket frame budget')};
   const refuse=e=>{mainError=e.message;blocked.push({kind:'websocket',reason:e.message});peer.close();route.close()};
   route.onMessage(data=>{try{if(endpoints.get(new URL(route.url()).port).reuse_pid)throw Error('Reused outbound WebSocket data refused');checkFrame(data);guardPayload(data);if(peer.readyState===WebSocket.OPEN)peer.send(data);else if(queue.length<10)queue.push(data)}catch(e){refuse(e)}});
   peer.addEventListener('open',()=>{try{verifyListener(new URL(route.url()).port);for(const data of queue)peer.send(data)}catch(e){refuse(e)}});
   peer.addEventListener('message',async e=>{try{const data=typeof e.data==='string'?e.data:Buffer.from(await e.data.arrayBuffer());checkFrame(data);route.send(data)}catch(e){refuse(e)}});
   peer.addEventListener('error',()=>{socketErrors.push('Approved app WebSocket failed');route.close()});peer.addEventListener('close',()=>{sockets.delete(peer);route.close()});route.onClose(()=>peer.close());
  }catch(e){blocked.push({kind:'websocket',reason:e.message});route.close()}
 });
 const created=performance.now();const page=await context.newPage();page.on('download',d=>{mainError='Application navigation triggered a download; select a public UI route';d.cancel().catch(()=>{})});page.on('filechooser',f=>f.setFiles([]).catch(()=>{}));try{await page.goto(document.url,{waitUntil:'load',timeout:20000});}catch(e){throw Error(mainError??e.message);}await page.waitForTimeout(1000);if(mainError)throw Error(mainError);
 const before=await inspectText(page);const title=safeText(await page.title()).slice(0,180);const controls=(await page.getByRole('button').evaluateAll(elements=>elements.slice(0,30).map(el=>el.innerText??''))).map(text=>safeText(text).slice(0,180));
 if(spec.inspect){
  await page.screenshot({path:path.join(out,`runtime-inspect-${spec.id}.png`)});await fs.writeFile(path.join(out,'runtime-view-private.json'),JSON.stringify({title,text:before,buttons:controls.slice(0,30)}));await context.close();
 }else{
  await page.screenshot({path:path.join(out,`source-${spec.id}-before.png`)});const ready=performance.now();await page.waitForTimeout(700);const performed=[];
  for(const action of spec.actions){
   if(/delete|remove|reset|login|sign.?in|password|pay|purchase|send|upload|download|account/i.test(action.name)||sensitive.test(action.value))throw Error('Private/destructive interaction refused');
   const locator=page.getByRole(action.role,{name:action.name,exact:true});if(await locator.count()!==1)throw Error('Runtime interaction missing/ambiguous');
   if(action.type==='click')await locator.click({timeout:3000});else if(action.type==='fill'&&action.role==='textbox')await locator.fill(action.value);else if(action.type==='select'&&action.role==='combobox')await locator.selectOption({label:action.value});else throw Error('Unsupported typed runtime action');
   await page.waitForTimeout(700);await inspectText(page);performed.push({type:action.type,role:action.role,name:action.name});
  }
  await page.waitForTimeout(1500);const after=await inspectText(page);if(mainError||socketErrors.length)throw Error(mainError??socketErrors[0]);const file=`source-${spec.id}.png`;await page.screenshot({path:path.join(out,file)});const usable=(performance.now()-ready)/1000,offset=(ready-created)/1000,playback=spec.duration??usable;
  if(!Number.isFinite(playback)||playback<=0||spec.duration!==undefined&&(playback<3||playback>8))throw Error('Invalid runtime source interval');
  const video=page.video();await context.close();const raw=await video.path();await browser.close();browser=undefined;safeText(after);const clip=`source-${spec.id}.webm`;
  await promisify(execFile)('ffmpeg',['-v','error','-y','-ss',String(offset),'-i',raw,'-vf',`trim=duration=${usable},setpts=${playback/usable}*(PTS-STARTPTS),fps=25,tpad=stop_mode=clone:stop_duration=1`,'-t',String(playback),'-an','-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-threads','2',path.join(out,clip)],{timeout:30000,maxBuffer:1000000});
  await fs.writeFile(path.join(out,'runtime-events.json'),JSON.stringify({before,after,actions:performed,requests,websocket_frames:frames,blocked_requests:blocked,policy:'Only verified app ports/routes/methods; fresh profile/deny transport; no cookies/auth/file/private paths'},null,2));
  await fs.writeFile(path.join(out,'runtime-capture.json'),JSON.stringify({id:spec.id,title,file,sha256:crypto.createHash('sha256').update(await fs.readFile(path.join(out,file))).digest('hex'),clip,clip_sha256:crypto.createHash('sha256').update(await fs.readFile(path.join(out,clip))).digest('hex'),clip_timing:{ready_offset:offset,recorded_demonstration_duration:usable,playback_duration:playback,method:'Loading trimmed; complete actual before/actions/after footage fitted to native source interval, no audio'},before_file:`source-${spec.id}-before.png`,before_sha256:crypto.createHash('sha256').update(await fs.readFile(path.join(out,`source-${spec.id}-before.png`))).digest('hex'),interaction_count:performed.length,websocket_frames:frames,blocked_requests:blocked},null,2));
 }
}finally{
 for(const q of active)q.destroy();for(const socket of sockets)socket.close();if(browser)await browser.close();deny.closeAllConnections();await new Promise(r=>deny.close(r));
}
