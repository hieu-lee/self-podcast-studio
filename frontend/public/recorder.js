// One sample clock for guest capture, actual rendered AI output and playback spans.
class Recorder extends AudioWorkletProcessor {
  constructor() {
    super(); this.frame=0; this.chunkStart=0; this.chunk=[]; this.mic=[]; this.queue=[];
    this.spans=[]; this.underruns=[]; this.active=true; this.currentItem=null; this.offset=0;
    this.done=new Set(); this.blocked=new Set(); this.starved=false;
    this.port.onmessage=({data:d})=>{
      if(d.type==='audio'&&!this.blocked.has(d.item)) {this.queue.push({item:d.item,pcm:d.pcm,pos:0}); this.starved=false;}
      if(d.type==='done') this.done.add(d.item);
      if(d.type==='clear') {
        const item=this.currentItem || this.queue[0]?.item;
        this.port.postMessage({type:'interrupted',item,played:this.currentItem?this.offset:0});
        if(item)this.blocked.add(item);
        for(const q of this.queue)this.blocked.add(q.item);
        this.queue=[]; this.currentItem=null; this.offset=0; this.starved=false;
      }
      if(d.type==='stop') {this.flush(); this.active=false; this.queue=[]; this.port.postMessage({type:'stopped',frames:this.frame});}
    };
  }
  flush() {
    if(!this.chunk.length)return;
    const pcm=new Int16Array(this.chunk);
    this.port.postMessage({type:'chunk',start:this.chunkStart,pcm:pcm.buffer,spans:this.spans,underruns:this.underruns},[pcm.buffer]);
    this.chunk=[]; this.chunkStart=this.frame; this.spans=[]; this.underruns=[];
  }
  process(inputs,outputs) {
    const input=inputs[0]?.[0]; const output=outputs[0][0];
    if(!this.active){output.fill(0);return false;}
    let micPeak=0,aiPeak=0;
    for(let i=0;i<output.length;i++) {
      const mic=Math.max(-1,Math.min(1,input?.[i]||0));
      let sample=0;
      if(this.queue.length) {
        const q=this.queue[0];
        if(q.item!==this.currentItem){this.currentItem=q.item;this.offset=0;}
        sample=q.pcm[q.pos++];
        const prev=this.spans[this.spans.length-1];
        if(prev&&prev.item===q.item&&prev.start+prev.frames===this.frame&&prev.offset+prev.frames===this.offset)prev.frames++;
        else this.spans.push({item:q.item,start:this.frame,frames:1,offset:this.offset});
        this.offset++;
        if(q.pos===q.pcm.length)this.queue.shift();
      } else if(this.currentItem&&!this.done.has(this.currentItem)&&!this.starved) {
        this.underruns.push(this.frame);this.starved=true;
      }
      output[i]=sample/32768;
      const m=Math.round(mic*(mic<0?32768:32767));
      this.chunk.push(m,sample); this.mic.push(m); this.frame++;
      micPeak=Math.max(micPeak,Math.abs(mic)); aiPeak=Math.max(aiPeak,Math.abs(output[i]));
      if(this.mic.length===2400) {
        const pcm=new Int16Array(this.mic);
        this.port.postMessage({type:'mic',pcm:pcm.buffer,micPeak,aiPeak},[pcm.buffer]); this.mic=[];
      }
      if(this.chunk.length===48000)this.flush();
    }
    return true;
  }
}
registerProcessor('recorder',Recorder);
