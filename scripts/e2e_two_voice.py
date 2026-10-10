"""Ground-truth two-voice fault simulation through the actual HTTP post-production path."""
import argparse
import unicodedata
import difflib
import hashlib
import json
import os
import re
import sqlite3
import struct
import subprocess
import time
import wave
from pathlib import Path

import httpx
import numpy as np
from websockets.sync.client import connect

parser=argparse.ArgumentParser();parser.add_argument('--language',choices=['en','vi'],default='en');language=parser.parse_args().language
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts'/('two-voice-vi' if language=='vi' else 'two-voice');OUT.mkdir(parents=True,exist_ok=True)
RATE=24000
texts={
 'q1':('marin','What would convince you that AI has discovered genuinely new mathematics?'),
 'g1':('cedar','For me, a new theorem needs a checkable proof. Recombination can still be creative. I care about a useful connection that a mathematician can explain.'),
 'ack':('marin','Mm-hm.'),
 'q2':('marin','What useful connection would you most like an AI to find?'),
 'g2':('cedar','A bridge between geometry and number theory would be exciting. But I still want the proof to make sense, not just the right answer.'),
 'q3':('marin','Who should check an AI proof before it is published?'),
 'g4':('cedar','Independent mathematicians should check it. A machine verifier can help, but the assumptions also need to be made clear.'),
 'cut':('marin','Would you trust a proof that no human can understand?'),
 'g3':('cedar','Let me clarify the point about that bridge. Understanding matters because it tells us where the result can be used.'),
 'close':('marin','That is a thoughtful distinction. Thank you for the conversation.')}
if language=='vi':
 texts={
 'q1':('marin','Điều gì khiến bạn tin rằng AI đã khám phá toán học thực sự mới?'),
 'g1':('cedar','Theo tôi, một định lý mới cần có chứng minh kiểm tra được. Kết hợp ý tưởng cũ vẫn có thể sáng tạo. Tôi quan tâm đến một kết nối hữu ích mà một nhà toán học có thể giải thích rõ ràng.'),
 'ack':('marin','Ừm.'),
 'q2':('marin','Bạn muốn AI tìm ra kết nối hữu ích nào nhất?'),
 'g2':('cedar','Một cầu nối giữa hình học và lý thuyết số sẽ rất thú vị. Nhưng tôi vẫn muốn hiểu chứng minh, chứ không chỉ biết đáp án đúng.'),
 'q3':('marin','Ai nên kiểm tra chứng minh của AI trước khi công bố?'),
 'g4':('cedar','Các nhà toán học độc lập nên kiểm tra. Machine verifier có thể giúp, nhưng các giả thiết cũng cần được làm rõ.'),
 'cut':('marin','Bạn có tin một chứng minh mà không ai có thể hiểu không?'),
 'g3':('cedar','Để tôi làm rõ ý về cầu nối đó. Hiểu biết rất quan trọng vì nó cho chúng ta biết kết quả có thể được dùng ở đâu.'),
 'close':('marin','Đó là một phân biệt sâu sắc. Cảm ơn bạn đã trò chuyện.')}
api=httpx.Client(headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},timeout=180)
clips={}
for key,(voice,text) in texts.items():
 p=OUT/(key+'.pcm')
 if not p.exists():
  r=api.post('https://api.openai.com/v1/audio/speech',json={'model':'gpt-4o-mini-tts','voice':voice,'input':text,'response_format':'pcm',
     'instructions':('Natural Vietnamese conversation with clear tones. ' if language=='vi' else '')+'Natural conversational pace. Say exactly this text without translation or additional words.'});r.raise_for_status();p.write_bytes(r.content)
 clips[key]=np.frombuffer(p.read_bytes(),dtype='<i2')
