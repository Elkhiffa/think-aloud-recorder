# Third-party components and distribution status

Experience Recorder application source is MIT licensed; see `LICENSE`. This does
not change the licenses of the independently bundled components below.

The current binary assembly is a **private evaluation candidate**. Its accompanying
dependency-sources ZIP contains actual, hashed source archives. It is not yet a
complete corresponding-source delivery for every binary dependency. See
`dependency-source-manifest.json` for the concrete open items. Do not publish this
candidate as a completed public redistributable release.

| Component | Version / identification | Notice and source |
| --- | --- | --- |
| CPython | 3.12.10, Windows x64 | `licenses/Python.txt`, `runtime/LICENSE.txt`; https://www.python.org/downloads/release/python-31210/ |
| distlib native launcher | Stub supplied by the builder's pip vendored distlib | `licenses/distlib.txt`; the per-file package manifest records the generated launcher digest |
| OBS Studio | 32.2.2, official Windows x64 executable | GPL-2.0-or-later, `licenses/OBS-GPL-2.0.txt`; accompanying `OBS-Studio-32.2.2-Sources.tar.gz` is the official release source asset, including its build materials/submodules |
| FFmpeg executable from imageio-ffmpeg | 7.1-essentials_build-www.gyan.dev; imageio-ffmpeg 0.6.0 | GPLv3 text is extracted from pinned source into `licenses/FFmpeg-GPL-3.0.txt`. Actual executable configuration enables GPL and version3; do not describe it as LGPL-only. Source core commit `b08d7969c550a804a59511c7b83f2dd8cc0499b8`; archived configure/version output and exact binary SHA256 accompany sources |
| pywebview | 6.2.1 | BSD-3-Clause; complete license in `runtime/Lib/site-packages/pywebview-6.2.1.dist-info/licenses/LICENSE` (or equivalent wheel metadata location) |
| Other Python packages and native wheels | Exact inventory in `requirements-lock.txt` and packaged `*.dist-info/METADATA` | Package license/NOTICE files, including dist-info license directories, are retained unchanged. Native wheel dependencies may have separate licenses |
| Media Transcript Obsidian plugin | 1.3.0 | `vault-template/.obsidian/plugins/media-transcript/LICENSE`; source distributed alongside plugin |
| Experience Opener plugin | Application source | Plugin JavaScript and manifest are shipped; this does not bundle Obsidian |
| Microsoft WebView2 SDK DLLs | 1.0.3856.49 | All five included SDK DLLs match the official NuGet package by SHA256. That exact SDK's `LICENSE.txt` permits redistribution under BSD-style conditions; preserve `Microsoft-WebView2-SDK-LICENSE.txt` and `Microsoft-WebView2-SDK-NOTICE.txt` from the companion materials |
| Microsoft C/C++ runtime | 14.44.35211.0 in the prepared Python runtime | Full Microsoft runtime end-user terms and Visual Studio Community 2022 terms are archived separately. Distributor rights arise from the applicable Visual Studio license, section 4, together with its redistributable list; the runtime end-user EULA alone does not grant republication |

OBS binaries are unmodified upstream program files; application-specific OBS
configuration is generated on first use and excluded from the distribution. OBS
dependency licenses may also be present in its data directory; those are retained.
The source package is based on the actual 32.2.2 release, not GitHub's generic
automatically generated archive.

The FFmpeg core source was identified from the official Gyan 7.1 release metadata:
https://github.com/GyanD/codexffmpeg/releases/tag/7.1 . Its original binary is
provided through the imageio-ffmpeg wheel. The core archive alone does not contain
all enabled external libraries (such as x264/x265) or the exact Gyan build scripts.
Those are a known release gap, not a source-completeness claim. Upstream licensing
guidance: https://ffmpeg.org/legal.html .

The upstream Gyan 7.1 release assets contain binary builds and identify the FFmpeg
core commit; they do not supply the matching external-library source bundle.
In the maintainer's answer to a build-script request, Gyan recommends the general
MABS project (https://github.com/GyanD/codexffmpeg/issues/25); that recommendation
does not identify the exact script revision/dependency snapshots used for this
binary. A current MABS checkout must not be labeled as its corresponding source.

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
