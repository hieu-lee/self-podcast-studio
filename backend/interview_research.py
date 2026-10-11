"""Own Realtime response scheduling so slow searches never block capture or overlap turns."""
import asyncio
import contextlib
import json
from . import research, store


class Interview:
    def __init__(self,sid,language,enabled,upstream,ws,instructions):
        self.instructions=instructions
        self.sid=sid;self.language=language;self.enabled=enabled;self.upstream=upstream;self.ws=ws
        self.closed=False;self.speaking=False;self.awaiting_commit=False;self.responding=False;self.response_id=None
        self.want_response=False;self.next_instructions=None;self.seen=set();self.task=None;self.cancelled_responses=set();self.cancel_before_created=False

    async def request(self,instructions=None):
        self.want_response=True
        if instructions:self.next_instructions=instructions
        await self.kick()

    async def kick(self):
        if self.closed or self.speaking or self.awaiting_commit or self.responding or self.task or not self.want_response:return
        self.want_response=False;self.responding=True
        e={'type':'response.create'}
        if self.next_instructions:e['response']={'instructions':self.next_instructions};self.next_instructions=None
        await self.upstream.send(json.dumps(e))

    async def output(self,call_id,result):
        if not self.closed:
            await self.upstream.send(json.dumps({'type':'conversation.item.create','item':{'type':'function_call_output','call_id':call_id,'output':json.dumps(result,ensure_ascii=False)}}))

    async def lookup(self,call_id,args):
        result=None
        try:
            if not self.enabled:raise ValueError('Web research is disabled for this episode.')
            if not isinstance(args,str) or len(args)>1000:raise ValueError('Invalid research arguments.')
            data=json.loads(args)
            if not isinstance(data,dict) or set(data)!={'query'}:raise ValueError('Invalid research arguments.')
            query=research.query_text(data['query']);research.reserve(self.sid)
            await self.ws.send_json({'type':'research.status','status':'checking','query':query})
            result=await research.search(query,self.language)
            if self.closed:return
            store.event(self.sid,{'type':'research_result','result':result})
            await self.output(call_id,result)
            await self.ws.send_json({'type':'research.result','result':result})
            self.next_instructions=self.instructions+'\nThe lookup finished. Give at most 40 spoken words: one sourced fact or honest uncertainty, then one open interview question. Do not list the briefing. Keep the fixed episode language.'
            self.want_response=True
        except (ValueError,TypeError,KeyError):
            result=research.failure('',self.language,'Invalid, disabled or exhausted research request. No fact verified.')
            await self.output(call_id,result);self.want_response=True
            if not self.closed:await self.ws.send_json({'type':'research.result','result':result})
        except asyncio.CancelledError:
            if not self.closed:
                await self.output(call_id,research.failure('',self.language,'Research cancelled; do not assert new current facts.'))
                await self.ws.send_json({'type':'research.status','status':'cancelled'})
            raise
        except Exception:
            self.closed=True
            with contextlib.suppress(Exception):
                await self.ws.send_json({'type':'connection_error','text':'Research/voice connection failed. Capture is preserved; reconnect or stop.'})
                await self.ws.close()
        finally:
            if research.pending.get(self.sid) is asyncio.current_task():research.pending.pop(self.sid,None)
            self.task=None
            # Cancellation must never restart the interviewer.
            if result is not None and not self.closed:await self.kick()

    async def observe(self,e):
        t=e['type']
        if t=='error':
            if e.get('error',{}).get('code')=='response_cancel_not_active':return
            # A rejected create need not produce created/done: never leave a false-connected scheduler.
            await self.close()
            await self.ws.send_json({'type':'connection_error','text':'Realtime rejected a request. Local capture continues; reconnect or stop.'})
            await self.ws.close();return
        if t=='input_audio_buffer.speech_started':
            self.speaking=True;self.awaiting_commit=True
        elif t=='input_audio_buffer.speech_stopped':self.speaking=False
        elif t=='input_audio_buffer.committed':self.awaiting_commit=False;self.want_response=True
        elif t=='response.created':
            self.responding=True;self.response_id=e['response']['id']
            if self.cancel_before_created:
                self.cancelled_responses.add(self.response_id);self.cancel_before_created=False
                await self.upstream.send(json.dumps({'type':'response.cancel','response_id':self.response_id}))
        elif t=='response.done':
            response=e['response']
            if self.response_id is None or response.get('id')==self.response_id:
                self.responding=False;self.response_id=None
            cancelled=response.get('id') in self.cancelled_responses
            if response.get('id'):self.cancelled_responses.discard(response['id'])
            if not self.responding:self.cancel_before_created=False
            for item in response.get('output',[]):
                if item.get('type')!='function_call':continue
                cid=item.get('call_id')
                if not isinstance(cid,str) or not 0<len(cid)<=100 or cid in self.seen:continue
                self.seen.add(cid)
                if len(self.seen)>128:raise ValueError('Excessive Realtime tool calls')
                if response.get('status')!='completed' or cancelled:
                    await self.output(cid,research.failure('',self.language,'Response cancelled or incomplete; no research dispatched.'));continue
                if item.get('name')!='search_current_topic' or self.task:
                    await self.output(cid,research.failure('',self.language,'Unknown tool or another lookup is pending. No fact verified.'))
                    self.want_response=True;continue
                self.task=asyncio.create_task(self.lookup(cid,item.get('arguments')))
                research.pending[self.sid]=self.task
        await self.kick()

    async def interrupt(self):
        self.want_response=False;self.next_instructions=None
        if self.responding:
            if self.response_id:self.cancelled_responses.add(self.response_id)
            else:self.cancel_before_created=True
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)

    async def close(self):
        self.closed=True
        await self.interrupt()