# Fixed timing policy applied to cached voices: no cut, speed change or mistiming of guest speech.
q1=RATE;g1=q1+len(clips['q1'])+RATE
ack=g1+RATE;q2=g1+3*RATE;split=min(int(1.3*RATE),len(clips['q2'])//2);stall=RATE//2
if language=='vi':q2=g1+len(clips['g1'])-len(clips['q2'])-stall-int(1.5*RATE)
q2end=q2+len(clips['q2'])+stall
assert ack+len(clips['ack'])<q2,'Backchannel must finish before AI question'
assert q2end<g1+len(clips['g1']),'Question must finish while guest continues prior answer'
g2=g1+len(clips['g1'])+RATE
q3=g2+len(clips['g2'])+RATE;g4=q3+len(clips['q3'])+int(.4*RATE)+RATE
cut=g4+len(clips['g4'])+RATE;cutlen=int(1.1*RATE)
g3=cut+cutlen+RATE;closing=g3+len(clips['g3'])+RATE
length=closing+len(clips['close'])+RATE
pcm=np.zeros((length,2),dtype='<i2');items=[];guests=[]
for key,start in [('g1',g1),('g2',g2),('g4',g4),('g3',g3)]:
 pcm[start:start+len(clips[key]),0]=clips[key];guests.append({'id':key,'start':start,'frames':len(clips[key]),'text':texts[key][1],'sha256':hashlib.sha256(clips[key].tobytes()).hexdigest()})
for key,start in [('q1',q1),('ack',ack),('q2',q2),('q3',q3),('cut',cut),('close',closing)]:
 spans=[]
 if key in ('q2','q3'):
  gap_frames=stall if key=='q2' else int(.4*RATE);point=split if key=='q2' else len(clips[key])//2
  pcm[start:start+point,1]=clips[key][:point];pcm[start+point+gap_frames:start+len(clips[key])+gap_frames,1]=clips[key][point:]
  spans=[(start,start+point,0),(start+point+gap_frames,start+len(clips[key])+gap_frames,point)]
 elif key=='cut':
  pcm[start:start+cutlen,1]=clips[key][:cutlen];spans=[(start,start+cutlen,0)]
 else:
  pcm[start:start+len(clips[key]),1]=clips[key];spans=[(start,start+len(clips[key]),0)]
 items.append({'id':key,'spans':spans,'generated':cutlen if key=='cut' else len(clips[key]),
   'known_full_question_samples':len(clips[key]),'done':True,'failed':key=='cut','text_generated':texts[key][1]})
faults={'q2':['intrusive full question over continuing guest answer','500ms playback starvation mid-question'],
        'q3':['isolated fully heard question with 400ms playback starvation'],
        'cut':['failed transport, partial question with unplayed tail'],'ack':['intentional natural backchannel — preserve overlap']}
ground={'language':language,'voices':{'interviewer':'marin','guest':'cedar (synthetic, not cloning Hieu)'},'guests':guests,'items':items,'faults':faults,
 'guest_policy':'Every guest clip remains intact, naturally paced and ordered. Questions q1 and q2 were fully heard; cut question tail was never heard.',
 'raw_stereo_sha256':hashlib.sha256(pcm.tobytes()).hexdigest()}
(OUT/'ground-truth.json').write_text(json.dumps(ground,indent=2))
for speaker,index in [('guest',0),('ai',1)]:
 with wave.open(str(OUT/f'damaged-{speaker}.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(pcm[:,index].tobytes())
subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/'damaged-guest.wav'),'-i',str(OUT/'damaged-ai.wav'),'-filter_complex','amix=inputs=2:normalize=0','-c:a','pcm_f32le',str(OUT/'damaged-mix.wav')],check=True)
client=httpx.Client(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=60);client.get('/api/bootstrap')
r=client.post('/api/sessions',json={'topic':'E2E two-voice '+language+' fault diagnosis/repair — synthetic speakers only','language':language});r.raise_for_status();sid=r.json()['id'];epoch='5'*32
client.post('/api/sessions/'+sid+'/epochs',json={'id':epoch,'wall_ms':time.time()*1000-length/24}).raise_for_status()
for seq,start in enumerate(range(0,length,RATE)):
 end=min(length,start+RATE);spans=[]
 for item in items:
  for a,b,offset in item['spans']:
   x=max(a,start);y=min(b,end)
   if y>x:spans.append({'item':item['id'],'start':x,'frames':y-x,'offset':offset+x-a})
 spans.sort(key=lambda s:s['start'])
 gap=q2+split
 h=json.dumps({'epoch':epoch,'seq':seq,'start':start,'spans':spans,'underruns':[gap] if start<=gap<end else []}).encode()
 client.post('/api/sessions/'+sid+'/chunks',content=struct.pack('<I',len(h))+h+pcm[start:end].tobytes()).raise_for_status()
client.post('/api/sessions/'+sid+'/seal',json={'epoch':epoch,'frames':length}).raise_for_status()
# Simulated API timing/terminal events, same schema as production Realtime event persistence.
with sqlite3.connect(ROOT/'.data'/sid/'recording.sqlite') as db:
 for item in items:
  ev=[{'type':'response.output_audio.delta','item_id':item['id'],'samples':item['generated']},
      {'type':'response.output_audio_transcript.done','item_id':item['id'],'transcript':item['text_generated']}]
  if item['done']:ev.append({'type':'response.output_audio.done','item_id':item['id']})
  ev.append({'type':'response.done','response':{'status':'failed' if item['failed'] else 'completed',
    'output':[{'id':item['id'],'status':'incomplete' if item['failed'] else 'completed'}]}})
  for e in ev:db.execute('INSERT INTO events(at,body) VALUES (?,?)',(time.time(),json.dumps(e)))
