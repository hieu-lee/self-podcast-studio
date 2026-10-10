import asyncio
import base64
import contextlib
import hashlib
import json
import os
import secrets
import struct
from pathlib import Path
from typing import Literal

import websockets
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import store

os.umask(0o077)
app = FastAPI()
COOKIE = secrets.token_urlsafe(32)
ORIGIN = 'http://127.0.0.1:8765'
MODEL = os.environ.get('SELF_PODCAST_MODEL','gpt-realtime-2.1')
active = set()
jobs = {}


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    if request.headers.get('host') != '127.0.0.1:8765':
        return JSONResponse({'detail':'Use the loopback app URL'},status_code=403)
    origin=request.headers.get('origin')
    if origin and origin != ORIGIN:
        return JSONResponse({'detail':'Cross-origin access denied'},status_code=403)
    if request.url.path.startswith('/api/') and request.url.path != '/api/bootstrap':
        if not secrets.compare_digest(request.cookies.get('local',''), COOKIE):
            return JSONResponse({'detail':'Open the app first'},status_code=403)
        if request.method != 'GET' and request.headers.get('x-self-podcast') != '1':
            return JSONResponse({'detail':'Missing local request header'},status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://127.0.0.1:8765; media-src 'self' blob:; worker-src 'self'; frame-ancestors 'none'"
    return response


@app.get('/api/bootstrap')
async def bootstrap():
    r=JSONResponse({'key_ready':bool(os.environ.get('OPENAI_API_KEY')),'model':MODEL})
    r.set_cookie('local',COOKIE,httponly=True,samesite='strict')
    return r


def checked(sid):
    try:
        return store.meta(sid)
    except (ValueError,FileNotFoundError):
        raise HTTPException(404,'Session not found')


def idle(sid):
    checked(sid)
    if sid in active or sid in jobs:
        raise HTTPException(409,'Session is recording or exporting')


class Topic(BaseModel):
    topic: str = Field(min_length=3,max_length=1000)
    language: Literal['en','vi'] = 'en'


@app.get('/api/sessions')
async def sessions():
    return sorted([store.meta(p.name) for p in store.ROOT.iterdir() if (p/'recording.sqlite').exists()],key=lambda m:float(m['created']),reverse=True)


@app.post('/api/sessions')
async def create(data: Topic):
    return store.meta(store.create(data.topic.strip(),data.language))


@app.get('/api/sessions/{sid}')
async def session(sid: str):
    m=checked(sid)
    # Polling the UI must not repeatedly ship an hour of private Realtime events.
    m['events']=store.events(sid,('recovery_warning',))
    m['exporting']=sid in jobs
    m['connected']=sid in active
    return m


class Epoch(BaseModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    wall_ms: float = Field(ge=0,le=1e14)


@app.post('/api/sessions/{sid}/epochs')
async def epoch(sid: str,data: Epoch):
    idle(sid)
    if any(e['expected'] is None for e in store.meta(sid)['epochs']):
        raise HTTPException(409,'Recover the previous unsealed capture first')
    store.add_epoch(sid,data.id,data.wall_ms)
    return {'ok':True}


@app.post('/api/sessions/{sid}/chunks')
async def chunks(sid: str,request: Request):
    checked(sid)
    if sid in jobs:
        raise HTTPException(409,'Export in progress')
    # Bound streaming before allocation, not only after request.body().
    raw=bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw)>160000:
            raise HTTPException(413,'Chunk too large')
    try:
        n=struct.unpack('<I',raw[:4])[0]
        if n>60000:
            raise ValueError('Header too large')
        h=json.loads(raw[4:4+n])
        pcm=bytes(raw[4+n:])
        frames=len(pcm)//4
        if not 0<frames<=24000 or len(pcm)%4:
            raise ValueError('Expected up to one second of stereo PCM16 at 24 kHz')
        if set(h)!= {'epoch','seq','start','spans','underruns'}:
            raise ValueError('Invalid chunk header')
        if not isinstance(h['epoch'],str) or len(h['epoch'])!=32 or any(c not in '0123456789abcdef' for c in h['epoch']):
            raise ValueError('Invalid epoch')
        if type(h['seq']) is not int or type(h['start']) is not int or not 0<=h['seq']<=21600 or h['start']!=h['seq']*24000:
            raise ValueError('Invalid sequence/sample position')
        if len(h['spans'])>300 or len(h['underruns'])>300:
            raise ValueError('Excessive timing records')
        for s in h['spans']:
            if set(s)!= {'item','start','frames','offset'} or not isinstance(s['item'],str) or len(s['item'])>100:
                raise ValueError('Invalid playback span')
            if any(type(s[k]) is not int for k in ('start','frames','offset')) or not h['start']<=s['start']<h['start']+frames or not 0<s['frames']<=h['start']+frames-s['start'] or s['offset']<0:
                raise ValueError('Invalid playback timing')
        for u in h['underruns']:
            if type(u) is not int or not h['start']<=u<h['start']+frames:
                raise ValueError('Invalid underrun timing')
        await asyncio.to_thread(store.chunk,sid,h,pcm)
    except (ValueError,KeyError,TypeError,struct.error,json.JSONDecodeError) as e:
        raise HTTPException(409,str(e))
    return {'ok':True,'seq':h['seq']}


class End(BaseModel):
    epoch: str
    frames: int = Field(ge=0,le=24000*21600)


@app.post('/api/sessions/{sid}/seal')
async def seal(sid: str,data: End):
    idle(sid)
    try:
        await asyncio.to_thread(store.seal,sid,data.epoch,data.frames)
    except ValueError as e:
        raise HTTPException(409,str(e))
    store.set_meta(sid,'state','saved')
    return checked(sid)


@app.post('/api/sessions/{sid}/recover')
async def recover(sid: str):
    idle(sid)
    # Explicit acceptance of a lost tail; never claim it is restored.
    with store.db(sid) as c:
        for e in c.execute('SELECT id FROM epochs WHERE expected IS NULL').fetchall():
            rows=c.execute('SELECT start,frames FROM chunks WHERE epoch=? ORDER BY seq',(e['id'],)).fetchall()
            cursor=0
            for r in rows:
                if r['start']!=cursor:
                    raise HTTPException(409,'Noncontiguous chunks: upload pending browser data first')
                cursor+=r['frames']
            c.execute('UPDATE epochs SET expected=? WHERE id=?',(cursor,e['id']))
    store.event(sid,{'type':'recovery_warning','text':'Unsealed capture recovered only through committed audio; unsaved tail/sleep gaps cannot be restored.'})
    store.set_meta(sid,'state','saved')
    return checked(sid)


@app.websocket('/api/sessions/{sid}/live')
async def live(ws: WebSocket,sid: str):
    if ws.headers.get('origin')!=ORIGIN or ws.headers.get('host')!='127.0.0.1:8765' or not secrets.compare_digest(ws.cookies.get('local',''),COOKIE):
        await ws.close(code=1008); return
    try:
        m=checked(sid)
    except HTTPException:
        await ws.close(code=1008); return
    if sid in active or sid in jobs or not os.environ.get('OPENAI_API_KEY'):
        await ws.close(code=1008); return
    active.add(sid)
    await ws.accept()
    children=[]
    try:
        context=await asyncio.to_thread(store.heard_context,sid)
        language=m['language']
        language_rule=('Phỏng vấn hoàn toàn bằng tiếng Việt tự nhiên, rõ dấu và thanh điệu. Hỏi và hỏi tiếp bằng tiếng Việt, kể cả khi chủ đề viết bằng tiếng Anh. Giữ nguyên tên riêng và thuật ngữ tiếng Anh khi cần. Không dịch lời khách sang tiếng Anh, không đổi ngôn ngữ theo chủ đề hay ngữ cảnh cũ.'
            if language=='vi' else 'Interview in natural English. Keep original names and technical terms.')
        instructions=f'''{language_rule}
You are an engaging, warm podcast interviewer; Hieu is the guest. Your voice is AI-generated. Topic: {m['topic']}.
Ask exactly one brief open question at a time. Listen to the whole answer. Ask responsive follow-ups about specific ideas, examples, disagreements and uncertainty. Never answer for Hieu or pretend to be him. Don't lecture, invent research claims, or repeat a prepared script. Aim for a thoughtful 30-60 minute discussion, not a timed monologue. Allow thinking pauses. If Hieu asks to finish, give a short genuine closing.
This is a fresh API connection. Earlier conversation is partial TEXT context, not restored audio. Only these verified complete heard turns and guest transcripts are retained (older context may be omitted):\n{context}'''
        async with websockets.connect('wss://api.openai.com/v1/realtime?model='+MODEL,
             additional_headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},max_size=2**22,open_timeout=20) as upstream:
            await upstream.send(json.dumps({'type':'session.update','session':{
                'type':'realtime','instructions':instructions,'output_modalities':['audio'],
                'max_output_tokens':800,
                'audio':{'input':{'format':{'type':'audio/pcm','rate':24000},
                    'transcription':{'model':'gpt-4o-transcribe','language':language,
                        'prompt':f'{store.LANGUAGES[language]} podcast conversation. Transcribe original spoken words including mixed English names/terms; never translate.'},
                    'turn_detection':{'type':'semantic_vad','eagerness':'low','create_response':True,'interrupt_response':True}},
                    'output':{'format':{'type':'audio/pcm','rate':24000},'voice':'marin'}}}}))
            async def receive():
                async for raw in upstream:
                    e=json.loads(raw)
                    t=e['type']
                    if t=='session.updated':
                        await ws.send_json({'type':'ready','context_chars':len(context),
                            'context_sha256':hashlib.sha256(context.encode()).hexdigest(),'model':MODEL,'language':language})
                    if t.startswith('response.') or t.startswith('input_audio_buffer.') or 'transcription' in t or t=='error':
                        saved=dict(e)
                        if t=='response.output_audio.delta':
                            saved.pop('delta',None)
                            saved['samples']=len(base64.b64decode(e['delta']))//2
                        await asyncio.to_thread(store.event,sid,saved)
                        await ws.send_json(e)
            async def send():
                while True:
                    raw=await ws.receive()
                    if raw['type']=='websocket.disconnect':
                        return
                    if raw.get('bytes') is not None:
                        pcm=raw['bytes']
                        if len(pcm)>9600 or len(pcm)%2:
                            raise ValueError('Invalid live audio frame')
                        await upstream.send(json.dumps({'type':'input_audio_buffer.append','audio':base64.b64encode(pcm).decode()}))
                    else:
                        e=json.loads(raw['text'])
                        if e['type']=='begin':
                            await upstream.send(json.dumps({'type':'response.create','response':{'instructions':instructions+('\nChào ngắn gọn và đặt một câu hỏi mở bằng tiếng Việt.' if language=='vi' else '\nStart with a brief welcome and one opening question.')}}))
                        elif e['type']=='continue':
                            await upstream.send(json.dumps({'type':'response.create','response':{'instructions':instructions+('\nXác nhận kết nối lại ngắn gọn bằng tiếng Việt; hỏi Hieu muốn tiếp tục ở đâu. Không bịa nội dung bị mất.' if language=='vi' else '\nBriefly acknowledge the reconnection; ask Hieu where to pick up. Do not invent what was lost.')}}))
                        elif e['type']=='interrupt':
                            await upstream.send(json.dumps({'type':'response.cancel'}))
                        elif e['type']=='truncate':
                            await upstream.send(json.dumps({'type':'conversation.item.truncate','item_id':e['item'],
                                'content_index':0,'audio_end_ms':max(0,min(int(e['played_ms']),600000))}))
                            await asyncio.to_thread(store.event,sid,{'type':'playback_interrupt','item':e['item'],'played_ms':e['played_ms']})
            children=[asyncio.create_task(receive()),asyncio.create_task(send())]
            done,_=await asyncio.wait(children,return_when=asyncio.FIRST_COMPLETED,timeout=55*60)
            for task in done:
                task.result()
            if not done:
                await ws.send_json({'type':'renew','text':'55-minute API session boundary. Local recording continues; reconnect to renew context.'})
    except (WebSocketDisconnect,websockets.ConnectionClosed):
        pass
    except Exception:
        with contextlib.suppress(Exception):
            await ws.send_json({'type':'connection_error','text':'Voice connection failed. Local recording is preserved; reconnect or stop.'})
    finally:
        for task in children:
            task.cancel()
        await asyncio.gather(*children,return_exceptions=True)
        active.discard(sid)
        with contextlib.suppress(Exception):
            await ws.close()


