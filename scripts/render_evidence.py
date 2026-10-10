"""Render repeatable two-voice source/final waveform evidence; no audio edits."""
import html
import json
import subprocess
import wave
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'.artifacts'/'two-voice'
s=json.loads((OUT/'session.json').read_text());export=ROOT/'.data'/s['session_id']/s['export_dir']
width=1600;plot=1500;parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="800" viewBox="0 0 {width} 800">',
 '<rect width="1600" height="800" fill="#101918"/>',
 '<text x="40" y="35" fill="white" font-family="Arial" font-size="24">Saved audio evidence - BEFORE / AFTER</text>',
 '<text x="40" y="62" fill="#a9b8ac" font-family="Arial" font-size="16">Separate sample clocks per view. Guest blue; interviewer amber before / lime after. Same amplitude scale.</text>']
for row,(label,path,color) in enumerate([
 ('BEFORE guest - immutable source',OUT/'damaged-guest.wav','#68afbc'),
 ('BEFORE AI - intrusive question, starvation, cut-off',OUT/'damaged-ai.wav','#daa873'),
 ('AFTER guest - final mastered track',export/'final-guest.wav','#68afbc'),
 ('AFTER AI - constrained repairs; natural backchannel retained',export/'final-ai.wav','#d6ed93')]):
 with wave.open(str(path)) as w:x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2');seconds=len(x)/w.getframerate()
 y=100+row*172;mid=y+75
 parts.append(f'<text x="40" y="{y}" fill="white" font-family="Arial" font-size="17">{html.escape(label)} - {seconds:.3f}s</text>')
 parts.append(f'<path d="M 40 {mid} H 1540" stroke="#34403a"/>')
 for column,chunk in enumerate(np.array_split(x,plot)):
  if len(chunk):
   a=mid-float(np.max(chunk))*48/32768;b=mid-float(np.min(chunk))*48/32768
   parts.append(f'<path d="M {40+column} {a:.2f} V {b:.2f}" stroke="{color}"/>')
 for tick in range(0,int(seconds)+1,5):
  pos=40+tick/seconds*plot
  parts.append(f'<text x="{pos:.2f}" y="{y+140}" fill="#a9b8ac" font-family="Arial" font-size="12">{tick}s</text>')
parts.append('</svg>');(OUT/'before-after-waveform.svg').write_text(''.join(parts))
subprocess.run(['ffmpeg','-v','error','-y','-i',str(export/'episode.mp3'),'-ac','1','-ar','24000','-c:a','pcm_s16le',str(OUT/'polished-listening.wav')],check=True)
print(OUT/'before-after-waveform.svg')
