"""Transactional, immutable recording chunks. No recording data lives in Git."""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

LANGUAGES={'en':'English','vi':'Vietnamese'}

ROOT = Path(os.environ.get('SELF_PODCAST_DATA', '.data')).resolve()
ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(ROOT, 0o700)


def db(sid):
    if len(sid) != 32 or any(c not in '0123456789abcdef' for c in sid):
        raise ValueError('Invalid session ID')
    path = ROOT / sid / 'recording.sqlite'
    if not path.exists():
        raise FileNotFoundError('Session not found')
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA synchronous=FULL')
    return con


def create(topic,language="en"):
    if language not in LANGUAGES:raise ValueError("Unsupported episode language")
    sid = uuid.uuid4().hex
    path = ROOT / sid
    path.mkdir(mode=0o700)
    with sqlite3.connect(path / 'recording.sqlite') as c:
        c.executescript('''
          PRAGMA journal_mode=WAL;
          PRAGMA synchronous=FULL;
          CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
          CREATE TABLE epochs (id TEXT PRIMARY KEY, wall_ms REAL, expected INTEGER);
          CREATE TABLE chunks (epoch TEXT, seq INTEGER, start INTEGER, frames INTEGER,
            header TEXT, pcm BLOB, PRIMARY KEY(epoch, seq));
          CREATE TABLE events (id INTEGER PRIMARY KEY, at REAL, body TEXT);
        ''')
        c.executemany('INSERT INTO meta VALUES (?,?)', [('topic',topic),('language',language),('created',str(time.time())),('state','saved')])
    return sid


def meta(sid):
    with db(sid) as c:
        m = dict(c.execute('SELECT key,value FROM meta').fetchall())
        m.setdefault('language','en')  # Legacy episodes stay English without a DB migration.
        m.update(id=sid, epochs=[dict(r) for r in c.execute('SELECT * FROM epochs ORDER BY wall_ms')],
                 chunks=c.execute('SELECT COUNT(*) FROM chunks').fetchone()[0],
                 frames=c.execute('SELECT COALESCE(SUM(frames),0) FROM chunks').fetchone()[0])
        return m


def set_meta(sid, key, value):
    with db(sid) as c:
        c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,str(value)))


def event(sid, body):
    with db(sid) as c:
        c.execute('INSERT INTO events(at,body) VALUES (?,?)',(time.time(),json.dumps(body)))


def events(sid, kinds=None):
    with db(sid) as c:
        if kinds:
            placeholders=','.join('?' for _ in kinds)
            return [json.loads(r[0]) for r in c.execute(f'SELECT body FROM events WHERE json_extract(body,\'$.type\') IN ({placeholders}) ORDER BY id',kinds)]
        return [json.loads(r[0]) for r in c.execute('SELECT body FROM events ORDER BY id')]


def add_epoch(sid, eid, wall):
    with db(sid) as c:
        c.execute('INSERT INTO epochs VALUES (?,?,NULL)',(eid,wall))
        c.execute("UPDATE meta SET value='recording' WHERE key='state'")
        c.execute("DELETE FROM meta WHERE key IN ('export_dir','export_status','export_audio_review')")


def chunk(sid, header, pcm):
    canonical = json.dumps(header,sort_keys=True,separators=(',',':'))
    with db(sid) as c:
        e = c.execute('SELECT expected FROM epochs WHERE id=?',(header['epoch'],)).fetchone()
        if not e:
            raise ValueError('Unknown recording epoch')
        old = c.execute('SELECT header,pcm FROM chunks WHERE epoch=? AND seq=?',(header['epoch'],header['seq'])).fetchone()
        if old:
            if old['header'] != canonical or old['pcm'] != pcm:
                raise ValueError('Conflicting immutable chunk')
            return
        if e['expected'] is not None:
            raise ValueError('Epoch already sealed')
        c.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',
                  (header['epoch'],header['seq'],header['start'],len(pcm)//4,canonical,pcm))


def seal(sid, eid, expected):
    with db(sid) as c:
        if not c.execute('SELECT id FROM epochs WHERE id=?',(eid,)).fetchone():
            raise ValueError('Unknown epoch')
        old = c.execute('SELECT expected FROM epochs WHERE id=?',(eid,)).fetchone()[0]
        if old is not None and old != expected:
            raise ValueError('Conflicting epoch end')
        rows = c.execute('SELECT start,frames FROM chunks WHERE epoch=? ORDER BY seq',(eid,)).fetchall()
        cursor = 0
        for r in rows:
            if r['start'] != cursor:
                raise ValueError('Missing or overlapping audio chunks; retry upload before saving')
            cursor += r['frames']
        if cursor != expected:
            raise ValueError('Incomplete audio; retry upload before saving')
        c.execute('UPDATE epochs SET expected=? WHERE id=?',(expected,eid))


def coverage(sid):
    m = meta(sid)
    warnings = []
    end_wall = None
    with db(sid) as c:
        for e in m['epochs']:
            rows=c.execute('SELECT start,frames FROM chunks WHERE epoch=? ORDER BY seq',(e['id'],)).fetchall()
            cursor=0
            for r in rows:
                if r['start'] != cursor:
                    raise ValueError('Missing/overlapping source chunks')
                cursor += r['frames']
            if e['expected'] is None or e['expected'] != cursor:
                raise ValueError('Recording epoch is unsealed/incomplete; recover and save first')
            if end_wall is not None and e['wall_ms']-end_wall > 250:
                warnings.append(f"Recording gap of approximately {(e['wall_ms']-end_wall)/1000:.1f}s between capture epochs; not restored.")
            if end_wall is not None and e['wall_ms'] < end_wall-250:
                raise ValueError('Overlapping recording epochs')
            end_wall=e['wall_ms']+cursor/24
    if not m['frames']:
        raise ValueError('No source audio')
    return warnings


def heard_context(sid):
    """Never seed a reconnect with an assistant transcript whose tail wasn't played."""
    ev=events(sid)
    generated={}
    played={}
    audio_done=set();completed=set()
    with db(sid) as c:
        for row in c.execute('SELECT header FROM chunks'):
            for span in json.loads(row[0]).get('spans',[]):
                played[span['item']]=played.get(span['item'],0)+span['frames']
    for e in ev:
        if e['type']=='response.output_audio.delta':
            generated[e['item_id']]=generated.get(e['item_id'],0)+e['samples']
        elif e['type']=='response.output_audio.done':
            audio_done.add(e['item_id'])
        elif e['type']=='response.done' and e['response'].get('status')=='completed':
            completed.update(i['id'] for i in e['response'].get('output',[]) if i.get('status')=='completed')
    texts=[]
    for e in ev:
        if e['type']=='conversation.item.input_audio_transcription.completed':
            texts.append('Guest: '+e.get('transcript',''))
        elif e['type']=='response.output_audio_transcript.done':
            item=e['item_id']
            if item in audio_done and item in completed and generated.get(item,0)>0 and played.get(item,0)==generated[item]:
                texts.append('Interviewer: '+e.get('transcript',''))
            else:
                texts.append('[Interrupted or unverified interviewer audio omitted]')
    # Last 24,000 characters only: earlier originals remain saved, not silently reconstructed.
    return '\n'.join(texts)[-24000:]
