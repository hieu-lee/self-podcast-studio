"""Catalog/credential HTTP and real redirect/interaction boundary E2E (written before fixes)."""
import hashlib,json,subprocess
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/source-acquisition/boundaries';OUT.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=30);c.get('/api/bootstrap').raise_for_status()
p=json.loads((ROOT/'.artifacts/source-acquisition/attempt.json').read_text());endpoint=f"/api/sessions/{p['session_id']}/video";catalog=ROOT/'.artifacts/source-acquisition/catalog.json';original=catalog.read_bytes();failures=[]
try:
 for value in [{'projects':None},{'projects':[1]},{'projects':[{'id':123,'root':None,'public_dir':'public','label':'fixture'}]},{'projects':[{'id':'fixture','root':None,'public_dir':'public','label':'fixture'}]},[]]:
  catalog.write_text(json.dumps(value));r=c.get('/api/video-sources');assert r.status_code==409,(value,r.status_code,r.text);assert 'configuration' in r.text and 'Traceback' not in r.text
  r=c.post(endpoint,json={'version':p['export'],'sources':{'project_ids':['comparison-demo']}});assert r.status_code==409 and 'configuration' in r.text,(value,r.status_code,r.text);failures.append(value)
finally:catalog.write_bytes(original)
assert catalog.read_bytes()==original
# Invalid-version sentinel prevents job creation even if the source guard regresses.
# Credential rejection must happen BEFORE version validation; all markers synthetic.
unsafe=['https://example.com/?sig=test-only-secret','https://example.com/?credential=test-only-secret','https://example.com/?code=test-only-secret','https://example.com/?key=test-only-secret','https://example.com/?unknown=test-only-secret','https://example.com/#access_token=test-only-secret','https://example.com/?url=https%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret']
unsafe += ['https://example.com/?url=+https%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret','https://example.com/?url=%2F%2Fuser%3Atest-only-secret%40example.com%2F','https://example.com/?url=https%253A%252F%252Fexample.com%252F%253Fsig%253Dtest-only-secret','https://example.com/?url=%2Fhtml%3Fsig%3Dtest-only-secret','https://example.com/?q=+https%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret','https://example.com/?url=ambiguous-test-only-value','https://example.com/?url=%2F%5Cuser%3Atest-only-secret%40example.com%2F']
unsafe += ['https://example.com/?q=%2Fhtml%3Fsig%3Dtest-only-secret','https://example.com/?query=%2Fhtml%3Ftoken%3Dtest-only-secret','https://example.com/?q=https%25252525253A%25252525252F%25252525252Fexample.com%25252525252F%25252525253Fsig%25252525253Dtest-only-secret','https://example.com/?q=%5C%5Cuser%3Atest-only-secret%40example.com%2F']
unsafe += ['https://example.com/?q=%EF%BB%BFhttps%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret','https://example.com/?query=%EF%BB%BF%2Fhtml%3Fsig%3Dtest-only-secret','https://example.com/?q=%E2%80%8Bhttps%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret','https://example.com/?q=%C2%85https%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret','https://example.com/?q=%EFhttps%3A%2F%2Fexample.com%2F%3Fsig%3Dtest-only-secret']
unsafe += ['https://example.com/?q=html%3Fsig%3Dtest-only-secret','https://example.com/?query=%3Ftoken%3Dtest-only-secret','https://example.com/?q=%23access_token%3Dtest-only-secret','https://example.com/?q=topic;sig=test-only-secret']
unsafe += [f'https://example.com/?q={scheme}%3A%2F%2Fuser%3Atest-only-secret%40example.com%2F' for scheme in ['ftp','sftp','wss','custom%2Bsource']]
for url in unsafe:
 r=c.post(endpoint,json={'version':'export-'+'0'*32,'sources':{'public_urls':[url]}});assert r.status_code==409 and 'Audio version changed' not in r.text,(url,r.status_code,r.text)
 spec=OUT/'reject.json';spec.write_text(json.dumps({'sources':[{'id':'s0','type':'public','url':url}]}));r=subprocess.run(['node',str(ROOT/'scripts/capture_sources.mjs'),str(OUT),str(spec)],capture_output=True,text=True,timeout=35);assert r.returncode and 'Public destination/redirect refused' in r.stderr,(url,r.stderr)
