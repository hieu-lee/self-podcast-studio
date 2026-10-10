# Prototype acceptance and failure inventory (defined before implementation)

## Scope and claims
Browser, single user, loopback backend; topic -> consent -> natural AI interview -> stop -> conservative audio export. No publishing/video/editor/cloud storage. Record microphone and AI PCM actually sent to the output on a shared AudioWorklet sample clock. Device audibility is not measurable; muted/broken hardware is not recoverable.

## Failure modes and targeted E2E plan
- Microphone denied, missing API key, unsupported 24 kHz AudioContext: no misleading live state; release devices.
- Cross-origin forms/fetch/WebSocket, DNS rebinding, path traversal, oversized/invalid chunks: reject without mutation; no key in frontend or repository.
- Duplicate/out-of-order/conflicting upload, server restart, browser reload/offline: IndexedDB queue and immutable SQLite chunks; retry idempotently, preserve committed chunks; identify missing samples rather than restore imaginary audio.
- Abrupt tab close can lose up to one uncommitted second; worklet suspension/sleep cannot record missing guest audio. Show warnings; export requires complete declared chunks and known gap acknowledgment.
- API disconnect or session/context limits: continue local capture, explicit reconnect/renew at a turn boundary; bounded context from heard complete assistant turns and guest transcripts, not generated unplayed speech. Reconnect is not recovery of the prior API audio state.
- Completion events can be emitted on failed/cancelled responses too. All delivered partial PCM played plus audio/transcript "done" must NOT count as a completed question. Require completed terminal response/output item and exact sample equality; E2E inject a failed partial turn with all delivered samples played, then verify the actual relay's reconnect context digest omits it.
- Interrupted/buffered AI speech: immediately clear playback and truncate API item to samples actually played; saved AI channel contains no discarded tail. Live transcript is provisional; final transcript is from audio.
- Stop during generation/upload/export: stop capture, flush final partial chunk, wait for durable queue; don't claim saved/export-ready until done; no guest synthesis, source overwrites, or API recordings in Git.
- Hour recording growth: accelerated 3,600-chunk HTTP write + retry/restart/export integrity test (not a real one-hour interview). Browser worklet long-enough chunk continuity and interrupted speech checks.
- Export: immutable originals, coverage audit, conservative silence trim with speech padding, balanced loudness, smooth joins, rebuilt timeline, final speaker-labelled timestamp transcript from saved individual tracks; repeatable manifest. Reject missing declared samples. Expose download + player and mark listening approval separately.
- Re-export the selected recording without reloading: player must load the new immutable export version, links must agree with that version, and approval of an obsolete version must fail rather than approve different audio.

## Exact validation / repeatable evidence
1. `scripts/e2e_backend.py`: live HTTP boundary/durability, conflicts, gaps, recovered stop, offline sustained recording, FFmpeg source/export integrity. Artifacts in ignored `.artifacts/`.
2. `scripts/e2e_browser.mjs`: Chromium fake microphone using a speech WAV; real Realtime AI audio, question/answer/follow-up, interruption and played-channel integrity, recording stop, real transcription/render/download. Desktop/mobile screenshots, browser trace, JSON assertions. No human microphone started by validation.
3. Manual visual screenshot inspection; listen to exported synthetic fixture and inspect waveform/levels/transcript/timing. Readiness doesn't claim a real 60-minute live session or perfect restoration.

## Visible controls / states
- Editable topic; prepared question outline; explicit consent + Start.
- Live elapsed time, mic/AI meters, local upload backlog, AI connection health.
- Interrupt, reconnect (same recording, new API session), Stop/save.
- Saved session list, Resume (explicit mic consent), Export with gap acknowledgment, progress/error, audio player/download, final transcript/edit record, listening confirmation.
- Main CTA/status visible at 1440x900 and 390x844; no horizontal clipping. Long transcript/history may scroll.

## Expanded quality-first acceptance (before implementing audio diagnosis)

The final episode must actively re-examine SAVED audio with an audio-capable model, not a text model claiming to listen. Known guest/AI tracks remain authoritative identities. Hosted OpenAI audio/text analysis is authorized; local code validates a constrained edit plan and executes FFmpeg/TTS, never model-generated shell commands.

Deterministic two-voice fixture: cached Marin AI questions/backchannel + Cedar synthetic guest (not Hieu cloning), natural guest cadence, exact item/playback timing and source sample hashes. Inject (a) full interviewer question starting in the middle of a guest answer, (b) 500ms playback starvation inside that same fully HEARD question, (c) transport-cut-off partial question with a generated-but-unplayed tail, (d) a brief intentional natural backchannel overlap that must remain. Guest answers follow only questions actually heard; a later guest clarification does not answer the unheard tail.

Failure cases / safe operations:
- Model hallucinated diagnosis, unknown item, invalid schema/range, omitted/changed guest, arbitrary execution, regenerated unplayed words: reject plan/action, preserve and flag.
- Natural backchannel/intentional interruption confused with technical overlap: audio evidence + timing classification required; preserve ambiguity, never remove all overlap.
- Complete heard AI question with audible playback gap: re-transcribe ACTUAL item audio; regenerate only that text and change its duration, not original slot.
- Mis-timed AI question over a continuing guest answer: move only fully heard complete AI question to after that uninterrupted answer; shift subsequent turns rather than overlap/squeeze/cut guest.
- Technical cut-off incomplete AI question: do not restore unseen generated tail. Omit only with high-confidence audio diagnosis + failed API/transport evidence and no dependent guest answer; otherwise preserve/flag.
- All guest waveform samples remain ordered/intact (join fades allowed only in padding). Guest speech is never synthesized. Original intentional overlap retained. No new overlaps; final captions derived from final audio.

Also exercise an isolated fully heard question with a 400ms playback gap and its naturally timed guest answer: repairing the question must not remove even silent microphone samples from the prepared timeline or overlap the answer.

Review regression cases: a one-second pause separates the prior answer from the answer to the intrusive question; silence-trimming unions may merge them, but movement must not use that merged end. Use actual acoustic block anchors and an audio-validated completed prior answer, otherwise preserve/flag. Word verification must distinguish "nowhere" from "now here" and "we'll" from "well"; preserve token boundaries and meaningful apostrophes, never fuzzy character matching.

E2E evidence: `.artifacts/two-voice/ground-truth.json`, damaged tracks/mix, audio-model request/response diagnosis (no auth headers), validated decision record, rebuilt sample/timing map, polished MP3/transcript, before/after waveform + independently measured overlapping/stall/cutoff corrections and guest word/sample preservation. Model self-grading alone is not proof. Human listening approval remains separate; disclose objective inspection vs actual listening.

Delayed UI polling regression: a detail poll for selected A can finish after selecting B or after a newer detail poll for A. Neither obsolete response may replace the current selection/export version. Browser E2E holds actual HTTP responses, switches sessions, and releases out-of-order same-session snapshots; retain screenshots/trace/JSON without microphone or paid model calls.
