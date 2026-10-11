"""Real source/job E2E; failure inventory precedes acquisition implementation."""
import argparse,hashlib,json,os,struct,subprocess,time,wave,uuid
from pathlib import Path
import httpx,numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/source-acquisition';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--setup',action='store_true');p.add_argument('--safety',action='store_true');p.add_argument('--local-directory',action='store_true');p.add_argument('--job',action='store_true');p.add_argument('--retry',action='store_true');a=p.parse_args()
project=OUT/'comparison-demo';project.mkdir(exist_ok=True);public=project/'public';public.mkdir(exist_ok=True)
if a.setup:
 (public/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><style>body{background:#101e32;color:white;font:32px Arial;padding:40px}h1{color:#b9e786}.grid{display:flex;gap:30px}.card{border:3px solid #9cb1d4;padding:30px}small{font-size:24px}</style><h1>Local comparison demo</h1><p>Illustrative fictional tools · Not benchmark results</p><div class="grid"><div class="card">Atlas<br>Initial: B<br>Revised: A</div><div class="card">Nova<br>A</div><div class="card">Cygnus<br>Uncertain / unranked</div></div><p>Existing project captured read-only.</p><small>No accounts, private profile or microphone.</small>''')
 (project/'.env').write_text('TEST_ONLY_SECRET_MUST_NOT_APPEAR=fixture-private-value')
 (public/'leak.env').write_text('fixture-private-value');(public/'linked.html').unlink(missing_ok=True);(public/'linked.html').symlink_to(project/'.env')
 catalog=OUT/'catalog.json';catalog.write_text(json.dumps({'projects':[{'id':'comparison-demo','label':'Existing local comparison demo (controlled fixture)','root':str(project),'public_dir':'public'}]},indent=2));catalog.chmod(0o600);print('Start studio with SELF_PODCAST_SOURCE_CATALOG='+str(catalog));raise SystemExit()
if a.local_directory:
 fixture=OUT/'static-directory';root=fixture/'public';docs=root/'docs';docs.mkdir(parents=True,exist_ok=True)
 destination='<!doctype html><meta charset="utf-8"><title>Safe directory destination</title><style>body{background:#08784b;color:white;font:40px Arial;padding:40px}</style><h1>Safe static directory</h1><p>Directory index with public language query.</p>'
 (docs/'index.html').write_text(destination);checks=[]
 for target in ['/docs/','/docs/?lang=en']:
  (root/'index.html').write_text('<!doctype html><script>location.replace('+json.dumps(target)+')</script>')
  capture=fixture/('plain' if '?' not in target else 'query');capture.mkdir(exist_ok=True);spec=capture/'selection.json';spec.write_text(json.dumps({'sources':[{'id':'s0','type':'local','project_id':'directory-fixture','root':str(root.resolve()),'path':'/'}]}))
  r=subprocess.run(['node',str(ROOT/'scripts/capture_sources.mjs'),str(capture),str(spec)],capture_output=True,text=True,timeout=35);assert r.returncode==0,(target,r.stderr)
  source=json.loads((capture/'source-provenance.json').read_text())['sources'][0];assert source['title']=='Safe directory destination',source;assert source['served_files']=={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'index.html',docs/'index.html']},source;assert not source['blocked_requests'],source
  png=capture/source['file'];assert png.read_bytes().startswith(b'\x89PNG\r\n\x1a\n');assert hashlib.sha256(png.read_bytes()).hexdigest()==source['sha256'];checks.append({'target':target,'source':source,'screenshot':str(png)})
 (fixture/'e2e.json').write_text(json.dumps({'checks':checks,'scope':'Actual confined Chromium follows local directory navigation through owned read-only static server; no model, accounts or microphone.'},indent=2));print('Local static directory E2E passed')
if a.safety:
 spec=OUT/'unsafe.json'
 for url in ['http://127.0.0.1:8765/','https://127.0.0.1/','https://127.0.0.1.nip.io/','https://[::1]/','https://user:pass@example.com/','https://example.com/?token=test-only-not-sent','https://example.com:8765/','file:///etc/passwd','https://httpbin.org/redirect-to?url=http%3A%2F%2F127.0.0.1%3A8765%2Fapi%2Fbootstrap']:
  spec.write_text(json.dumps({'sources':[{'id':'s0','type':'public','url':url}]}));r=subprocess.run(['node',str(ROOT/'scripts/capture_sources.mjs'),str(OUT),str(spec)],capture_output=True,text=True,timeout=35);assert r.returncode!=0,url
  if 'redirect-to' in url:assert 'Public destination/redirect refused' in r.stderr,r.stderr
  if 'nip.io' in url:assert 'Non-public DNS refused' in r.stderr,r.stderr
 # Local chosen public root may not serve private/symlink/encoded traversal/POST.
 from backend.sources import selected_sources
 try:selected_sources({'public_urls':[],'project_ids':['../../private']});raise AssertionError('Unknown project accepted')
 except ValueError:pass
 for pathname in ['/.env','/leak.env','/linked.html','/%2e%2e/.env']:
  spec.write_text(json.dumps({'sources':[{'id':'s0','type':'local','project_id':'comparison-demo','root':str(public),'path':pathname}]}));r=subprocess.run(['node',str(ROOT/'scripts/capture_sources.mjs'),str(OUT),str(spec)],capture_output=True,text=True,timeout=35);assert r.returncode!=0,pathname
 (OUT/'safety-e2e.json').write_text(json.dumps({'checks':['public private/literal/nonHTTPS/credentials/port refused','real public redirect toward studio refused','unknown project id refused','local traversal/symlink/secret files refused'],'scope':'Actual source capture CLI/HTTP route boundaries, controlled existing fixture'},indent=2));print('Source safety E2E passed')
if a.job:
 original={str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file() and not p.is_symlink()}
 c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=90);c.get('/api/bootstrap').raise_for_status();api=httpx.Client(headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},timeout=180)
 if not a.retry:
  texts=[('ai','We are illustrating two visual sources: the public Example Domain page and our existing local comparison demo. Example Domain is documentation, not an AI benchmark.'),('guest','Show the Example Domain page now. Next, show our local comparison demo. These are fictional tools. I put Atlas in tier B and Nova in tier A. Later I move Atlas to tier A. I am unsure about Cygnus, so keep it unranked. That is the complete ending.')]
  tracks=[];turns=[];cursor=0
  for i,(speaker,text) in enumerate(texts):
   f=OUT/f'voice-{i}.wav'
   if not f.exists():
    r=api.post('https://api.openai.com/v1/audio/speech',json={'model':'gpt-4o-mini-tts','voice':'marin' if speaker=='ai' else 'cedar','input':text,'response_format':'wav'});r.raise_for_status();f.write_bytes(r.content)
   with wave.open(str(f)) as w:x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').reshape(-1);assert w.getframerate()==24000
   pcm=np.zeros((len(x)+48000,2),dtype='<i2');pcm[:len(x),0 if speaker=='guest' else 1]=x;tracks.append(pcm);turns.append({'speaker':speaker,'text':text,'start':cursor/24000,'end':(cursor+len(x))/24000});cursor+=len(pcm)
  pcm=np.concatenate(tracks);r=c.post('/api/sessions',json={'topic':'Visual source E2E: public Example Domain documentation and existing local comparison demo; fictional Atlas/Nova/Cygnus rankings','language':'en'});r.raise_for_status();sid=r.json()['id'];epoch=uuid.uuid4().hex
  c.post(f'/api/sessions/{sid}/epochs',json={'id':epoch,'wall_ms':time.time()*1000}).raise_for_status()
  for seq,begin in enumerate(range(0,len(pcm),24000)):
   header=json.dumps({'epoch':epoch,'seq':seq,'start':begin,'spans':[],'underruns':[]}).encode();c.post(f'/api/sessions/{sid}/chunks',content=struct.pack('<I',len(header))+header+pcm[begin:begin+24000].tobytes()).raise_for_status()
  c.post(f'/api/sessions/{sid}/seal',json={'epoch':epoch,'frames':len(pcm)}).raise_for_status();c.post(f'/api/sessions/{sid}/export',json={'quality_edit':False,'polish_audio':True,'acknowledge_gaps':True}).raise_for_status()
  for _ in range(1200):
   d=c.get(f'/api/sessions/{sid}').json()
   if not d['exporting']:break
   time.sleep(.5)
  assert d.get('polished_audio'),d;version=d['export_dir']
 else:
  previous=json.loads((OUT/'attempt.json').read_text());sid=previous['session_id'];version=previous['export']
 selection={'public_urls':['https://example.com/'],'project_ids':['comparison-demo']}
 r=c.post(f'/api/sessions/{sid}/video',json={'version':version,'sources':selection});r.raise_for_status();job=r.json()['job_id'];(OUT/'attempt.json').write_text(json.dumps({'session_id':sid,'export':version,'job_id':job}))
 for _ in range(2400):
  v=c.get(f'/api/sessions/{sid}').json()['video']
  if v['state'] not in ['queued','running','cancelling']:break
  time.sleep(.5)
 assert v['state']=='completed',v
 data=Path(os.environ['SELF_PODCAST_DATA'])/sid/version;folder=data/job;prov=json.loads((folder/'source-provenance.json').read_text());story=json.loads((folder/'storyboard.json').read_text());events=json.loads((folder/'capture-events.json').read_text());validation=json.loads((folder/'validation.json').read_text())
 assert {s['type'] for s in prov['sources']}=={'public','local'};assert len(story['source_uses'])==2
 ranks=[e for e in events if e['type']=='drag'];assert any('atlas' in e['item'].lower() and e['observed_rank']=='B' for e in ranks);assert any('atlas' in e['item'].lower() and e['observed_rank']=='A' for e in ranks);assert any('nova' in e['item'].lower() and e['observed_rank']=='A' for e in ranks);assert not any('cygnus' in e['item'].lower() for e in ranks)
 assert validation['ending_intact'] and validation['decoded_similarity']>.995
 for use in story['source_uses']:
  assert any(e.get('type')=='source' and e.get('item')==use['id'] for e in events)
  subprocess.run(['ffmpeg','-v','error','-y','-ss',str(use['start']+1),'-i',str(folder/'episode.mp4'),'-frames:v','1',str(OUT/('encoded-'+use['id']+'.png'))],check=True)
 native=json.loads((data/'transcript.json').read_text());cues=json.loads((folder/'captions.json').read_text())['cues'];
 for speaker in ['Hieu','AI interviewer']:
  assert ' '.join(s['text'] for s in native['segments'] if s['speaker']==speaker).split()==' '.join(x['text'].removeprefix(speaker+': ') for x in cues if x['text'].startswith(speaker+': ')).split()
 before={str(p.relative_to(project)):hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob('*') if p.is_file() and not p.is_symlink()};assert before==original;assert 'fixture-private-value' not in json.dumps(prov)
 report={'session_id':sid,'export':version,'job_id':job,'selection':selection,'sources':prov,'source_uses':story['source_uses'],'events':events,'validation':validation,'project_hashes':before,'scope':('Reused immutable polished synthetic export; fresh actual Codex/source capture/render job.' if a.retry else 'New actual synthetic voices/full export/Codex/source capture/render job.')+' Public live Example Domain plus existing controlled static project; not a human recording or arbitrary app runtime.'};(OUT/'e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ['events','validation','project_hashes']},indent=2))