class Export(BaseModel):
    acknowledge_gaps: bool = False
    quality_edit: bool = True


@app.post('/api/sessions/{sid}/export')
async def export(sid: str,data: Export):
    idle(sid)
    try:
        warnings=store.coverage(sid)
        if any(e['type']=='recovery_warning' for e in store.events(sid)):
            warnings.append('An abrupt capture recovery may have lost an unsaved tail. Missing guest audio cannot be restored.')
    except ValueError as e:
        raise HTTPException(409,str(e))
    if warnings and not data.acknowledge_gaps:
        raise HTTPException(409,'Acknowledge known recording gaps before export: '+' '.join(warnings))
    from .edit import render
    async def work():
        try:
            store.set_meta(sid,'export_status','Rendering / transcribing actual saved audio…')
            await asyncio.to_thread(render,sid,warnings,data.quality_edit)
            store.set_meta(sid,'export_status','Ready to listen — not yet approved')
        except Exception as e:
            # Save type, not raw API request/header diagnostics.
            store.set_meta(sid,'export_status','Export failed ('+type(e).__name__+'). Originals are safe; retry.')
        finally:
            jobs.pop(sid,None)
    jobs[sid]=asyncio.create_task(work())
    return {'ok':True}


class Approval(BaseModel):
    version: str = Field(pattern=r'^export-[a-f0-9]{32}$')


