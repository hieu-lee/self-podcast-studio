# Self Podcast — local prototype

A browser interview studio for Hieu: type a topic, explicitly permit recording, talk with an AI interviewer, stop/save, then export an audio episode and matching speaker-labelled transcript. Polished audio can then become an illustrated interactive video. No publishing, accounts, hosting, or elaborate editor.

## Start

Requirements: macOS, Python 3.10+, Node 20.19+ (or 22.12+), FFmpeg/ffprobe on PATH, Chrome, an OpenAI API key with paid Realtime/audio access. The first start installs pinned Python/Node dependencies and builds the UI.

```sh
cd /Users/hieu.leduc/Documents/ChatGPT/self-podcast
# OPENAI_API_KEY must already be set in your shell environment.
./start.sh
```

Open **http://127.0.0.1:8765**. Keep the terminal, browser tab and Mac awake. Use headphones. Nothing records until you check consent and press Start; Resume also needs consent. For an already running instance, just open the URL. Stop the server with Ctrl-C **after** saving the recording. Optional: `SELF_PODCAST_DATA=/absolute/private/path` changes local storage; `SELF_PODCAST_MODEL` changes the Realtime model.

The starter topic is **“Can AI discover new mathematics, or only recombine what humans already know?”** with three exploratory questions. The interviewer follows actual answers, one question at a time; the outline is not a rigid script.

## English / Vietnamese episodes

Choose **Podcast language → English or Tiếng Việt** on the setup screen **before Start**. English remains the default. You can enter the topic in either language; when Tiếng Việt is selected, the preparation prompts, spoken interviewer questions/follow-ups, guest caption hints, saved-audio diagnosis, interviewer-only repairs, and final transcription use Vietnamese—not an English interview translated afterward. Answer naturally in Vietnamese; English names/technical terms can remain as spoken.

Language is fixed when an episode is created and shown in live/saved views. Resume/reconnect/export use that episode's language regardless of the selector for a new episode. Existing recordings without a language field read as English without rewriting their recordings or older exports. No guest voice is synthesized or translated. Repair verification keeps Vietnamese tone/vowel marks and đ; equivalent NFC/NFD encodings agree, but different accented words do not.

