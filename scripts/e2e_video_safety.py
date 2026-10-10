"""Real process/HTTP/capture boundary E2E; synthetic test-owned data only."""
import hashlib,json,os,shutil,signal,subprocess,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/production/safety';OUT.mkdir(parents=True,exist_ok=True)
(OUT/'process.pid').unlink(missing_ok=True)
# Kill a dummy parent, never the studio; its supervised real sleeping child must die.
parent=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-c',"import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,sys.argv[1],'--parent',str(__import__('os').getpid()),'--',sys.executable,'-c','import time;time.sleep(90)'],start_new_session=True);pathlib.Path(sys.argv[2]).write_text(str(p.pid));time.sleep(90)",str(ROOT/'scripts/job_process.py'),str(OUT/'process.pid')])
try:
 for _ in range(100):
  if (OUT/'process.pid').exists():break
  time.sleep(.05)
 pg=int((OUT/'process.pid').read_text());time.sleep(.4);parent.kill();parent.wait()
 for _ in range(100):
  result=subprocess.run(['ps','-axo','pgid=,stat=,command='],capture_output=True,text=True)
  live=[x for x in result.stdout.splitlines() if x.split() and x.split()[0]==str(pg) and not x.split()[1].startswith('Z')]
  if not live:break
  time.sleep(.05)
 assert not live,live
finally:
 if parent.poll() is None:parent.kill();parent.wait()
# An adversarial app runs through the real browser boundary, not a mocked request.
hostile=OUT/'hostile';hostile.mkdir(exist_ok=True)
html='''<!doctype html><html lang="en"><meta charset="utf-8"><body>Sealed capture probe<script>fetch('http://127.0.0.1:8765/api/sessions',{credentials:'include'}).catch(()=>{});fetch('https://example.com/').catch(()=>{});let a=document.createElement('img');a.src='/producer-prompt.txt';document.body.append(a);window.open('http://127.0.0.1:8765/api/bootstrap');</script></body></html>'''
(hostile/'scene-0.html').write_text(html);(hostile/'storyboard.json').write_text(json.dumps({'scenes':[{'start':0,'end':2,'assets':[],'actions':[]}]}));(hostile/'captions.json').write_text('{"cues":[]}')
subprocess.run(['node',str(ROOT/'scripts/capture_video.mjs'),str(hostile)],check=True,timeout=60)
security=json.loads((hostile/'capture-security.json').read_text());assert security['fresh_profile'] and security['no_permissions'];assert security['blocked_requests'],security
assert any('8765' in x['host'] or not x['host'] for x in security['blocked_requests']),security
# Import only already verified synthetic media into a NEW empty test-owned episode.
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=20);c.get('/api/bootstrap').raise_for_status()
fixture=json.loads((ROOT/'.artifacts/production/vi/e2e.json').read_text());data=Path(os.environ.get('SELF_PODCAST_DATA',ROOT/'.data'));source=data/fixture['session_id']/fixture['export']
r=c.post('/api/sessions',json={'topic':'Video lifecycle safety E2E — imported synthetic export, no microphone','language':'vi'});r.raise_for_status();sid=r.json()['id']
from backend import store
version='export-'+uuid.uuid4().hex;target=data/sid/version;target.mkdir()
for name in ['episode.mp3','polish.json','edit.json','transcript.json','final-guest.wav','final-ai.wav']:shutil.copy2(source/name,target/name)
store.set_meta(sid,'export_dir',version)
assert c.get(f'/api/sessions/{sid}').json()['polished_audio']
r=c.post(f'/api/sessions/{sid}/video',json={'version':version});r.raise_for_status();job=r.json()['job_id']
assert c.post(f'/api/sessions/{sid}/video',json={'version':version}).status_code==409
assert c.post(f'/api/sessions/{sid}/video/cancel',json={'version':version,'job_id':job}).status_code==200
for _ in range(250):
 v=c.get(f'/api/sessions/{sid}').json()['video']
 if v['state']=='cancelled':break
 time.sleep(.1)
assert v['state']=='cancelled',v
assert c.get(f'/api/sessions/{sid}/video/{job}/files/episode.mp4',params={'version':version}).status_code==409
assert c.get(f'/api/sessions/{sid}/video/{job}/files/producer-prompt.txt',params={'version':version}).status_code==404
assert c.post(f'/api/sessions/{sid}/video/approve',json={'version':version,'job_id':job}).status_code==409
r=c.post(f'/api/sessions/{sid}/video',json={'version':version});r.raise_for_status();retry=r.json()['job_id'];assert retry!=job
c.post(f'/api/sessions/{sid}/video/cancel',json={'version':version,'job_id':retry}).raise_for_status()
for _ in range(250):
 if c.get(f'/api/sessions/{sid}').json()['video']['state']=='cancelled':break
 time.sleep(.1)
# Re-export-equivalent version switch, followed by real resume invalidation.
new='export-'+uuid.uuid4().hex;store.set_meta(sid,'export_dir',new)
assert c.get(f'/api/sessions/{sid}').json()['video'] is None
assert c.post(f'/api/sessions/{sid}/video/approve',json={'version':version,'job_id':retry}).status_code==409
assert c.post(f'/api/sessions/{sid}/video',json={'version':version}).status_code==409
assert not c.get(f'/api/sessions/{sid}').json()['polished_audio']
store.set_meta(sid,'export_dir',version)
eid=uuid.uuid4().hex
c.post(f'/api/sessions/{sid}/epochs',json={'id':eid,'wall_ms':time.time()*1000}).raise_for_status()
assert c.get(f'/api/sessions/{sid}').json()['video'] is None
c.post(f'/api/sessions/{sid}/seal',json={'epoch':eid,'frames':0}).raise_for_status()
assert hashlib.sha256((target/'episode.mp3').read_bytes()).hexdigest()==hashlib.sha256((source/'episode.mp3').read_bytes()).hexdigest()
report={'session_id':sid,'scope':'Actual isolated parent death/child process group; real hostile Chromium app; real local HTTP lifecycle with imported verified synthetic export (not a new audio-production run)','checks':['parent-death child cleanup','sealed hostile app requests blocked','duplicate rejected','cancel reaches terminal state','retry new immutable job','incomplete video withheld','private files withheld','stale/failed approval rejected','changed audio version and resume invalidate current job','legacy/unpolished eligibility false','source audio immutable'],'security':security}
(OUT/'e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