@app.post('/api/sessions/{sid}/approve')
async def approve(sid: str,data: Approval):
    idle(sid)
    if store.meta(sid).get('export_dir')!=data.version:
        raise HTTPException(409,'Export version changed; listen to the current episode before approving')
    if not (store.ROOT/sid/data.version/'episode.mp3').exists():
        raise HTTPException(409,'No export to listen to')
    store.set_meta(sid,'export_status','Listening review confirmed by user')
    return {'ok':True}


@app.get('/api/sessions/{sid}/files/{name}')
async def file(sid: str,name: str,version: str | None=Query(default=None,pattern=r'^export-[a-f0-9]{32}$')):
    checked(sid)
    if name not in {'episode.mp3','transcript.json','transcript.txt','edit.json','original-guest.wav','original-ai.wav','audio-diagnosis.json','audio-edit-plan.json'}:
        raise HTTPException(404,'Unknown artifact')
    root=store.ROOT/sid/('sources' if name.startswith('original') else version or store.meta(sid).get('export_dir','export'))
    path=root/name
    if not path.exists():
        raise HTTPException(404,'Artifact not ready')
    return FileResponse(path,filename=name)


DIST=Path(__file__).resolve().parent.parent/'frontend'/'dist'
if DIST.exists():
    app.mount('/',StaticFiles(directory=DIST,html=True),name='ui')