# Printable native Unicode search text stays supported at both boundaries.
safe_query='https://httpbin.org/html?q=Gi%C3%A1+tr%E1%BB%8B+gi%C3%A1o+d%E1%BB%A5c';r=c.post(endpoint,json={'version':'export-'+'0'*32,'sources':{'public_urls':[safe_query]}});assert r.status_code==409 and 'Audio version changed' in r.text,r.text
spec=OUT/'printable-query.json';spec.write_text(json.dumps({'sources':[{'id':'s0','type':'public','url':safe_query}]}));subprocess.run(['node',str(ROOT/'scripts/capture_sources.mjs'),str(OUT),str(spec)],check=True,timeout=35);(OUT/'printable-query-source.png').write_bytes((OUT/'source-s0.png').read_bytes())
# Actual public redirect; its browser URL (and relative URL resolution) must be final.
url='https://httpbin.org/redirect-to?url=%2Fhtml';spec=OUT/'redirect.json';spec.write_text(json.dumps({'sources':[{'id':'s0','type':'public','url':url}]}));subprocess.run(['node',str(ROOT/'scripts/capture_sources.mjs'),str(OUT),str(spec)],check=True,timeout=35)
source=json.loads((OUT/'source-provenance.json').read_text())['sources'][0];assert source['selected_url']==url and source['url']=='https://httpbin.org/html',source
(OUT/'redirect-source.png').write_bytes((OUT/source['file']).read_bytes());assert hashlib.sha256((OUT/'redirect-source.png').read_bytes()).hexdigest()==source['sha256']
# Real source pixels and native drag at start-.01; no generated producer/API/mic.
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=white:s=1280x720','-frames:v','1',str(OUT/'source-s0.png')],check=True)
def pixel_at(file,x,y):
 return tuple(subprocess.check_output(['ffmpeg','-v','error','-i',str(file),'-vf',f'format=rgb24,crop=1:1:{x}:{y}','-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']))
html='''<!doctype html><meta charset="utf-8"><style>body{background:#08784b;color:white;font:40px Arial;margin:0}.zone{position:absolute;top:200px;width:300px;height:250px;border:4px solid white}#u{left:100px}#a{left:700px}.card{background:#13528a;padding:30px}</style><h1>Boundary native drag evidence</h1><div id="u" class="zone" data-tier="unranked"><div class="card" data-item="atlas" draggable="true">Atlas</div></div><div id="a" class="zone" data-tier="A">Tier A</div><script>document.querySelector('[data-item]').ondragstart=e=>e.dataTransfer.setData('text/plain','atlas');for(const z of document.querySelectorAll('[data-tier]')){z.ondragover=e=>e.preventDefault();z.ondrop=e=>{e.preventDefault();z.append(document.querySelector('[data-item]'));}}</script>'''
(OUT/'scene-0.html').write_text(html);(OUT/'captions.json').write_text('{"cues":[]}');(OUT/'storyboard.json').write_text(json.dumps({'scenes':[{'start':0,'end':5,'assets':[],'actions':[{'type':'drag','time':.99,'item':'atlas','tier':'A','evidence':'boundary fixture'}]}],'source_uses':[{'id':'s0','start':1,'end':4,'label':'Boundary fixture','evidence':'real source fixture'}]}))
subprocess.run(['node',str(ROOT/'scripts/capture_video.mjs'),str(OUT)],check=True,timeout=35)
events=json.loads((OUT/'capture-events.json').read_text());assert any(e['type']=='drag' and e['observed_rank']=='A' for e in events);assert any(e['type']=='source' for e in events)
checks={}
for phase in ['before','during','after']:
 pixel=pixel_at(OUT/f'frame-0-0-{phase}.png',60,160);assert pixel==(8,120,75),(phase,pixel);checks[phase]=pixel
clip=json.loads((OUT/'capture-clips.json').read_text())[0];subprocess.run(['ffmpeg','-v','error','-y','-ss',str(clip['offset']+3),'-i',str(OUT/clip['file']),'-frames:v','1',str(OUT/'resumed-source.png')],check=True);pixel=pixel_at(OUT/'resumed-source.png',100,150);assert min(pixel)>235,pixel
report={'catalog_bad_shapes_sanitized':failures,'catalog_sha256_unchanged':hashlib.sha256(original).hexdigest(),'credential_urls_rejected':unsafe,'printable_vietnamese_query_accepted':safe_query,'real_redirect_source':source,'interaction_pixels':checks,'events':events,'resumed_source_pixel':pixel,'scope':'Actual HTTP errors/CLI rejection/live public redirect and native Chromium drag capture; synthetic secrets/fixture only'};(OUT/'e2e.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
