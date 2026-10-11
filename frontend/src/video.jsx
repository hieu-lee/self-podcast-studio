import React,{useState,useEffect} from 'react';
import {api} from './recording.js';
export function VideoStage({session,busy,action,refresh}){
 const [urls,setUrls]=useState(''),[projects,setProjects]=useState([]),[chosen,setChosen]=useState([]),[catalogError,setCatalogError]=useState('');
 useEffect(()=>{let live=true;api('video-sources').then(r=>{if(live)setProjects(r.projects)}).catch(e=>{if(live)setCatalogError(e.message)});return()=>{live=false}},[]);
 useEffect(()=>{setUrls('');setChosen([])},[session.id]);
 const v=session.video,version=session.export_dir;
 const running=v&&['queued','running','cancelling'].includes(v.state);
 const ready=v?.state==='completed';
 const invoke=route=>action(async()=>{await api(`sessions/${session.id}/video${route}`,{method:'POST',body:JSON.stringify({version,...(route?{job_id:v.job_id}:{sources:{public_urls:urls.split('\n').map(x=>x.trim()).filter(Boolean),project_ids:chosen}})})});await refresh();});
 const file=name=>`/api/sessions/${session.id}/video/${v.job_id}/files/${name}?version=${version}`;
 return <section className="video-stage"><span className="tiny">03 · ILLUSTRATE THE FINISHED EPISODE</span><h3>Let the visual producer build it</h3><p className="hint">AI listens to this final audio, then Codex chooses relevant visual sources and creates an interactive app. Source capture is separate; the app renderer stays offline. Your complete episode stays the soundtrack; nothing is published.</p>
 <label className="field-label">Optional public visual sources<textarea aria-label="Public visual sources" disabled={busy||running} value={urls} onChange={e=>setUrls(e.target.value)} placeholder="https://example.com/ — one relevant public HTTPS URL per line"/></label>
 <p className="hint">Only explicitly supplied public destinations can be chosen. No login, private hosts or browser profile. Local projects require the trusted host catalog; only their selected public subtree is served read-only, with no shell or installs.</p>
 {projects.map(p=><label className="check" key={p.id}><input type="checkbox" disabled={busy||running} checked={chosen.includes(p.id)} onChange={e=>setChosen(e.target.checked?[...chosen,p.id]:chosen.filter(id=>id!==p.id))}/>{p.label}</label>)}
 {catalogError&&<p role="alert">{catalogError}</p>}
 <button disabled={busy||session.exporting||running||!session.polished_audio} onClick={()=>invoke('')}>{running?'Video production in progress…':v?'Make a new video attempt':'Make video from this audio'}</button>
 {!session.polished_audio&&<p className="hint">Export again with speaker balance and noise cleanup enabled before making video.</p>}
 {v&&<><p className="video-status" role="status">{v.state} · {v.progress}% · {v.message}</p><progress aria-label="Video production" value={v.progress} max="100"/>{running&&<button disabled={busy||v.state==='cancelling'} onClick={()=>invoke('/cancel')}>Cancel video job</button>}</>}
 {ready&&<><video key={version+v.job_id} controls preload="metadata" src={file('episode.mp4')}/><div className="downloads"><a href={file('episode.mp4')}>Download video ↗</a><a href={file('captions.srt')}>Video captions ↗</a><a href={file('storyboard.json')}>Storyboard ↗</a><a href={file('provenance.json')}>Visual sources ↗</a><a href={file('project.zip')}>Editable project & replay evidence ↗</a></div><p className="hint">Review captured sources, illustrations, rankings/revisions and sync. Generated art is illustrative; estimated captions can contain recognition errors.</p><button disabled={busy||session.exporting||v.approved} onClick={()=>invoke('/approve')}>{v.approved?'This exact video/audio version reviewed':'I have watched and checked this video'}</button></>}
 </section>;
}
