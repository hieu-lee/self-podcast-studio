"""Durable local finishing orchestration around the existing export/video jobs."""
import asyncio
import json
import uuid
from . import store,video,sources,research
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

pending={}
running={}
ACTIVE={'polishing','producing_video','stopping'}

def write(sid,state):
    store.set_meta(sid,'workflow',json.dumps(state,ensure_ascii=False))
    return state

def current(sid):
    m=store.meta(sid);state=running.get(sid) or json.loads(m.get('workflow','null'))
    if not state:return None
    if state['state'] in ACTIVE and sid not in pending:
        state.update(state='interrupted',message='Studio restarted. Saved media is safe; retry finishing explicitly.')
        write(sid,state)
    if state['state'] not in ACTIVE and (state['capture_frames']!=m['frames'] or state.get('audio_ready') and state.get('version')!=m.get('export_dir')):
        state.update(state='interrupted',message='Recording/audio version changed. Finish the current recording again.')
        write(sid,state)
    if state['state']=='ready':
        v=video.current(sid)
        if not v or v['state']!='completed' or v['job_id']!=state['job_id']:
            state.update(state='interrupted',message='Video attempt changed. Review the current attempt or retry finishing.')
            write(sid,state)
    return state

def review_notes(sid,version):
    root=store.ROOT/sid/version;edit=json.loads((root/'edit.json').read_text());polish=json.loads((root/'polish.json').read_text())
    notes=list(edit.get('warnings',[]))
    notes.extend(str(d['flag']) for d in edit.get('audio_decisions',[]) if d.get('flag'))
    for d in polish.get('noise_events',[]):
        benign=d.get('kind') in ('speech','breath','laughter') and d.get('flag')=='Natural, overlapping or uncertain event retained'
        if d.get('flag') and not benign:notes.append(str(d['flag']))
        elif d.get('kind')=='uncertain':notes.append('An uncertain noise event was preserved, not removed.')
    return list(dict.fromkeys(notes))[:20]

def episode_sources(selection,evidence):
    # Explicit projects/URLs keep priority; research never grants project execution.
    sources.selected_sources(selection)
    selected={'public_urls':list(selection['public_urls']),'project_ids':list(selection['project_ids'])}
    for packet in evidence:
        for source in packet['sources']:
            if len(selected['public_urls'])+len(selected['project_ids'])>=4:return selected
            raw=source['url']
            if not research.safe_url(raw):continue
            u=urlsplit(raw)
            # Tracking/anchor text is not a capability; retain all functional queries.
            url=urlunsplit((u.scheme,u.netloc,u.path,urlencode([(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if not k.lower().startswith('utm_')]),''))
            try:sources.public_url(url)
            except ValueError:continue
            if url not in selected['public_urls']:selected['public_urls'].append(url)
    return selected

def start(sid,data,exporter):
    m=store.meta(sid);old=current(sid)
    if data.version!=m.get('export_dir'):raise ValueError('Audio version changed; reload the current recording.')
    if sid in pending:return old
    if old and not data.retry and old['capture_frames']==m['frames']:return old
    if not data.polish_audio:raise ValueError('Guided video finishing requires audio polish.')
    if m['frames']==0:raise ValueError('Record an interview before finishing.')
    v=video.current(sid)
    if v and v['state'] in ('queued','running','cancelling'):raise ValueError('A video attempt is already active.')
    evidence=json.loads(research.context(sid));selection=episode_sources(data.sources.model_dump(),evidence)
    reuse=bool(old and data.retry and old.get('audio_ready') and old.get('version')==m.get('export_dir'))
    if old and old['state']=='review_required' and reuse and not data.reviewed_audio:return old
    state={'id':uuid.uuid4().hex,'state':'producing_video' if reuse else 'polishing','message':'Preparing full episode video…' if reuse else 'Polishing and transcribing actual saved audio…',
        'capture_frames':m['frames'],'version':m.get('export_dir'),'audio_ready':reuse,'sources':selection,'review_notes':review_notes(sid,m['export_dir']) if reuse else [],'stop_requested':False,'job_id':None}
    write(sid,state);running[sid]=state
    async def run():
        try:
            if not reuse:
                task=exporter(sid,data);await task
                fresh=store.meta(sid);version=fresh.get('export_dir')
                if not version or version==state['version'] or fresh.get('export_status','').startswith('Export failed'):
                    raise ValueError('Audio export failed; originals and previous exports remain safe.')
                state.update(version=version,audio_ready=True,review_notes=review_notes(sid,version));write(sid,state)
            if state['stop_requested']:
                state.update(state='cancelled',message='Stopped after audio. Saved polished audio is retained; no video was started.');return
            if state['review_notes'] and not data.reviewed_audio:
                state.update(state='review_required',message='Audio uncertainties were preserved. Inspect the audio and flags before continuing to video.');return
            state.update(state='producing_video',message='Analyzing full polished audio/transcript and producing synchronized video…');write(sid,state)
            job=video.start(sid,state['version'],state['sources'],evidence=evidence);state['job_id']=job;write(sid,state)
            await video.TASKS[job]
            v=video.current(sid)
            if state['stop_requested'] or v and v['state']=='cancelled':state.update(state='cancelled',message='Video cancelled; original and polished audio remain safe.')
            elif v and v['job_id']==job and v['audio_version']==state['version'] and v['state']=='completed':state.update(state='ready',message='Ready to preview and download. Nothing is publicly shared; review before sharing.')
            else:state.update(state='failed',message=v['message'] if v else 'Video/audio version changed. Retry explicitly; saved audio is safe.')
        except Exception as e:
            state.update(state='failed',message=str(e) if isinstance(e,ValueError) else f'Finishing failed ({type(e).__name__}). Originals are safe; retry explicitly.')
        finally:
            write(sid,state);pending.pop(sid,None);running.pop(sid,None)
    pending[sid]=asyncio.create_task(run())
    return state

def cancel(sid):
    state=current(sid)
    if not state or sid not in pending:return state
    # Export is a live thread: finish it safely rather than falsely cancelling its writes.
    state['stop_requested']=True;state['state']='stopping';state['message']='Stopping after the current audio operation; no new video will start.'
    if state.get('job_id'):
        video.cancel(sid,state['version'],state['job_id']);state['message']='Stopping owned video processes; keeping saved audio…'
    return write(sid,state)

async def shutdown():
    for sid in list(pending):cancel(sid)
    await asyncio.gather(*list(pending.values()),return_exceptions=True)
