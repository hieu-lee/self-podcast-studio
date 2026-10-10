export async function api(path, options={}) {
  const r=await fetch('/api/'+path,{signal:AbortSignal.timeout(15000),...options,headers:{'X-Self-Podcast':'1',...(options.body instanceof ArrayBuffer?{}:{'Content-Type':'application/json'}),...options.headers}});
  if(!r.ok){const e=await r.json().catch(()=>({detail:'Local server unavailable'}));throw new Error(e.detail||'Request failed');}
  return r.json();
}
let database;
async function db() {
  if(!database)database=await new Promise((resolve,reject)=>{
    const r=indexedDB.open('self-podcast-recording',1);
    r.onupgradeneeded=()=>{r.result.createObjectStore('chunks',{keyPath:'id'});r.result.createObjectStore('ends',{keyPath:'id'});};
    r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
  });
  return database;
}
async function transaction(store,action) {
  const d=await db();return new Promise((resolve,reject)=>{
    const tx=d.transaction(store,'readwrite');let result;
    const r=action(tx.objectStore(store));r.onsuccess=()=>{result=r.result;};
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('Local recording write aborted'));
  });
}
let draining;
export async function drain(onCount=()=>{}) {
  if(draining)return draining;
  draining=(async()=>{
    // One immutable chunk per request; IDB is the retry queue, not an hour in RAM.
    while(true) {
      const batch=await transaction('chunks',s=>s.openCursor());
      if(!batch){onCount(0);break;}
      const row=batch.value; const header=new TextEncoder().encode(JSON.stringify(row.header));
      const body=new Uint8Array(4+header.length+row.pcm.byteLength);
      new DataView(body.buffer).setUint32(0,header.length,true);body.set(header,4);body.set(new Uint8Array(row.pcm),4+header.length);
      await api(`sessions/${row.sid}/chunks`,{method:'POST',body:body.buffer});
      await transaction('chunks',s=>s.delete(row.id));
      const count=await transaction('chunks',s=>s.count());onCount(count);
    }
  })().finally(()=>{draining=null;});
  return draining;
}
export async function recoverPending(onCount) {
  await drain(onCount);
  const ends=await transaction('ends',s=>s.getAll());
  for(const e of ends) {
    const m=await api('sessions/'+e.sid);
    if(m.connected)throw new Error('Recording connection still closing; retry in a moment');
    await api(`sessions/${e.sid}/seal`,{method:'POST',body:JSON.stringify({epoch:e.epoch,frames:e.frames})});
    await transaction('ends',s=>s.delete(e.id));
  }
}

