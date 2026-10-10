"""Real HTTP/model/DSP/Codex/browser/video E2E. Inventory precedes feature code."""
import argparse,base64,hashlib,json,os,struct,subprocess,time,unicodedata,wave
from pathlib import Path
import httpx
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--language',choices=['en','vi'],default='vi');p.add_argument('--reuse',action='store_true');p.add_argument('--video-only',action='store_true',help='Reuse already polished synthetic export; rerun real visual production only');args=p.parse_args()
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts'/'production'/args.language;OUT.mkdir(parents=True,exist_ok=True);RATE=24000
c=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=60);c.get('/api/bootstrap').raise_for_status()
api=httpx.Client(headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},timeout=180)
texts={
'en': [('ai','Let us compare fictional AI tools Atlas, Nova and Cygnus. These are illustrative names, not real benchmark results.'),
 ('guest','I put Atlas in tier B. I put Nova in tier A. Atlas is useful, but its explanations need work.'),
 ('ai','Does your next example change the ranking?'),
 ('guest','Yes. After that example, I move Atlas from tier B to tier A. For Cygnus, I am unsure. Leave Cygnus unranked.'),
 ('guest','Ha ha, that is only my opinion, not a measurement. Keep the names and my uncertainty. That is the end of our discussion.')],
'vi':[('ai','Chúng ta so sánh các công cụ AI giả định Atlas, Nova và Cygnus. Đây là tên minh họa, không phải kết quả đo thực tế.'),
 ('guest','Tôi đặt Atlas ở hạng B. Tôi đặt Nova ở hạng A. Atlas hữu ích, nhưng cách giải thích còn cần cải thiện.'),
 ('ai','Ví dụ tiếp theo có khiến bạn thay đổi thứ hạng không?'),
 ('guest','Có. Sau ví dụ đó, tôi đổi Atlas từ hạng B sang hạng A. Với Cygnus, tôi chưa chắc. Để Cygnus ở nhóm chưa xếp hạng.'),
 ('guest','Ha ha, đó chỉ là ý kiến của tôi, không phải phép đo. Giữ nguyên tên và sự chưa chắc chắn. Cuộc thảo luận kết thúc ở đây.')]}
def voice(text,index):
 path=OUT/f'voice-{index}-{hashlib.sha256(text.encode()).hexdigest()[:12]}.wav'
 if not path.exists():
  r=api.post('https://api.openai.com/v1/audio/speech',json={'model':'gpt-4o-mini-tts','voice':'marin' if texts[args.language][index][0]=='ai' else 'cedar','input':text,'response_format':'wav','instructions':'Natural '+('Vietnamese with full tones' if args.language=='vi' else 'English')+'. Speak exactly these words, clear names and tier letters. Preserve Ha ha laughter.'});r.raise_for_status();path.write_bytes(r.content)
 with wave.open(str(path)) as w:assert w.getframerate()==RATE;return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
if args.reuse:
 sid=json.loads((OUT/'fixture.json').read_text())['session_id']
