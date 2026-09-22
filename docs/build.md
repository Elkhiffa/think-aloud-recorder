# Build and reconstruction

## What is reproducible

`scripts/build_portable.py` deterministically packages an already prepared Windows
x64 runtime/OBS seed: sorted paths, fixed ZIP timestamps/permissions, fixed native
launcher ZIP metadata, explicit root-file allowlist, and SHA256 inventories. With
the same inputs, Python/compressor implementation and distlib launcher stub, two
builds produce identical bytes. This is **not** a claim that today's seed can be
rebuilt byte-for-byte from only `requirements-lock.txt`.

The current seed was copied from a private portable installation into this
isolated checkout. Its Python reports 3.12.10 x64; OBS reports 32.2.2; pywebview is
6.2.1. Package version pins do not pin wheel hashes or all native transitive
dependencies. The archive manifest records the exact bytes actually shipped.
No private installation paths are written into generated metadata.

## Prepare a clean Windows seed

Use an isolated Windows x64 build VM/account and a new staging directory. Do not
install packages globally on a user's working computer.

1. Obtain the official **full** Python 3.12.10 x64 Windows installer from
   https://www.python.org/downloads/release/python-31210/ . Verify its signature
   and upstream integrity material. Install it within the isolated builder to
   `<stage>/runtime` without PATH changes or a global launcher. Include pip and
   Tcl/Tk. The embeddable-only ZIP does not contain Tcl/Tk and is not an equivalent
   seed for the application's error dialog.
2. In that private builder, run `<stage>/runtime/python.exe -m pip install --no-cache-dir -r requirements-lock.txt`.
   Capture wheel filenames, SHA256 values, package licenses, and upstream binary
   source materials. Current version pins reproduce version intent, not an
   authenticated byte-for-byte wheel set. Test before replacing the accepted seed.
3. Preserve `python.exe`, `pythonw.exe`, Python DLLs, standard library, `DLLs`,
   Tcl/Tk, installed site-packages and their license metadata. Supply
   `runtime/python312._pth` with the following lines, including the final
   `import site`; the `..` line makes the adjacent application source importable:

   ```text
   .
   Lib
   DLLs
   Lib/site-packages
   ..
   import site
   ```

4. Extract the official OBS Studio 32.2.2 Windows x64 portable distribution into
   `<stage>/tools/obs`. Retain `bin`, `data`, `obs-plugins`, notices and a blank
   `portable_mode.txt`. Never copy an existing user's OBS `config` directory.
   Validate the executable version and preserve upstream asset checksums.
5. Review Microsoft VC runtime and WebView2 SDK redistribution terms for the
   actual DLLs included. The current WebView2 SDK 1.0.3856.49 DLLs have now been
   matched by SHA256 to the official NuGet package, whose BSD-style LICENSE and
   third-party NOTICE are archived verbatim. Preserve both with the binaries.
   VC DLL redistribution follows the applicable Visual Studio license section 4
   and unmodified redistributable-file list; its runtime end-user license is a
   separate document and does not itself authorize republication.
   WebView2 browser runtime is a separate system prerequisite;
   the package does not claim to install it or bundle Obsidian.
6. Run `runtime/python.exe scripts/fetch_input_runtime.py --root <stage>` to
   prepare the pinned official SDL2 2.32.10 x64 controller runtime. It downloads
   binary/source archives into the stage build cache, validates fixed SHA256
   values, and writes only `tools/input/SDL2.dll`, its provenance, and the exact
   upstream zlib license. No global installation or PATH changes. Existing
   differing files are preserved and cause a failure. Add the verified source
   archive to a successor dependency-source manifest before packaging.
7. Copy the application's allowlisted source/assets/licenses into `<stage>`.
   Model weights remain optional. Run the tests and native launcher checks below.

## Acquire source materials

From the prepared checkout:

```powershell
runtime/python.exe scripts/fetch_runtime.py --outdir build/dependency-sources
```

Despite the historical script name, this command only downloads source materials
and captures local FFmpeg version/configuration; it never installs a runtime.
It obtains and hashes:

- Official OBS `OBS-Studio-32.2.2-Sources.tar.gz`: 16,660,601 bytes, SHA256
  `ec81fb66b03e75ddb3076b576f62679c39262e0e9960cef3e17a40dc5d68e6b4`.
- FFmpeg source at exact commit `b08d7969c550a804a59511c7b83f2dd8cc0499b8`,
  identified by https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/7.1 .