export class Recording {
  constructor(sid,onState,onEvent) {this.sid=sid;this.onState=onState;this.onEvent=onEvent;this.writes=Promise.resolve();this.running=false;this.ready=false;this.connecting=false;this.endReason='';}
  state(change){this.onState(change);}
  async start(resume=false) {
    try {
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:false,autoGainControl:false}});
      this.ctx=new AudioContext({sampleRate:24000});await this.ctx.resume();
      if(this.ctx.sampleRate!==24000)throw new Error('This browser cannot capture at 24 kHz. Use Chrome on this Mac.');
      await this.ctx.audioWorklet.addModule('/recorder.js');
      this.epoch=crypto.randomUUID().replaceAll('-','');
      await api(`sessions/${this.sid}/epochs`,{method:'POST',body:JSON.stringify({id:this.epoch,wall_ms:Date.now()})});
      this.node=new AudioWorkletNode(this.ctx,'recorder',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
      this.node.port.onmessage=({data:d})=>this.message(d);
      this.running=true;
      this.source=this.ctx.createMediaStreamSource(this.stream);this.source.connect(this.node);this.node.connect(this.ctx.destination);
      this.ctx.onstatechange=()=>{if(this.running&&this.ctx.state!=='running'){this.endReason='Recording stopped because the audio engine suspended. Resume after waking; uncaptured microphone audio cannot be restored.';this.state({warning:this.endReason});this.stop().catch(e=>this.state({error:e.message}));}};
      this.stream.getAudioTracks()[0].onended=()=>{if(this.running){this.endReason='Recording stopped because the microphone disconnected. Captured audio is preserved; reconnect the device before resuming.';this.state({warning:this.endReason});this.stop().catch(e=>this.state({error:e.message}));}};
      this.timer=setInterval(()=>drain(n=>this.state({backlog:n})).catch(()=>this.state({warning:'Local server unavailable — chunks queued in this browser. Keep this tab open.'})),1000);
      this.state({phase:'live',connection:'Connecting',started:Date.now(),warning:'',error:''});
      await this.connect(resume);
    } catch(e) {
      if(!this.running)this.release();
      throw e;
    }
  }
  async message(d) {
    if(d.type==='mic') {
      this.state({mic:d.micPeak,ai:d.aiPeak});
      if(this.ready&&this.ws?.readyState===WebSocket.OPEN&&this.ws.bufferedAmount<48000)this.ws.send(d.pcm);
      else if(this.ready)this.state({warning:'Voice uplink congested: some live audio may not reach the AI. Originals still record locally.'});
    }
    if(d.type==='chunk') {
      const row={id:`${this.sid}:${this.epoch}:${String(d.start/24000).padStart(6,'0')}`,sid:this.sid,
        header:{epoch:this.epoch,seq:d.start/24000,start:d.start,spans:d.spans,underruns:d.underruns},pcm:d.pcm};
      this.writes=this.writes.then(()=>transaction('chunks',s=>s.put(row)));
      this.writes.catch(e=>{this.state({error:'Browser disk write failed. Stop recording; an unsaved tail may be lost. '+e.message});this.release();this.state({phase:'saved',connection:'Closed'});});
      this.writes.then(()=>transaction('chunks',s=>s.count())).then(n=>this.state({backlog:n})).catch(()=>{});
    }
    if(d.type==='interrupted'&&d.item&&this.ws?.readyState===WebSocket.OPEN)
      this.ws.send(JSON.stringify({type:'truncate',item:d.item,played_ms:Math.floor(d.played/24)}));
    if(d.type==='stopped')this.resolveStop?.(d.frames);
  }
  async connect(resume=true) {
    if(this.connecting||!this.running)return;
    this.connecting=true;
    try {
      await api('bootstrap');
      await drain(n=>this.state({backlog:n}));
      this.ws?.close();this.ready=false;this.node.port.postMessage({type:'clear'});
      // Wait for the old relay to release its single-connection lock.
      for(let i=0;i<30;i++){const m=await api('sessions/'+this.sid);if(!m.connected)break;await new Promise(r=>setTimeout(r,100));}
      if(!this.running)return;
      const socket=new WebSocket(`ws://${location.host}/api/sessions/${this.sid}/live`);
      this.ws=socket;
      socket.onmessage=({data})=>{
        if(this.ws!==socket||!this.running)return;
        const e=JSON.parse(data);
        if(e.type==='ready') {
          this.ready=true;this.state({connection:'Connected',warning:resume?'Reconnected with bounded transcript context; prior API state is not restored.':''});
          this.ws.send(JSON.stringify({type:resume?'continue':'begin'}));
        } else if(e.type==='response.output_audio.delta') {
          const binary=atob(e.delta);const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
          const pcm=new Int16Array(bytes.buffer);this.node.port.postMessage({type:'audio',item:e.item_id,pcm},[pcm.buffer]);
        } else if(e.type==='response.output_audio.done')this.node.port.postMessage({type:'done',item:e.item_id});
        else if(e.type==='input_audio_buffer.speech_started')this.node.port.postMessage({type:'clear'});
        else if(['connection_error','renew','error'].includes(e.type)) {
          if(e.error?.code==='response_cancel_not_active')return;
          this.state({warning:e.text||e.error?.message||'Voice API error; originals remain saved.'});
        }
        this.onEvent(e);
      };
      socket.onclose=()=>{if(this.ws!==socket||!this.running)return;this.ready=false;this.node?.port.postMessage({type:'clear'});this.state({connection:'Disconnected',warning:'AI disconnected. Local recording continues. Reconnect to resume with transcript context.'});};
      socket.onerror=()=>{if(this.ws===socket&&this.running)this.state({connection:'Disconnected'});};
    } finally {this.connecting=false;}
  }
  interrupt(){if(this.ws?.readyState===WebSocket.OPEN)this.ws.send(JSON.stringify({type:'interrupt'}));this.node?.port.postMessage({type:'clear'});}
  release() {
    this.running=false;this.ready=false;clearInterval(this.timer);this.ws?.close();
    this.stream?.getTracks().forEach(t=>t.stop());this.source?.disconnect();this.node?.disconnect();this.ctx?.close().catch(()=>{});
  }
  async stop() {
    if(this.stopping)return this.stopping;
    if(!this.running)return;
    this.stopping=this.finishStop();
    return this.stopping;
  }
  async finishStop() {
    this.state({phase:'saving',connection:'Closing'});this.ready=false;
    this.interrupt();
    // Stop before closing AudioContext so the final partial chunk is emitted.
    const frames=await new Promise(resolve=>{let timer;this.resolveStop=n=>{clearTimeout(timer);resolve(n);};timer=setTimeout(()=>resolve(null),2000);this.node.port.postMessage({type:'stop'});});
    this.release();
    await this.writes;
    if(frames!==null)await transaction('ends',s=>s.put({id:this.sid+':'+this.epoch,sid:this.sid,epoch:this.epoch,frames}));
    try {
      await drain(n=>this.state({backlog:n}));
      for(let i=0;i<30;i++){const m=await api('sessions/'+this.sid);if(!m.connected)break;await new Promise(r=>setTimeout(r,100));}
      await recoverPending(n=>this.state({backlog:n}));
      if(frames===null)await api(`sessions/${this.sid}/recover`,{method:'POST'});
      this.state({phase:'saved',connection:'Closed',warning:frames===null?'Audio engine stopped unexpectedly. Only committed audio was recovered; the unsaved tail cannot be restored.':this.endReason});
    } catch(e) {this.state({phase:'saved',connection:'Closed',error:'Audio pending save in this browser. Retry local upload before export. '+e.message});}
  }
}
