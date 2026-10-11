// Trusted typed controller: capture only a sealed disposable HTML app, never user Chrome.
import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {performance} from 'node:perf_hooks';
const root=await fs.realpath(process.argv[2]);
const story=JSON.parse(await fs.readFile(path.join(root,'storyboard.json'),'utf8'));
const captions=JSON.parse(await fs.readFile(path.join(root,'captions.json'),'utf8')).cues;
const allowed=new Set(story.scenes.map((_,i)=>`scene-${i}.html`));
for(const scene of story.scenes)for(const asset of scene.assets)allowed.add(`asset-${asset.id}.png`);
const sources=story.source_uses??[];
for(const use of sources){if(!/^s[0-3]$/.test(use.id)||use.clip&&use.clip!==`source-${use.id}.webm`)throw Error('Invalid source asset');allowed.add(`source-${use.id}.png`);if(use.clip)allowed.add(use.clip);}
let origin;
const server=http.createServer(async(req,res)=>{
 try{
  const target=new URL(req.url,origin),name=decodeURIComponent(target.pathname.slice(1));
  if(target.origin!==origin||req.method!=='GET'||!allowed.has(name)){res.writeHead(403);res.end();return;}
  const file=await fs.realpath(path.join(root,name));if(path.dirname(file)!==root)throw Error('Outside job');
  res.setHeader('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; media-src 'self'; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; worker-src 'none'");
  res.setHeader('Content-Type',name.endsWith('.html')?'text/html; charset=utf-8':name.endsWith('.webm')?'video/webm':'image/png');const bytes=await fs.readFile(file);let body=bytes;
  if(name.endsWith('.webm')){
   res.setHeader('Accept-Ranges','bytes');
   if(req.headers.range){const match=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range),start=match?Number(match[1]):NaN,end=match&&match[2]?Math.min(Number(match[2]),bytes.length-1):bytes.length-1;
    if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start>=bytes.length||end<start){res.writeHead(416,{'Content-Range':`bytes */${bytes.length}`});res.end();return;}
    res.statusCode=206;res.setHeader('Content-Range',`bytes ${start}-${end}/${bytes.length}`);body=bytes.subarray(start,end+1);
   }
  }
  res.setHeader('Content-Length',body.length);res.end(body);
 }catch{res.writeHead(404);res.end();}
});
// The same strict server is the browser proxy: never tunnel TURN/TLS or forward.
server.on('connect',(_req,socket)=>socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'));
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
origin=`http://127.0.0.1:${server.address().port}`;
let browser;
const events=[],clips=[],blocked=[];
const wait=ms=>new Promise(resolve=>setTimeout(resolve,Math.max(0,ms)));
try{
 // Policy 4 forces WebRTC through the deny-tunnel HTTP proxy; no UDP/DNS bypass.
 browser=await chromium.launch({headless:true,chromiumSandbox:true,proxy:{server:origin,bypass:'<-loopback>'},args:['--force-webrtc-ip-handling-policy=disable_non_proxied_udp','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
 for(let i=0;i<story.scenes.length;i++){
  const scene=story.scenes[i];const created=performance.now();
  const context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:path.join(root,'capture'),size:{width:1280,height:720}},serviceWorkers:'block',acceptDownloads:false});
  await context.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.origin===origin&&allowed.has(decodeURIComponent(url.pathname.slice(1)))&&route.request().method()==='GET')await route.continue();
   else{blocked.push({scheme:url.protocol,host:url.host});await route.abort();}
  });
  const page=await context.newPage();page.on('download',d=>d.cancel());
  await page.goto(`${origin}/scene-${i}.html`,{waitUntil:'load',timeout:30000});
  await page.evaluate(()=>{
   const caption=document.createElement('div');caption.id='podcast-captions';Object.assign(caption.style,{position:'fixed',bottom:'18px',left:'55px',right:'55px',font:'25px Arial',lineHeight:'1.3',color:'#fff',background:'#101820ed',padding:'12px 18px',borderRadius:'8px',textAlign:'center',zIndex:2147483647,pointerEvents:'none'});document.body.append(caption);
   const note=document.createElement('div');note.textContent='Episode illustration · recorded interactive app · captions estimated';Object.assign(note.style,{position:'fixed',bottom:'1px',left:'40px',font:'11px Arial',color:'#bcc7c3',zIndex:2147483647,pointerEvents:'none'});document.body.append(note);
   const source=document.createElement('div');source.id='podcast-source';Object.assign(source.style,{display:'none',position:'fixed',inset:'15px 35px 120px',background:'#101820',boxShadow:'0 0 0 100vmax #101820',zIndex:2147483646,padding:'12px',pointerEvents:'none'});document.body.append(source);
  });
  const start=performance.now();const offset=(start-created)/1000;
  let shown,interacting=false;
  const timer=setInterval(()=>{
   const now=scene.start+(performance.now()-start)/1000;const active=captions.filter(c=>c.start<=now&&c.end>now);
   page.locator('#podcast-captions').evaluate((el,text)=>{el.textContent=text;},active.map(c=>c.text).join(' · ')).catch(()=>{});
   const source=interacting?undefined:sources.find(s=>s.start<=now&&s.end>now);
   if(source?.id!==shown){shown=source?.id;if(source)events.push({type:'source',item:source.id,scheduled_time:source.start,actual_time:now,evidence:source.evidence,clip:source.clip??null});page.locator('#podcast-source').evaluate((el,s)=>{el.replaceChildren();el.style.display=s?'block':'none';if(s){const label=document.createElement('div');label.textContent='Captured source · '+s.label+(s.clip?' · fitted playback':'');Object.assign(label.style,{font:'22px Arial',color:'white',height:'32px',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'});const img=document.createElement(s.clip?'video':'img');img.src='/'+(s.clip??'source-'+s.id+'.png');if(s.clip){img.muted=true;img.autoplay=true;img.playsInline=true;img.addEventListener('loadedmetadata',()=>{img.currentTime=Math.min(s.playbackOffset,Math.max(0,img.duration-.01));});}Object.assign(img.style,{width:'100%',height:'calc(100% - 32px)',objectFit:'contain',background:'white'});el.append(label,img);}},source?{...source,playbackOffset:Math.max(0,now-source.start)}:null).catch(()=>{});}
  },120);
  await page.screenshot({path:path.join(root,`frame-${i}-initial.png`)});
  try{
   for(let j=0;j<scene.actions.length;j++){
    const a=scene.actions[j];await wait((a.time-scene.start)*1000-(performance.now()-start));
    const actual=scene.start+(performance.now()-start)/1000;
    interacting=true;shown=undefined;await page.locator('#podcast-source').evaluate(el=>{el.style.display='none';});
    if(a.type==='drag'){
     const card=page.locator(`[data-item="${a.item}"]`),zone=page.locator(`[data-tier="${a.tier}"]`);
     if(await card.count()!==1||await zone.count()!==1)throw Error('Ambiguous/missing interactive item or tier');
     await page.screenshot({path:path.join(root,`frame-${i}-${j}-before.png`)});
     const from=await card.boundingBox(),to=await zone.boundingBox();if(!from||!to)throw Error('Drag target not visible');
     await page.mouse.move(from.x+from.width/2,from.y+from.height/2);await page.mouse.down();
     await page.mouse.move((from.x+to.x)/2,(from.y+to.y)/2,{steps:8});
     await page.screenshot({path:path.join(root,`frame-${i}-${j}-during.png`)});
     await page.mouse.move(to.x+Math.min(to.width-15,120),to.y+to.height/2,{steps:12});
     await page.mouse.move(to.x+Math.min(to.width-15,120)+1,to.y+to.height/2);await page.mouse.up();
     const rank=await card.evaluate(el=>el.closest('[data-tier]')?.getAttribute('data-tier'));
     if(rank!==a.tier)throw Error('Actual drag did not result in the declared tier');
     events.push({...a,scene:i,scheduled_time:a.time,actual_time:actual,observed_rank:rank});
    }else{
     const control=page.locator(`[data-control="${a.item}"]`);if(await control.count()!==1)throw Error('Ambiguous/missing visualization control');
     await control.click();events.push({...a,scene:i,scheduled_time:a.time,actual_time:actual});
    }
    await wait(150);await page.screenshot({path:path.join(root,`frame-${i}-${j}-after.png`)});interacting=false;
   }
   await wait((scene.end-scene.start)*1000-(performance.now()-start));
   await page.screenshot({path:path.join(root,`frame-${i}-final.png`)});
  }finally{clearInterval(timer);}
  const video=page.video();await context.close();const videoPath=await video.path();
  clips.push({file:path.relative(root,videoPath),offset,scene_start:scene.start,scene_end:scene.end});
  await fs.writeFile(path.join(root,'capture-events.json'),JSON.stringify(events,null,2));
  await fs.writeFile(path.join(root,'capture-clips.json'),JSON.stringify(clips,null,2));
 }
 await fs.writeFile(path.join(root,'capture-security.json'),JSON.stringify({fresh_profile:true,no_permissions:true,network:'Declared job HTML/images only; strict HTTP proxy denies CONNECT, WebRTC non-proxied UDP disabled, DNS resolver denied, CSP/connect-src none',blocked_requests:blocked,viewport:[1280,720]},null,2));
}finally{
 if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));
}
