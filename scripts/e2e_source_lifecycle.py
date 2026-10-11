"""Actual source planning needs-source/cancel/retry via HTTP, synthetic import."""
import json,os,shutil,time,uuid,subprocess
from pathlib import Path
import httpx
from backend import store
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/source-acquisition'
p=json.loads((OUT/'attempt.json').read_text());source=store.ROOT/p['session_id']/p['export'];c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=30);c.get('/api/bootstrap').raise_for_status();r=c.post('/api/sessions',json={'topic':'Source lifecycle E2E: actual saved public Example Domain/local comparison demo narration','language':'en'});r.raise_for_status();sid=r.json()['id'];version='export-'+uuid.uuid4().hex;dest=store.ROOT/sid/version;dest.mkdir()
for name in ['episode.mp3','polish.json','edit.json','transcript.json','final-guest.wav','final-ai.wav']:shutil.copy2(source/name,dest/name)
store.set_meta(sid,'export_dir',version)
assert c.post(f'/api/sessions/{sid}/video',json={'version':version,'sources':{'project_ids':['../../secret']}}).status_code==409
assert c.post(f'/api/sessions/{sid}/video',json={'version':version,'sources':{'root':'/private','command':'not-executed'}}).status_code==422
r=c.post(f'/api/sessions/{sid}/video',json={'version':version});r.raise_for_status();missing=r.json()['job_id']
for _ in range(1500):
 v=c.get(f'/api/sessions/{sid}').json()['video']
 if v['state'] not in ['running','queued','cancelling']:break
 time.sleep(.2)
assert v['state']=='needs_source',v;assert 'Select sources' in v['message'];assert not (dest/missing/'source-provenance.json').exists()
selection={'public_urls':['https://example.com/'],'project_ids':['comparison-demo']};r=c.post(f'/api/sessions/{sid}/video',json={'version':version,'sources':selection});r.raise_for_status();job=r.json()['job_id'];assert job!=missing
for _ in range(1500):
 v=c.get(f'/api/sessions/{sid}').json()['video']
 if v['progress']==21:break
 assert v['state'] not in ['failed','completed','needs_source'],v
 time.sleep(.02)
else:raise AssertionError('Acquisition stage not entered')
# Wait for actual acquisition Node/server/browser descendants, not just a queued cancel.
for _ in range(150):
 rows=subprocess.check_output(['ps','-axo','pid=,ppid=,command='],text=True).splitlines();matches=[row for row in rows if 'node ' in row and 'capture_sources.mjs' in row and str(dest/job) in row]
 if matches:break
 time.sleep(.02)
assert matches,'Acquisition process not observed';node=int(matches[0].split()[0]);runtime=dest/job/'source-runtime-private.json'
for _ in range(300):
 if runtime.exists():break
 time.sleep(.02)
assert runtime.exists(),'Actual local listener not observed';port=json.loads(runtime.read_text())['port']
pairs=[tuple(map(int,row.split())) for row in subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines()];owned={node}
while True:
 new=owned|{pid for pid,parent in pairs if parent in owned}
 if new==owned:break
 owned=new
assert len(owned)>2,('Actual Chromium descendants not observed',owned);begin=time.monotonic();c.post(f'/api/sessions/{sid}/video/cancel',json={'version':version,'job_id':job}).raise_for_status()
for _ in range(150):
 v=c.get(f'/api/sessions/{sid}').json()['video']
 if v['state']=='cancelled':break
 time.sleep(.1)
assert v['state']=='cancelled',v
rows=subprocess.check_output(['ps','-axo','pid=,stat='],text=True).splitlines();assert not any(int(row.split()[0]) in owned and not row.split()[1].startswith('Z') for row in rows)
import socket
with socket.socket() as sock:
 sock.settimeout(.5);assert sock.connect_ex(('127.0.0.1',port))!=0,'Owned source listener still open'
assert not (dest/job/'episode.mp4').exists();assert c.get(f'/api/sessions/{sid}/video/{job}/files/source-capture-private.json',params={'version':version}).status_code==404
# A new attempt works after cleanup; immediate cancellation avoids another paid run.
r=c.post(f'/api/sessions/{sid}/video',json={'version':version,'sources':selection});r.raise_for_status();retry=r.json()['job_id'];assert retry not in [missing,job];c.post(f'/api/sessions/{sid}/video/cancel',json={'version':version,'job_id':retry}).raise_for_status()
for _ in range(150):
 if c.get(f'/api/sessions/{sid}').json()['video']['state']=='cancelled':break
 time.sleep(.1)
report={'session_id':sid,'missing_job':missing,'capture_cancel_job':job,'retry_job':retry,'cancel_seconds':time.monotonic()-begin,'owned_processes_gone':sorted(owned),'owned_port_closed':port,'checks':['actual Codex missing source returns actionable needs_source with no fake capture','unknown project and startup/path injection rejected','actual acquisition Node/server/browser started then cancelled','capture process gone; incomplete media/private inputs withheld','retry new immutable attempt after cleanup'],'scope':'New test-owned imported synthetic source narration, real hosted planning and HTTP job, no human media/live service disruption'};(OUT/'lifecycle-e2e.json').write_text(json.dumps(report,indent=2));print(report)