Vietnamese speech support is documented in [official OpenAI TTS documentation](https://developers.openai.com/api/docs/guides/text-to-speech), which also notes voices are optimized for English. Account/model access and actual Vietnamese audio are tested, not assumed equivalent across models. Human listening must still check pronunciation, accent, names, transcription and joins; no promise of perfect/native regional pronunciation or a validated full Vietnamese hour.

Focused Vietnamese validation (paid requests, synthetic voices only):

```sh
.venv/bin/python scripts/make_fixture.py --language vi
PYTHONPATH=. .venv/bin/python scripts/e2e_languages.py # Boundary/Unicode + legacy English setup, no human mic
node scripts/e2e_browser.mjs --vietnamese             # Actual Vietnamese Realtime capture/STT/export
.venv/bin/python scripts/e2e_vietnamese_transcript.py # Immutable native saved-audio caption re-export
.venv/bin/python scripts/audit_audio.py --language vi # Played PCM/guest preservation + independent AI language
.venv/bin/python scripts/e2e_two_voice.py --language vi
.venv/bin/python scripts/render_evidence.py --language vi
```

The Vietnamese fault fixture verifies a 400ms isolated interviewer repair and exact guest sample preservation. Its model misclassified an intrusive overlap and gave low confidence to a failed fragment; the unchanged local safety guards preserved/flagged those instead of forcing unsafe edits. This is not proof of automatic repair of every Vietnamese fault. Independent guest transcription scored about 97.5% accented-token similarity in that synthetic fixture; tone-word errors can remain in captions and need listening review.

Artifacts are separate in ignored `.artifacts/vietnamese/` and `.artifacts/two-voice-vi/`. The language-boundary E2E reads the initial saved synthetic English browser fixture when available; otherwise it simulates missing legacy metadata only in a new empty synthetic episode owned by the test. It never edits a real user recording.

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
- Live captions are provisional and can contain unplayed AI words. Final captions are re-transcribed from cropped edited speaker audio, never translated from English. English uses Whisper segment estimates; Vietnamese uses `gpt-transcribe` for improved native text with acoustic crop-boundary timestamp estimates (not word alignment). Timing/text remains estimated and needs listening review—not guaranteed verbatim accuracy.
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

Current selected models were verified against official documentation and actual account access: `gpt-realtime-2.1`, `gpt-4o-transcribe` for provisional captions, `whisper-1` for English timestamped export transcription, `gpt-transcribe` for native Vietnamese export captions (acoustic-crop estimates), `gpt-audio-1.5` for saved-audio diagnosis, `gpt-transcribe` for independent played-word verification, and `gpt-4o-mini-tts` / `marin` for interviewer-only delivery repair. Relevant docs: [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations), [Realtime WebSockets](https://developers.openai.com/api/docs/guides/voice-websockets?api=realtime), [File transcription](https://developers.openai.com/api/docs/guides/speech-to-text), [Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech).

The two-voice test preserves a naturally timed Cedar guest and Marin interviewer (neither is a clone of Hieu), injects an intrusive question with a tight one-second answer boundary, 500 ms starvation, isolated 400 ms starvation, and a failed cut-off with an unheard tail, and retains a natural backchannel. `.artifacts/two-voice/` contains raw damaged tracks/mix, ground-truth fault manifest, actual model audio input hashes/responses, validated decisions, polished audio/transcript and independent sample/transcription comparison. Hosted models can misclassify audio; confidence/metadata constraints do not make them infallible. Ambiguous cases remain for human listening review.

## Polished audio → autonomous interactive video

Export defaults to **Speaker balance & cautious noise/cough cleanup**. Both real speaker tracks receive bounded adaptive gain (−10 to +9 dB, three-second smoothing, no full upward speech gain on quiet-room windows), gentle compression and the existing measured −16 LUFS master / −1.5 dBTP target. Original recordings never change. Noise candidates are DSP-anchored, actually heard by `gpt-audio-1.5`, independently heard again, then vetoed if `gpt-transcribe` detects words. Only verified speech-free unwanted events with ≥0.95 independent safety confidence receive faded −36 dB masks. Breath, laughter, syllables/names, overlapping speech and uncertainty are protected. This is conservative attenuation, **not perfect denoising**; many noises remain. `polish.json` and `noise-evidence.json` document masks, evidence, source hashes, levels and time maps. Final captions are re-transcribed from the actual final speaker audio. Disable polishing to retain the earlier conservative export behavior.

After that export, **Make video from this audio** starts a version-bound background job. It listens to the actual final soundtrack and reads its transcript/independent final-audio word estimates. A real authenticated `codex exec` producer authors complete, topic-specific interactive HTML and a typed action storyboard. A fresh isolated Chromium page executes real clicks/drags and records only the disposable app. No fixed slideshow or fixture rankings are built into production. Rankings start neutral, explicit later revisions become real drags, and uncertain items stay unranked. Generated illustrations use exactly **`gpt-image-2.5-sunburst`**, via the installed imagegen skill CLI; unavailable access fails honestly, with no substitute. Other topics can use editable code-native diagrams. The implementation currently selects disposable apps/generated art, **not arbitrary existing websites or local projects**.

The entire final episode is converted once to AAC and packet-copied into H.264 MP4, with full decode, duration/ending and decoded-waveform comparison. Download MP4, native estimated captions, storyboard, provenance and **editable project & replay evidence** (HTML, generated assets, screenshots, typed actions, word estimates and replay controller). Real actions use audio decision-word anchors; captions retain native final text and use exact-token matching anchors where possible, with explicitly estimated fallback timing. Always listen/watch before approval; recognition and timing can be wrong. Approval binds both immutable audio version and video attempt. Re-export/resume invalidates the current video/approval, not old artifacts. Cancel stops subprocess groups; abrupt studio death is guarded by a parent-death supervisor. A unique inherited per-command marker retains ownership through immediate detachment/reparenting; cleanup verifies process birth identity, and environment contents are never logged, saved or sent to models. Only trusted production commands run; this is not containment for arbitrary executables deliberately stripping ownership. Restart reports interrupted jobs and allows a new attempt. Heavy video work stays outside the API/recording lock; one video worker runs at a time.

When upgrading an existing checkout/virtualenv, run `.venv/bin/pip install -r requirements.txt` once before restarting; `start.sh` only installs dependencies when creating a new environment.

Runtime prerequisites: the already installed Playwright Chromium/Node/FFmpeg, an authenticated Codex CLI (`codex login`), and the imagegen skill CLI at `~/.codex/skills/.system/imagegen/scripts/image_gen.py`. `requirements.txt` pins the SDK used by that bundled CLI. Optional trusted host overrides: `SELF_PODCAST_CODEX_BIN` (direct executable when a wrapper cannot work in a fresh HOME), `SELF_PODCAST_IMAGE_CLI` (installed bundled CLI path), `SELF_PODCAST_VIDEO_MODEL` (Codex producer model, default `gpt-6-astra`). The raster model is **not** overridden. API keys never enter the producer's environment; a temporary private Codex authentication home is removed afterward. No user plugins/MCP/skills or shell tools are enabled for the producer. The app never executes model-generated shell commands. HTML has restrictive CSP, no service workers/permissions/private profile, and a declared-asset-only request allowlist. A strict loopback HTTP proxy serves only those assets, refuses CONNECT tunnels, forces WebRTC away from direct UDP, and disables DNS resolution (except the literal proxy loopback); the same policy ships in the replay controller. This closes transport paths that CSP/HTTP routing alone do not cover. It cannot use the studio API or fetch external content. Producer prompts are supplied through a private regular-file stdin, so even a stalled reader remains cancellable/timed out. This is a local single-user workflow, not a general-purpose hardened untrusted-code service or unrestricted `--yolo` machine operator.

Focused paid/synthetic E2Es (no human microphone):

```sh
# With the studio running; use the SAME SELF_PODCAST_DATA if configured.
.venv/bin/python scripts/e2e_production.py --language vi
.venv/bin/python scripts/e2e_production.py --language en
.venv/bin/python scripts/audit_production.py --language vi
PYTHONPATH=. .venv/bin/python scripts/e2e_video_safety.py
PYTHONPATH=. .venv/bin/python scripts/e2e_video_midflight.py
.venv/bin/python scripts/e2e_job_process.py
node scripts/e2e_video_ui.mjs
node scripts/e2e_polling.mjs
# After renderer-only changes, avoid repeating paid audio polish:
.venv/bin/python scripts/e2e_production.py --language vi --reuse --video-only
```

Evidence is private under `.artifacts/production/<language>/` and the immutable export/job directory. Fixtures vary speaker volumes and contain isolated public-domain coughs ([stilgar source/license](https://commons.wikimedia.org/wiki/File:Short_coughs.ogg)), a synthetic beep, speech-overlapping noise, uncertainty, laughter and an explicit ending. Audits compare prepared PCM outside masks exactly, prove accepted masks avoid fixture speech, measure actual attenuation/active-window level spreads, inspect encoded MP4 frames, and verify exact-model image hashes/project archives. Safety E2E uses actual isolated process death and hostile Chromium capture, plus real HTTP cancel/retry/stale approval/resume on **new test-owned** metadata with imported verified synthetic media. It does not claim a new polish run for that imported media.

Limits: short English/Vietnamese production fixtures are not a validated hour-long production run. Capture currently runs approximately real-time; audio inspection makes per-candidate hosted requests and can be slow/costly on long or noisy episodes. Text-model context and episode scene/action bounds can fail large jobs rather than fabricate output. Hosted model decisions are fallible; conservative gates do not prove perfect semantic preservation. No subjective human listening approval, real-device hour endurance, third-party project demonstrations or publishing are claimed.
