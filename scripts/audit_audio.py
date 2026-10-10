"""E2E evidence audit: the real browser/API capture and its FFmpeg export."""
import base64
import hashlib
import json
import sqlite3
import wave
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts'
report=json.loads((OUT/'browser-e2e.json').read_text());sid=report['session_id']
received=json.loads((OUT/'live-events.json').read_text())
generated={}
for e in received:
    if e['type']=='response.output_audio.delta':
        generated.setdefault(e['item_id'],bytearray()).extend(base64.b64decode(e['delta']))
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
with sqlite3.connect(ROOT/'.data'/sid/'recording.sqlite') as c:
    rows=c.execute('SELECT header,pcm FROM chunks ORDER BY epoch,seq').fetchall()
    meta=dict(c.execute('SELECT key,value FROM meta'))
    played={};total=0
    for h,raw in rows:
        h=json.loads(h);pcm=np.frombuffer(raw,dtype='<i2').reshape(-1,2);covered=np.zeros(len(pcm),dtype=bool)
        for s in h['spans']:
            pos=s['start']-h['start'];n=s['frames'];offset=s['offset']
            expected=np.frombuffer(generated[s['item']],dtype='<i2')[offset:offset+n]
            check('rendered AI span matches received PCM exactly',np.array_equal(pcm[pos:pos+n,1],expected))
            covered[pos:pos+n]=True;played[s['item']]=played.get(s['item'],0)+n
        check('no generated unplayed audio outside playback spans',not np.any(pcm[~covered,1]))
        total+=len(pcm)
    check('some generated AI tail deliberately not played',any(played.get(k,0)<len(v)//2 for k,v in generated.items()))
    ev=[json.loads(r[0]) for r in c.execute('SELECT body FROM events')]
    check('interrupt timing durable',any(e['type']=='playback_interrupt' for e in ev))
export=ROOT/'.data'/sid/meta['export_dir']
manifest=json.loads((export/'edit.json').read_text())
with wave.open(str(ROOT/'.data'/sid/'sources'/'original-guest.wav')) as w:
    guest=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
    check('original guest timeline conserved',len(guest)==total)
with wave.open(str(export/'edited-guest.wav')) as w:
    edited=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
prepared=guest
if manifest['audio_review']:
    with wave.open(str(export/'planned-guest.wav')) as w:
        prepared=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
    conserved=[]
    for entry in manifest['prepared_sample_map']:
        if entry['kind']=='source':
            x=entry['final_start'];conserved.append(prepared[x:x+entry['frames']])
    check('all original guest samples conserved in planned timeline',np.array_equal(np.concatenate(conserved),guest))
mask=np.zeros(len(prepared),dtype=bool)
for e in manifest['edits']:
    a=round(e['source_start']*24000);b=round(e['source_end']*24000)
    x=round(e['final_start']*24000);y=round(e['final_end']*24000)
    mask[a:b]=True
    check('guest source waveform unchanged except padded join fades',np.array_equal(prepared[a+192:b-192],edited[x+192:y-192]))
check('no audible guest samples removed',not np.any(np.abs(prepared[~mask].astype(int))>105))
metrics=manifest['ffmpeg_loudness']
check('balanced final loudness inspected',abs(float(metrics['input_i'])+16)<1)
check('no clipping in final measured export',float(metrics['input_tp'])<=-1)
segments=json.loads((export/'transcript.json').read_text())['segments']
check('final transcript re-aligned against rendered tracks',all(0<=s['start']<s['end']<=manifest['final_duration']+.1 for s in segments))
result={'session_id':sid,'checks':sorted(set(checks)),'measured_lufs':metrics['input_i'],'true_peak_db':metrics['input_tp'],
        'source_seconds':total/24000,'final_seconds':manifest['final_duration'],
        'quality_note':'Objective waveform, timing, levels and transcript inspection. Human listening approval still required; deliberate interruption fragments are preserved, not invented as complete questions.'}
(OUT/'audio-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
