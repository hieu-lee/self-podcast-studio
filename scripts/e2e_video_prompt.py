"""Real supervised stalled-reader and successful file-input E2E, no paid API."""
import json,os,subprocess,threading,time
from pathlib import Path
from backend.video import run_tool,Cancelled
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/production/prompt';OUT.mkdir(parents=True,exist_ok=True)
prompt=OUT/'producer-prompt.txt';prompt.write_text('Synthetic episode input.\n'*50000)
checks=[]
for mode in ['cancel','timeout']:
 event=threading.Event();pidfile=OUT/(mode+'.pid');pidfile.unlink(missing_ok=True);errors=[]
 def worker():
  try:run_tool([str(ROOT/'.venv/bin/python'),'-c',"import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(90)",str(pidfile)],mode,1 if mode=='timeout' else 30,out=OUT,event=event,stdin_file=prompt)
  except Exception as e:errors.append(e)
 t=threading.Thread(target=worker);begin=time.monotonic();t.start()
 for _ in range(100):
  if pidfile.exists():break
  time.sleep(.05)
 assert pidfile.exists(),'Stalled reader did not launch'
 if mode=='cancel':event.set()
 t.join(9);assert not t.is_alive(),mode+' stuck in prompt delivery';assert errors and isinstance(errors[0],Cancelled if mode=='cancel' else RuntimeError),errors
 pid=int(pidfile.read_text());rows=subprocess.check_output(['ps','-axo','pid=,stat='],text=True).splitlines();assert not any(l.split()[0]==str(pid) and not l.split()[1].startswith('Z') for l in rows)
 checks.append({'mode':mode,'elapsed':time.monotonic()-begin,'child_gone':True,'terminal':type(errors[0]).__name__})
run_tool([str(ROOT/'.venv/bin/python'),'-c',"import sys,hashlib;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"],'success',10,out=OUT,event=threading.Event(),stdin_file=prompt)
import hashlib
assert (OUT/'success.log').read_text().strip()==hashlib.sha256(prompt.read_bytes()).hexdigest()
report={'scope':'Actual trusted subprocess supervisor: >1MB regular-file stdin, stalled reader cancellation/deadline and complete successful read','checks':checks,'successful_bytes':prompt.stat().st_size};(OUT/'e2e.json').write_text(json.dumps(report,indent=2));print(report)
