"""Synthetic TEST guest, never a replacement for Hieu's recorded voice."""
import argparse
import os
import wave
from pathlib import Path
import httpx

parser=argparse.ArgumentParser();parser.add_argument('--language',choices=['en','vi'],default='en');language=parser.parse_args().language
out=Path('.artifacts')/('vietnamese' if language=='vi' else '');out.mkdir(parents=True,exist_ok=True)
p=out/'synthetic-guest.pcm'
text='I think AI can discover genuinely new mathematics. Recombination is part of human creativity too. But finding a pattern is not enough. I would want a proof we can check, and a useful new connection, rather than merely a theorem nobody understands.'
if language=='vi':text='Tôi nghĩ AI có thể khám phá toán học mới. Nhưng một mẫu hình chưa phải là một chứng minh. Theo tôi, một chứng minh cần được kiểm tra độc lập. Ví dụ, một kết nối giữa hình học và lý thuyết số sẽ rất thú vị. Tôi vẫn muốn hiểu các giả thiết, chứ không chỉ biết đáp án đúng.'
if not p.exists():
    r=httpx.post('https://api.openai.com/v1/audio/speech',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},
        json={'model':'gpt-4o-mini-tts','voice':'cedar','input':text,'response_format':'pcm','instructions':'Natural Vietnamese conversation, clear tones, exact provided words without translation.' if language=='vi' else 'Natural conversational English; exact text.'},timeout=120)
    r.raise_for_status();p.write_bytes(r.content)
# Chromium's fake mic loops the file. Leave opening and thinking silence.
with wave.open(str(out/'synthetic-guest.wav'),'wb') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
    w.writeframes(bytes(24000*2*14));w.writeframes(p.read_bytes());w.writeframes(bytes(24000*2*12))
(out/'fixture.txt').write_text('SYNTHETIC TEST GUEST (not Hieu)\n'+text+'\n')
print('Synthetic fixture ready:',out/'synthetic-guest.wav')
