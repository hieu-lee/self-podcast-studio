"""Repeatable audit of actual research browser E2E PCM; not a model self-grade."""
import base64
import hashlib
import json
import os
import sqlite3
import wave
from pathlib import Path
import httpx
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/research'
report=json.loads((OUT/'real-browser-e2e.json').read_text());audits=[]
for run in report['checks']:
    language=run['language'];sid=run['sid']
    events=json.loads((OUT/f'real-{language}-browser-events.json').read_text());generated={}
    for e in events:
        if e['type']=='response.output_audio.delta':generated.setdefault(e['item_id'],bytearray()).extend(base64.b64decode(e['delta']))
    ai=[];guest=[];played={};item_pcm={}
    with sqlite3.connect(f'file:{OUT}/real-data/{sid}/recording.sqlite?mode=ro',uri=True) as c:
        for header,raw in c.execute('SELECT header,pcm FROM chunks ORDER BY epoch,seq'):
            h=json.loads(header);pcm=np.frombuffer(raw,dtype='<i2').reshape(-1,2);covered=np.zeros(len(pcm),bool)
            for span in h['spans']:
                start=span['start']-h['start'];n=span['frames'];offset=span['offset']
                assert offset==played.get(span['item'],0),'Playback item offsets must remain exact and contiguous'
                expected=np.frombuffer(generated[span['item']],dtype='<i2')[offset:offset+n]
                assert np.array_equal(pcm[start:start+n,1],expected),'Played PCM diverged from received item audio'
                item_pcm.setdefault(span['item'],bytearray()).extend(pcm[start:start+n,1].tobytes())
                covered[start:start+n]=True;played[span['item']]=played.get(span['item'],0)+n
            assert not np.any(pcm[~covered,1]),'Unplayed generated audio in saved AI channel'
            ai.append(pcm[:,1].tobytes());guest.append(pcm[:,0].tobytes())
        assert c.execute("SELECT COUNT(*) FROM events WHERE json_extract(body,'$.type')='playback_interrupt'").fetchone()[0]
    last_result=max(i for i,e in enumerate(events) if e['type']=='research.result' and e['result']['status']=='ready')
    final_items=[item['id'] for e in events[last_result+1:] if e['type']=='response.done' and e['response']['status']=='completed' for item in e['response'].get('output',[]) if item.get('type')=='message']
    assert any(played.get(item,0)==len(generated.get(item,b''))//2>0 for item in final_items),'At least one complete sourced follow-up must be fully digitally played/saved'
    assert sum(played.values())>24000*5
    assert any(played.get(item,0)<len(raw)//2 for item,raw in generated.items()),'Deliberate interrupt must leave an unplayed tail'
    audio=b''.join(ai);wav=OUT/f'real-{language}-actually-played-ai.wav'
    with wave.open(str(wav),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(audio)
    item=next(item for item in final_items if played.get(item,0)==len(generated.get(item,b''))//2>0)
    sourced=OUT/f'real-{language}-actually-played-sourced-response.wav'
    with wave.open(str(sourced),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(item_pcm[item])
    assert bytes(item_pcm[item])==bytes(generated[item])
    with sourced.open('rb') as f:r=httpx.post('https://api.openai.com/v1/audio/transcriptions',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},data={'model':'gpt-4o-transcribe'},files={'file':(sourced.name,f,'audio/wav')},timeout=90)
    r.raise_for_status();text=r.json()['text'];assert len(text)>20
    if language=='vi':assert sum(ch in 'ăâđêôơưáàảãạếềểễệốồổỗộ' for ch in text)>3,text
    audits.append({'language':language,'sid':sid,'captured_seconds':len(audio)/48000,'played_frames':sum(played.values()),'guest_pcm_sha256':hashlib.sha256(b''.join(guest)).hexdigest(),'ai_pcm_sha256':hashlib.sha256(audio).hexdigest(),'sourced_item':item,'sourced_item_pcm_sha256':hashlib.sha256(item_pcm[item]).hexdigest(),'independent_unhinted_sourced_transcript':text,'checks':['at least one completed post-search sourced follow-up fully digitally played/saved','all saved playback spans byte-match actual received audio','no unplayed generated audio in AI channel','deliberate interrupted tail excluded and timing persisted','independent transcription of bounded actually played post-tool AI item without language hint']})
(OUT/'capture-audit.json').write_text(json.dumps({'audits':audits,'scope':'Actual browser capture only; no export changes or subjective human listening approval.'},ensure_ascii=False,indent=2));print(json.dumps(audits,ensure_ascii=False,indent=2))
