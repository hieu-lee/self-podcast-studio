import React,{useState,useEffect} from 'react';
import {api} from './recording.js';
export function VideoStage({session,busy,action,refresh,selection,onSelectionChange,hideSources=false}){
 const v=session.video,version=session.export_dir;
 const running=v&&['queued','running','cancelling'].includes(v.state);
 const ready=v?.state==='completed';
 const invoke=route=>action(async()=>{await api(`sessions/${session.id}/video${route}`,{method:'POST',body:JSON.stringify({version,...(route?{job_id:v.job_id}:{sources:{public_urls:selection.public_urls.map(x=>x.trim()).filter(Boolean),project_ids:selection.project_ids}})})});await refresh();});
 const file=name=>`/api/sessions/${session.id}/video/${v.job_id}/files/${name}?version=${version}`;
 return <section className="video-stage"><span className="tiny">03 · ILLUSTRATE THE FINISHED EPISODE</span><h3>Let the visual producer build it</h3><p className="hint">AI listens to this final audio, then Codex chooses relevant visual sources and creates an interactive app. Source capture is separate; the app renderer stays offline. Your complete episode stays the soundtrack; nothing is published.</p>
 {!hideSources&&<SourceChoices selection={selection} onChange={onSelectionChange} disabled={busy||running}/>}
 <button disabled={busy||session.exporting||running||!session.polished_audio} onClick={()=>invoke('')}>{running?'Video production in progress…':v?'Make a new video attempt':'Make video from this audio'}</button>
 {!session.polished_audio&&<p className="hint">Export again with speaker balance and noise cleanup enabled before making video.</p>}
 {v&&<><p className="video-status" role="status">{v.state} · {v.progress}% · {v.message}</p><progress aria-label="Video production" value={v.progress} max="100"/>{running&&<button disabled={busy||v.state==='cancelling'} onClick={()=>invoke('/cancel')}>Cancel video job</button>}</>}
 {ready&&<><video key={version+v.job_id} controls preload="metadata" src={file('episode.mp4')}/><div className="downloads"><a href={file('episode.mp4')}>Download video ↗</a><a href={file('captions.srt')}>Video captions ↗</a><a href={file('storyboard.json')}>Storyboard ↗</a><a href={file('provenance.json')}>Visual sources ↗</a><a href={file('project.zip')}>Editable project & replay evidence ↗</a></div><p className="hint">Review captured sources, illustrations, rankings/revisions and sync. Generated art is illustrative; estimated captions can contain recognition errors.</p><button disabled={busy||session.exporting||v.approved} onClick={()=>invoke('/approve')}>{v.approved?'This exact video/audio version reviewed':'I have watched and checked this video'}</button></>}
 </section>;
}

export function SourceChoices({selection,onChange,disabled=false}){
 const [projects,setProjects]=useState([]),[catalogError,setCatalogError]=useState('');
 useEffect(()=>{let live=true;api('video-sources').then(r=>{if(live)setProjects(r.projects)}).catch(e=>{if(live)setCatalogError(e.message)});return()=>{live=false}},[]);
 return <details className="source-choices"><summary>Optional visual sources</summary> <label className="field-label">Optional public visual sources<textarea aria-label="Public visual sources" disabled={disabled} value={selection.public_urls.join('\n')} onChange={e=>onChange({...selection,public_urls:e.target.value.split('\n')})} placeholder="https://example.com/ — one relevant public HTTPS URL per line"/></label>
 <p className="hint">Guided finishing also carries this episode's dated research citations into video planning; source-backed summaries are fallible, not proof of every spoken claim. Extra public destinations can be supplied here. No login, private hosts or browser profile. Selecting an application runtime authorizes trusted Codex to inspect that project, prepare job-owned dependencies and start its frontend/backend workflow. Startup has full machine execution, not an OS sandbox: select only trusted project code and instructions. Original source stays unchanged; task-owned services stop after capture. Approved existing services are reused read-only only when the host catalog permits it. Static projects still use their read-only public folder.</p>
 {projects.map(p=><label className="check" key={p.id}><input type="checkbox" disabled={disabled} checked={selection.project_ids.includes(p.id)} onChange={e=>onChange({...selection,project_ids:e.target.checked?[...selection.project_ids,p.id]:selection.project_ids.filter(id=>id!==p.id)})}/>{p.kind==='application'?'Application runtime · ':''}{p.label}</label>)}
 {catalogError&&<p role="alert">{catalogError}</p>}
</details>;
}
