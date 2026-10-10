"""HTTP recording/export/resume E2E and deliberate overlap intermediate audit."""
import base64
import hashlib
import json
import struct
import subprocess
import time
from pathlib import Path
import httpx
import numpy as np

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts';RATE=24000
client=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=60)
client.get('/api/bootstrap').raise_for_status()
received=json.loads((OUT/'live-events.json').read_text());item=next(e['item_id'] for e in received if e['type']=='response.output_audio.delta')
ai=b''.join(base64.b64decode(e['delta']) for e in received if e['type']=='response.output_audio.delta' and e['item_id']==item)
x=np.frombuffer(ai,dtype='<i2');stereo=np.column_stack([x,x]).astype('<i2')
s=client.post('/api/sessions',json={'topic':'E2E deliberate correlated voice overlap + stale-export lifecycle — synthetic only'});s.raise_for_status();sid=s.json()['id']

def capture(eid,pcm):
 client.post('/api/sessions/'+sid+'/epochs',json={'id':eid,'wall_ms':time.time()*1000-len(pcm)/24}).raise_for_status()
 for seq,start in enumerate(range(0,len(pcm),RATE)):
  end=min(len(pcm),start+RATE)
  h=json.dumps({'epoch':eid,'seq':seq,'start':start,'spans':[{'item':'overlap_fixture','start':start,'frames':end-start,'offset':start}],'underruns':[]}).encode()
  client.post('/api/sessions/'+sid+'/chunks',content=struct.pack('<I',len(h))+h+pcm[start:end].tobytes()).raise_for_status()
 client.post('/api/sessions/'+sid+'/seal',json={'epoch':eid,'frames':len(pcm)}).raise_for_status()
def export():
 client.post('/api/sessions/'+sid+'/export',json={'acknowledge_gaps':True,'quality_edit':False}).raise_for_status()
 for _ in range(360):
  m=client.get('/api/sessions/'+sid).json()
  if not m['exporting']:
   assert m.get('export_dir'),m
   return m
  time.sleep(.5)
 raise RuntimeError('Export timeout')

capture('3'*32,stereo);m=export();old=ROOT/'.data'/sid/m['export_dir'];old_hash=hashlib.sha256((old/'episode.mp3').read_bytes()).hexdigest()
codec=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_name','-of','json',str(old/'mix.wav')]))['streams'][0]['codec_name']
assert codec=='pcm_f32le',codec
# Independently decode float data: correlated normalized voices must sum without integer clipping.
raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(old/'mix.wav'),'-f','f32le','-acodec','pcm_f32le','-'])
mix=np.frombuffer(raw,dtype='<f4')
parts=[]
for name in ('guest','ai'):
 data=subprocess.check_output(['ffmpeg','-v','error','-i',str(old/f'final-{name}.wav'),'-f','f32le','-acodec','pcm_f32le','-'])
 parts.append(np.frombuffer(data,dtype='<f4'))
assert np.max(np.abs(mix))>1,'Fixture must really exceed PCM16 headroom'
assert np.allclose(mix,parts[0]+parts[1],atol=1e-6),'Float intermediate altered overlapping sum'
edit=json.loads((old/'edit.json').read_text());assert float(edit['ffmpeg_loudness']['input_tp'])<0
capture('4'*32,stereo[:RATE])
after=client.get('/api/sessions/'+sid).json();assert 'export_dir' not in after and 'export_status' not in after
assert client.post('/api/sessions/'+sid+'/approve',json={'version':m['export_dir']}).status_code==409
assert hashlib.sha256((old/'episode.mp3').read_bytes()).hexdigest()==old_hash,'Previous version changed'
new=export();assert new['export_dir']!=m['export_dir']
assert client.post('/api/sessions/'+sid+'/approve',json={'version':m['export_dir']}).status_code==409
assert hashlib.sha256(client.get('/api/sessions/'+sid+'/files/episode.mp3',params={'version':m['export_dir']}).content).hexdigest()==old_hash
assert client.post('/api/sessions/'+sid+'/approve',json={'version':new['export_dir']}).status_code==200
report={'session_id':sid,'previous_export':m['export_dir'],'current_export':new['export_dir'],
 'checks':['float intermediate conserves actual overlapping sum beyond PCM16 headroom','final peak below clipping','resume invalidates current export/approval','previous export version unchanged','regeneration produces current approvable episode'],
 'intermediate_peak':float(np.max(np.abs(mix))),'scope':'Deliberately correlated synthetic speaker overlap, real HTTP/STT/FFmpeg export; listening confirmation tests the control, not subjective quality.'}
(OUT/'export-lifecycle-e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
