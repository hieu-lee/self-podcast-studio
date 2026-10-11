"""Owned deterministic orchestration jobs only; never imported by production."""
import asyncio,json,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import e2e_research_server as fixture
from backend import edit,store,video
mode='normal';fixture.guided_jobs=True
@fixture.fixture.post('/guided-mode')
async def set_mode(request:fixture.Request):
 global mode
 mode=(await request.json())['mode'];return {'ok':True}
def render(sid,warnings,quality,polish):
 chosen=mode;time.sleep(3)
 if chosen=='export-fail':raise RuntimeError('Owned export failure')
 out=store.ROOT/sid/('export-'+uuid.uuid4().hex);out.mkdir()
 for name,data in {'edit.json':{'warnings':warnings,'audio_decisions':[{'flag':'Owned ambiguous source preserved'}] if chosen=='flag' else []},'polish.json':{'noise_events':([{'action':'preserve','flag':'Invalid noise classification; source retained'},{'kind':'cough','action':'preserve','flag':'Invalid independent verification'},{'kind':'environment','action':'preserve','flag':'Independent speech check failed; preserve source'},{'kind':'environment','action':'preserve','flag':'Independent audio inspection did not prove speech-free unwanted noise'}] if chosen=='noise-flag' else [{'kind':'breath','action':'preserve','flag':'Natural, overlapping or uncertain event retained'}] if chosen=='natural' else [])},'transcript.json':{'language':store.meta(sid)['language'],'segments':[]}}.items():(out/name).write_text(json.dumps(data))
 (out/'episode.mp3').write_bytes(b'Owned controlled metadata fixture, not playable production media');store.set_meta(sid,'export_dir',out.name);store.set_meta(sid,'export_audio_review','yes' if quality else 'no')
edit.render=render
def build(sid,version,job,out,event):
 out=video.status_path(sid,version,job).parent;chosen=mode
 for i in range(30):
  if event.is_set():raise video.Cancelled()
  time.sleep(.1)
 if chosen=='video-fail':raise RuntimeError('Owned video failure')
 state=video.load(out/'status.json');state.update(state='completed',progress=100,message='Owned controlled job; not real media');video.write(out/'status.json',state);(out/'episode.mp4').write_bytes(b'Owned controlled metadata fixture')
video.build=build
if __name__=='__main__':asyncio.run(fixture.main())
