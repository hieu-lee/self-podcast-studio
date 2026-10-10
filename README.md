# Self Podcast — local prototype

A browser interview studio for Hieu: type a topic, explicitly permit recording, talk with an AI interviewer, stop/save, then export an audio episode and matching speaker-labelled transcript. No video, publishing, accounts, hosting, or elaborate editor.

## Start

Requirements: macOS, Python 3.10+, Node 20.19+ (or 22.12+), FFmpeg/ffprobe on PATH, Chrome, an OpenAI API key with paid Realtime/audio access. The first start installs pinned Python/Node dependencies and builds the UI.

```sh
cd /Users/hieu.leduc/Documents/ChatGPT/self-podcast
# OPENAI_API_KEY must already be set in your shell environment.
./start.sh
```

Open **http://127.0.0.1:8765**. Keep the terminal, browser tab and Mac awake. Use headphones. Nothing records until you check consent and press Start; Resume also needs consent. For an already running instance, just open the URL. Stop the server with Ctrl-C **after** saving the recording. Optional: `SELF_PODCAST_DATA=/absolute/private/path` changes local storage; `SELF_PODCAST_MODEL` changes the Realtime model.

The starter topic is **“Can AI discover new mathematics, or only recombine what humans already know?”** with three exploratory questions. The interviewer follows actual answers, one question at a time; the outline is not a rigid script.

## What is actually saved

- `.data/<id>/recording.sqlite`: immutable one-second stereo PCM16 chunks (24 kHz), speaker channels, capture-epoch/sample positions, playback spans, underruns, API transcripts/events and explicit interruption timing. SQLite FULL synchronous transactions acknowledge only committed writes.
- Browser IndexedDB: ordered upload retry queue and final capture ends. Chunks enter this durable queue before HTTP upload and are deleted only after server acknowledgment. Do not clear browser storage or change profile while uploads are pending.
- `sources/original-guest.wav` and `original-ai.wav`: aggregate source views built from the immutable DB. Resuming adds new source epochs; the previous original chunks are never overwritten.
- `export-<version>/`: final MP3, edited/final speaker WAVs, final transcript JSON/text and `edit.json` (source hashes, retained source ranges, rebuilt output timing, audio diagnosis, constrained AI replacements, sample maps, tools, loudness, warnings). Repeat exports retain older versions. Player/download URLs are bound to an immutable export version; re-export refreshes the player without reloading the page, and obsolete listening confirmations cannot approve a different version. Resuming invalidates the current export/approval; regenerate after adding audio.

The AudioWorklet renders received AI PCM into the same output buffer it records, while independently capturing microphone samples. Thus the saved AI channel contains the actual digital speaker output, not buffered/unplayed tails. Late output deltas from interrupted items are discarded. Hardware mute/failure cannot be detected; this does not prove the sound physically reached your ears.

## Recovery and honest limits

- Network/server failure: local capture continues into IndexedDB. Reconnect manually after connectivity returns; the app reboots local authentication, drains uploads and opens a new API session. Earlier API state isn't magically restored. Pending local save can be retried.
- Abrupt tab close/sleep/device failure: recover the ordered committed chunks, explicitly acknowledge any lost tail/gaps before export. Up to one uncommitted second (and anything never captured during suspension) can be lost. Missing guest audio cannot be reconstructed from a transcript.
- Resume creates a fresh capture epoch; wall-clock gaps are approximate, sample timing within an epoch is precise. Export concatenates available epochs and documents gaps, not synthesized silence or imaginary answers.
- Realtime connections deliberately end at 55 minutes (the documented session maximum is 60). The screen offers reconnect/renew while local capture continues. New connections use at most 24,000 characters of guest transcripts and **only fully played, successfully completed** AI turn transcripts (terminal response/item completion is required; audio/transcript “done” alone can also mean cancellation); incomplete/unverified AI speech is omitted. Completion and sample checks prove delivery, not perfect accuracy of provisional API text. Earlier context may be forgotten or truncated by the API, but originals remain saved. A genuinely uninterrupted 60-minute API conversation is **not yet validated**.
- Live captions are provisional and can contain unplayed AI words. Final captions are re-transcribed from cropped edited speaker audio with Whisper segment timestamps, then mapped to the final duration. Segment timing/text is estimated and needs listening review—not forced word alignment or guaranteed verbatim accuracy.
- Exports conservatively remove long shared silence, preserve guest waveforms except short padded-join fades, balance speaker loudness, retain floating-point overlap headroom until final encoding, and mix to a -16 LUFS target. No guest voice synthesis or meaning-changing edits. Default audio-aware review sends bounded, separate saved speaker WAV windows, provisional transcript hints, and exact playback facts to `gpt-audio-1.5`. A strict local plan validator can repair fully heard AI questions with starvation, move intrusive questions after an audio-validated completed prior guest answer using an actual acoustic-block anchor, never a silence-trimming union that could merge separate answers, or omit an unambiguously failed fragment only when the next guest speech is independent. Short natural backchannels and ambiguity are preserved. Replacements use independently transcribed **played** words, verified again after TTS using exact normalized word tokens (including meaningful apostrophes), never an unheard generated tail. No model commands or free edit coordinates are executed. Every guest sample remains ordered in the prepared timeline; the final shared-silence trim is separately recorded. You can disable audio review for a conservative silence/level-only export.
- Real interruptions may leave incomplete speech fragments in the conservative edit. No claim of perfect restoration, mastering, or a publication-ready result without listening. Player/download and explicit listening confirmation are provided; success does not auto-approve quality.

