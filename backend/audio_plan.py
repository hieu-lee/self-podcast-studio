"""Audio-capable diagnosis -> validated interviewer-only edits. No executable model plans."""
import base64
import io
import hashlib
import json
import re
import wave

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from . import store

RATE=24000

class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    item_id: str = Field(max_length=100)
    action: Literal['preserve','repair','move_repair','omit']
    confidence: float = Field(ge=0,le=1)
    complete_heard_question: bool
    natural_overlap: bool
    independent_next_guest: bool
    heard_text: str = Field(max_length=3000)
    evidence: str = Field(max_length=2000)
    move_after_guest_block: int | None = Field(default=None,ge=0)
    prior_guest_answer_complete: bool = False

class Diagnosis(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items: list[Decision] = Field(max_length=100)


def wav_bytes(pcm):
    b=io.BytesIO()
    with wave.open(b,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(RATE);w.writeframes(pcm)
    return b.getvalue()


def text_audio(client,pcm):
    r=client.post('https://api.openai.com/v1/audio/transcriptions',data={'model':'gpt-transcribe'},
        files={'file':('played.wav',wav_bytes(pcm),'audio/wav')})
    r.raise_for_status()
    return r.json()['text'].strip()


def same_words(a,b):
    # Fuzzy similarity can admit a short added "not" and reverse a question.
    # Ignore punctuation/case only; disagreement preserves the actual recording.
    normalize=lambda s: re.findall(r"\w+(?:'\w+)*",s.casefold().replace('’',"'"),flags=re.UNICODE)
    return bool(normalize(a)) and normalize(a)==normalize(b)


def metadata(sid,epochs):
    offsets={e['epoch']:round(e['original_start']*RATE) for e in epochs}
    items={}
    with store.db(sid) as c:
        for row in c.execute('SELECT header FROM chunks ORDER BY epoch,seq'):
            h=json.loads(row[0]);off=offsets[h['epoch']]
            for span in h['spans']:
                item=items.setdefault(span['item'],{'id':span['item'],'spans':[],'generated':0,'done':False,'completed':False,'failed':False,'intentional_interrupt':False})
                item['spans'].append([off+span['start'],off+span['start']+span['frames']])
    for e in store.events(sid):
        if e['type']=='response.output_audio.delta' and e['item_id'] in items:
            items[e['item_id']]['generated']+=e['samples']
        if e['type']=='response.output_audio.done' and e['item_id'] in items:
            items[e['item_id']]['done']=True
        if e['type']=='response.output_audio_transcript.done' and e['item_id'] in items:
            items[e['item_id']]['generated_transcript_hint']=e.get('transcript','')[:3000]
        if e['type']=='playback_interrupt' and e['item'] in items:
            items[e['item']]['intentional_interrupt']=True
        if e['type']=='response.done':
            for output in e['response'].get('output',[]):
                if output['id'] in items:
                    item=items[output['id']]
                    item['failed']=e['response'].get('status') in ('failed','incomplete')
                    item['completed']=e['response'].get('status')=='completed' and output.get('status')=='completed'
    for item in items.values():
        item['spans'].sort();item['start']=item['spans'][0][0];item['end']=item['spans'][-1][1]
        item['played']=sum(b-a for a,b in item['spans'])
        item['full']=item['generated']>0 and item['played']==item['generated'] and item['done'] and item['completed']
        item['gaps']=[[b,a] for (_,b),(a,_) in zip(item['spans'],item['spans'][1:]) if a-b>=RATE*.12]
    return sorted(items.values(),key=lambda item:item['start'])


def plan_audio(sid,guest,ai,epochs,out,client):
    from .edit import activity,union,cut,wav_writer,duration
    items=metadata(sid,epochs);length=duration(guest)
    # Silence-trim unions can merge two different answers: never use their ends
    # as conversational anchors. The audio reviewer must confirm an actual block.
    guest_blocks=activity(guest)
    guest_turns=union(guest_blocks,length)
    raw=[];accepted=[]
    with wave.open(str(guest)) as g,wave.open(str(ai)) as a:
        for window in range(0,int(length)+1,60):
            group=[i for i in items if window<=i['start']/RATE<window+60]
            if not group:continue
            left=max(0,window-8);right=min(length,max(window+68,max(i['end']/RATE+8 for i in group)))
            # Huge/ambiguous AI turns remain untouched rather than unbounded API uploads.
            if right-left>120:
                for item in group:accepted.append({'item_id':item['id'],'action':'preserve','flag':'AI turn exceeds bounded review window'})
                continue
            facts=[]
            blocks=[{'index':index,'start':x,'end':y} for index,(x,y) in enumerate(guest_blocks) if x<right and y>left]
            for item in group:
                overlap=sum(max(0,min(item['end']/RATE,y)-max(item['start']/RATE,x)) for x,y in guest_turns)
                facts.append({'item_id':item['id'],'start':item['start']/RATE,'end':item['end']/RATE,
                    'fully_played_and_done':item['full'],'playback_gaps':[[x/RATE,y/RATE] for x,y in item['gaps']],
                    'guest_overlap_seconds':overlap,'api_failed':item['failed'],'intentional_interrupt':item['intentional_interrupt'],
                    'generated_transcript_hint_NOT_proof_of_heard_words':item.get('generated_transcript_hint')})
            prompt=f'''You are reviewing actual saved podcast AUDIO, not hypothetical text. File 1 is the authoritative GUEST microphone track; file 2 is the authoritative AI INTERVIEWER output track. Same sample clock, time window {left:.3f} to {right:.3f} seconds in the source. Guest speech/meaning must never change. Listen to both and distinguish a short natural backchannel or intentional interruption from an intrusive mistimed full interviewer question while the guest continues a prior answer. Diagnose technical gaps/stutters/cut-off speech from the audio plus these playback facts: {json.dumps(facts)}.
Actual guest acoustic blocks (NOT necessarily complete answers): {json.dumps(blocks)}. For move_repair, return move_after_guest_block (an index from this list) and prior_guest_answer_complete=true ONLY if audio proves that block ends the PRIOR answer, not a phrase pause or the subsequent answer to this question. Select the block where the guest is still speaking when the intrusive question finishes. If the prior answer continues across a later pause, or the boundary is ambiguous, preserve/flag rather than moving past a subsequent answer. Other actions use move_after_guest_block=null and prior_guest_answer_complete=false.
For the natural_overlap field: TRUE means a short intentional natural backchannel/acknowledgment or deliberate natural interruption that should remain. Mere temporal overlap is NOT natural_overlap: a full intrusive question over the continuing previous answer is FALSE. If action/evidence and this classification disagree, preserve and flag ambiguity rather than invent an edit.
Generated transcript hints are provisional and MAY contain unheard tails. Audio is authoritative; these hints NEVER authorize reconstructing an unheard question.
Return ONLY JSON with items, one for every supplied item_id. Each item has item_id, action (preserve|repair|move_repair|omit), confidence 0..1, complete_heard_question boolean, natural_overlap boolean, independent_next_guest boolean, heard_text (ONLY words audible in the SAVED AI track, never an unheard generated tail), evidence (specific acoustic/conversational reason), move_after_guest_block, prior_guest_answer_complete. Preserve clean questions, intentional natural backchannels, and ambiguity. Repair only fully heard complete AI questions with audible technical playback gaps. move_repair only a fully HEARD complete question intruding over a continuing prior guest answer; it will be placed after that answer, preserving every guest sample and shifting later turns. Omit only a clearly technical cut-off fragment whose unheard tail cannot be restored, when following guest speech is an independent clarification rather than an answer dependent on that fragment. Do not fabricate missing questions or guest answers. Confidence below .85 means preserve/flag. No code, commands, guest edits, new words or free time coordinates.'''
            inputs=[{'type':'text','text':prompt}]
            audio_refs=[]
            for label,reader in (('guest',g),('ai',a)):
                payload=wav_bytes(cut(reader,left,right));path=out/f'review-{window}-{label}.wav';path.write_bytes(payload)
                audio_refs.append({'speaker':label,'file':path.name,'sha256':hashlib.sha256(payload).hexdigest()})
                inputs.append({'type':'input_audio','input_audio':{'data':base64.b64encode(payload).decode(),'format':'wav'}})
            r=client.post('https://api.openai.com/v1/chat/completions',json={'model':'gpt-audio-1.5','modalities':['text'],
                'temperature':0,'store':False,'max_tokens':4000,'messages':[{'role':'user','content':inputs}]})
            r.raise_for_status();response=r.json();content=response['choices'][0]['message']['content']
            raw.append({'window':[left,right],'audio_inputs':audio_refs,'guest_acoustic_blocks':blocks,'prompt':prompt,
                        'facts':facts,'model':'gpt-audio-1.5','response':response})
            try:
                parsed=Diagnosis.model_validate_json(content.strip().removeprefix('```json').removesuffix('```').strip())
                ids=[d.item_id for d in parsed.items]
                if set(ids)!={i['id'] for i in group} or len(ids)!=len(set(ids)):raise ValueError('Unknown/missing/duplicate audio item')
            except ValueError:
                for item in group:accepted.append({'item_id':item['id'],'action':'preserve','flag':'Invalid audio model plan; source preserved'})
                continue
            for d in parsed.items:
                item=next(i for i in group if i['id']==d.item_id)
                entry=d.model_dump();entry['requested_action']=d.action
                target=None;reason=None
                if d.action!='preserve':
                    if d.confidence<.85 or d.natural_overlap:reason='Low confidence or natural overlap'
                    elif d.action in ('repair','move_repair') and (not item['full'] or not d.complete_heard_question):reason='Not a verified fully heard complete AI question'
                    elif d.action=='omit' and (item['full'] or not item['failed'] or item['intentional_interrupt'] or not d.independent_next_guest):reason='No unambiguous failed/incomplete independent fragment evidence'
                    elif d.action=='repair' and (not item['gaps'] or any(x<item['end']/RATE and y>item['start']/RATE for x,y in guest_turns)):reason='Repair requires actual starvation and an isolated AI interval'
                    elif d.action=='move_repair':
                        begin=item['start']/RATE;finish=item['end']/RATE
                        prior=any(x+.5<begin<y for x,y in guest_blocks)
                        overlap=sum(max(0,min(finish,y)-max(begin,x)) for x,y in guest_blocks)
                        ending=next((index for index,(x,y) in enumerate(guest_blocks) if x<finish<y),None)
                        if not prior or overlap<=1:reason='No substantial overlap with a continuing prior guest answer'
                        elif ending is None or d.move_after_guest_block!=ending or not d.prior_guest_answer_complete:
                            reason='No audio-validated completed prior answer at the actual acoustic boundary'
                        elif guest_blocks[ending][1]>=right-.5:
                            reason='Prior answer boundary lies outside fully reviewed audio context'
                        else:
                            target=min(length,guest_blocks[ending][1]+.25)
                            if ending+1<len(guest_blocks) and guest_blocks[ending+1][0]<=target:
                                reason='Movement anchor would cross the next guest block'
                if reason:entry.update(action='preserve',flag=reason)
                if entry['action'] in ('repair','move_repair'):
                    if item['end']-item['start']>120*RATE:
                        entry.update(action='preserve',flag='Repair turn too long')
                    else:
                        played=cut(a,item['start']/RATE,item['end']/RATE)
                        played_path=out/('played-'+str(len(accepted))+'.wav')
                        played_path.write_bytes(wav_bytes(played))
                        text=text_audio(client,played)
                        entry.update(played_verification={'model':'gpt-transcribe','file':played_path.name,
                            'sha256':hashlib.sha256(played_path.read_bytes()).hexdigest(),'text':text})
                        if not text or not same_words(text,d.heard_text):
                            entry.update(action='preserve',flag='Independent audio transcription disagrees with diagnosis; no new words allowed')
                        else:
                            speech=client.post('https://api.openai.com/v1/audio/speech',json={'model':'gpt-4o-mini-tts','voice':'marin',
                                'input':text,'response_format':'pcm','instructions':'Natural warm interviewer. Speak exactly these words; no added introduction or content.'})
                            speech.raise_for_status();pcm=speech.content
                            verified=text_audio(client,pcm) if len(pcm)%2==0 else ''
                            entry['replacement_verification']={'model':'gpt-transcribe','text':verified,
                                'pcm_sha256':hashlib.sha256(pcm).hexdigest()}
                            if not verified or not same_words(text,verified):
                                entry.update(action='preserve',flag='Regenerated audio failed independent word verification')
                            else:
                                path=out/('repair-'+str(len(accepted))+'.wav')
                                with wav_writer(path) as w:w.writeframes(bytes(4800)+pcm+bytes(4800))
                                entry.update(repair_text=text,replacement=path.name,
                                    insert_sample=round(target*RATE) if target is not None else item['start'],
                                    source_start=item['start'],source_end=item['end'])
                if entry['action']=='omit':entry.update(source_start=item['start'],source_end=item['end'])
                accepted.append(entry)
    # A movement may not jump across a later preserved substantive interviewer turn.
    actions={d['item_id']:d for d in accepted}
    by_id={i['id']:i for i in items}
    for d in accepted:
        if d['action']=='move_repair':
            original=by_id[d['item_id']]
            if any(original['start']<i['start']<d['insert_sample'] and actions[i['id']]['action']=='preserve'
                   and not actions[i['id']].get('natural_overlap',False) for i in items):
                d.update(action='preserve',flag='Movement would reorder a later substantive interviewer turn')
            elif any(i['id']!=d['item_id'] and any(x<d['insert_sample']<y for x,y in i['spans']) for i in items):
                d.update(action='preserve',flag='Movement would split another interviewer turn')
    (out/'audio-diagnosis.json').write_text(json.dumps({'audio_model':'gpt-audio-1.5','windows':raw,'decisions':accepted},indent=2))
    return accepted,items


def apply_plan(guest,ai,decisions,items,out):
    """Insert new AI durations while every guest sample stays in chronological order."""
    from .edit import wav_writer
    clear=[];insert={}
    by_id={i['id']:i for i in items}
    for d in sorted(decisions,key=lambda d:by_id[d['item_id']]['start']):
        if d['action']=='preserve':continue
        item=by_id[d['item_id']]
        clear.extend(item['spans'])
        if d['action'] in ('repair','move_repair'):insert.setdefault(d['insert_sample'],[]).append(d)
    with wave.open(str(guest)) as g,wave.open(str(ai)) as a,wav_writer(out/'planned-guest.wav') as go,wav_writer(out/'planned-ai.wav') as ao:
        total=g.getnframes();cursor=0;mapping=[]
        bounds=sorted({0,total,*insert.keys()})
        def replacements(pos):
            nonlocal cursor
            for d in insert.get(pos,[]):
                with wave.open(str(out/d['replacement'])) as w:pcm=w.readframes(w.getnframes())
                go.writeframesraw(bytes(len(pcm)));ao.writeframesraw(pcm)
                mapping.append({'kind':'AI replacement','item_id':d['item_id'],'final_start':cursor,'frames':len(pcm)//2});cursor+=len(pcm)//2
        for start,end in zip(bounds,bounds[1:]):
            replacements(start)
            # Fixed-size streaming blocks; no hour-long in-memory audio buffers.
            for pos in range(start,end,RATE*30):
                stop=min(end,pos+RATE*30);g.setpos(pos);a.setpos(pos)
                gp=g.readframes(stop-pos);ap=np.frombuffer(a.readframes(stop-pos),dtype='<i2').copy()
                for x,y in clear:
                    left=max(pos,x);right=min(stop,y)
                    if right>left:ap[left-pos:right-pos]=0
                go.writeframesraw(gp);ao.writeframesraw(ap.tobytes())
            mapping.append({'kind':'source','source_start':start,'source_end':end,'final_start':cursor,'frames':end-start});cursor+=end-start
        replacements(total)
    (out/'audio-edit-plan.json').write_text(json.dumps({'decisions':decisions,'sample_map':mapping,'guest_policy':'No guest synthesis, deletion, word edits or reordered samples; only inserted AI time.'},indent=2))
    return out/'planned-guest.wav',out/'planned-ai.wav',mapping
