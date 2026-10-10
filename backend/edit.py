"""Conservative FFmpeg editing; transcripts come from saved audio, never guessed turns."""
import hashlib
import json
import os
import re
import subprocess
import uuid
import wave

import httpx
import numpy as np

from . import store

RATE=24000


def ffmpeg(*args):
    p=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-y',*map(str,args)],capture_output=True,text=True,timeout=900)
    if p.returncode:
        raise RuntimeError('FFmpeg failed')
    return p.stderr


def normalize(source,target,level,pre=''):
    base=(pre+',') if pre else ''
    log=ffmpeg('-i',source,'-af',base+f'loudnorm=I={level}:TP=-1.5:LRA=11:print_format=json','-f','null','-')
    m=json.loads(log[log.rfind('{'):log.rfind('}')+1])
    if all(np.isfinite(float(m[k])) for k in ('input_i','input_tp','input_lra','input_thresh','target_offset')):
        filt=base+f"loudnorm=I={level}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
    else:
        filt=pre or 'anull'
    codec=['-c:a','libmp3lame','-b:a','160k'] if str(target).endswith('.mp3') else ['-c:a','pcm_s16le']
    ffmpeg('-i',source,'-af',filt,'-ar',RATE,*codec,target)


def wav_writer(path):
    w=wave.open(str(path),'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
    return w


def duration(path):
    with wave.open(str(path)) as w:
        return w.getnframes()/w.getframerate()


def activity(path):
    end=duration(path)
    log=ffmpeg('-i',path,'-af','silencedetect=noise=-50dB:d=0.35','-f','null','-')
    tokens=re.findall(r'silence_(start|end): ([\d.]+)',log)
    intervals=[]; cursor=0
    for kind,t in tokens:
        t=min(end,float(t))
        if kind=='start':
            if t>cursor: intervals.append([cursor,t])
        else: cursor=t
    if not tokens or tokens[-1][0]!='start':
        if end>cursor: intervals.append([cursor,end])
    return intervals


def union(intervals,end):
    ranges=[]
    for a,b in sorted(intervals):
        a=max(0,a-.25); b=min(end,b+.25)
        if ranges and a-ranges[-1][1]<1.2:
            ranges[-1][1]=max(ranges[-1][1],b)
        else: ranges.append([a,b])
    return ranges


def intersects(ranges,a,b):
    return any(x<b and y>a for x,y in ranges)


def transcribe(client,path,language="en"):
    data={'model':'whisper-1','response_format':'verbose_json','timestamp_granularities[]':'segment','language':language}
    if language=='vi':
        # Better native captions; this model has no segment timestamps. Never
        # attach another model's word/segment alignment to its different text.
        data={'model':'gpt-transcribe','languages[]':['vi','en'],
              'prompt':'Vietnamese interview; retain original words, tones, names and mixed English terms. Never translate.'}
    with open(path,'rb') as f:
        r=client.post('https://api.openai.com/v1/audio/transcriptions',
             data=data,
             files={'file':(path.name,f,'audio/wav')})
    r.raise_for_status()
    if language=='vi':
        text=r.json()['text'].strip()
        return {'segments':[{'start':0,'end':duration(path),'text':text}] if text else []}
    return r.json()


def sources(sid):
    root=store.ROOT/sid/'sources'
    root.mkdir(exist_ok=True)
    guest=root/'original-guest.wav'; ai=root/'original-ai.wav'
    # Rebuild only after new capture epochs; prior recording DB always retains originals.
    temp_g=root/'guest.tmp.wav'; temp_a=root/'ai.tmp.wav'
    timeline=[]; cursor=0; underruns=[]
    with wav_writer(temp_g) as g,wav_writer(temp_a) as a,store.db(sid) as c:
        for e in store.meta(sid)['epochs']:
            start=cursor
            for r in c.execute('SELECT pcm,header FROM chunks WHERE epoch=? ORDER BY seq',(e['id'],)):
                pcm=np.frombuffer(r['pcm'],dtype='<i2').reshape(-1,2)
                g.writeframesraw(pcm[:,0].tobytes()); a.writeframesraw(pcm[:,1].tobytes())
                h=json.loads(r['header'])
                underruns.extend((start+u)/RATE for u in h['underruns'])
                cursor+=len(pcm)
            timeline.append({'epoch':e['id'],'wall_ms':e['wall_ms'],'original_start':start/RATE,'frames':cursor-start})
    os.replace(temp_g,guest); os.replace(temp_a,ai)
    return guest,ai,timeline,underruns


def cut(reader,a,b):
    reader.setpos(round(a*RATE))
    return reader.readframes(round(b*RATE)-round(a*RATE))


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def render(sid,warnings,quality_edit=True,polish_audio=True):
    language=store.meta(sid)['language']
    guest,ai,epochs,underruns=sources(sid)
    out=store.ROOT/sid/('export-'+uuid.uuid4().hex)
    out.mkdir(mode=0o700)
    original_guest=guest;original_ai=ai;original_total=duration(guest)
    timeline=[]; cursor=0;decisions=[];sample_map=[]
    client=httpx.Client(headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},timeout=180)
    try:
        if quality_edit:
            from .audio_plan import plan_audio,apply_plan
            decisions,items=plan_audio(sid,guest,ai,epochs,out,client)
            guest,ai,sample_map=apply_plan(guest,ai,decisions,items,out)
        polish_report=None
        if polish_audio:
            from .polish import clean_noise,level
            cleaned,noise,hashes=clean_noise(guest,ai,out,client,language)
            guest,ai=cleaned['guest'],cleaned['ai']
            polish_report={'version':1,'noise_events':noise,'source_audit':hashes,'speaker_levels':{},
                'policy':'Only DSP-anchored unwanted non-speech with audio classification, independent safe-attenuation confidence >=.95 and empty target ASR attenuated with 20ms fades; same-channel speech/normal breaths/laughter/uncertainty retained. No time deletion or guest synthesis. All originals immutable.'}
        total=duration(guest)
        g_active=activity(guest); a_active=activity(ai)
        ranges=union(g_active+a_active,total)
        if not ranges: raise ValueError('No audible speech recorded')
        with wave.open(str(guest)) as g,wave.open(str(ai)) as a,\
             wav_writer(out/'edited-guest.wav') as go,wav_writer(out/'edited-ai.wav') as ao:
            for start,end in ranges:
                entry={'source_start':start,'source_end':end,'final_start':cursor/RATE}
                # Bound working memory even if a noisy mic makes an hour one activity block.
                def pieces_iter():
                    first=round(start*RATE); last=round(end*RATE)
                    for pos in range(first,last,RATE*60):
                        stop=min(last,pos+RATE*60)
                        g.setpos(pos); a.setpos(pos)
                        yield g.readframes(stop-pos),a.readframes(stop-pos),pos==first,stop==last
                pieces=pieces_iter()
                for gp,ap,first,last in pieces:
                    # 8ms fades only at padded block joins, never at internal streaming boundaries.
                    for payload,w in ((gp,go),(ap,ao)):
                        x=np.frombuffer(payload,dtype='<i2').astype(np.float64)
                        n=min(192,len(x)//2)
                        if first: x[:n]*=np.linspace(0,1,n)
                        if last: x[-n:]*=np.linspace(1,0,n)
                        w.writeframesraw(x.astype('<i2').tobytes())
                    cursor+=len(gp)//2
                entry['final_end']=cursor/RATE
                timeline.append(entry)
        # Normalize each real speaker, then mix and apply a conservative final broadcast target.
        for name in ('guest','ai'):
            input_track=out/f'edited-{name}.wav'
            if polish_audio:
                input_track=out/f'dynamics-{name}.wav'
                polish_report['speaker_levels'][name]=level(out/f'edited-{name}.wav',input_track,out,name)
            normalize(input_track,out/f'final-{name}.wav',-19,pre='' if polish_audio else 'highpass=f=60')
        ffmpeg('-i',out/'final-guest.wav','-i',out/'final-ai.wav','-filter_complex',
               '[0:a][1:a]amix=inputs=2:duration=longest:normalize=0',
               '-ar',RATE,'-c:a','pcm_f32le',out/'mix.wav')
        normalize(out/'mix.wav',out/'episode.mp3',-16)
        transcript=[]
        # File limit is 25MB: 5min mono PCM = 14.4MB. Avoid transcribing all-silent speaker windows.
        for speaker,name in (('Hieu','guest'),('AI interviewer','ai')):
            final=out/f'final-{name}.wav'
            active_ranges=activity(final)
            with wave.open(str(final)) as w:
                length=w.getnframes()/RATE
                for begin,finish in union(active_ranges,length):
                    offset=begin
                    while offset<finish:
                        end=min(finish,offset+300)
                        clip=out/'transcription-part.wav'
                        with wav_writer(clip) as cw: cw.writeframes(cut(w,offset,end))
                        result=transcribe(client,clip,language)
                        for s in result.get('segments',[]):
                            left=max(offset,offset+float(s['start'])); right=min(end,offset+float(s['end']))
                            audible=[[max(left,x),min(right,y)] for x,y in active_ranges if x<right and y>left]
                            if audible and s.get('no_speech_prob',0)<.8:
                                transcript.append({'speaker':speaker,'start':round(audible[0][0],3),'end':round(audible[-1][1],3),'text':s['text'].strip()})
                        offset=end
        transcript.sort(key=lambda s:s['start'])
        if not transcript: raise ValueError('No reliable audio transcript')
        alignment='Acoustic crop-boundary estimates on edited speaker tracks; not word alignment; review against audio' if language=='vi' else 'Whisper segment estimates on edited speaker tracks; review against audio'
        (out/'transcript.json').write_text(json.dumps({'language':language,'alignment':alignment,'segments':transcript},indent=2))
        (out/'transcript.txt').write_text('\n'.join(f"[{s['start']:.2f}–{s['end']:.2f}] {s['speaker']}: {s['text']}" for s in transcript)+'\n')
        measure=ffmpeg('-i',out/'episode.mp3','-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-')
        metrics=json.loads(measure[measure.rfind('{'):measure.rfind('}')+1])
        manifest={'version':1,'language':language,'source_sha256':{'guest':sha(original_guest),'ai':sha(original_ai)},'original_duration':original_total,
            'final_duration':cursor/RATE,'epochs':epochs,'warnings':warnings,'edits':timeline,
            'polish_audio':polish_audio,'audio_review':quality_edit,'audio_decisions':decisions,'prepared_sample_map':sample_map,
            'edit_timebase':'planned speaker tracks when audio_review enabled; sample map links back to immutable originals',
            'policy':'Guest voice/meaning preserved; audio-capable saved-track diagnosis, constrained AI-only edits, rebuilt sample map, conservative shared silence trimming and smooth padded joins. Ambiguity preserved/flagged; no unheard questions restored.',
            'tools':{'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
                'transcription':'gpt-transcribe' if language=='vi' else 'whisper-1','audio_diagnosis':'gpt-audio-1.5' if quality_edit else None,
                'tts':'gpt-4o-mini-tts' if any(d['action'] in ('repair','move_repair') for d in decisions) else None},
            'ffmpeg_loudness':metrics,'episode_sha256':sha(out/'episode.mp3'),'listening_review':'Required; export success is not quality approval'}
        if polish_report:
            polish_report['final_timeline']=timeline
            polish_report['final_loudness']=metrics
            (out/'polish.json').write_text(json.dumps(polish_report,ensure_ascii=False,indent=2))
        (out/'edit.json').write_text(json.dumps(manifest,indent=2))
        for name in ('repair-source.wav','transcription-part.wav'):
            (out/name).unlink(missing_ok=True)
        store.set_meta(sid,'export_dir',out.name)
        store.set_meta(sid,'export_audio_review','yes' if quality_edit else 'no')
    except httpx.HTTPStatusError as error:
        body=error.response.json() if error.response.headers.get('content-type','').startswith('application/json') else {'message':'Non-JSON API failure'}
        (out/'api-error.json').write_text(json.dumps({'status':error.response.status_code,'error':body.get('error',body)},indent=2))
        raise
    finally:
        client.close()