client.post('/api/sessions/'+sid+'/export',json={'quality_edit':True}).raise_for_status()
for _ in range(900):
 state=client.get('/api/sessions/'+sid).json()
 if not state['exporting']:break
 time.sleep(.5)
assert state.get('export_dir'),state
export=ROOT/'.data'/sid/state['export_dir'];plan=json.loads((export/'audio-edit-plan.json').read_text())
(OUT/'session.json').write_text(json.dumps({'session_id':sid,'export_dir':state['export_dir']},indent=2))
print('Actual app export:',export)
print(json.dumps(plan['decisions'],indent=2))
# Independent source/sample and acoustic/transcription validation (not model self-grading).
decisions={d['item_id']:d for d in plan['decisions']}
if language=='vi':
 assert decisions['q2']['action']=='move_repair' or (decisions['q2']['action']=='preserve' and decisions['q2'].get('flag')),decisions['q2']
else:assert decisions['q2']['action']=='move_repair',decisions['q2']
assert decisions['q3']['action']=='repair',decisions['q3']
if language=='vi':
 assert decisions['cut']['action']=='omit' or (decisions['cut']['action']=='preserve' and decisions['cut'].get('flag')),decisions['cut']
else:assert decisions['cut']['action']=='omit',decisions['cut']
assert decisions['ack']['action']=='preserve',decisions['ack']
with wave.open(str(export/'planned-guest.wav')) as w:pg=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
with wave.open(str(export/'planned-ai.wav')) as w:pa=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
mapping=plan['sample_map'];positions=[]
all_original=np.concatenate([pg[m['final_start']:m['final_start']+m['frames']] for m in mapping if m['kind']=='source'])
assert np.array_equal(all_original,pcm[:,0]),'Any original guest samples lost or reordered'
for guest in guests:
 cover=[]
 for entry in mapping:
  if entry['kind']!='source':continue
  a=max(guest['start'],entry['source_start']);b=min(guest['start']+guest['frames'],entry['source_end'])
  if b>a:
   pos=entry['final_start']+a-entry['source_start'];cover.append(pg[pos:pos+b-a]);positions.append((guest['id'],pos,pos+b-a))
 assert np.array_equal(np.concatenate(cover),clips[guest['id']]),'Guest waveform/words altered: '+guest['id']
if decisions['q2']['action']=='move_repair':
 replacement=next(m for m in mapping if m.get('item_id')=='q2')
 assert replacement['final_start']>=max(b for key,a,b in positions if key=='g1'),'Moved interviewer still overlaps guest1'
 assert replacement['final_start']+replacement['frames']<=min(a for key,a,b in positions if key=='g2'),'New interviewer overlaps guest2'
else:
 assert not any(m.get('item_id')=='q2' for m in mapping),'Rejected question movement still inserted'
 for m in mapping:
  if m['kind']=='source':
   a=max(q2,m['source_start']);b=min(q2end,m['source_end'])
   if b>a:
    pos=m['final_start']+a-m['source_start']
    assert np.array_equal(pa[pos:pos+b-a],pcm[a:b,1]),'Flagged intrusive question changed'
isolated=next(m for m in mapping if m.get('item_id')=='q3')
assert isolated['final_start']>=max(b for key,a,b in positions if key=='g2')
assert isolated['final_start']+isolated['frames']<=min(a for key,a,b in positions if key=='g4'),'Isolated repair overlaps next guest'
# Natural backchannel remains an exact original segment in original overlap relation.
ackmap=next(m for m in mapping if m['kind']=='source' and m['source_start']<=ack and m['source_end']>=ack+len(clips['ack']))
ackpos=ackmap['final_start']+ack-ackmap['source_start'];assert np.array_equal(pa[ackpos:ackpos+len(clips['ack'])],clips['ack'])
assert np.any(np.abs(pg[ackpos:ackpos+len(clips['ack'])].astype(int))>100),'Natural overlap was removed'
for m in mapping:
 if m['kind']=='source':
  a=max(cut,m['source_start']);b=min(cut+cutlen,m['source_end'])
  if b>a:
   pos=m['final_start']+a-m['source_start']
   if decisions['cut']['action']=='omit':assert not np.any(pa[pos:pos+b-a]),'Broken cut question retained'
   else:assert np.array_equal(pa[pos:pos+b-a],pcm[a:b,1]),'Ambiguous failed fragment altered or unheard tail restored'
