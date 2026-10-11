import React,{useState,useEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {api,Recording,recoverPending} from './recording.js';
import './style.css';
import {ResearchPanel} from './research.jsx';
import {VideoStage,SourceChoices} from './video.jsx';
import {EpisodeSteps,FinishStage} from './workflow.jsx';
const TOPIC='Can AI discover new mathematics, or only recombine what humans already know?';
const outline=['What would count as genuinely new mathematics?','Where is the line between a surprising pattern and a proof?','If an AI finds a theorem nobody understands, what have we learned?'];
const languageLabel=code=>code==='vi'?'Tiếng Việt':'English';
const vietnameseOutline=['Điều gì được xem là toán học thực sự mới?','Ranh giới giữa một mẫu hình bất ngờ và một chứng minh là gì?','Nếu AI tìm ra định lý mà không ai hiểu, chúng ta đã học được gì?'];
const clock=n=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;
function App(){
 const [topic,setTopic]=useState(TOPIC),[language,setLanguage]=useState('en'),[consent,setConsent]=useState(false),[boot,setBoot]=useState(null),[sessions,setSessions]=useState([]),[selected,setSelected]=useState(null),[status,setStatus]=useState({phase:'idle',connection:'Not started',backlog:0,mic:0,ai:0}),[turns,setTurns]=useState([]),[elapsed,setElapsed]=useState(0),[quality,setQuality]=useState(true),[polish,setPolish]=useState(true),[gaps,setGaps]=useState(false),[busy,setBusy]=useState(false);
 const [researchEnabled,setResearchEnabled]=useState(true),[researchQuery,setResearchQuery]=useState(TOPIC.slice(0,280)),[prep,setPrep]=useState(null),[liveQuery,setLiveQuery]=useState(''),[researchStatus,setResearchStatus]=useState('');
 const [visualSources,setVisualSources]=useState({public_urls:[],project_ids:[]});
 const actionBusy=useRef(false),startRequest=useRef(null);
 const prepAbort=useRef(null),prepGeneration=useRef(0);
 const recorder=useRef(null),refreshGeneration=useRef(0);const merge=s=>{setStatus(x=>({...x,...s}));if(s.connection&&s.connection!=='Connected')setResearchStatus('');};
 async function refresh(){const generation=++refreshGeneration.current,sid=selected?.id;const items=await api('sessions');if(generation!==refreshGeneration.current)return;setSessions(items);if(sid){const fresh=await api('sessions/'+sid);if(generation===refreshGeneration.current)setSelected(current=>current?.id===sid?fresh:current);}}
 useEffect(()=>{(async()=>{try{setBoot(await api('bootstrap'));await recoverPending(n=>merge({backlog:n}));const items=await api('sessions');setSessions(items);const savedId=localStorage.getItem('self-podcast-selected');if(items.some(s=>s.id===savedId))await selectSession(items.find(s=>s.id===savedId));}catch(e){merge({error:e.message});}})();},[]);
 useEffect(()=>{const t=setInterval(()=>{if(status.started&&['live','saving'].includes(status.phase))setElapsed((Date.now()-status.started)/1000);},500);return()=>clearInterval(t);},[status.started,status.phase]);
 useEffect(()=>{const t=setInterval(()=>refresh().catch(()=>{}),3000);return()=>{clearInterval(t);refreshGeneration.current++;};},[selected?.id]);
 useEffect(()=>{const guard=e=>{if(recorder.current?.running||status.backlog){e.preventDefault();e.returnValue='Recording or pending upload';}};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[status.backlog]);
 async function action(fn){if(actionBusy.current)return;actionBusy.current=true;refreshGeneration.current++;setBusy(true);merge({error:''});try{await fn();}catch(e){merge({error:e.message});}finally{actionBusy.current=false;setBusy(false);}}

 function savedSources(s){
   try{const draft=JSON.parse(localStorage.getItem('self-podcast-sources-'+s.id));if(draft&&Array.isArray(draft.public_urls)&&Array.isArray(draft.project_ids)&&[...draft.public_urls,...draft.project_ids].every(x=>typeof x==='string'))return draft;}catch{}
   return s.workflow?.sources||{public_urls:[],project_ids:[]};
 }
 function chooseSources(next){setVisualSources(next);if(selected?.id){try{localStorage.setItem('self-podcast-sources-'+selected.id,JSON.stringify(next));}catch{merge({warning:'Source choices could not be saved in this browser. Keep this tab open or reselect them after refresh.'});}}}
 async function selectSession(s){
   const fresh=await api('sessions/'+s.id);setGaps(false);setSelected(fresh);setTopic(fresh.topic);setLanguage(fresh.language||'en');setResearchQuery(fresh.preparation?.query||fresh.topic.slice(0,280));setResearchEnabled(fresh.research_enabled!=='no');setTurns([]);setVisualSources(savedSources(fresh));merge({phase:'saved',warning:''});setPrep(null);
 }
 useEffect(()=>{if(selected?.id)localStorage.setItem('self-podcast-selected',selected.id);},[selected?.id]);
 useEffect(()=>{const p=selected?.preparation;if(!live&&p&&((p.capture_frames===selected.frames&&p.capture_epochs===selected.epochs.length)||(p.capture_frames===undefined&&selected.frames===0&&!selected.epochs.length)))setPrep({sid:selected.id,resume:!!selected.epochs.length,status:p.status==='checking'?'checking':p.status==='ready'?'ready':'failed',query:p.query,topic:selected.topic});},[selected?.preparation?.id,selected?.preparation?.status]);
 async function finishEpisode(retry=false,reviewed=false){await action(async()=>{
   if(recorder.current?.running)await recorder.current.stop();
   await recoverPending(n=>merge({backlog:n}));const fresh=await api('sessions/'+selected.id);setSelected(fresh);
   await api(`sessions/${fresh.id}/finish`,{method:'POST',body:JSON.stringify({version:fresh.export_dir||null,acknowledge_gaps:gaps,quality_edit:quality,polish_audio:true,sources:{public_urls:visualSources.public_urls.map(x=>x.trim()).filter(Boolean),project_ids:visualSources.project_ids},retry,reviewed_audio:reviewed})});await refresh();
 });}
 function newEpisode(){setGaps(false);setQuality(true);setPolish(true);prepGeneration.current++;setPrep(null);setSelected(null);setVisualSources({public_urls:[],project_ids:[]});startRequest.current=null;localStorage.removeItem('self-podcast-selected');localStorage.removeItem('self-podcast-start');merge({phase:'idle',error:'',warning:''});}

 async function record(s,resume){
   setGaps(false);setSelected(s);setTurns([]);setElapsed(0);setPrep(null);setResearchStatus('');
   recorder.current=new Recording(s.id,merge,e=>{
     if(e.type==='response.output_audio_transcript.done')setTurns(t=>[...t.slice(-11),{speaker:'AI interviewer · provisional',text:e.transcript}]);
     if(e.type==='conversation.item.input_audio_transcription.completed')setTurns(t=>[...t.slice(-11),{speaker:'Hieu · provisional',text:e.transcript}]);
     if(e.type==='research.status')setResearchStatus(e.status==='checking'?'Checking web sources while recording continues…':e.status==='cancelled'?'Research cancelled; no new fact verified.':e.text||e.status);
     if(e.type==='research.result'){setResearchStatus(e.result.status==='ready'?'New evidence saved; interviewer will continue after your turn.':'Research unavailable; facts remain unverified.');setSelected(current=>current?.id===s.id?{...current,research:[...(current.research||[]),e.result].slice(-3)}:current);}
   });
   await recorder.current.start(resume);
 }
 async function prepare(s,resume){
   const generation=++prepGeneration.current;
   prepAbort.current=new AbortController();
   setPrep({sid:s.id,resume,status:'checking',query:researchQuery,topic:s.topic});
   try{
     const result=await api(`sessions/${s.id}/research`,{method:'POST',body:JSON.stringify({query:researchQuery}),signal:AbortSignal.any([prepAbort.current.signal,AbortSignal.timeout(60000)])});
     if(generation!==prepGeneration.current)return;
     setSelected(current=>current?.id===s.id?{...current,research:[...(current.research||[]),result].slice(-3)}:current);
     setPrep({sid:s.id,resume,status:result.status==='ready'?'ready':'failed',query:researchQuery,topic:s.topic});
   }catch(e){if(generation===prepGeneration.current){setPrep({sid:s.id,resume,status:'failed',query:researchQuery,topic:s.topic});merge({error:e.message});}}
 }
 async function cancelPrep(){
   const sid=prep?.sid;prepGeneration.current++;prepAbort.current?.abort();
   if(sid)await api(`sessions/${sid}/research/cancel`,{method:'POST'});
   setPrep(current=>current?{...current,status:'failed'}:current);
 }
 async function start(resume=false){await action(async()=>{
   if(!consent)throw new Error('Please confirm audio and research consent first.');
   await recoverPending(n=>merge({backlog:n}));
   const key=JSON.stringify({topic,language});
   if(!startRequest.current){try{startRequest.current=JSON.parse(localStorage.getItem('self-podcast-start'));}catch{}}
   if(!startRequest.current||startRequest.current.key!==key)startRequest.current={key,id:crypto.randomUUID().replaceAll('-','')};
   localStorage.setItem('self-podcast-start',JSON.stringify(startRequest.current));
   const s=resume?selected:await api('sessions',{method:'POST',body:JSON.stringify({topic,language,request_id:startRequest.current.id})});
   if(resume&&s.epochs.some(e=>e.expected===null))throw new Error('Recover the interrupted capture first.');
   s.research_enabled=researchEnabled?'yes':'no';setSelected(s);
   await api(`sessions/${s.id}/research/settings`,{method:'POST',body:JSON.stringify({enabled:researchEnabled})});
   if(researchEnabled)await prepare(s,resume);else await record(s,resume);
 });}
 async function startPrepared(){await action(async()=>{
   if(!consent)throw new Error('Confirm microphone and research consent first.');
   if(selected?.id!==prep?.sid)throw new Error('Select the prepared episode first.');
   // A failed prep never silently turns off live research; unavailable facts stay uncertain.
   await record(selected,prep.resume);
 });}
 const live=['live','saving'].includes(status.phase);
 const finishing=selected?.workflow&&['polishing','producing_video','stopping'].includes(selected.workflow.state);
 const unsealed=selected?.epochs?.some(e=>e.expected===null);
 const files=name=>`/api/sessions/${selected.id}/files/${name}${name.startsWith('original')?'':'?version='+selected.export_dir}`;
 const prompts=language==='vi'?(topic===TOPIC?vietnameseOutline:['Điều gì khiến chủ đề này quan trọng với bạn?','Bạn có thể kể một ví dụ cụ thể không?','Điều gì sẽ khiến bạn thay đổi quan điểm?']):(topic===TOPIC?outline:['What makes this topic matter to you?','Can you walk me through a concrete example?','What would change your mind?']);
 return <div className="shell">
  <header><a className="brand" href="/" onClick={e=>live&&e.preventDefault()}>Self Podcast</a><button disabled={live||busy||prep?.status==='checking'} onClick={newEpisode}>New episode</button></header>
  <main>
   <section className="stage">
    <EpisodeSteps phase={live?'interview':prep?'prepare':selected?.workflow?.state==='ready'?'ready':selected?.workflow?.job_id?'producing_video':selected?.frames?'polishing':'prepare'}/>
    {status.error&&<div className="notice error" role="alert">{status.error}</div>}
    {status.warning&&<div className="notice" role="status">{status.warning}</div>}
    {!live&&!prep&&selected?.frames>0?<><FinishStage session={selected} busy={busy} selection={visualSources} setSelection={chooseSources} finish={finishEpisode} cancel={()=>action(async()=>{await api(`sessions/${selected.id}/finish/cancel`,{method:'POST',body:'{}'});await refresh();})}/><label className="consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>Allow microphone/audio processing to resume this recording. Research queries may reach OpenAI web-search providers.</span></label></>:!live ? <>
     <label className="sr-only" htmlFor="topic">Topic</label>
     <textarea id="topic" className="topic" value={topic} disabled={busy||!!prep} onChange={e=>{setTopic(e.target.value);setResearchQuery(e.target.value.slice(0,280));}} maxLength={1000} rows={3} placeholder="What do you want to talk about?"/>
     <ul className="prompts">{prompts.map(q=><li key={q}>{q}</li>)}</ul>
      <label className="check"><input type="checkbox" checked={researchEnabled} disabled={busy||!!prep} onChange={e=>setResearchEnabled(e.target.checked)}/>Prepare with web research & allow live public lookups</label>
      {researchEnabled&&<><label className="field-label" htmlFor="research-query">PUBLIC RESEARCH QUERY</label><input id="research-query" aria-label="Public research query" value={researchQuery} maxLength={280} disabled={prep?.status==='checking'} onChange={e=>setResearchQuery(e.target.value)}/><p className="hint">Only this short query is sent for prep. Live lookups send short public questions, not your full transcript. Remove personal details. Sources and retrieval times stay with this episode.</p></>}
     <label className="consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>Record my microphone and send necessary audio and text to OpenAI. With research enabled, short public queries may reach web-search providers. Recordings stay on this Mac. The interviewer voice is AI.</span></label>
     <div className="start-row">
      {!prep&&<button className="primary" disabled={busy||!consent||!boot?.key_ready||topic.trim().length<3||(researchEnabled&&researchQuery.trim().length<3)} onClick={()=>start()}><span className="dot"/>Start the conversation</button>}
      <select id="language" aria-label="Podcast language" value={language} disabled={busy||!!prep} onChange={e=>setLanguage(e.target.value)}><option value="en">English</option><option value="vi">Tiếng Việt</option></select>
      <span className="hint">Use headphones</span>
     </div>
      {prep&&<div className="research-prep" role="status"><b>{prep.status==='checking'?'Checking web sources — microphone is off':prep.status==='ready'?'Sourced briefing ready — microphone is still off':'Research unavailable — microphone is still off'}</b><p>{prep.topic}</p>{prep.query!==researchQuery&&<p className="hint">Query changed; retry before using the briefing.</p>}{prep.status==='checking'?<button onClick={()=>cancelPrep().catch(e=>merge({error:e.message}))}>Cancel research</button>:<><button disabled={busy||!consent||(prep.status==='ready'&&prep.query!==researchQuery)} className="primary" onClick={startPrepared}>{prep.status==='ready'?'Start with researched briefing':'Continue without verified research'}</button><button disabled={busy||researchQuery.trim().length<3} onClick={()=>action(()=>prepare(selected,prep.resume))}>Retry research</button><button disabled={busy} onClick={()=>{prepGeneration.current++;setPrep(null);}}>Back to topic</button></>}</div>}
     {boot&&!boot.key_ready&&<div className="notice error">Set OPENAI_API_KEY in the backend environment and restart.</div>}
    </> : <>
     <div className="live-top"><span className="dot pulse"/><h2>{status.phase==='saving'?'Saving your conversation':'On the record'}</h2><span className="timer">{clock(elapsed)}</span></div>
     <h3 className="topic">{selected?.topic}</h3>
     <div className="meters">{[['You',status.mic],['Interviewer',status.ai]].map(([label,level])=><div key={label}><span>{label}</span><div className="meter"><div style={{width:`${Math.min(100,level*180)}%`}}/></div></div>)}</div>
     <div className="health"><span><i className={status.connection==='Connected'?'good':'amber'}/>{status.connection}</span><span>{status.backlog?`${status.backlog}s queued locally`:'Upload caught up'}</span><span>{languageLabel(selected?.language)}</span></div>
     <div className="live-controls"><button disabled={status.phase==='saving'||busy} onClick={()=>recorder.current.interrupt()}>Interrupt AI</button><button disabled={status.phase==='saving'||busy} onClick={()=>action(()=>recorder.current.connect(true))}>Reconnect AI</button><button className="stop" disabled={status.phase==='saving'||busy} onClick={()=>action(async()=>{await recorder.current.stop();await refresh();})}>Stop & save</button><button className="primary" disabled={status.phase==='saving'||busy} onClick={()=>finishEpisode()}>Finish & make video</button></div>
     <p className="hint">Keep this tab open and your Mac awake. Finish starts audio polish and a full-episode video; nothing is publicly shared.</p><SourceChoices selection={visualSources} onChange={chooseSources} disabled={busy||status.phase==='saving'}/>
      {selected?.research_enabled==='yes'&&<div className="live-research"><label className="field-label" htmlFor="live-research-query">LIVE PUBLIC RESEARCH QUERY</label><input id="live-research-query" aria-label="Live public research query" value={liveQuery} maxLength={280} onChange={e=>setLiveQuery(e.target.value)}/><button disabled={busy||status.phase==='saving'||status.connection!=='Connected'||liveQuery.trim().length<3} onClick={()=>{recorder.current.ws.send(JSON.stringify({type:'research_request',query:liveQuery}));setLiveQuery('');}}>Ask interviewer to check</button><p className="hint">Or ask aloud for a current fact. Your capture continues during a lookup.</p></div>}
      {researchStatus&&<p className="notice" role="status">{researchStatus}</p>}
     <div className="transcripts"><h4>Live notes <span>Provisional. May include unplayed AI words.</span></h4>{turns.length?turns.map((t,i)=><p key={i}><b>{t.speaker}</b>{t.text}</p>):<p className="muted">Listening…</p>}</div>
    </>}
    {selected?.preparation&&<a className="prep-download" href={`/api/sessions/${selected.id}/files/preparation.json`}>Download preparation info</a>}<ResearchPanel entries={selected?.research||[]} topic={selected?.topic}/>
   </section>
   <aside>
    <h2>Recordings</h2>
    <div className="session-list">{sessions.length?sessions.map(s=><button className={selected?.id===s.id?'session selected':'session'} key={s.id} data-session-id={s.id} disabled={live||busy||!!prep} onClick={()=>action(()=>selectSession(s))}><span>{s.topic}</span><small><span>{clock(s.frames/24000)}</span><span>{languageLabel(s.language)}</span><span>{live&&selected?.id===s.id?'Recording':s.epochs.some(e=>e.expected===null)?'Needs recovery':'Saved'}</span></small></button>):<p className="muted">No recordings yet.</p>}</div>
    {selected&&!live&&!prep&&<details className="export-panel" open={!selected.workflow}><summary>Audio, recovery & advanced controls</summary>
     <h3>{selected.topic}</h3><p className="meta"><span>{clock(selected.frames/24000)}</span><span>{languageLabel(selected.language)}</span></p>
     <div className="row">{unsealed?<button disabled={busy} onClick={()=>action(async()=>{await recoverPending(n=>merge({backlog:n}));await api(`sessions/${selected.id}/recover`,{method:'POST'});merge({warning:'Recovered committed audio only. Unsaved tail is not restored.'});await refresh();})}>Recover committed audio</button>:<button disabled={busy||finishing||!!prep||!consent||selected.exporting} onClick={()=>start(true)}>Resume recording</button>}
      <button disabled={busy} onClick={()=>action(async()=>{await api('bootstrap');await recoverPending(n=>merge({backlog:n}));await refresh();})}>Retry upload</button></div>
     {!unsealed&&!consent&&!selected.exporting&&<p className="hint">Check the recording consent to resume.</p>}
     <label className="check"><input type="checkbox" checked={quality} onChange={e=>setQuality(e.target.checked)}/>AI audio repair (never my voice)</label>
     <label className="check"><input type="checkbox" checked={polish} onChange={e=>setPolish(e.target.checked)}/>Speaker balance & cautious noise/cough cleanup</label>
     <label className="check"><input type="checkbox" checked={gaps} onChange={e=>setGaps(e.target.checked)}/>Accept capture gaps or lost audio</label>
     <button className="primary wide" disabled={busy||finishing||unsealed||selected.exporting||!selected.frames} onClick={()=>action(async()=>{await recoverPending(n=>merge({backlog:n}));await api(`sessions/${selected.id}/export`,{method:'POST',body:JSON.stringify({acknowledge_gaps:gaps,quality_edit:quality,polish_audio:polish})});await refresh();})}>{selected.exporting?'Rendering & transcribing…':'Make the episode'}</button>
     {selected.export_status&&<p role="status" className="export-status">{selected.export_status}</p>}
     {selected.export_dir&&<><audio key={selected.export_dir} controls src={files('episode.mp3')}/><div className="downloads"><a href={files('episode.mp3')}>Download audio</a><a href={files('transcript.txt')}>Final transcript</a><a href={files('edit.json')}>Edit record</a>{selected.polished_audio&&<a href={files('polish.json')}>Noise & volume audit</a>}{selected.export_audio_review==='yes'&&<><a href={files('audio-diagnosis.json')}>AI audio diagnosis</a><a href={files('audio-edit-plan.json')}>Validated audio plan</a></>}<a href={files('original-guest.wav')}>Original guest</a><a href={files('original-ai.wav')}>Original AI</a></div><p className="hint">Listen before approving. Transcript timing is estimated.</p><button className="wide" disabled={busy||selected.exporting} onClick={()=>action(async()=>{await api(`sessions/${selected.id}/approve`,{method:'POST',body:JSON.stringify({version:selected.export_dir})});await refresh();})}>I've listened and checked the episode</button><VideoStage session={selected} busy={busy||finishing} action={action} refresh={refresh} selection={visualSources} onSelectionChange={chooseSources} hideSources={selected.workflow?.state!=='ready'}/></>}
    </details>}
   </aside>
  </main>
 </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
