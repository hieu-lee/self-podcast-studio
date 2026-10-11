import React from 'react';
import {SourceChoices} from './video.jsx';
export function EpisodeSteps({phase}){
 const labels=['Prepare','Interview','Polish audio','Produce video','Ready'];const index={prepare:0,interview:1,polishing:2,producing_video:3,ready:4}[phase]??0;
 return <ol className="episode-steps" aria-label="Episode workflow">{labels.map((label,i)=><li key={label} aria-current={i===index?'step':undefined} className={i<index?'complete':i===index?'current':''}><span>{i<index?'✓':i+1}</span>{label}</li>)}</ol>;
}
export function FinishStage({session,busy,selection,setSelection,finish,cancel}){
 const w=session.workflow,v=session.video;const active=w&&['polishing','producing_video','stopping'].includes(w.state);const ready=w?.state==='ready'&&v?.state==='completed'&&v.job_id===w.job_id&&v.audio_version===session.export_dir;
 const title=ready?'Ready to download':w?.state==='polishing'?'Polishing audio':w?.state==='producing_video'?'Producing video':w?.state==='review_required'?'Preserved audio needs review':w?.state==='stopping'?'Stopping safely':w?.state==='failed'?'Finishing needs attention':w?.state==='cancelled'?'Finishing stopped':w?.state==='interrupted'?'Resume finishing':'Interview saved';
 const audio=name=>`/api/sessions/${session.id}/files/${name}?version=${session.export_dir}`;
 const video=name=>`/api/sessions/${session.id}/video/${v.job_id}/files/${name}?version=${session.export_dir}`;
 return <section className="workflow" aria-label="Finish this episode"><h2>{title}</h2><h3 className="topic">{session.topic}</h3><p className="hint">{w?.message||'Continue with conservative audio polish, then a video using the entire polished soundtrack and transcript. Nothing is publicly shared.'}</p>
 {w?.review_notes?.length>0&&<div className="notice"><b>Preserved uncertainties — inspect before continuing</b><ul>{w.review_notes.map((n,i)=><li key={i}>{n}</li>)}</ul></div>}
 {w?.state==='producing_video'&&v&&<><p role="status">{v.message}</p><progress aria-label="Episode video production" value={v.progress} max="100"/></>}
 {w?.audio_ready&&!ready&&<><audio controls key={session.export_dir} src={audio('episode.mp3')}/><a href={audio('transcript.txt')}>Read the whole transcript</a></>}
 {ready?<><video controls preload="metadata" key={w.version+w.job_id} src={video('episode.mp4')}/><a className="primary wide download-video" href={video('episode.mp4')} download>Download video</a><div className="downloads"><a href={audio('episode.mp3')}>Download polished audio</a><a href={audio('transcript.txt')}>Read the whole transcript</a><a href={video('captions.srt')}>Download captions</a><a href={video('project.zip')}>Download editable project</a><a href={video('provenance.json')}>Video provenance</a><a href={audio('edit.json')}>Audio edit record</a></div><p className="hint">Preview before sharing. Captions/timing and model decisions can be wrong. This is a local download, not public publication or quality approval.</p></>:<>
 {!active&&<SourceChoices selection={selection} onChange={setSelection} disabled={busy}/>}
 {active?<button disabled={busy||w.state==='stopping'} onClick={cancel}>{w.state==='polishing'?'Stop after audio':'Cancel finishing'}</button>:<button className="primary" disabled={busy||!session.frames||session.epochs.some(e=>e.expected===null)} onClick={()=>finish(!!w,w?.state==='review_required')}>{w?.state==='review_required'?'Continue with preserved uncertainties':w?'Retry finishing':'Finish & make video'}</button>}
 </>}
 </section>;
}