else:
 pieces=[];turns=[];cursor=0
 for i,(speaker,text) in enumerate(texts[args.language]):
  x=voice(text,i);x*=10**([-24,-35,-15,-22,-27][i]/20)/(np.sqrt(np.mean(x*x))+1e-12);x=np.clip(x,-.9,.9)
  pcm=np.zeros((len(x),2));pcm[:,0 if speaker=='guest' else 1]=x
  turns.append({'speaker':speaker,'start':cursor/RATE,'end':(cursor+len(x))/RATE,'text':text,'target_rms_db':[-24,-35,-15,-22,-27][i]});pieces.append(pcm);cursor+=len(x)
  gap=np.zeros((RATE*3,2));pieces.append(gap);cursor+=len(gap)
 stereo=np.concatenate(pieces);noise=[]
 rng=np.random.default_rng(31415)
 # Environmental ringing/clatter separated from words; rough cough-like DSP burst
 # is honestly synthetic, never presented as a human cough recording.
 start=round((turns[0]['end']+.5)*RATE);n=round(.65*RATE);t=np.arange(n)/RATE
 bell=.16*np.sin(2*np.pi*1700*t)*np.exp(-t*5);stereo[start:start+n,0]+=bell
 noise.append({'kind':'environment','start':start/RATE,'end':(start+n)/RATE,'speaker':'guest','isolated':True})
 start=round((turns[1]['end']+.3)*RATE)
 cough=OUT.parent/'short-coughs.wav'
 if not cough.exists():
  url='https://upload.wikimedia.org/wikipedia/commons/a/a6/Short_coughs.ogg'
  r=httpx.get(url,headers={'User-Agent':'SelfPodcast/0.1 (local audio test; source attribution retained)'},timeout=60);r.raise_for_status();ogg=OUT.parent/'short-coughs.ogg';ogg.write_bytes(r.content)
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(ogg),'-ac','1','-ar',str(RATE),str(cough)],check=True)
  (OUT.parent/'cough-source.json').write_text(json.dumps({'url':'https://commons.wikimedia.org/wiki/File:Short_coughs.ogg','original':url,'author':'stilgar','license':'Public domain as declared on source page','sha256':hashlib.sha256(r.content).hexdigest()},indent=2))
 with wave.open(str(cough)) as w:burst=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
 n=len(burst);stereo[start:start+n,0]+=.5*burst/max(.001,float(np.max(np.abs(burst))))
 noise.append({'kind':'public-domain stock coughs by stilgar','start':start/RATE,'end':(start+n)/RATE,'speaker':'guest','isolated':True})
 start=round((turns[3]['start']+1)*RATE);n=round(.5*RATE);stereo[start:start+n,0]+=.015*rng.normal(size=n)
 noise.append({'kind':'overlapping noise and meaningful guest speech','start':start/RATE,'end':(start+n)/RATE,'speaker':'guest','isolated':False})
 stereo=np.clip(stereo,-.98,.98);pcm=(stereo*32767).astype('<i2')
 with wave.open(str(OUT/'before.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(pcm.tobytes())
 r=c.post('/api/sessions',json={'topic':'Illustrative AI tier ranking — production E2E, synthetic voices only','language':args.language});r.raise_for_status();sid=r.json()['id'];eid='9'*32
 c.post(f'/api/sessions/{sid}/epochs',json={'id':eid,'wall_ms':time.time()*1000-len(pcm)/24}).raise_for_status()
 for seq,start in enumerate(range(0,len(pcm),RATE)):
  piece=pcm[start:start+RATE];header=json.dumps({'epoch':eid,'seq':seq,'start':start,'spans':[],'underruns':[]}).encode();c.post(f'/api/sessions/{sid}/chunks',content=struct.pack('<I',len(header))+header+piece.tobytes()).raise_for_status()
 c.post(f'/api/sessions/{sid}/seal',json={'epoch':eid,'frames':len(pcm)}).raise_for_status()
 (OUT/'fixture.json').write_text(json.dumps({'session_id':sid,'turns':turns,'noise':noise,'original_sha256':hashlib.sha256(pcm.tobytes()).hexdigest(),'scope':'Distinct synthetic speech voices, DSP beep and public-domain stock cough source (stilgar/Wikimedia), no user microphone'},ensure_ascii=False,indent=2))
def wait(field,done,timeout=1800):
 end=time.time()+timeout
 while time.time()<end:
  m=c.get(f'/api/sessions/{sid}').json()
  if done(m):return m
  time.sleep(1)
 raise RuntimeError('Timed out waiting for '+field)
m=c.get(f'/api/sessions/{sid}').json();previous=m.get('export_dir')
if not args.video_only:
 c.post(f'/api/sessions/{sid}/export',json={'quality_edit':True,'acknowledge_gaps':True}).raise_for_status();m=wait('polish',lambda m:not m['exporting']);assert m.get('export_dir') and m['export_dir']!=previous,m
else:assert args.reuse and previous,'--video-only requires --reuse and a verified existing polished synthetic export'
version=m['export_dir'];folder=Path(os.environ.get('SELF_PODCAST_DATA',ROOT/'.data'))/sid/version
polish=json.loads((folder/'polish.json').read_text());assert polish['version']==1 and polish['speaker_levels'] and polish['noise_events']
assert any(e['action']=='attenuate' for e in polish['noise_events']),'No confidently unwanted event actually attenuated'
assert all(not e['contains_speech'] and e['confidence']>=.95 and e['verification']['safe'] for e in polish['noise_events'] if e['action']=='attenuate')
edit=json.loads((folder/'edit.json').read_text());assert -17<float(edit['ffmpeg_loudness']['input_i'])<-15 and float(edit['ffmpeg_loudness']['input_tp'])<0
for speaker in ('guest','ai'):
 metrics=polish['speaker_levels'][speaker];assert metrics['after_spread_db']<metrics['before_spread_db'] or metrics['before_spread_db']<3,metrics
trans=json.loads((folder/'transcript.json').read_text());text=unicodedata.normalize('NFC',' '.join(s['text'] for s in trans['segments'])).casefold()
for name in ('atlas','nova','cygnus'):assert name in text
r=c.post(f'/api/sessions/{sid}/video',json={'version':version});r.raise_for_status();job=r.json()['job_id']
assert c.post(f'/api/sessions/{sid}/video',json={'version':version}).status_code==409
m=wait('video',lambda m:m.get('video',{}).get('state') in ('completed','failed','cancelled'),3600);v=m['video'];assert v['state']=='completed',v
path=folder/job;story=json.loads((path/'storyboard.json').read_text());events=json.loads((path/'capture-events.json').read_text())
assert any(s['kind']=='tier_list' for s in story['scenes']),'Content-driven tier list was not produced'
rank_events=[e for e in events if e['type']=='drag'];assert len(rank_events)>=3,events
atlas=[e for e in rank_events if 'atlas' in e['label'].casefold()];assert [e['tier'] for e in atlas]==['B','A'],atlas
assert any('nova' in e['label'].casefold() and e['tier']=='A' for e in rank_events)
assert all('cygnus' not in e['label'].casefold() or e['tier']=='unranked' for e in rank_events),'Uncertain item ranked'
assert all(abs(e['scheduled_time']-e['actual_time'])<.5 for e in events if e['type']=='drag'),events
cues=json.loads((path/'captions.json').read_text())['cues']
for speaker in ['Hieu','AI interviewer']:
 native=' '.join(s['text'] for s in trans['segments'] if s['speaker']==speaker).split()
 caption=' '.join(x['text'].removeprefix(speaker+': ') for x in cues if x['text'].startswith(speaker+': ')).split()
 assert native==caption,('Native caption words lost',speaker)
assert all(0<=x['start']<x['end']<=edit['final_duration']+.05 for x in cues)
validation=json.loads((path/'validation.json').read_text());assert validation['full_decode'] and validation['soundtrack_stream_copy'] and validation['ending_intact']
assert (path/'episode.mp4').stat().st_size>10000 and list(path.glob('scene-*.html')) and list(path.glob('frame-*.png'))
assert c.post(f'/api/sessions/{sid}/video/approve',json={'version':version,'job_id':job}).status_code==200
report={'session_id':sid,'export':version,'job_id':job,'checks':['real audio-aware noise detection/independent safe attenuation','adaptive both-speaker levels and final true peak','native meaningful names retained','actual Codex content-driven interactive HTML','captured real tier drags B/A and B→A revision/uncertain neutral','full original final soundtrack/ending/decode','version bound immutable video and approval'],'polish':polish,'video_validation':validation,'events':events}
(OUT/'e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('polish','events')},indent=2))