tokens=lambda text:re.findall(r"\w+(?:'\w+)*",unicodedata.normalize('NFC',text).casefold().replace('’',"'"))
if decisions['q2']['action']=='move_repair':assert tokens(decisions['q2']['repair_text'])==tokens(texts['q2'][1]),'Regenerated unspoken or differently accented question words'
assert tokens(decisions['q3']['repair_text'])==tokens(texts['q3'][1]),'Isolated repair changed heard words'
# Re-transcribe final guest to check words after actual mastering, independently of diagnosis.
with open(export/'final-guest.wav','rb') as f:
 tr=api.post('https://api.openai.com/v1/audio/transcriptions',data={'model':'gpt-transcribe','languages[]':[language,'en'] if language=='vi' else ['en']},files={'file':('guest.wav',f,'audio/wav')})
tr.raise_for_status();heard=tr.json()['text'];expected=' '.join(texts[k][1] for k in ('g1','g2','g4','g3'))
word_score=difflib.SequenceMatcher(None,tokens(heard),tokens(expected)).ratio();assert word_score>.96,(word_score,heard)
(OUT/'independent-guest-transcription.json').write_text(json.dumps({'model':'gpt-transcribe','response':tr.json(),
 'expected':expected,'similarity':word_score,'final_guest_sha256':hashlib.sha256((export/'final-guest.wav').read_bytes()).hexdigest()},indent=2))
# Actual relay setup (no microphone or generated response): compare the exact
# seeded context digest against completed turns, excluding the fully played
# FAILED fragment even though both audio and transcript "done" were received.
expected_context='\n'.join('[Interrupted or unverified interviewer audio omitted]' if i['failed'] else 'Interviewer: '+i['text_generated'] for i in items)
cookie='; '.join(k+'='+v for k,v in client.cookies.items())
with connect('ws://127.0.0.1:8765/api/sessions/'+sid+'/live',origin='http://127.0.0.1:8765',additional_headers={'Cookie':cookie},open_timeout=30) as socket:
 while True:
  ready=json.loads(socket.recv(timeout=45))
  if ready['type']=='ready':break
  assert ready['type']!='connection_error',ready
 assert ready['context_sha256']==hashlib.sha256(expected_context.encode()).hexdigest(),ready
 assert ready['context_chars']==len(expected_context)
 assert ready['language']==language
completion_check={'expected_sha256':hashlib.sha256(expected_context.encode()).hexdigest(),'actual_ready':ready,
 'checks':['actual Realtime relay receives only completed heard turns','fully played failed partial with audio/transcript done omitted','no microphone or AI response generation during context probe']}
(OUT/'reconnect-completion-e2e.json').write_text(json.dumps(completion_check,indent=2))
record={'language':language,'session_id':sid,'export_dir':state['export_dir'],'checks':['audio-capable saved-track diagnosis (not text-only)',('mistimed fully heard AI question relocated after intact prior guest answer' if decisions['q2']['action']=='move_repair' else 'ambiguous/misclassified intrusive question preserved exactly and flagged by local safety validator'),('500ms AI starvation repaired with verified heard words' if decisions['q2']['action']=='move_repair' else 'unsafe AI movement/repair rejected; no source question words invented'),('failed unheard-tail fragment omitted, not reconstructed' if decisions['cut']['action']=='omit' else 'ambiguous failed fragment preserved/flagged exactly, never reconstructed'),'natural backchannel overlap preserved exactly','all guest clips exactly sample-preserved and ordered in planned timeline','no new repaired-question overlap with next guest','independent final guest transcription compared with accented ground-truth tokens (not guaranteed verbatim)'],
 'guest_word_similarity':word_score,'isolated_repair':'400ms starvation corrected without deleting any original guest samples or overlapping next answer','raw_seconds':length/RATE,'polished_seconds':json.loads((export/'edit.json').read_text())['final_duration'],
 'listening':'Objective saved-audio model analysis + independent waveform/metadata/ground-truth transcription checks. Human subjective listening approval not claimed.'}
(OUT/'comparison.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
for name in ['episode.mp3','transcript.txt','transcript.json','audio-diagnosis.json','audio-edit-plan.json','edit.json']:
 (OUT/name).write_bytes((export/name).read_bytes())
