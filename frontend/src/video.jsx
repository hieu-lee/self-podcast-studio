import React from 'react';
import {api} from './recording.js';
export function VideoStage({session,busy,action,refresh}){
 const v=session.video,version=session.export_dir;
 const running=v&&['queued','running','cancelling'].includes(v.state);
 const ready=v?.state==='completed';
 const invoke=route=>action(async()=>{await api(`sessions/${session.id}/video${route}`,{method:'POST',body:JSON.stringify({version,...(route?{job_id:v.job_id}:{})})});await refresh();});
 const file=name=>`/api/sessions/${session.id}/video/${v.job_id}/files/${name}?version=${version}`;
 return <section className="video-stage"><span className="tiny">03 · ILLUSTRATE THE FINISHED EPISODE</span><h3>Let the visual producer build it</h3><p className="hint">AI listens to this final audio, then Codex creates and operates a topic-specific interactive app. Only its isolated viewport is recorded. Your complete episode stays the soundtrack; nothing is published.</p>
 <button disabled={busy||session.exporting||running||!session.polished_audio} onClick={()=>invoke('')}>{running?'Video production in progress…':v?'Make a new video attempt':'Make video from this audio'}</button>
 {!session.polished_audio&&<p className="hint">Export again with speaker balance and noise cleanup enabled before making video.</p>}
 {v&&<><p className="video-status" role="status">{v.state} · {v.progress}% · {v.message}</p><progress aria-label="Video production" value={v.progress} max="100"/>{running&&<button disabled={busy||v.state==='cancelling'} onClick={()=>invoke('/cancel')}>Cancel video job</button>}</>}
 {ready&&<><video key={version+v.job_id} controls preload="metadata" src={file('episode.mp4')}/><div className="downloads"><a href={file('episode.mp4')}>Download video ↗</a><a href={file('captions.srt')}>Video captions ↗</a><a href={file('storyboard.json')}>Storyboard ↗</a><a href={file('provenance.json')}>Visual sources ↗</a><a href={file('project.zip')}>Editable project & replay evidence ↗</a></div><p className="hint">Review illustrations, actual rankings/revisions and sync. Generated art is illustrative; estimated captions can contain recognition errors.</p><button disabled={busy||session.exporting||v.approved} onClick={()=>invoke('/approve')}>{v.approved?'This exact video/audio version reviewed':'I have watched and checked this video'}</button></>}
 </section>;
}
