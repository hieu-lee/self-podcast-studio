"""Actual studio with a sanitized public Responses evidence observer; separate test data."""
import json
import os
import sys
import uuid
from pathlib import Path
import httpx
import uvicorn
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['SELF_PODCAST_DATA']=str(ROOT/'.artifacts/research/real-data')
OUT=ROOT/'.artifacts/research/provider';OUT.mkdir(parents=True,exist_ok=True)
RealClient=httpx.AsyncClient
async def evidence(response):
    if str(response.request.url)=='https://api.openai.com/v1/responses':
        await response.aread()
        (OUT/(uuid.uuid4().hex+'.json')).write_text(json.dumps({'request':json.loads(response.request.content),'status':response.status_code,'response':response.json()},ensure_ascii=False,indent=2))
class ObservedClient(RealClient):
    def __init__(self,*args,**kwargs):
        kwargs['event_hooks']={'response':[evidence]};super().__init__(*args,**kwargs)
httpx.AsyncClient=ObservedClient
from backend.app import app
uvicorn.run(app,host='127.0.0.1',port=8765,log_level='warning',access_log=False)
