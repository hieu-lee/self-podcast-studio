"""Download actual project via HTTP, verify privacy/pixel hashes and replay real source/rank capture."""
import hashlib,json,subprocess,threading,zipfile,io
from pathlib import Path
import httpx
from backend.video import run_tool
ROOT=Path(__file__).resolve().parents[1];p=json.loads((ROOT/'.artifacts/source-acquisition/e2e.json').read_text());OUT=ROOT/'.artifacts/source-acquisition/replay'/p['job_id'];OUT.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=60);c.get('/api/bootstrap').raise_for_status();base=f"/api/sessions/{p['session_id']}/video/{p['job_id']}/files/";r=c.get(base+'project.zip',params={'version':p['export']});r.raise_for_status();(OUT/'downloaded-project.zip').write_bytes(r.content)
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
 names=z.namelist();assert not any('private' in n or 'selection' in n or 'prompt' in n or 'auth' in n or n.endswith('.log') for n in names)
 for name in names:
  target=(OUT/name).resolve();assert target.is_relative_to(OUT.resolve())
  body=z.read(name);assert b'fixture-private-value' not in body
  if name.endswith('.json'):assert str(ROOT/'.artifacts/source-acquisition/comparison-demo').encode() not in body
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
 for source in p['sources']['sources']:assert hashlib.sha256(z.read(source['file'])).hexdigest()==source['sha256']
for name in ['source-selection.json','source-capture-private.json','source-runtime-private.json','source-plan-prompt.txt']:
 assert c.get(base+name,params={'version':p['export']}).status_code==404
run_tool(['node',OUT/'replay/capture_video.mjs',OUT],'replay',90,out=OUT,event=threading.Event())
events=json.loads((OUT/'capture-events.json').read_text());before=[(e['item'],e['observed_rank']) for e in p['events'] if e['type']=='drag'];after=[(e['item'],e['observed_rank']) for e in events if e['type']=='drag'];assert before==after,(before,after)
clips=json.loads((OUT/'capture-clips.json').read_text())
for use in p['source_uses']:
 assert any(e.get('type')=='source' and e['item']==use['id'] and abs(e['actual_time']-use['start'])<.3 for e in events),use
 clip=next(x for x in clips if x['scene_start']<=use['start']<x['scene_end']);time=clip['offset']+use['start']-clip['scene_start']+1
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(time),'-i',str(OUT/clip['file']),'-frames:v','1',str(OUT/('replayed-'+use['id']+'.png'))],check=True)
report={'job_id':p['job_id'],'download_sha256':hashlib.sha256(r.content).hexdigest(),'archived_files':names,'source_hashes_match':True,'private_files_http404':True,'real_rank_events':after,'events':events,'scope':'Actual downloaded immutable project, task-supervised bundled replay, matching source pixels/provenance, same real drags/native captions; no live source/network/model/microphone during replay'};(OUT/'replay-e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
