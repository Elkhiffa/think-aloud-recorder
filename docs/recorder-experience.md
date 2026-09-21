# Recorder experience contract

The daily screen contains one primary action: Start recording. A compact preset
selector chooses the game/project configuration; New/Edit are secondary actions.
Each preset independently stores output vault, capture mode/target, microphone,
quality, transcription provider, language, vocabulary and Obsidian path. Shared
model files and encrypted service credentials remain application resources.
The saved output
folder appears as secondary text. Recent sessions live in a collapsible area with
its own scroll region. Settings are a small secondary action. No dashboard,
technical track diagrams, permanent engine checklist, model cards, or sidebar.

First use opens a three-step setup wizard:
1. Preset name, target window/display and microphone. Suggest the game/project
   name as the preset name. Actual devices are loaded.
2. Recording quality and transcription: record only, local model, or Qwen.
   Model import/download and token entry appear only for their chosen mode.
   Language and vocabulary are optional advanced fields.
   Vocabulary is file-first: select multiple TXT/SCEL dictionaries, see filenames
   and word counts, and remove individual entries. Merge overlapping words without
   removing words still supplied by another file or manual input. Manual words live
   in a secondary disclosure. Link to the official Sogou dictionary download site
   in the system browser, without sending the preset/project name. Dictionary word
   snapshots are saved per preset, so moving source files does not break recording.
   Cancelling selection or any file parsing failure preserves the current draft.
3. Output folder, optional installed Obsidian path, and a short summary. Save the
   choices as a named reusable preset; do not start recording here. First setup
   and New preset use the same wizard. Edit starts from the selected preset.

Fresh installations suggest `<app parent>/think-aloud-database`, outside the
versioned application folder. The database is created only when the user finishes
setup. If that default directory already exists, step 3 asks whether to reuse it
or choose another folder. Do not inspect/recover its sessions or install plugins
before this first-use confirmation. Confirmation is tied to the selected path and
cleared on cancellation. An explicitly chosen folder also counts as confirmation.
Recheck existence at save: if a directory appeared since the wizard snapshot, ask
for reuse instead of silently adopting it. A same-named file requires a different
folder. Existing preset paths and existing data are not relocated. New/edit preset
flows after setup retain the selected saved location without repeated prompts.

Existing users can reopen this wizard. Unsaved edits do not alter the saved
configuration. Cancel returns to the saved configuration. A new preset must not
overwrite an existing preset. Switching presets also switches the displayed vault,
session list and readiness result. On first use, cancel
leaves Start disabled until setup has been saved. Finishing setup saves valid
choices even if their selected device later becomes unavailable.

Before enabling Start, the backend checks the saved configuration. When blocked,
show specific red text adjacent to the disabled Start button: chosen window or
process unavailable, microphone disconnected, local model missing, cloud key
missing/unreadable, output folder inaccessible or insufficient space, or OBS
unavailable/busy. Backend state is authoritative. Never infer device availability
from merely saved values. Recheck on launch, periodically while idle, after saving,
and immediately before recording. A manual recheck is secondary, shown when needed.

Recording shows actual elapsed time and changes the same primary action to Stop
and save / Stop and transcribe. Disallow changing capture settings during recording
or capture start/save. Once OBS confirms stop and the original file is saved and
validated, transcription runs in a separate background queue and Start becomes
available after the saved preset passes readiness again. Background transcription
must not lock preset selection or replace the active recording's timer, Stop
button or errors. Process one session at a time; later sessions wait in the queue.
Show a compact processing/queued count beside Recent sessions, and each session's
own progress on its row. Keep progress visible even after switching output vaults.
Failures belong to the failed session and do not interrupt another recording.
Duplicate processing, review of files being rewritten and export are disabled for
that session; its folder remains accessible. Closing during queued/running work
retains the existing background/minimize protection. Interrupted queued work stays
recoverable without automatically uploading again on restart.
Background setup and model progress remain visible in the
wizard, not the daily screen. Report only actionable failures on the daily screen.
Cloud recording consent is established by the explicit wizard choice and its
upload disclosure; do not repeatedly ask the same question on every recording.

Session rows expose review, pending-processing and failure states concisely.
Details/actions expand within the session area; long lists scroll without hiding
the recording action. Obsidian is primary; HTML is a secondary fallback in details.
Preserve export, retry, raw files and cloud task recovery without permanent clutter.

Acceptance: first-run setup -> save -> minimal home; cancel/reopen retains saved
configuration; disappearing source/token disables Start with the actual reason;
restored conditions allow Start after verified refresh; setup data is not lost on
polling; long sessions stay inside scroll area; keyboard navigation, narrow window
and dark theme remain usable. No real device capture during agent validation.
Concurrency acceptance: while A's processing is deliberately blocked, start and
stop B; B queues without another processor, A's progress/failure cannot change B's
capture activity, and each task retains its admitted preset and output directory.