## Privacy and boundary

Key stays in the Python process. Browser receives no OpenAI credentials. Backend binds only `127.0.0.1:8765`, requires the exact loopback Host, rejects foreign Origins, authenticates local API calls with an HttpOnly SameSite cookie, and requires a custom header for writes. WebSocket requires same-origin cookie authentication. This is a **single-user Mac** boundary, not protection from malicious local programs or other OS users.

This is local storage, **not fully offline**: OpenAI receives necessary voice/text for interview/transcription/TTS. Data, caches, screenshots, recordings, transcripts, `.env`, and exports are ignored by Git. The repository is private. Nothing is automatically pushed or published.

## Targeted E2E validation

Acceptance/failure inventory was defined first in `ACCEPTANCE.md`. No unit-test suite was added after implementation.

```sh
# Run server first. Each script saves repeatable private artifacts under .artifacts/.
.venv/bin/python scripts/make_fixture.py     # Short paid synthetic test voice fixture; cached
.venv/bin/python scripts/e2e_backend.py      # 3600 accelerated one-second HTTP chunks + source hash
# Restart the server, then:
.venv/bin/python scripts/e2e_backend.py --verify-restart
npm run e2e                                # Short real paid Realtime/STT/render/browser path
node scripts/e2e_polling.mjs                # Delayed/out-of-order saved-session UI reads (no paid API)
node scripts/e2e_failures.mjs               # Mic denial, upload outage, crash/recovery, suspension
.venv/bin/python scripts/audit_audio.py      # Exact played PCM / interruption / guest preservation / levels
.venv/bin/python scripts/e2e_two_voice.py    # Paid two-voice known faults, actual audio diagnosis/edits
.venv/bin/python scripts/render_evidence.py  # Reproducible labelled before/after waveform SVG
.venv/bin/python scripts/e2e_export_lifecycle.py # Overlap/headroom + stale export/reapproval
```

`e2e_failures.mjs` can run directly or export `runFailures(browser)` for persistent Playwright QA: microphone denial, failed chunk uploads, abrupt tab-close recovery, gap acknowledgment and suspended-engine stop. Browser trace/screenshots, JSON assertions, original source DBs and edit manifests are the evidence. Test microphones are synthetic, never Hieu's real microphone. The accelerated hour validates storage/sample order, **not** an hour of live AI conversation or physical device reliability.

Current selected models were verified against official documentation and actual account access: `gpt-realtime-2.1`, `gpt-4o-transcribe` for provisional captions, `whisper-1` for timestamped export transcription, `gpt-audio-1.5` for saved-audio diagnosis, `gpt-transcribe` for independent played-word verification, and `gpt-4o-mini-tts` / `marin` for interviewer-only delivery repair. Relevant docs: [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations), [Realtime WebSockets](https://developers.openai.com/api/docs/guides/voice-websockets?api=realtime), [File transcription](https://developers.openai.com/api/docs/guides/speech-to-text), [Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech).

The two-voice test preserves a naturally timed Cedar guest and Marin interviewer (neither is a clone of Hieu), injects an intrusive question with a tight one-second answer boundary, 500 ms starvation, isolated 400 ms starvation, and a failed cut-off with an unheard tail, and retains a natural backchannel. `.artifacts/two-voice/` contains raw damaged tracks/mix, ground-truth fault manifest, actual model audio input hashes/responses, validated decisions, polished audio/transcript and independent sample/transcription comparison. Hosted models can misclassify audio; confidence/metadata constraints do not make them infallible. Ambiguous cases remain for human listening review.
