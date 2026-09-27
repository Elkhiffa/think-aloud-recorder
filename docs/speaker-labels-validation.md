# Speaker labels and recorder recommendation — 2026-09-27

## Delivered behavior

New Qwen file-transcription jobs request `diarization_enabled=true`. The supported app model is `qwen-audio-3.0-asr-flash-filetrans`. The provider's sentence-level `speaker_id` is retained unchanged in the transcript JSON and Markdown. The independent mono microphone track remains the only ASR input; the playback mix is not used for speaker analysis.

The recorder is a recommendation, not a voice identity match. Speaking duration contributes 75% of the score and typical microphone level contributes 25%. Word intervals are used when available, pauses and duplicate intervals are excluded, and overlapping speakers' intervals are excluded from level attribution. A duration-weighted median RMS level limits the effect of isolated loud sounds. The audio decoder streams once with bounded histograms rather than loading an entire recording into memory.

A recommendation needs at least two seconds of speech and measurable audio. Close scores are marked as uncertain; missing or silent audio does not produce a confident identity. Recorded level does not establish microphone distance, and automatic gain or background voices can affect the recommendation.

In the review, the recorder summary opens a dialog with original speaker numbers, speaking duration, speech share, relative typical volume, and a short preview of each voice from the isolated microphone audio. The user can select another recorder, explicitly leave the recorder unassigned, or restore the automatic recommendation. All transcript text remains available.

Measurements and the automatic recommendation are saved in `录像.whisper.json.speaker_analysis`. A native manual choice is saved in `session.json.recorder_speaker`, bound to a hash of this transcript's words, times and speaker IDs. Re-transcription cannot silently reuse an earlier choice with different speaker IDs. Other open reviews refresh the annotation. A standalone portable HTML review explicitly offers temporary choices only.

Old transcripts without speaker IDs remain unlabelled. Updating the app does not upload or re-transcribe them. Users can request re-transcription if they want speaker labels. Resuming an unfinished cloud job keeps its original request profile to avoid abandoning an already submitted or uncertain billable task after the upgrade.

## Provider contract

- [Recorded speech HTTP API](https://help.aliyun.com/zh/model-studio/fun-asr-recorded-speech-recognition-http-api): diarization flag and sentence-level speaker IDs; mono input required.
- [Recorded speech guide](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide): model capabilities and usage.
- [ASR models](https://help.aliyun.com/zh/model-studio/asr-model): distinguish the supported 3.0 model from the older similarly named `qwen3-asr-flash-filetrans`.

The provider recommends at most two hours for diarization. This change still submits a whole recording as one task; longer jobs show a warning and may fail or time out. It does not add chunking, cross-task speaker matching, or automatic extra paid submissions.

## Validation

- Full Python suite: 537 tests, 534 passed and 3 environment-dependent skips (`work/speaker-python-final.log`).
- Ten focused speaker tests use generated mono audio, real decoding and local API calls. They cover duration/level scoring, loud spikes, ambiguous or silent audio, word gaps, overlap, ID preservation, saved manual choices, reopening, reset, stale transcript rejection and pending-task upgrade recovery. HTTP tests use a synthetic transport, not the cloud.
- Speaker browser acceptance: 9/9 checks in actual headless Edge using the production page and a simulated native bridge. Independent audio preview, keyboard save, save failure, unassigned/reset choices, metadata refresh, narrow/dark layout, temporary portable choices and legacy transcripts passed (`work/speaker-review/acceptance.json`).
- Review aspect regression: 14/14; input timeline regression: 32/32. Review UI unit checks and `git diff --check` passed.
- Packaged native WebView2 smoke: a clearly labelled synthetic fixture loaded the production page with the real packaged API and acknowledged readiness with no error. Its native accessibility tree exposed the automatic recorder summary and both correctly labelled transcript rows. Native interactive click/save/reopen acceptance could not be completed: Computer Use repeatedly returned `failed to activate captured window`, including after re-binding the window. Native persistence is covered separately by the Python API tests; browser interaction is covered by browser acceptance. This is not a claim of successful native clicking.
- No real cloud recognition or real-voice diarization accuracy test was performed. No personal recordings were uploaded during validation.

## Local installation

Installed `0.6.0-preview.6+local.20260927.4` into `F:\ThinkAloud` through the transaction updater and explicit file allowlist. The package inventory contains 7,341 files; this update changed 11 files including its manifest. The updater verified the installed inventory and kept the previous-version backup. Before/after preservation snapshots matched for user settings, credentials, vocabulary and the recording library.

After the user closed the old application, the updated app was reopened successfully. Its native UI reports version `.20260927.4`, library `F:\think-aloud-database` and the existing 17 sessions. The current preset still reports that recording conditions are not met; this smoke check verifies startup/library loading, not device readiness or a new recording.

Transaction receipt: `F:\CodexHome\ThinkAloud-input-fix-20260926\transaction-speaker-roles\job.json`. Native observation: `work/speaker-review/native-observation.json`. Synthetic fixtures and receipts stay in ignored work directories and are not packaged with user data.
