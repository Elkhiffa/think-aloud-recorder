# Recorder experience contract

The daily screen contains one primary action: Start recording. A compact preset
selector chooses the game/project configuration; New/Edit are secondary actions.
Each preset independently stores output vault, capture mode/target, microphone,
quality, transcription provider, language, vocabulary. Shared
model files and encrypted service credentials remain application resources.
The saved output folder wraps onto as many lines as needed. A compact recording
strip sits above the full-width experience list at all window sizes.
The experience list is always visible and has its own scroll region; its heading is not a disclosure control. Each session expands to reveal secondary actions. Settings are a small secondary action. No dashboard, technical
track diagrams, permanent engine checklist, model cards or navigation sidebar.

First use opens a four-step setup wizard:
1. Explain think-aloud recording with observation, interpretation, planned action and reflection examples. Natural pauses, uncertainty and changing one's mind are welcome. Advance without saving or starting recording.
2. Preset name, target window/display and microphone. Suggest the game/project
   name as the preset name. Explain that a preset saves the recording settings;
   the same game and devices normally need setup only once. Select it to record,
   use the gear to edit it, or create another preset for a different configuration.
   Actual devices are loaded.
3. Recording quality and transcription: record only, local model, or Qwen.
   Model import/download and token entry appear only for their chosen mode.
   Language and vocabulary are optional advanced fields.
   Vocabulary is file-first: select multiple TXT/SCEL dictionaries, see filenames
   and word counts, and remove individual entries. Merge overlapping words without
   removing words still supplied by another file or manual input. Manual words live
   in a secondary disclosure. Link to the official Sogou dictionary download site
   in the system browser, without sending the preset/project name. Dictionary word
   snapshots are saved per preset, so moving source files does not break recording.
   Cancelling selection or any file parsing failure preserves the current draft.
4. Output folder and a short summary. Save the
   choices as a named reusable preset; do not start recording here. First setup
   and New preset use the same wizard. Edit has three numbered settings steps,
   excludes the recording-method guide and starts from the selected preset.

Fresh installations suggest `<app parent>/think-aloud-database`, outside the
versioned application folder. The database is created only when the user finishes
setup. If that default directory already exists, the final step asks whether to reuse it
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
show specific red text above the disabled Start button in the same slot that
otherwise shows readiness. Ready and blocked messages are mutually exclusive;
pending requests and device checks have their own truthful status. Historical
operation failures must not replace a subsequently recovered ready state; show
these as transient notices. Examples of blockers: chosen window or
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
that session; its folder remains accessible. Closing during queued/running work asks whether to stop recording, save, and wait
for admitted processing to finish before closing. Never silently minimize. Idle
readiness checking must not veto close. Interrupted queued work stays
recoverable without automatically uploading again on restart.
Background setup and model progress remain visible in the
wizard, not the daily screen. Report only actionable failures on the daily screen.
Cloud recording consent is established by the explicit wizard choice and its
upload disclosure; do not repeatedly ask the same question on every recording.

Session rows expose review, pending-processing and failure states concisely.
Details/actions expand within the session area; long lists scroll without hiding
the recording action. Review opens an independent resizable native WebView2 window with the local Plyr
player. Multiple viewers have independent playback; closing the recorder leaves
viewers alive. The last window closes the application. Keep video fixed while
the transcript pane scrolls, including narrow windows. Click text to seek/play;
use arrow keys for 15-second steps, and Space for play/pause. Inputs keep normal
keyboard editing. Below the video, put Open folder beside a split Copy button.
The main copy action uses the current session folder; the arrow offers individual
video/transcript JSON paths and document actions. Successful copy replaces the
icon with a check and shows `copied!` for two seconds without changing the layout.
Constrain the disclosure to the visible window and scroll it when necessary.
Keep playback shortcuts working without a permanent hint row. Export a self-contained offline HTML
viewer. Existing sessions use the current template without re-transcription or
rewriting notes. No Obsidian setup, plugin install, or plugin export.
Preserve export, retry, raw files and cloud task recovery without permanent clutter.

Acceptance: first-run setup -> save -> minimal home; cancel/reopen retains saved
configuration; disappearing source/token disables Start with the actual reason;
restored conditions allow Start after verified refresh; setup data is not lost on
polling; long sessions stay inside scroll area; keyboard navigation, narrow window
and dark theme remain usable. No real device capture during agent validation.
Concurrency acceptance: while A's processing is deliberately blocked, start and
stop B; B queues without another processor, A's progress/failure cannot change B's
capture activity, and each task retains its admitted preset and output directory.

The method guide is also available from the home header without opening a configuration draft. Editing an existing preset starts at devices and Back cannot enter the guide; a new preset includes the guide. The four speaking prompts are labelled excerpts, not a required sequence. Number only the actual setup steps. Use warm paper surfaces, a restrained brick-red accent, 15–16 px body/action text and 13–14 px supporting text. In review, align timestamps with their original words; very narrow transcript panes can put the timestamp above the words. Reduce spacing rather than text size on small windows. Main and review surfaces offer light and dark themes.

Visual identity: warm white `#FCFAF5`, parchment recording band `#EDE7DB`, ink
`#292722`, brick-red actions `#B64B37`, thin warm-gray borders and 5–6 px control
corners. Use the original quote/bookmark mark with a serif Think Aloud wordmark;
Chinese controls remain clear sans-serif. Recording and experience-list headings
share 22 px / 600. The screen contains the actual application window only, without
design-board captions or state-example panels. Wizard overlays show the real home
beneath them, with one scrolling body and fixed header, step rail and footer.
Selected transcript rows use a pale warm fill, red timestamp and a red separator
between time and words; reserve its space in unselected rows to prevent shifting.
