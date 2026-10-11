"""Actual Responses + Realtime search in en/vi through live HTTP/WebSocket (synthetic PCM)."""
import asyncio
import json
import sys
from pathlib import Path
import httpx
import websockets

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts/research'
OUT.mkdir(parents=True,exist_ok=True)
# Run against actual server, preserving raw public provider evidence in the separate server observer.
async def main():
    evidence=[]
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8765',headers={'X-Self-Podcast':'1'},timeout=65) as client:
        await client.get('/api/bootstrap')
        for language in ('en','vi'):
            s=await client.post('/api/sessions',json={'topic':'Current official OpenAI model releases and what counts as evidence','language':language});s.raise_for_status();sid=s.json()['id']
            prep=await client.post(f'/api/sessions/{sid}/research',json={'query':'Current OpenAI API model releases official documentation'});prep.raise_for_status();packet=prep.json();assert packet['status']=='ready',packet
            assert packet['web_searches']>0 and packet['citations'] and packet['sources']
            assert all('openai.com' in x['url'] for x in packet['sources']),packet
            assert all(s['published_at'] is None for s in packet['sources'])
            cookie='; '.join(f'{k}={v}' for k,v in client.cookies.items())
            events=[];audio=[];found=False
            async with websockets.connect(f'ws://127.0.0.1:8765/api/sessions/{sid}/live',origin='http://127.0.0.1:8765',additional_headers={'Cookie':cookie}) as ws:
                deadline=asyncio.get_running_loop().time()+125
                while True:
                        raw=await asyncio.wait_for(ws.recv(),max(.1,deadline-asyncio.get_running_loop().time()))
                        e=json.loads(raw);events.append(e)
                        if e['type']=='ready':
                            # A public synthetic text turn tests actual model-selected function calls, not injected remote output.
                            await ws.send(json.dumps({'type':'research_request','query':'Which current OpenAI API model is documented officially? Verify with a new web search before answering.'}))
                        if e['type']=='research.result' and e['result']['status']=='ready':found=True
                        if e['type']=='response.output_audio.delta':audio.append(e['delta'])
                        if found and audio and e['type']=='response.done' and e['response']['status']=='completed':break
                        assert e['type']!='connection_error',e
            assert found and audio,'Need real function result and actual interviewer audio'
            ledger=(await client.get(f'/api/sessions/{sid}/research')).json()
            calls=[item for e in events if e['type']=='response.done' for item in e.get('response',{}).get('output',[]) if item.get('type')=='function_call']
            assert calls,'Model must produce real function_call'
            (OUT/f'live-{language}-events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
            # Independent saved speech decoding/transcription, not grading only text from the same Realtime model.
            import base64,wave,os
            wav=OUT/f'live-{language}-ai.wav'
            with wave.open(str(wav),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b''.join(base64.b64decode(x) for x in audio))
            async with httpx.AsyncClient(timeout=60) as hosted:
                with wav.open('rb') as f:r=await hosted.post('https://api.openai.com/v1/audio/transcriptions',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},data={'model':'gpt-4o-transcribe','language':language},files={'file':(wav.name,f,'audio/wav')})
                r.raise_for_status();transcript=r.json()['text']
            assert len(transcript)>10
            if language=='vi':assert any(c in transcript for c in 'ăâđêôơưáàảãạếềểễệốồổỗộ'),transcript
            evidence.append({'language':language,'sid':sid,'prep':packet,'ledger':ledger,'function_calls':calls,'independent_ai_transcript':transcript})
    (OUT/'real-e2e.json').write_text(json.dumps({'evidence':evidence,'scope':'Actual paid hosted Responses search and Realtime function calls/audio; public synthetic text request, no human mic or guest impersonation.'},ensure_ascii=False,indent=2));print(json.dumps([{'language':e['language'],'sid':e['sid'],'transcript':e['independent_ai_transcript']} for e in evidence],ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
