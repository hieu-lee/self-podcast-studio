import React,{useState,useEffect,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {api,Recording,recoverPending} from './recording.js';
import './style.css';
const TOPIC='Can AI discover new mathematics, or only recombine what humans already know?';
const outline=['What would count as genuinely new mathematics?','Where is the line between a surprising pattern and a proof?','If an AI finds a theorem nobody understands, what have we learned?'];
const clock=n=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;
function App(){
 const [topic,setTopic]=useState(TOPIC),[consent,setConsent]=useState(false),[boot,setBoot]=useState(null),[sessions,setSessions]=useState([]),[selected,setSelected]=useState(null),[status,setStatus]=useState({phase:'idle',connection:'Not started',backlog:0,mic:0,ai:0}),[turns,setTurns]=useState([]),[elapsed,setElapsed]=useState(0),[quality,setQuality]=useState(true),[gaps,setGaps]=useState(false),[busy,setBusy]=useState(false);
 const recorder=useRef(null),refreshGeneration=useRef(0);const merge=s=>setStatus(x=>({...x,...s}));
 async function refresh(){const generation=++refreshGeneration.current,sid=selected?.id;const items=await api('sessions');if(generation!==refreshGeneration.current)return;setSessions(items);if(sid){const fresh=await api('sessions/'+sid);if(generation===refreshGeneration.current)setSelected(current=>current?.id===sid?fresh:current);}}
 useEffect(()=>{(async()=>{try{setBoot(await api('bootstrap'));await recoverPending(n=>merge({backlog:n}));setSessions(await api('sessions'));}catch(e){merge({error:e.message});}})();},[]);
 useEffect(()=>{const t=setInterval(()=>{if(status.started&&['live','saving'].includes(status.phase))setElapsed((Date.now()-status.started)/1000);},500);return()=>clearInterval(t);},[status.started,status.phase]);
 useEffect(()=>{const t=setInterval(()=>refresh().catch(()=>{}),3000);return()=>{clearInterval(t);refreshGeneration.current++;};},[selected?.id]);
 useEffect(()=>{const guard=e=>{if(recorder.current?.running||status.backlog){e.preventDefault();e.returnValue='Recording or pending upload';}};window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);},[status.backlog]);
 async function action(fn){refreshGeneration.current++;setBusy(true);merge({error:''});try{await fn();}catch(e){merge({error:e.message});}finally{setBusy(false);}}
 async function start(resume=false){await action(async()=>{
   if(!consent)throw new Error('Please confirm audio consent first.');
   await recoverPending(n=>merge({backlog:n}));
   let s=resume?selected:await api('sessions',{method:'POST',body:JSON.stringify({topic})});
   if(resume&&s.epochs.some(e=>e.expected===null))throw new Error('Recover the interrupted capture first.');
   setSelected(s);setTurns([]);setElapsed(0);
   recorder.current=new Recording(s.id,merge,e=>{
     if(e.type==='response.output_audio_transcript.done')setTurns(t=>[...t.slice(-11),{speaker:'AI interviewer · provisional',text:e.transcript}]);
     if(e.type==='conversation.item.input_audio_transcription.completed')setTurns(t=>[...t.slice(-11),{speaker:'Hieu · provisional',text:e.transcript}]);
   });
   await recorder.current.start(resume);
 });}
 const live=['live','saving'].includes(status.phase);
 const unsealed=selected?.epochs?.some(e=>e.expected===null);
 const files=name=>`/api/sessions/${selected.id}/files/${name}${name.startsWith('original')?'':'?version='+selected.export_dir}`;
 return <div className="shell">
  <header><a className="brand" href="/" onClick={e=>live&&e.preventDefault()}><span className="mark">s/</span> self podcast</a><div className="local"><i/> LOCAL STUDIO <span>·</span> HIEU</div></header>
  <main>
   <div className="eyebrow">A GOOD QUESTION IS A PLACE TO BEGIN</div>
   <div className="heading"><h1>Your ideas,<br/><em>out loud.</em></h1><p>A thoughtful conversation.<br/>Your real voice. An AI interviewer.<br/>An episode worth listening to.</p></div>
   {status.error&&<div className="notice error" role="alert">{status.error}</div>}
   {status.warning&&<div className="notice" role="status">{status.warning}</div>}
   <div className="grid">
    <section className="studio">
     {!live ? <>
      <div className="section-top"><span className="number">01</span><h2>Choose the conversation</h2><span className="tag">30—60 MIN</span></div>
      <label className="field-label" htmlFor="topic">WHAT'S ON YOUR MIND?</label>
      <textarea id="topic" value={topic} onChange={e=>setTopic(e.target.value)} maxLength={1000} rows={3}/>
      <div className="prepared"><span className="tiny">A FEW DOORS WE COULD OPEN</span><ul>{(topic===TOPIC?outline:['What makes this topic matter to you?','Can you walk me through a concrete example?','What would change your mind?']).map(q=><li key={q}>{q}</li>)}</ul><p>Prompts, not a script. Follow-ups come from your answers.</p></div>
      <label className="consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I agree to microphone recording and sending necessary audio/text to OpenAI. Recordings stay on this Mac; the interviewer voice is AI-generated.</span></label>
      <button className="primary" disabled={busy||!consent||!boot?.key_ready||topic.trim().length<3} onClick={()=>start()}>Start the conversation <span>↗</span></button>
      <div className="hint">Use headphones · Chrome recommended · Recording starts only when you choose</div>
      {boot&&!boot.key_ready&&<div className="notice error">Set OPENAI_API_KEY in the backend environment and restart. No key belongs in this page.</div>}
     </> : <>
      <div className="section-top"><span className="record-dot"/><h2>{status.phase==='saving'?'Saving your conversation':'On the record'}</h2><span className="tag">{clock(elapsed)}</span></div>
      <h3 className="live-topic">{selected?.topic}</h3>
      <div className="meters">{[['Your microphone',status.mic],['AI speaker output',status.ai]].map(([label,level])=><div key={label}><span>{label}</span><div className="meter"><div style={{width:`${Math.min(100,level*180)}%`}}/></div></div>)}</div>
      <div className="health"><span><i className={status.connection==='Connected'?'good':'amber'}/>{status.connection}</span><span>{status.backlog?`${status.backlog}s queued locally`:'1s chunks · upload caught up'}</span></div>
      <p className="live-help">Take your time. The interviewer will follow your lead.<br/>Keep this tab open and the Mac awake. Missing audio cannot be recreated.</p>
      <div className="live-controls"><button disabled={status.phase==='saving'||busy} onClick={()=>recorder.current.interrupt()}>Interrupt AI</button><button disabled={status.phase==='saving'||busy} onClick={()=>action(()=>recorder.current.connect(true))}>Reconnect AI</button><button className="stop" disabled={status.phase==='saving'||busy} onClick={()=>action(async()=>{await recorder.current.stop();await refresh();})}>■ Stop & save</button></div>
      <div className="transcripts"><span className="tiny">LIVE NOTES · MAY INCLUDE UNPLAYED AI WORDS · FINAL TRANSCRIPT USES AUDIO</span>{turns.length?turns.map((t,i)=><p key={i}><b>{t.speaker}</b>{t.text}</p>):<p className="muted">Listening for the first exchange…</p>}</div>
     </>}
    </section>
    <aside><div className="section-top"><span className="number">02</span><h2>Your recordings</h2></div><p className="aside-copy">From a live exchange to a finished episode. Originals are never discarded.</p>
     <div className="session-list">{sessions.length?sessions.map(s=><button className={selected?.id===s.id?'session selected':'session'} key={s.id} data-session-id={s.id} disabled={live||busy} onClick={()=>action(async()=>{setSelected(await api('sessions/'+s.id));setTurns([]);merge({phase:'saved',warning:''});})}><span>{s.topic}</span><small>{clock(s.frames/24000)} captured · {live&&selected?.id===s.id?'recording':s.epochs.some(e=>e.expected===null)?'needs recovery':'saved'}</small></button>):<div className="empty"><span>◎</span><p>Your first conversation<br/>belongs here.</p></div>}</div>
     {selected&&!live&&<div className="export-panel"><span className="tiny">SELECTED RECORDING</span><h3>{selected.topic}</h3><p>{clock(selected.frames/24000)} of saved source audio</p>
      <button disabled={busy} onClick={()=>action(async()=>{await api('bootstrap');await recoverPending(n=>merge({backlog:n}));await refresh();})}>Retry pending local upload</button>
      {unsealed?<button disabled={busy} onClick={()=>action(async()=>{await recoverPending(n=>merge({backlog:n}));await api(`sessions/${selected.id}/recover`,{method:'POST'});merge({warning:'Recovered committed audio only. Unsaved tail is not restored.'});await refresh();})}>Recover committed audio</button>:<button disabled={busy||!consent||selected.exporting} onClick={()=>start(true)}>Resume with microphone consent</button>}
      <label className="check"><input type="checkbox" checked={gaps} onChange={e=>setGaps(e.target.checked)}/>I acknowledge any capture gaps / lost tail</label>
      <label className="check"><input type="checkbox" checked={quality} onChange={e=>setQuality(e.target.checked)}/>Audio-aware AI review & repairs (never my voice)</label>
      <button className="primary" disabled={busy||unsealed||selected.exporting||!selected.frames} onClick={()=>action(async()=>{await recoverPending(n=>merge({backlog:n}));await api(`sessions/${selected.id}/export`,{method:'POST',body:JSON.stringify({acknowledge_gaps:gaps,quality_edit:quality})});await refresh();})}>{selected.exporting?'Rendering & transcribing…':'Make the episode'} <span>↗</span></button>
      {selected.export_status&&<p role="status" className="export-status">{selected.export_status}</p>}
      {selected.export_dir&&<><audio key={selected.export_dir} controls src={files('episode.mp3')}/><div className="downloads"><a href={files('episode.mp3')}>Download audio ↗</a><a href={files('transcript.txt')}>Final transcript ↗</a><a href={files('edit.json')}>Edit record ↗</a>{selected.export_audio_review==='yes'&&<><a href={files('audio-diagnosis.json')}>AI audio diagnosis ↗</a><a href={files('audio-edit-plan.json')}>Validated audio plan ↗</a></>}<a href={files('original-guest.wav')}>Original guest ↗</a><a href={files('original-ai.wav')}>Original AI ↗</a></div><p className="hint">Listen for missing words, joins, overlap and levels. Transcript timing is estimated, not word-perfect.</p><button disabled={busy||selected.exporting} onClick={()=>action(async()=>{await api(`sessions/${selected.id}/approve`,{method:'POST',body:JSON.stringify({version:selected.export_dir})});await refresh();})}>I've listened and checked the episode</button></>}
     </div>}
     <div className="privacy"><span>⌁</span><div><b>A private, local studio</b><p>Audio and transcripts are saved on this Mac. Hosted AI processes necessary audio/text. No automatic publishing.</p></div></div>
    </aside>
   </div>
  </main><footer><span>LESS PRODUCTION. MORE CONVERSATION.</span><span>SELF PODCAST / PROTOTYPE 01</span></footer>
 </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
