"""Downloaded runtime project ZIP privacy, immutable clips and actual offline replay."""
import argparse,hashlib,io,json,subprocess,threading,zipfile
from pathlib import Path
import httpx
from backend.video import run_tool
ROOT=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser();p.add_argument('language',choices=['en','vi']);a=p.parse_args();report=json.loads((ROOT/f'.artifacts/runtime-acquisition/{a.language}/e2e.json').read_text());out=ROOT/f'.artifacts/runtime-acquisition/{a.language}/replay';out.mkdir(exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=90);c.get('/api/bootstrap').raise_for_status();base=f"/api/sessions/{report['session_id']}/video/{report['job_id']}/files/";params={'version':report['export']};r=c.get(base+'project.zip',params=params);r.raise_for_status();(out/'downloaded-project.zip').write_bytes(r.content)
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
 names=z.namelist();assert not any(any(s in n for s in ['private','workspace','runtime-home','prompt','selection','startup','auth']) or n.endswith('.log') for n in names),names
 for name in names:
  target=(out/name).resolve();assert target.is_relative_to(out.resolve());body=z.read(name)
  if name.endswith(('.json','.html','.md','.txt')):assert b'/Users/' not in body and b'never-copy-this-marker' not in body and b'sk-proj-' not in body,name
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
 for s in report['sources']['sources']:
  for key,digest in [('file','sha256'),('clip','clip_sha256'),('before_file','before_sha256')]:assert hashlib.sha256(z.read(s[key])).hexdigest()==s[digest],(s['id'],key)
private=['source-selection.json','source-plan-prompt.txt','runtime-s0/startup-private.json','runtime-s0/runtime-private.json','runtime-s0/runtime-startup.log','runtime-s0/selection-private.json','runtime-s0/workspace/README.md']
for name in private:assert c.get(base+name,params=params).status_code==404,name
run_tool(['node',out/'replay/capture_video.mjs',out],'replay',180,out=out,event=threading.Event());events=json.loads((out/'capture-events.json').read_text());clips=json.loads((out/'capture-clips.json').read_text())
for use in report['source_uses']:
 assert any(e.get('type')=='source' and e['item']==use['id'] and e['clip']==use['clip'] and abs(e['actual_time']-use['start'])<.3 for e in events),use
 clip=next(x for x in clips if x['scene_start']<=use['start']<x['scene_end'])
 for stage,seconds in [('before',.5),('after',2.5)]:
  offset=clip['offset']+use['start']-clip['scene_start']+seconds
  subprocess.run(['ffmpeg','-v','error','-y','-ss',str(offset),'-i',str(out/clip['file']),'-frames:v','1',str(out/(use['id']+'-'+stage+'.png'))],check=True)
result={'job_id':report['job_id'],'download_sha256':hashlib.sha256(r.content).hexdigest(),'archived_files':names,'source_and_clip_hashes_match':True,'private_http404':private,'actual_replay_events':events,'scope':'Actual downloaded immutable project replay with native captions and timed real runtime WebM; no live startup/model/network/microphone required'};(out/'e2e.json').write_text(json.dumps(result,indent=2));print(a.language,'runtime ZIP privacy and actual offline replay passed')
