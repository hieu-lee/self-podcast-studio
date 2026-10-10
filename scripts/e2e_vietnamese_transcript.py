"""Native saved-audio captions: HTTP immutable re-export, not mocked STT."""
import hashlib
import json
import shutil
import time
import unicodedata
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts'/'vietnamese'
sid=json.loads((OUT/'browser-e2e.json').read_text())['session_id']
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=60)
c.get('/api/bootstrap').raise_for_status()
m=c.get('/api/sessions/'+sid).json();assert m['language']=='vi' and not m['connected'] and not m['exporting']
root=ROOT/'.data'/sid;old=root/m['export_dir'];assert not json.loads((old/'edit.json').read_text())['audio_review']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old_hashes={p.name:sha(p) for p in old.iterdir() if p.is_file()}
source_hashes={p.name:sha(p) for p in (root/'sources').glob('original-*.wav')}
c.post('/api/sessions/'+sid+'/export',json={'acknowledge_gaps':True,'quality_edit':False}).raise_for_status()
for _ in range(480):
 new=c.get('/api/sessions/'+sid).json()
 if not new['exporting']:
  assert new.get('export_dir')!=m['export_dir'] and not new.get('export_error'),new
  break
 time.sleep(.5)
else:raise RuntimeError('Export timeout')
current=root/new['export_dir'];edit=json.loads((current/'edit.json').read_text());t=json.loads((current/'transcript.json').read_text())
assert edit['tools']['transcription']=='gpt-transcribe',edit['tools']
assert 'acoustic crop' in t['alignment'].lower() and 'not word alignment' in t['alignment'].lower(),t['alignment']
assert t['language']=='vi'
assert all(0<=s['start']<s['end']<=edit['final_duration']+.001 and s['text'].strip() for s in t['segments'])
assert {s['speaker'] for s in t['segments']}=={'Hieu','AI interviewer'}
ai=unicodedata.normalize('NFC',' '.join(s['text'] for s in t['segments'] if s['speaker']=='AI interviewer')).casefold()
# Known audible phrases from the independent no-language-hint AI recording audit,
# not injected prompts/expected text sent to the caption model.
for phrase in ('đáng tin cậy','gợi ra','hình học','lý thuyết số'):assert phrase in ai,(phrase,ai)
assert all(sha(old/name)==h for name,h in old_hashes.items()),'Immutable earlier export changed'
assert all(sha(root/'sources'/name)==h for name,h in source_hashes.items()),'Source audio changed'
for name in ('edited-guest.wav','final-guest.wav','final-ai.wav','episode.mp3'):
 assert sha(current/name)==old_hashes[name],('Caption refinement changed audio',name)
assert c.post('/api/sessions/'+sid+'/approve',json={'version':m['export_dir']}).status_code==409
report={'session_id':sid,'previous_export':m['export_dir'],'current_export':new['export_dir'],
 'checks':['native saved-audio caption model','honest acoustic-crop estimates bounded to duration','both original speaker languages retained',
 'independently observed complete Vietnamese question phrases recovered','original and final guest/interviewer audio unchanged',
 'earlier immutable export unchanged','stale approval rejected'],
 'alignment':t['alignment'],'source_sha256':source_hashes,
 'scope':'Actual synthetic browser recording, real HTTP/STT/FFmpeg. Recognition remains estimated; no perfect captions, invented partial tail, human pronunciation or word alignment claim.'}
(OUT/'transcript-e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for name in ('episode.mp3','transcript.json','transcript.txt','edit.json'):shutil.copy2(current/name,OUT/name)
print(json.dumps(report,ensure_ascii=False,indent=2))
