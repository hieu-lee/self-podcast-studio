"""Cancel a real video job after final-word alignment starts, not just queued."""
import json,os,shutil,time,uuid
from pathlib import Path
import httpx
from backend import store
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/production/safety';OUT.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=30);c.get('/api/bootstrap').raise_for_status()
r=json.loads((ROOT/'.artifacts/production/vi/e2e.json').read_text());source=store.ROOT/r['session_id']/r['export']
s=c.post('/api/sessions',json={'topic':'Midflight cancellation E2E — imported synthetic audio','language':'vi'});s.raise_for_status();sid=s.json()['id'];version='export-'+uuid.uuid4().hex;p=store.ROOT/sid/version;p.mkdir()
for name in ['episode.mp3','polish.json','edit.json','transcript.json','final-guest.wav','final-ai.wav']:shutil.copy2(source/name,p/name)
store.set_meta(sid,'export_dir',version)
x=c.post(f'/api/sessions/{sid}/video',json={'version':version});x.raise_for_status();job=x.json()['job_id'];start=time.monotonic()
while time.monotonic()-start<30:
 v=c.get(f'/api/sessions/{sid}').json()['video']
 if v['message'].startswith('Aligning final-audio words'):break
 assert v['state'] not in ['completed','failed'],v
 time.sleep(.02)
else:raise AssertionError('Word-alignment stage never observed')
c.post(f'/api/sessions/{sid}/video/cancel',json={'version':version,'job_id':job}).raise_for_status();cancelled=time.monotonic()
while time.monotonic()-cancelled<200:
 v=c.get(f'/api/sessions/{sid}').json()['video']
 if v['state']=='cancelled':break
 time.sleep(.1)
assert v['state']=='cancelled',v
folder=p/job
assert not any((folder/name).exists() for name in ['word-timing.json','audio-analysis.json','storyboard.json','episode.mp4'])
report={'session_id':sid,'job_id':job,'cancel_seconds':time.monotonic()-cancelled,'checks':['real word-alignment stage entered','in-flight hosted request bounded; no subsequent word/audio-analysis/producer/capture output','terminal cancelled, not completed'],'scope':'New test-owned imported synthetic media, real HTTP/job/request execution; no human recordings or server kill'}
(OUT/'midflight-e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
