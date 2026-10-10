"""Real ignored-TERM/detached-Chromium process ownership E2E, no studio kill."""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/production/process';OUT.mkdir(parents=True,exist_ok=True)
def tree(pid):
 pairs=[list(map(int,l.split())) for l in subprocess.check_output(['ps','-axo','pid=,ppid='],text=True).splitlines() if len(l.split())==2];owned={pid}
 while True:
  new=owned|{p for p,pp in pairs if pp in owned}
  if new==owned:return owned
  owned=new
def gone(pids):
 rows=subprocess.check_output(['ps','-axo','pid=,stat='],text=True).splitlines();return not any(int(l.split()[0]) in pids and not l.split()[1].startswith('Z') for l in rows if l.split())
checks=[]
# Supervisor must survive TERM long enough to kill a child that ignores it.
p=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/job_process.py'),'--parent',str(os.getpid()),'--',str(ROOT/'.venv/bin/python'),'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)'],start_new_session=True)
try:
 time.sleep(.5);owned=tree(p.pid);assert len(owned)>1;os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=7)
 for _ in range(40):
  if gone(owned):break
  time.sleep(.1)
 assert gone(owned),owned;checks.append('TERM-ignoring real child cleaned before supervisor exit')
finally:
 if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
# Normal early child exit must also clean a grandchild that ignores TERM.
p=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/job_process.py'),'--parent',str(os.getpid()),'--',str(ROOT/'.venv/bin/python'),'-c',"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)']);time.sleep(1)"],start_new_session=True)
try:
 time.sleep(.5);owned=tree(p.pid);assert len(owned)>2;p.wait(timeout=7)
 assert p.returncode==0
 for _ in range(50):
  if gone(owned):break
  time.sleep(.1)
 assert gone(owned),owned;checks.append('normal early child exit retains status and cleans TERM-ignoring grandchild')
finally:
 for pid in owned:
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
# No artificial parent sleep: ancestry can vanish before the first inventory.
sentinel=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-c','import time;time.sleep(90)'])
try:
 for index in range(4):
  pidfile=OUT/f'immediate-{index}.pid';pidfile.unlink(missing_ok=True)
  code="import subprocess,sys,pathlib;p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)'],start_new_session=True);pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
  p=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/job_process.py'),'--parent',str(os.getpid()),'--',str(ROOT/'.venv/bin/python'),'-c',code,str(pidfile)],start_new_session=True)
  try:
   p.wait(timeout=7);assert p.returncode==0;grandchild=int(pidfile.read_text())
   for _ in range(50):
    if gone({grandchild}):break
    time.sleep(.1)
   assert gone({grandchild}),grandchild;assert sentinel.poll() is None
  finally:
   if pidfile.exists():
    try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
    except ProcessLookupError:pass
   if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
 checks.append('4 immediate detached-child exits cleaned without ancestry observation; unrelated sentinel untouched')
finally:sentinel.kill();sentinel.wait()
# A TERM handler can fork a detached child after the initial cleanup inventory.
pidfile=OUT/'term-fork.pid';pidfile.unlink(missing_ok=True)
code="import signal,subprocess,sys,time,pathlib\ndef stop(s,f):\n signal.signal(signal.SIGTERM,signal.SIG_IGN)\n p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)'],start_new_session=True)\n pathlib.Path(sys.argv[1]).write_text(str(p.pid));sys.exit(0)\nsignal.signal(signal.SIGTERM,stop);time.sleep(90)"
p=subprocess.Popen([str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/job_process.py'),'--parent',str(os.getpid()),'--',str(ROOT/'.venv/bin/python'),'-c',code,str(pidfile)],start_new_session=True)
try:
 time.sleep(.5);os.killpg(p.pid,signal.SIGTERM);p.wait(timeout=7);grandchild=int(pidfile.read_text())
 for _ in range(50):
  if gone({grandchild}):break
  time.sleep(.1)
 assert gone({grandchild}),grandchild;checks.append('detached child born inside TERM handler discovered and cleaned')
finally:
 if pidfile.exists():
  try:os.kill(int(pidfile.read_text()),signal.SIGKILL)
  except ProcessLookupError:pass
 if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()
for mode in ['cancel','parent-death','child-failure']:
 fixture=OUT/mode;fixture.mkdir(exist_ok=True)
 for old in fixture.glob('frame-*.png'):old.unlink()
 (fixture/'scene-0.html').write_text('<!doctype html><html><body>Real browser cleanup E2E</body></html>');(fixture/'storyboard.json').write_text(json.dumps({'scenes':[{'start':0,'end':90,'assets':[],'actions':[]}]}));(fixture/'captions.json').write_text('{"cues":[]}');pidfile=fixture/'pid';pidfile.unlink(missing_ok=True)
 parent=subprocess.Popen([str(ROOT/'.venv/bin/python'),'-c',"import subprocess,sys,time,pathlib,os; p=subprocess.Popen([sys.executable,sys.argv[1],'--parent',str(os.getpid()),'--','node',sys.argv[2],sys.argv[3]],start_new_session=True);pathlib.Path(sys.argv[4]).write_text(str(p.pid));time.sleep(90)",str(ROOT/'scripts/job_process.py'),str(ROOT/'scripts/capture_video.mjs'),str(fixture),str(pidfile)])
 try:
  for _ in range(200):
   if (fixture/'frame-0-initial.png').exists() and pidfile.exists():break
   time.sleep(.05)
  assert (fixture/'frame-0-initial.png').exists();pid=int(pidfile.read_text());owned=tree(pid);assert len(owned)>3,owned
  if mode=='cancel':os.killpg(pid,signal.SIGTERM)
  elif mode=='parent-death':parent.kill();parent.wait()
  else:
   rows=subprocess.check_output(['ps','-axo','pid=,ppid=,comm='],text=True).splitlines()
   node=next(int(row.split()[0]) for row in rows if len(row.split())>=3 and row.split()[1]==str(pid) and row.split()[2].endswith('node'))
   os.kill(node,signal.SIGKILL)
  for _ in range(100):
   if gone(owned):break
   time.sleep(.1)
  assert gone(owned),(mode,owned);checks.append(mode+': actual detached Chromium/Node/supervisor descendants terminated')
 finally:
  if parent.poll() is None:parent.kill();parent.wait()
  for child in locals().get('owned',[]):
   try:os.kill(child,signal.SIGKILL)
   except ProcessLookupError:pass
(OUT/'e2e.json').write_text(json.dumps({'checks':checks,'scope':'Dedicated synthetic process/browser fixtures; never killed the studio or accessed human mic/profiles'},indent=2));print(checks)
