"""Real Codex application reuse/owned cancellation/parent-death E2E, before code."""
import argparse,json,os,signal,socket,subprocess,time,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/runtime-acquisition';p=argparse.ArgumentParser();p.add_argument('case',choices=['reuse','cancel','parent-death']);a=p.parse_args();folder=OUT/(a.case+'-'+uuid.uuid4().hex[:8]);folder.mkdir();root=OUT/'projects/node';services=[]
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def closed(p):
 with socket.socket() as s:s.settimeout(.3);return s.connect_ex(('127.0.0.1',p))!=0
def live(pid):return subprocess.run(['kill','-0',str(pid)],stderr=subprocess.DEVNULL).returncode==0
env=os.environ.copy();api=port();front=port()
try:
 if a.case=='reuse':
  for filename,extra in [('api.mjs',{'API_PORT':str(api)}),('frontend.mjs',{'API_PORT':str(api),'PORT':str(front)})]:services.append(subprocess.Popen(['node',filename],cwd=root,env={**env,**extra},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True))
  for _ in range(100):
   if not closed(api) and not closed(front):break
   time.sleep(.05)
 spec=folder/'selection-private.json';spec.write_text(json.dumps({'id':'s0','type':'application','project_id':'runtime-node','label':'Counter Studio application','root':str(root.resolve()),'reuse_existing':a.case=='reuse'}))
 command=[str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/acquire_runtime.py'),str(folder),str(spec)]
 if a.case=='parent-death':
  owner=folder/'owner.py';owner.write_text('import os,subprocess,time\nsubprocess.Popen('+repr([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/job_process.py'),'--parent'])+'+[str(os.getpid()),"--"]+'+repr(command)+')\ntime.sleep(1200)\n');command=[str(ROOT/'.venv/bin/python'),str(owner)]
 with (folder/'owner.log').open('wb') as log:
  process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  if a.case=='reuse':
   assert process.wait(timeout=900)==0;source=json.loads((folder/'source-provenance.json').read_text())['sources'][0];assert source['runtime']['decision']=='reused',source;assert source['websocket_frames']>0,source;assert all(live(p.pid) for p in services);assert httpx.get(f'http://127.0.0.1:{api}/state').json()['count']==0
   report={'decision':'reused','reused_pids_untouched':[p.pid for p in services],'state_unchanged':True}
  else:
   for _ in range(4500):
    private=folder/'runtime-private.json'
    if private.exists() and json.loads(private.read_text()).get('phase')=='ready':break
    assert process.poll() is None,'Owner failed before real readiness';time.sleep(.1)
   else:raise AssertionError('Actual owned runtime readiness not observed')
   runtime=json.loads(private.read_text());ports=[s['port'] for s in runtime['listeners']];pids=[s['pid'] for s in runtime['listeners']];assert all(not closed(p) for p in ports)
   process.kill() if a.case=='parent-death' else process.terminate();process.wait(timeout=15)
   for _ in range(150):
    if all(closed(p) for p in ports) and not any(live(pid) for pid in pids):break
    time.sleep(.1)
   assert all(closed(p) for p in ports) and not any(live(pid) for pid in pids),(ports,pids);assert not (folder/'source-provenance.json').exists();report={'decision':a.case,'owned_pids_gone':pids,'owned_ports_closed':ports}
 (folder/'e2e.json').write_text(json.dumps(report,indent=2));(OUT/(a.case+'-e2e.json')).write_text(json.dumps({'folder':str(folder),'report':report},indent=2));print(report)
finally:
 if 'process' in globals() and process.poll() is None:process.terminate();process.wait(timeout=15)
 for p in services:
  if p.poll() is None:os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=10)
