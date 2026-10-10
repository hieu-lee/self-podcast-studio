"""Own trusted children by inherited job marker, even through rapid reparenting."""
import contextlib,os,signal,subprocess,sys,time,uuid
parent=int(sys.argv[2]);stopping=False

def stop(signum,frame):
    global stopping
    stopping=True

signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)

def snapshot():
    # Birth identity protects unrelated processes if an owned PID gets reused.
    proc=subprocess.Popen(['ps','-axo','pid=,ppid=,uid=,lstart='],stdout=subprocess.PIPE,text=True)
    rows={}
    for line in proc.communicate()[0].splitlines():
        fields=line.split(maxsplit=3)
        if len(fields)==4:rows[int(fields[0])]=(int(fields[1]),int(fields[2]),fields[3])
    rows.pop(proc.pid,None)
    return rows

baseline=snapshot();marker='SELF_PODCAST_PROCESS_OWNER='+uuid.uuid4().hex
os.environ[marker.split('=')[0]]=marker.split('=')[1]
child=subprocess.Popen(sys.argv[4:])

def owned_processes():
    live=snapshot();owned={os.getpid()}
    while True:
        new=owned|{pid for pid,(ppid,uid,birth) in live.items() if ppid in owned}
        if new==owned:break
        owned=new
    # Inspect only newly born same-user processes for our exact marker. Raw
    # environment text never leaves this function, logs, files or model inputs.
    candidates=[pid for pid,(ppid,uid,birth) in live.items() if uid==os.getuid() and (pid not in baseline or baseline[pid][2]!=birth)]
    for begin in range(0,len(candidates),100):
        result=subprocess.run(['ps','eww','-p',','.join(map(str,candidates[begin:begin+100])),'-o','pid=,command='],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,errors='replace')
        for line in result.stdout.splitlines():
            fields=line.split(maxsplit=1)
            if len(fields)==2 and fields[0].isdigit() and marker in fields[1].split():owned.add(int(fields[0]))
    return {pid:live[pid][2] for pid in owned if pid!=os.getpid() and pid in live}

def send(owned,sig):
    live=snapshot()
    for pid,birth in owned.items():
        if pid in live and live[pid][2]==birth:
            with contextlib.suppress(ProcessLookupError):os.kill(pid,sig)

owned=owned_processes()
while child.poll() is None and not stopping and os.getppid()==parent:
    owned.update(owned_processes());time.sleep(.25)
# All exits, including a child that detaches and immediately exits successfully.
owned.update(owned_processes());send(owned,signal.SIGTERM)
deadline=time.monotonic()+3
while time.monotonic()<deadline:
    fresh=owned_processes();send({pid:birth for pid,birth in fresh.items() if pid not in owned},signal.SIGTERM);owned.update(fresh)
    live=snapshot()
    if not any(pid in live and live[pid][2]==birth for pid,birth in owned.items()):break
    time.sleep(.1)
owned.update(owned_processes());send(owned,signal.SIGKILL);child.wait()
raise SystemExit(128+signal.SIGTERM if stopping or os.getppid()!=parent else child.returncode)
