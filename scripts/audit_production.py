"""Repeatable PCM-mask and actual final-video evidence audit; no unit tests."""
import argparse,hashlib,json,math,subprocess,wave,zipfile
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--language',choices=['en','vi'],default='vi');a=p.parse_args()
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/production'/a.language
r=json.loads((OUT/'e2e.json').read_text());fixture=json.loads((OUT/'fixture.json').read_text())
import os
folder=Path(os.environ.get('SELF_PODCAST_DATA',ROOT/'.data'))/r['session_id']/r['export'];video=folder/r['job_id'];polish=r['polish'];RATE=24000
read=lambda path:np.frombuffer(wave.open(str(path)).readframes(10**9),dtype='<i2')
# For this known fixture, verify storage and guest preparation before any masks.
import sqlite3
with sqlite3.connect(folder.parent/'recording.sqlite') as db:
 digest=hashlib.sha256()
 for row in db.execute('SELECT pcm FROM chunks ORDER BY epoch,seq'):digest.update(row[0])
assert digest.hexdigest()==fixture['original_sha256'],'Immutable recorded fixture PCM changed'
with wave.open(str(OUT/'before.wav')) as w:raw=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').reshape(-1,2)
assert np.array_equal(read(folder/'planned-guest.wav'),raw[:,0]),'Fixture guest changed before noise masks'
measurements=[]
for speaker in ['guest','ai']:
 before=read(folder/f'planned-{speaker}.wav');after=read(folder/f'clean-{speaker}.wav');assert len(before)==len(after)
 masks=np.zeros(len(before),dtype=bool)
 for event in polish['noise_events']:
  if event['action']!='attenuate' or event['speaker']!=speaker:continue
  left,right=round(event['start']*RATE),round(event['end']*RATE);masks[left:right]=True
  # This fixture's audio plan does not move the guest. No accepted mask touches speech.
  assert any(n['speaker']==speaker and n['isolated'] and n['start']<=event['start']<event['end']<=n['end']+.05 for n in fixture['noise']),event
  assert not any(t['speaker']==speaker and t['start']<event['end'] and t['end']>event['start'] for t in fixture['turns']),event
  x=before[left+480:right-480].astype(float);y=after[left+480:right-480].astype(float)
  if len(x)>0:
   db=20*math.log10(max(1,np.linalg.norm(y))/max(1,np.linalg.norm(x)));assert db<-30,event
   measurements.append({'speaker':speaker,'range':[event['start'],event['end']],'core_attenuation_db':db})
 assert np.array_equal(before[~masks],after[~masks]),'Changed source samples outside accepted masks'
assert measurements
# Every declared illustration is actual output from the exact model and is archived.
provenance=json.loads((video/'provenance.json').read_text());assert provenance['assets']
with zipfile.ZipFile(video/'project.zip') as z:
 names=z.namelist();assert not any('auth' in n or n.endswith('.log') for n in names)
 for asset in provenance['assets']:
  assert asset['model']=='gpt-image-2.5-sunburst';assert asset['file'] in names
  assert hashlib.sha256((video/asset['file']).read_bytes()).hexdigest()==asset['sha256']
# Exact encoded frames near actions + ending (not just browser screenshots).
for label,t in [('first-rank',14),('revision',32),('ending',r['video_validation']['duration']-.3)]:
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(video/'episode.mp4'),'-frames:v','1',str(OUT/f'encoded-{label}.png')],check=True)
# Render measured per-second before/after levels as an editable, labelled SVG.
parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="550" viewBox="0 0 1000 550"><rect width="1000" height="550" fill="#fff"/><text x="40" y="30" font-size="22">Measured speaker levels — edited-track time, before/after adaptive dynamics</text>']
for i,speaker in enumerate(['guest','ai']):
 m=polish['speaker_levels'][speaker];top=80+i*220;parts.append(f'<text x="40" y="{top-12}" font-size="18">{speaker}: active-window spread {m["before_spread_db"]:.1f} → {m["after_spread_db"]:.1f} dB (1s RMS, not listening approval)</text>')
 for db in [-20,-40,-60]:
  y=top+(-db-10)*2;parts.append(f'<path d="M70 {y}H960" stroke="#ddd"/><text x="20" y="{y}" font-size="12">{db}dBFS</text>')
 for t in range(0,len(m['before_window_rms_db']),10):
  parts.append(f'<text x="{70+t*890/max(1,len(m["before_window_rms_db"])-1):.1f}" y="{top+180}" font-size="12">{t}s</text>')
 for key,color in [('before_window_rms_db','#b64e43'),('after_window_rms_db','#167d72')]:
  values=m[key];points=' '.join(f'{70+j*890/max(1,len(values)-1):.1f},{top+(-max(-85,v)-10)*2:.1f}' for j,v in enumerate(values));parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
parts.append('<text x="70" y="525" fill="#b64e43" font-size="16">Red: before</text><text x="240" y="525" fill="#167d72" font-size="16">Green: after</text><text x="470" y="525" font-size="16">Horizontal: episode seconds; silence windows included</text></svg>');(OUT/'levels.svg').write_text(''.join(parts))
report={'checks':['same duration and exact PCM outside masks on both prepared tracks','accepted masks isolated inside ground-truth noise, never meaningful same-channel speech','actual core attenuation measured below -30 dB','exact-model image source hashes and project archive checked','decoded video action/ending frames saved','before/after active-window level graph saved'],'attenuations':measurements,'scope':'Known synthetic fixture; speech outside masks is sample-identical BEFORE intentional shared trim/dynamics. Final soundtrack checked separately by full decode and waveform correlation. No claim of human listening quality.'}
(OUT/'preservation-audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
