// Trusted source acquisition, distinct from offline generated-app replay.
import {chromium} from 'playwright';import fs from 'node:fs/promises';import path from 'node:path';import http from 'node:http';import https from 'node:https';import dns from 'node:dns/promises';import net from 'node:net';import crypto from 'node:crypto';
const out=await fs.realpath(process.argv[2]),spec=JSON.parse(await fs.readFile(process.argv[3],'utf8'));let browser,local;const active=new Set(),records=[];let requests=0;
const deny=http.createServer((_q,s)=>{s.writeHead(403);s.end();});deny.on('connect',(_q,s)=>s.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'));await new Promise(r=>deny.listen(0,'127.0.0.1',r));
const ranges=[[0,8],[0x0a000000,8],[0x64400000,10],[0x7f000000,8],[0xa9fe0000,16],[0xac100000,12],[0xc0000000,24],[0xc0000200,24],[0xc0586300,24],[0xc0a80000,16],[0xc6120000,15],[0xc6336400,24],[0xcb007100,24],[0xe0000000,3]];
function publicAddress(ip){const n=ip.split('.').reduce((a,v)=>a*256+Number(v),0);return net.isIP(ip)===4&&!ranges.some(([base,bits])=>Math.floor(n/2**(32-bits))===Math.floor(base/2**(32-bits)));}
const publicQueryKeys=new Set(['q','query','search','lang','hl','page','p','limit','offset','sort','order','view','tab','url']);
const redirectStatuses=new Set([301,302,303,307,308]);
function publicURL(value,origin,depth=0){
 const u=new URL(value);if(depth>4||value.length>2000||value.includes('#')||(depth===0?u.protocol!=='https:':!['http:','https:'].includes(u.protocol))||u.username||u.password||depth===0&&(u.port&&u.port!=='443'||net.isIP(u.hostname.replace(/[\[\]]/g,'')))||origin&&u.origin!==origin)throw Error('Public destination/redirect refused');
 for(const [key,val] of u.searchParams){
  if(!publicQueryKeys.has(key.toLowerCase()))throw Error('Public destination/redirect refused');let candidate=val;
  for(let i=0;i<4;i++){let decoded;try{decoded=decodeURIComponent(candidate);if(/[\p{C}\uFFFD]/u.test(decoded))throw Error('Ambiguous Unicode');decoded=decoded.trim()}catch{throw Error('Public destination/redirect refused')}if(decoded===candidate)break;candidate=decoded;}
  if(candidate.includes('%')||candidate.includes(';')||/[\\\x00-\x1f\x7f]/.test(candidate))throw Error('Public destination/redirect refused');
  if(candidate.startsWith('//'))throw Error('Public destination/redirect refused');const absolute=/^[a-z][a-z0-9+.-]*:/i.test(candidate);
  if(key.toLowerCase()==='url'){if(val!==candidate||/\s/.test(candidate)||!absolute&&!candidate.startsWith('/'))throw Error('Public destination/redirect refused');}
  if(absolute)publicURL(candidate,undefined,depth+1);else publicURL('https://relative.invalid/'+candidate.replace(/^\//,''),undefined,depth+1);
 }return u;
}
async function fetchPublic(value,origin,follow=false,depth=0){
 if(++requests>100||depth>4)throw Error('Source request/redirect limit');const u=publicURL(value,origin);const ips=await dns.resolve4(u.hostname);if(!ips.length||!ips.every(publicAddress))throw Error('Non-public DNS refused');
 return await new Promise((resolve,reject)=>{
  const q=https.get({hostname:u.hostname,port:443,path:u.pathname+u.search,family:4,autoSelectFamily:false,agent:false,lookup:(_h,_o,cb)=>cb(null,ips[0],4),headers:{'User-Agent':'SelfPodcast/1.0 source capture','Accept':'*/*'}},r=>{
   let size=0,chunks=[];r.on('data',b=>{size+=b.length;if(size>8_000_000)q.destroy(Error('Source body limit'));else chunks.push(b)});r.on('error',reject);r.on('end',async()=>{
    try{if(redirectStatuses.has(r.statusCode)){if(!r.headers.location)throw Error('Missing redirect');const next=publicURL(new URL(r.headers.location,u).href,origin);if(!follow)throw Error('Redirected subresource/navigation unsupported');resolve(await fetchPublic(next.href,origin,true,depth+1));return;}
     resolve({url:u.href,status:r.statusCode,body:Buffer.concat(chunks),headers:{'content-type':r.headers['content-type']??'application/octet-stream'}});
    }catch(e){reject(e)}
   });
  });active.add(q);q.on('close',()=>active.delete(q));q.on('error',reject);q.setTimeout(8000,()=>q.destroy(Error('Source request timeout')));
 });
}
const mime={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.woff':'font/woff','.woff2':'font/woff2'};
async function localFile(root,value,files){
 const pathname=decodeURIComponent(new URL(value,'http://localhost').pathname),parts=pathname.split('/').filter(Boolean);if(!parts.length||pathname.endsWith('/'))parts.push('index.html');
 if(parts.some(x=>x.startsWith('.')||x.includes('\\'))||!mime[path.extname(parts.at(-1))])throw Error('Private local path refused');let p=root;
 for(const part of parts){p=path.join(p,part);if((await fs.lstat(p)).isSymbolicLink())throw Error('Symlink refused');}
 const real=await fs.realpath(p);if(!real.startsWith(root+path.sep))throw Error('Local path escaped');const stat=await fs.stat(real);if(!stat.isFile()||stat.size>8_000_000)throw Error('Local body limit');const body=await fs.readFile(real);files[path.relative(root,real)]=crypto.createHash('sha256').update(body).digest('hex');return {body,headers:{'content-type':mime[path.extname(real)]}};
}
try{
 browser=await chromium.launch({headless:true,chromiumSandbox:true,proxy:{server:`http://127.0.0.1:${deny.address().port}`,bypass:'<-loopback>'},args:['--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 for(const source of spec.sources){
  if(!/^s[0-3]$/.test(source.id)||!['public','local'].includes(source.type))throw Error('Invalid selected source');let url,origin,document,navigationURL,files={},blocked=[],mainError;
  if(source.type==='public'){url=publicURL(source.url).href;origin=new URL(url).origin;document=await fetchPublic(url,origin,true);if(document.status!==200)throw Error('Source returned non-success');navigationURL=document.url;}
  else{
   const root=await fs.realpath(source.root);if(root!==source.root)throw Error('Local root changed');local=http.createServer(async(q,s)=>{try{if(q.method!=='GET')throw Error('Method');const f=await localFile(root,q.url,files);s.writeHead(200,f.headers);s.end(f.body);}catch{s.writeHead(403);s.end();}});await new Promise(r=>local.listen(0,'127.0.0.1',r));origin=`http://127.0.0.1:${local.address().port}`;await fs.writeFile(path.join(out,'source-runtime-private.json'),JSON.stringify({id:source.id,pid:process.pid,port:local.address().port}));url=new URL(source.path??'/',origin).href;if(new URL(url).origin!==origin)throw Error('Local origin refused');
  }
  const context=await browser.newContext({viewport:{width:1280,height:720},serviceWorkers:'block',acceptDownloads:false});
  await context.route('**/*',async route=>{
   const req=route.request(),target=new URL(req.url());const main=req.isNavigationRequest()&&req.frame()===page.mainFrame();
   try{
    if(target.origin!==origin||req.method()!=='GET'||source.type==='local'&&++requests>100)throw Error('Source request refused');
    let response;
    if(source.type==='public'){if(main&&document&&target.href===navigationURL){response=document;document=undefined;}else response=await fetchPublic(target.href,origin);}
    else response=await new Promise((resolve,reject)=>{const q=http.get(target,{agent:false},r=>{let chunks=[];r.on('data',b=>chunks.push(b));r.on('end',()=>resolve({status:r.statusCode,body:Buffer.concat(chunks),headers:{'content-type':r.headers['content-type']??'application/octet-stream'}}));r.on('error',reject)});active.add(q);q.on('close',()=>active.delete(q));q.on('error',reject);q.setTimeout(8000,()=>q.destroy(Error('Local request timeout')));});
    if(response.status!==200)throw Error('Source returned non-success');
    await route.fulfill({status:response.status,body:response.body,headers:{...response.headers,'Content-Security-Policy':"default-src 'self' data:; connect-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-src 'none'; worker-src 'none'; object-src 'none'; form-action 'none'; base-uri 'none'; sandbox allow-scripts allow-same-origin"}});
   }catch(e){blocked.push({origin:target.origin,reason:e.message});if(main)mainError=e.message;await route.abort();}
  });
  const page=await context.newPage();page.on('download',d=>d.cancel());try{await page.goto(navigationURL??url,{waitUntil:'load',timeout:20000});}catch(e){await fs.writeFile(path.join(out,'source-capture-failure.json'),JSON.stringify({id:source.id,reason:mainError??'Page loading failed',blocked_requests:blocked},null,2));throw Error(mainError??'Page loading failed');}await page.waitForTimeout(500);if(mainError)throw Error(mainError);
  let focus=null,focusKind='heading';
  for(const selector of ['main h1, article h1, [role="main"] h1','main, article, [role="main"]','h1, h2']){
   const matches=page.locator(selector);
   for(let i=0,n=Math.min(50,await matches.count());i<n;i++){
    const candidate=matches.nth(i);
    if(!await candidate.isVisible()||!await candidate.evaluate(el=>!el.closest('header, nav, aside, [role="navigation"], [role="dialog"], dialog')&&el.innerText.trim().length>=3))continue;
    focus=candidate;focusKind=await candidate.evaluate(el=>/^H[12]$/.test(el.tagName)?'heading':'content');break;
   }
   if(focus)break;
  }
  if(!focus)throw Error('Source content unavailable under the confined capture boundary; no navigation-only reference accepted');
  await focus.evaluate(el=>el.scrollIntoView({block:'start'}));const focused=await focus.evaluate(el=>({focus_text:el.innerText.trim().slice(0,180),focus_top:el.getBoundingClientRect().top}));
  const viewport=await page.evaluate(()=>({scroll_x:scrollX,scroll_y:scrollY,width:innerWidth,height:innerHeight}));Object.assign(viewport,focused,{focus_kind:focusKind});
  const finalURL=page.url();if(source.type==='public')publicURL(finalURL,origin);const title=(await page.title()).slice(0,180),filename=`source-${source.id}.png`;await page.screenshot({path:path.join(out,filename)});await context.close();
  records.push({id:source.id,type:source.type,label:source.label??source.project_id??new URL(url).hostname,...(source.type==='public'?{selected_url:url,url:finalURL}:{project_id:source.project_id,served_files:files}),title,viewport,file:filename,sha256:crypto.createHash('sha256').update(await fs.readFile(path.join(out,filename))).digest('hex'),blocked_requests:blocked});
  if(local){local.closeAllConnections();await new Promise(r=>local.close(r));local=null;}
 }
 await fs.writeFile(path.join(out,'source-provenance.json'),JSON.stringify({sources:records,policy:'Explicit selected sources only; pinned public IPv4 HTTPS/same-origin redirects; local static public subtree read-only; fresh transport-confined browser; no credentials/private profile'},null,2));
}finally{
 for(const q of active)q.destroy();if(browser)await browser.close();if(local){local.closeAllConnections();await new Promise(r=>local.close(r));}deny.closeAllConnections();await new Promise(r=>deny.close(r));
}
