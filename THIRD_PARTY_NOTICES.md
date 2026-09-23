# Third-party components and distribution status

Experience Recorder application source is MIT licensed; see `LICENSE`. This does
not change the licenses of the independently bundled components below.

The prepared binary assembly is accompanied by a dependency-sources ZIP containing
hashed source archives, fixed recipes, patches and original notices. The exact
material-review status and any open items are recorded in
`dependency-source-manifest.json`; candidate builds are not public releases.
Runtime acceptance and the publisher's third-party distribution obligations are
separate from source-material collection. Preserve the companion archive when
distributing the software; the application's MIT license does not replace these
third-party terms.

| Component | Version / identification | Notice and source |
| --- | --- | --- |
| CPython | 3.12.10, Windows x64 | `licenses/Python.txt`, `runtime/LICENSE.txt`; https://www.python.org/downloads/release/python-31210/ |
| distlib native launcher | Stub supplied by the builder's pip vendored distlib | `licenses/distlib.txt`; the per-file package manifest records the generated launcher digest |
| OBS Studio | 32.2.2, official Windows x64 executable | GPL-2.0-or-later, `licenses/OBS-GPL-2.0.txt`; accompanying `OBS-Studio-32.2.2-Sources.tar.gz` is the official release source asset, including its build materials/submodules |
| FFmpeg CLI from official OBS dependencies | n8.1.2, obs-deps 2026-07-15, Windows x64 | GPL-3.0-or-later; isolated in `runtime/Lib/think_aloud_media`. Exact 12-file closure and loader-local VC copies are recorded in its provenance. Core commit `38b88335f99e76ed89ff3c93f877fdefce736c13`, fixed recipe `8683107a02300923abe4f293920f4b5edc8cb624`, corresponding source revisions and patches accompany the source bundle. External libraries retain their own terms |
| Plyr | 3.8.4 | MIT, `licenses/Plyr-MIT.txt`; https://github.com/sampotts/plyr/tree/v3.8.4; unmodified assets in `ui/vendor/plyr`, also embedded in exported HTML |
| SDL2 controller runtime | 2.32.10, official Windows x64 DLL | zlib, `licenses/SDL2-zlib.txt`; https://github.com/libsdl-org/SDL/releases/tag/release-2.32.10; binary/source asset digests and DLL digest in `tools/input/provenance.json`, matching source in companion dependency archive |
| pywebview | 6.2.1 | BSD-3-Clause; complete license in `runtime/Lib/site-packages/pywebview-6.2.1.dist-info/licenses/LICENSE` (or equivalent wheel metadata location) |
| Other Python packages and native wheels | Exact inventory in `requirements-lock.txt` and packaged `*.dist-info/METADATA` | Package license/NOTICE files, including dist-info license directories, are retained unchanged. Native wheel dependencies may have separate licenses |
| CTranslate2 | 4.8.2, exact CPython 3.12 Windows wheel | Original MIT text in `licenses/native/CTranslate2-4.8.2`; its Intel/NVIDIA components have separate terms below |
| NVIDIA cuDNN | 9.10.2.21 runtime DLL | `licenses/native/NVIDIA-cuDNN-9.10.2.21/LICENSE`; exact DLL matches the corresponding official NVIDIA archive member. Preserve the full upstream terms, including distribution conditions |
| Intel OpenMP / oneMKL / oneTBB / oneDNN | 2025.3.0 / 2025.3.0 / 2022.2.0 / 3.1.1 | Original EULA, component terms and nested third-party notices in the matching `licenses/native` directories. Evidence distinguishes DLL byte identity from recipe/build-marker correlation for static libraries; these are not covered by the application's MIT license |
| Microsoft WebView2 SDK DLLs | 1.0.3856.49 | All five included SDK DLLs match the official NuGet package by SHA256. That exact SDK's `LICENSE.txt` permits redistribution under BSD-style conditions; preserve `Microsoft-WebView2-SDK-LICENSE.txt` and `Microsoft-WebView2-SDK-NOTICE.txt` from the companion materials |
| Microsoft C/C++ runtime | 14.44.35211.0 in the prepared Python runtime | Full Microsoft runtime end-user terms and Visual Studio Community 2022 terms are archived separately. Distributor rights arise from the applicable Visual Studio license, section 4, together with its redistributable list; the runtime end-user EULA alone does not grant republication |

OBS binaries are unmodified upstream program files; application-specific OBS
configuration is generated on first use and excluded from the distribution. OBS
dependency licenses may also be present in its data directory; those are retained.
The source package is based on the actual 32.2.2 release, not GitHub's generic
automatically generated archive.

The new package excludes the old Gyan 7.1 EXE supplied by imageio-ffmpeg. The
Python package's original notices remain. Official replacement release:
https://github.com/obsproject/obs-deps/releases/tag/2026-07-15 . Its FFmpeg build
enables GPL and version3; do not describe it as LGPL-only. The isolated CLI does
not replace OBS's or PyAV's native libraries. Their corresponding components
remain separately identified in the companion source materials.

PyAV 18.1.0 matches the official Windows wheel and pinned pyav-ffmpeg 8.1.2-1
vendor recipe. That build ships x264/x265; its configure-list patch does not
change those libraries' licenses. Preserve their original GPL source/notice
materials rather than relying only on the FFmpeg library's runtime license text.
Upstream licensing guidance: https://ffmpeg.org/legal.html .

`licenses/native/NOTICE-INDEX.json` records the exact bytes, origin basis and
limitations of added Python-native notices. The same-version oneMKL component
notice explicitly lists Intel OpenMP Runtime and its ISSL conditions; this does
not replace or omit the original Intel wheel EULA. The bundled OpenMP DLL also
identifies embedded oneTBB 2022.2.0, whose original notices are included. NVIDIA,
Intel and Microsoft distributor conditions remain applicable to the publisher.

An upgrade preserves obsolete managed files rather than deleting them. Thus an
existing private installation may retain its inactive old Gyan EXE. The new
application always selects the isolated CLI; clean new archives exclude the old
EXE. No claim is made that updating removes every historical dependency file.

Microsoft SDK evidence is available in the successor source bundle created with
`--supplement-existing`. Its `webview2-binary-match.json` identifies every local DLL
and matching member of the official Microsoft.Web.WebView2 1.0.3856.49 NuGet
package. The archive retains the license and third-party notices verbatim. These
SDK terms are distinct from the separately installed WebView2 browser runtime.

The official VC redistribution list is
https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution .
The companion files `Visual-C-Runtime-2015-2022-License.docx` and
`Visual-Studio-2022-Community-License.docx` preserve Microsoft's full documents.
The latter permits qualifying distributors to ship listed, unmodified code with
substantial application functionality and the required protective terms. Do not
extend the application's MIT license to Microsoft runtime files or replace their
terms with a two-line URL notice. This project does not infer the distributor's
Visual Studio entitlement from the mere presence of DLLs.

Optional Whisper model weights are **not in either software archive**. If users
choose to fetch/import large-v3, the fixed model revision and hashes are in
`model-manifest.json`; model origin is https://huggingface.co/Systran/faster-whisper-large-v3
and the supplied Whisper license is `licenses/Whisper-MIT.txt`.

No Obsidian executable, user recordings, vault data, credentials, runtime model
registry, custom vocabulary, or saved application settings are distributed.
