"""Owned upstream fixtures + actual studio. Test process only; no production test switches."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from fastapi.responses import JSONResponse
import uvicorn
import websockets
from fastapi import FastAPI, Request, WebSocket

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['SELF_PODCAST_DATA']=str(ROOT/'.artifacts/research/fixture-data')
os.environ.setdefault('OPENAI_API_KEY','owned-fixture-key')
from backend import app, research, store
fixture=FastAPI();connections=[];requests=[];messages=[];frames=0;hold_next=False;held=False
real_connect=websockets.connect
app.websockets.connect=lambda *a,**kw:real_connect('ws://127.0.0.1:8766/realtime',max_size=2**22)
research.ENDPOINT='http://127.0.0.1:8766/responses'
research.DEADLINE=5
real_event=store.event
def delayed_event(sid,body):
    if body.get('type')=='input_audio_buffer.speech_started':time.sleep(4)
    return real_event(sid,body)
store.event=delayed_event

guided_jobs=False
@app.app.get('/api/owned-fixture-identity')
async def identity():return {'fixture':'self-podcast-owned-research','guided_jobs':guided_jobs,'nonce':os.environ.get('SELF_PODCAST_E2E_NONCE')}
# Production's catch-all static mount must not shadow this test-only ownership proof.
app.app.router.routes.insert(0,app.app.router.routes.pop())

@fixture.post('/responses')
async def responses(request:Request):
    body=await request.json();requests.append(body)
    query=body['input']
    if 'timeout' in query:await asyncio.sleep(10)
    if 'slow' in query:await asyncio.sleep(3)
    if 'failure' in query:return JSONResponse({'error':'owned failure'},status_code=500)
    text='Thông tin có dẫn nguồn, không xác nhận tên ví dụ của khách.' if 'Vietnamese' in body['instructions'] else 'Sourced information; guest examples are not verified.'
    annotation={'type':'url_citation','url':'https://openai.com/index/','title':'Official source','start_index':len(text),'end_index':len(text)+3}
    if 'unsafe' in query:annotation['url']='javascript:alert(1)'
    for name,url in {'loopback-short':'https://127.1/','loopback-octal':'https://0177.0.0.1/','loopback-hex':'https://0x7f.0.0.1/','private-hex':'https://0xc0.0xa8.0.0x1/'}.items():
        if name in query:annotation['url']=url
    output=[{'type':'web_search_call','status':'completed','action':{'type':'search','sources':[{'url':annotation['url'],'title':annotation['title']}]}}]
    if 'no-search' in query:output=[]
    output.append({'type':'message','content':[{'type':'output_text','text':text+' [1]','annotations':[] if 'no-citations' in query else [annotation]}]})
    return {'id':'owned-response','status':'completed','output':output}

@fixture.websocket('/realtime')
async def realtime(ws:WebSocket):
    global frames,hold_next,held
    await ws.accept();connections.append(ws)
    try:
        while True:
            e=await ws.receive_json();messages.append({'connection':len(connections),'event':e})
            if e['type']=='input_audio_buffer.append':frames+=1
            if e['type']=='session.update':await ws.send_json({'type':'session.updated'})
            if e['type']=='response.cancel' and held:
                await ws.send_json({'type':'error','error':{'code':'response_cancel_not_active','message':'Owned pending-create race'}})
            if e['type']=='response.create':
                if hold_next:hold_next=False;held=True;continue
                await ws.send_json({'type':'response.created','response':{'id':'owned-opening'}})
                await ws.send_json({'type':'response.done','response':{'id':'owned-opening','status':'completed','output':[]}})
    except Exception:pass

@fixture.post('/hold')
async def hold():
    global hold_next
    hold_next=True
    return {'ok':True}

@fixture.post('/emit')
async def emit(request:Request):
    global held
    for e in await request.json():
        if e['type']=='response.created':held=False
        await connections[-1].send_json(e)
    return {'ok':True}

@fixture.get('/state')
async def state():return {'frames':frames,'requests':requests,'messages':messages,'connections':len(connections)}

async def main():
    await asyncio.gather(uvicorn.Server(uvicorn.Config(fixture,host='127.0.0.1',port=8766,log_level='warning',access_log=False)).serve(),uvicorn.Server(uvicorn.Config(app.app,host='127.0.0.1',port=8765,log_level='warning',access_log=False)).serve())

if __name__=='__main__':asyncio.run(main())
