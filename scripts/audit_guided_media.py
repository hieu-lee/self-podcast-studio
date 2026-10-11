"""Independent decoded soundtrack/caption/provenance/ending audit of downloaded guided output."""
import hashlib,json,subprocess,wave,zipfile
from pathlib import Path
import numpy as np
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/guided';report=json.loads((OUT/'real-guided-e2e.json').read_text());audits=[]
for run in report['checks']:
 p=OUT/run['language'];validation=json.loads((p/'validation.json').read_text());assert validation['full_decode'] and validation['ending_intact'] and validation['soundtrack_stream_copy']
 provenance=json.loads((p/'provenance.json').read_text());assert provenance['audio_version']==run['export_dir'];assert provenance['audio_sha256']==hashlib.sha256((p/'episode.mp3').read_bytes()).hexdigest();assert provenance['transcript_sha256']==hashlib.sha256((p/'transcript.json').read_bytes()).hexdigest()
 tracks=[]
 for file in ['episode.mp3','episode.mp4']:
  wav=p/(file+'.wav');subprocess.run(['ffmpeg','-v','error','-y','-i',str(p/file),'-vn','-ac','1','-ar','24000',str(wav)],check=True)
  with wave.open(str(wav)) as w:tracks.append(np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float))
 a,b=tracks;n=min(len(a),len(b));assert n>24000*10;assert abs(len(a)-len(b))<24000*.15
 corr=float(np.corrcoef(a[:n],b[:n])[0,1]);ending=float(np.corrcoef(a[n-72000:n],b[n-72000:n])[0,1]);assert corr>.96 and ending>.95,(corr,ending)
 sources=json.loads((p/'source-provenance.json').read_text())['sources'];plan=json.loads((p/'source-plan.json').read_text());assert not plan['needs_source'];assert any(s['type']=='public' and 'developers.openai.com'==urlsplit(s['url']).hostname for s in sources)
 with zipfile.ZipFile(p/'project.zip') as z:
  assert 'source-selection.json' not in z.namelist()
  for source in sources:
   pixels=z.read(source['file']);assert hashlib.sha256(pixels).hexdigest()==source['sha256'];(p/source['file']).write_bytes(pixels)
   if source['type']=='public':
    view=source['viewport'];assert view.get('focus_text',view.get('heading')) and -2<=view.get('focus_top',view.get('heading_top',720))<240
 for use in plan['uses']:
  t=(use['start']+use['end'])/2;subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(p/'episode.mp4'),'-frames:v','1',str(p/('frame-source-'+use['id']+'.png'))],check=True)
 transcript=json.loads((p/'transcript.json').read_text());captions=json.loads((p/'captions.json').read_text())['cues'];edit=json.loads((p/'edit.json').read_text())
 for speaker in ['Hieu','AI interviewer']:
  original=' '.join(s['text'] for s in transcript['segments'] if s['speaker']==speaker).split();rendered=' '.join(s['text'].removeprefix(speaker+': ') for s in captions if s['text'].startswith(speaker+': ')).split();assert original==rendered,(run['language'],speaker)
 assert all(0<=s['start']<s['end']<=edit['final_duration']+.1 for s in captions)
 for label,t in [('start',.2),('middle',n/48000),('ending',n/24000-.3)]:subprocess.run(['ffmpeg','-v','error','-y','-ss',str(max(0,t)),'-i',str(p/'episode.mp4'),'-frames:v','1',str(p/('frame-'+label+'.png'))],check=True)
 audits.append({'language':run['language'],'sid':run['sid'],'audio_version':run['export_dir'],'job_id':run['workflow']['job_id'],'decoded_seconds':n/24000,'waveform_correlation':corr,'last_three_seconds_correlation':ending,'checks':['downloaded MP4 full decode/complete soundtrack/ending match','downloaded audio/transcript hashes match actual producer provenance','all native caption words retained within full final timeline','real primary source pixels/viewport/provenance from downloaded ZIP; no source-selection private file','actual start/middle/ending/source-interval frames extracted for visual inspection'],'scope':'Short actual synthetic-microphone guided output, no human listening approval or hour endurance.'})
(OUT/'media-audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2));print(json.dumps(audits,indent=2))
