"""Real loopback HTTP E2E; saved source inspection, no post-hoc unit tests."""
import argparse
import hashlib
import json
import math
import struct
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.artifacts';OUT.mkdir(exist_ok=True)
BASE='http://127.0.0.1:8765'
client=httpx.Client(base_url=BASE,headers={'X-Self-Podcast':'1'},timeout=60)
client.get('/api/bootstrap').raise_for_status()
checks=[]
def check(name,passed):
    assert passed,name
    checks.append(name)
def post(path,data=None):
    r=client.post('/api/'+path,json=data);r.raise_for_status();return r.json()
def packet(epoch,seq,pcm):
    h=json.dumps({'epoch':epoch,'seq':seq,'start':seq*24000,'spans':[],'underruns':[]},separators=(',',':')).encode()
    return struct.pack('<I',len(h))+h+pcm
def chunk(sid,epoch,seq,pcm):
    return client.post(f'/api/sessions/{sid}/chunks',content=packet(epoch,seq,pcm))

parser=argparse.ArgumentParser();parser.add_argument('--verify-restart',action='store_true');parser.add_argument('--seconds',type=int,default=3600);args=parser.parse_args()
if args.verify_restart:
    report=json.loads((OUT/'backend-e2e.json').read_text())
    sid=report['session_id']
    m=client.get('/api/sessions/'+sid).json()
    check('recording survives server restart',m['frames']==report['frames'] and m['chunks']==report['chunks'])
    # Original duplicate must survive restart. Reconstruct deterministic tone chunk instead below.
    tone=struct.pack('<'+ 'h'*24000,*[round(math.sin(i*2*math.pi*440/24000)*2000) for i in range(24000)])
    stereo=b''.join(tone[i:i+2]+b'\0\0' for i in range(0,len(tone),2))
    r=chunk(sid,report['epoch'],0,stereo)
    check('idempotent retry survives restart',r.status_code==200)
    report['checks']+=checks;report['restart_verified']=True
    (OUT/'backend-e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));raise SystemExit
check('host boundary',httpx.get(BASE+'/api/bootstrap',headers={'Host':'attacker.example'}).status_code==403)
check('cross-origin mutation',client.post('/api/sessions',json={'topic':'forbidden'},headers={'Origin':'https://attacker.example'}).status_code==403)
check('unauthenticated read',httpx.get(BASE+'/api/sessions').status_code==403)
check('form/simple mutation',httpx.post(BASE+'/api/sessions',cookies=client.cookies,json={'topic':'forbidden'}).status_code==403)
check('path traversal/id boundary',client.get('/api/sessions/not-a-uuid').status_code==404)
s=post('sessions',{'topic':'E2E SYNTHETIC accelerated hour durability fixture — NOT a live interview'})
sid=s['id'];epoch='1'*32
post('sessions/'+sid+'/epochs',{'id':epoch,'wall_ms':time.time()*1000})
tone=struct.pack('<'+ 'h'*24000,*[round(math.sin(i*2*math.pi*440/24000)*2000) for i in range(24000)])
stereo=b''.join(tone[i:i+2]+b'\0\0' for i in range(0,len(tone),2))
chunk(sid,epoch,1,stereo).raise_for_status()
r=client.post('/api/sessions/'+sid+'/seal',json={'epoch':epoch,'frames':48000})
check('missing chunk blocks save',r.status_code==409)
chunk(sid,epoch,0,stereo).raise_for_status()
check('duplicate idempotent',chunk(sid,epoch,0,stereo).status_code==200)
check('conflicting duplicate refused',chunk(sid,epoch,0,bytes(96000)).status_code==409)
check('oversized upload refused',client.post('/api/sessions/'+sid+'/chunks',content=bytes(170000)).status_code==413)
started=time.time()
for seq in range(2,args.seconds):chunk(sid,epoch,seq,stereo).raise_for_status()
post('sessions/'+sid+'/seal',{'epoch':epoch,'frames':args.seconds*24000})
m=client.get('/api/sessions/'+sid).json()
check('hour samples and chunks',m['frames']==args.seconds*24000 and m['chunks']==args.seconds)
check('sealed new write refused',chunk(sid,epoch,args.seconds,stereo).status_code==409)
check('sealed exact retry accepted',chunk(sid,epoch,0,stereo).status_code==200)
# Independent source inspection is a repeatable artifact, not a unit test.
import sqlite3
with sqlite3.connect(ROOT/'.data'/sid/'recording.sqlite') as db:
    h=hashlib.sha256();frames=0
    for start,pcm in db.execute('SELECT start,pcm FROM chunks ORDER BY seq'):
        assert start==frames
        h.update(pcm);frames+=len(pcm)//4
    expected_hash=hashlib.sha256()
    for _ in range(args.seconds): expected_hash.update(stereo)
    expected=expected_hash.hexdigest()
    check('saved stereo payload/sample clock integrity',h.hexdigest()==expected)
report={'session_id':sid,'epoch':epoch,'frames':m['frames'],'chunks':m['chunks'],'checks':checks,
        'accelerated_seconds':args.seconds,'wall_seconds':round(time.time()-started,2),
        'source_sha256':h.hexdigest(),'last_pcm_prefix':stereo[:16].hex(),'restart_verified':False,
        'scope':'Accelerated one-hour synthetic PCM writes via real HTTP, not 60 minutes of live API or microphone recording.'}
(OUT/'backend-e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
