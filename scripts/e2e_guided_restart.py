"""Actual owned fixture-server death/restart around persisted finishing; no human media."""
import concurrent.futures,json,os,signal,socket,subprocess,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/guided';OUT.mkdir(exist_ok=True)
log=(OUT/'restart-server.log').open('wb');proc=None
def boot():
 global proc
 for port in (8765,8766):
  with socket.socket() as s:
   s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
   try:s.bind(('127.0.0.1',port))
   except OSError:raise RuntimeError(f'Owned restart test refuses occupied port {port}; stop only your owned fixture first') from None
 nonce=uuid.uuid4().hex
 proc=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/e2e_guided_server.py')],cwd=ROOT,stdout=log,stderr=log,start_new_session=True,env={**os.environ,'SELF_PODCAST_E2E_NONCE':nonce})
 for _ in range(100):
  if proc.poll() is not None:raise RuntimeError('Owned server startup failed')
  try:
   c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=10);c.get('/api/bootstrap').raise_for_status();identity=c.get('/api/owned-fixture-identity');identity.raise_for_status();assert identity.json()=={'fixture':'self-podcast-owned-research','guided_jobs':True,'nonce':nonce};return c
  except (httpx.HTTPError,AssertionError):c.close();time.sleep(.1)
 raise RuntimeError('Owned server readiness timed out')
try:
 c=boot();sid=c.post('/api/sessions',json={'topic':'Owned restart fixture','language':'en'}).json()['id'];epoch=uuid.uuid4().hex;c.post(f'/api/sessions/{sid}/epochs',json={'id':epoch,'wall_ms':time.time()*1000}).raise_for_status()
 import struct
 h=json.dumps({'epoch':epoch,'seq':0,'start':0,'spans':[],'underruns':[]}).encode();c.post(f'/api/sessions/{sid}/chunks',content=struct.pack('<I',len(h))+h+b'\1\0'*48000).raise_for_status();c.post(f'/api/sessions/{sid}/seal',json={'epoch':epoch,'frames':24000}).raise_for_status()
 c.post(f'/api/sessions/{sid}/finish',json={}).raise_for_status();time.sleep(.3);assert c.get(f'/api/sessions/{sid}').json()['workflow']['state']=='polishing';os.killpg(proc.pid,signal.SIGKILL);proc.wait();c.close();c=boot();m=c.get(f'/api/sessions/{sid}').json();assert m['workflow']['state']=='interrupted' and not m['exporting']
 c.post(f'/api/sessions/{sid}/finish',json={'retry':True}).raise_for_status()
 for _ in range(150):
  m=c.get(f'/api/sessions/{sid}').json()
  if m['workflow']['state']=='ready':break
  time.sleep(.1)
 assert m['workflow']['state']=='ready'
 preparation_sid=c.post('/api/sessions',json={'topic':'Owned checking-preparation crash','language':'en'}).json()['id']
 def prepare():
  try:return c.post(f'/api/sessions/{preparation_sid}/research',json={'query':'slow preparation restart'}).status_code
  except httpx.HTTPError:return 'owned-server-killed'
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(prepare)
  for _ in range(30):
   if (c.get(f'/api/sessions/{preparation_sid}').json().get('preparation') or {}).get('status')=='checking':break
   time.sleep(.05)
  else:raise RuntimeError('Owned preparation did not begin')
  os.killpg(proc.pid,signal.SIGKILL);proc.wait();future.result(timeout=10)
 c.close();c=boot();prepared=c.get(f'/api/sessions/{preparation_sid}').json()['preparation'];assert prepared['status']=='failed';assert not prepared['sources'];assert c.get(f'/api/sessions/{preparation_sid}/files/preparation.json').json()['status']=='failed'
 (OUT/'restart-e2e.json').write_text(json.dumps({'sid':sid,'checks':['actual owned server abrupt death persists interrupted finishing','no nonexistent job reported active after restart','explicit retry creates one coherent ready version','preparation crash becomes durably failed in UI and downloaded info file'],'scope':'Controlled job workers, real server process death/restart; not renderer child-process safety or paid production.'},indent=2));print('Guided abrupt-death/restart E2E passed')
finally:
 if 'c' in locals():c.close()
 if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=30)
 log.close()
