/** Owned-real listener refusal/positive CLI E2E; written before adding ownership guard. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {writeFile} from 'node:fs/promises';
const owned=process.argv[2]==='owned',origin='http://127.0.0.1:8765';
const boot=await fetch(origin+'/api/bootstrap'),cookie=boot.headers.get('set-cookie').split(';')[0];
const sessions=async()=>{const r=await fetch(origin+'/api/sessions',{headers:{Cookie:cookie}});assert.ok(r.ok);return (await r.json()).map(s=>s.id).sort();};
const before=await sessions();let output='';
const code=await new Promise((resolve,reject)=>{
 // Nonexistent resume protects all normal/human recordings even if the guard regresses.
 const p=spawn('node',['scripts/e2e_guided_real_browser.mjs'],{env:{...process.env,SELF_PODCAST_E2E_LANGUAGES:'en',SELF_PODCAST_E2E_RESUME_EN:'0'.repeat(32),SELF_PODCAST_E2E_OWNERSHIP_ONLY:'1'}});
 p.stdout.on('data',b=>output+=b);p.stderr.on('data',b=>output+=b);p.on('error',reject);p.on('exit',resolve);
});
if(owned){assert.equal(code,0,output);assert.match(output,/Owned real fixture identity verified before episode operations/);}
else{assert.notEqual(code,0,output);assert.match(output,/Owned real fixture required before episode operations/);}
assert.deepEqual(await sessions(),before);
await writeFile(`.artifacts/guided/real-ownership-${owned?'positive':'refusal'}.json`,JSON.stringify({checks:[owned?'actual isolated real listener nonce/data-root accepted before episode operations':'unrelated normal listener refused before selection/resume/microphone/jobs','session IDs unchanged; nonexistent resume sentinel protects even a guard regression'],code,scope:'Child actual real-browser CLI; ownership-only, no paid jobs, microphone or recording mutations'},null,2));console.log(owned?'Real isolated ownership positive passed':'Real browser normal-listener refusal passed');
