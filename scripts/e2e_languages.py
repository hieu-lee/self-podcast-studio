"""HTTP episode language boundary/legacy compatibility + repair word invariants."""
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path
import httpx
from websockets.sync.client import connect
from backend.audio_plan import same_words

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts'/'vietnamese';OUT.mkdir(parents=True,exist_ok=True)
# Isolation failure inventory was written first: canonical spelling should agree,
# but tones, đ, word boundaries, meaningful apostrophes and added negation must not.
cases=[('Toán học mới!',unicodedata.normalize('NFD','toán học mới'),True),
       ('ma','má',False),('má','mà',False),('mã','mạ',False),('đúng','dung',False),
       ('đáp án','dap an',False),("we’ll","well",False),('nowhere','now here',False),
       ('tin chứng minh','không tin chứng minh',False)]
for a,b,expected in cases:assert same_words(a,b)==expected,(a,b,expected)
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=30);c.get('/api/bootstrap')
assert c.post('/api/sessions',json={'topic':'Invalid language fixture','language':'fr'}).status_code==422
default=c.post('/api/sessions',json={'topic':'E2E default English episode'});default.raise_for_status();assert default.json()['language']=='en'
vi=c.post('/api/sessions',json={'topic':'AI khám phá toán học mới hay chỉ kết hợp ý tưởng cũ?','language':'vi'});vi.raise_for_status();assert vi.json()['language']=='vi'
assert c.get('/api/sessions/'+vi.json()['id']).json()['language']=='vi'
legacy=next((s for s in c.get('/api/sessions').json() if s['id']=='68600c81d0294c1192ef5d5e2b56f3e0'),None)
if legacy is None:
 # Simulate legacy metadata only in the new empty synthetic episode owned by this run.
 legacy=default.json()
 with sqlite3.connect(ROOT/'.data'/legacy['id']/'recording.sqlite') as d:d.execute("DELETE FROM meta WHERE key='language'")
 legacy=c.get('/api/sessions/'+legacy['id']).json()
path=ROOT/'.data'/legacy['id'];db=path/'recording.sqlite'
with sqlite3.connect(db) as d:assert not d.execute("SELECT value FROM meta WHERE key='language'").fetchone()
before=hashlib.sha256(db.read_bytes()).hexdigest();media=path/legacy['export_dir']/'episode.mp3' if legacy.get('export_dir') else None;media_hash=hashlib.sha256(media.read_bytes()).hexdigest() if media else None
assert legacy['language']=='en'
cookie='; '.join(k+'='+v for k,v in c.cookies.items())
with connect('ws://127.0.0.1:8765/api/sessions/'+legacy['id']+'/live',origin='http://127.0.0.1:8765',additional_headers={'Cookie':cookie}) as socket:
 while True:
  ready=json.loads(socket.recv(timeout=45))
  if ready['type']=='ready':break
  assert ready['type']!='connection_error',ready
 assert ready['language']=='en'
assert hashlib.sha256(db.read_bytes()).hexdigest()==before,'Legacy DB rewritten'
if media:assert hashlib.sha256(media.read_bytes()).hexdigest()==media_hash,'Legacy media changed'
report={'checks':['invalid language rejected','English remains creation default','Vietnamese episode persisted',
 'canonical Unicode agrees, distinct Vietnamese tones/letters and word tokens never collapse',
 'legacy missing language reads/reconnects English without DB or media rewrite'],
 'unicode_cases':cases,'legacy_ready':ready,'legacy_media_sha256':media_hash,
 'scope':'Actual local HTTP + legacy Realtime setup, no microphone or generated interview.'}
(OUT/'language-boundary-e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(report)