- A `source-manifest.json` containing URLs, revisions, sizes, source digests,
  local FFmpeg binary digest, and unresolved redistribution requirements.
- `ffmpeg-buildconf.txt` captured from the actual bundled executable.

Partial downloads are retained. If acquisition failed with a `.part` file, choose
a fresh `--outdir`; the fetcher does not overwrite or delete evidence. The OBS
asset's hash is independently available in the upstream GitHub release API.

The current Gyan static FFmpeg build enables GPLv3 and many external libraries.
Its core source archive and configure line are now present, but matching external
library source snapshots and exact build scripts are not yet archived. Review the
OBS dependency and binary-wheel source/license coverage too. Until those concrete
gaps are resolved, `redistribution_ready` remains false; do not merely toggle the
flag to bypass review. Add reviewed source archives and evidence to a successor
source manifest once they are available.

Create a successor bundle with the exact Microsoft SDK/license evidence without
altering the original source records:

```powershell
runtime/python.exe scripts/fetch_runtime.py --supplement-existing build/dependency-sources --outdir build/dependency-sources-v2
```

This verifies the pinned official WebView2 NuGet package, matches all included SDK
DLLs by SHA256, and extracts its original LICENSE and NOTICE. It also obtains
Microsoft's full VC runtime end-user terms and VS Community 2022 distributor
terms. The new manifest retains the predecessor manifest digest. A byte mismatch
or existing successor manifest stops the operation; it never replaces the prior
evidence. Pass `--source-dir build/dependency-sources-v2` to the packager to include
this successor material. Put the extracted WebView2 LICENSE/NOTICE beside the
software notices as well when assembling the final release.

The concrete outstanding source blocker is the Gyan FFmpeg 7.1 external libraries
and exact build recipe. Its maintainer points script requesters to generic MABS,
not a versioned recipe for this binary. Changing the FFmpeg binary or replacing
its work with PyAV/OBS libav would require media regression work; it is not a
notice-only change. In particular, preserve all-stream recovery, selected video
plus mixed-audio remux, microphone-only track selection, asynchronous resampling
with `first_pts=0`, FLAC encoding and 600-second chunk timing. Do not replace a
validated media path merely to remove a license label without proving those
behaviors and the replacement's own matching-source materials.

## Build a private evaluation candidate

```powershell
runtime/python.exe -m unittest discover -s tests
runtime/python.exe scripts/build_portable.py --outdir dist/candidate-001 --candidate
```

The command requires a new output path and never overwrites an existing archive.
Outputs are the Windows portable ZIP, a separate dependency-sources ZIP, and a
SHA256SUMS file. Both ZIPs must travel together during evaluation. The software
contains `package-manifest.json`, its dependency source manifest, application MIT
license, and upstream notices. A candidate suffix and metadata explicitly mark
the uncompleted public redistribution review.

Once complete corresponding-source and redistribution evidence has been reviewed,
the same build command **without** `--candidate` produces the public-named archives.
Without that evidence the command refuses a public build. This script does not
publish, upload, sign, or deploy an archive.

The native `ExperienceRecorder.exe` uses pip's vendored distlib x64 GUI launcher
and a deterministic appended `__main__.py` which imports `portable_entry:main`.
Its shebang points to `<launcher_dir>\runtime\pythonw.exe`, so launch works from
another working directory. Build using the supplied 64-bit
runtime. No absolute developer-machine Python path is embedded.

## Validation and boundaries

- Synthetic packaging tests inject fake credentials, models, OBS settings,
  runtime caches and vault recordings into a temporary seed and assert that none
  enter the archive. They also verify two-build byte equality, source hashes,
  launcher metadata and the incomplete-source release gate.
- The packager streams large inputs rather than retaining runtime/OBS in memory.
  It refuses symlink/path escapes, validates source hashes, checks ZIP CRCs, and
  emits per-file digests. Models, saved settings and logs are outside its allowlist.
- Extract the real candidate to a fresh directory with a different path (including
  spaces/Chinese characters). Run `ExperienceRecorder.exe --self-check`, inspect
  its report, then perform the real UI/OBS synthetic recording, recovery and review
  checks. Passing fixture tests does not establish these native/live results.
- External Obsidian installation and provider/GPU behavior require their own real
  checks. A successful archive is not a claim of public release readiness.
- Input recording uses the Windows Raw Input API and portable SDL2 controller
  events. Synthetic focus/timing tests and a listener lifecycle smoke do not
  establish physical Xbox/DualSense compatibility. Keep actual device findings
  separate in `docs/input-capture-validation.md`.
