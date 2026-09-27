# Native Frame edition — additional dependency notes

Original `quest2frame` Python, shell, HTML, CSS, JavaScript, SVG, tests, and documentation: GPL-3.0-only under the repository LICENSE. Shared VDF and launcher code comes from this same project. The existing root `THIRD_PARTY_NOTICES.md` remains applicable, including the unresolved licensing inventory for OVR Port's runtime/vendor libraries.

## Downloaded, not redistributed in Git

- **Debian bookworm ARM64 adb, aapt, zipalign, apksigner and support libraries:** official Debian package URLs, versions, and SHA-256 digests are pinned in `tools.lock.json`. Package copyright files are retained at `runtime/debian/usr/share/doc/<package>/copyright`. This bundle is **not uniformly Apache-2.0**: Android/AOSP tools and dependencies, BoringSSL, BSD libraries, zopfli, protobuf, and p7zip have their own notices/terms. Consult the exact extracted copyright files and Debian source-package links before binary redistribution. We extract archives into a user directory; no system packages are installed.
- **Eclipse Temurin JRE 21, Linux aarch64:** pinned official Adoptium GitHub release/checksum. The runtime's GPLv2 + Classpath Exception and additional component notices remain in its extracted `legal/` tree. Runtime source and build information are available through the [Temurin project](https://github.com/adoptium/temurin21-binaries).
- **OVR Port CLI 1.2.3:** pinned official GitHub release asset/checksum. GPLv3 application; see [upstream](https://github.com/ovrport/app). Its vendor/runtime bundle is downloaded separately by the CLI. Do not infer a blanket GPL grant for those vendor binaries or converted games.
- **Chrome Flatpak:** existing device-installed application, not downloaded or redistributed by our bootstrap. Chrome/Chromium and its dependencies have separate terms. We do not disable its sandbox or grant additional filesystem privileges.
- **Steam and Lepton:** existing device software. We generate per-app launch scripts using their documented/local interface, not redistribute their implementation.
- **Khronos OpenXR headers / custom adapter:** adapter source is in the original app directory. The headers' MIT alternative is selected as documented by `build-native.ps1`; retain the included Khronos MIT notice when distributing compiled copies. The deployer transfers only a locally built adapter to the user's own Frame.
- **Paramiko:** needed only by the optional PC-side deployment helper, not by the native app. Its LGPL terms are documented in the root audit.

## Network privacy and artwork

Game files and saves are not uploaded. Tool downloads contact Debian, GitHub/Adoptium, and OVR Port's library service. Artwork searches send the chosen **game title** to Steam; a matching Steam App ID is used for CDN image requests. Disable automatic artwork if you do not want that search. CDN availability is not permission to redistribute the images; they remain local and excluded from Git.

For a public binary release, inventory the exact shipped files, preserve notices, supply required corresponding source and replacement/relinking provisions, and resolve runtime/vendor redistribution rights first. A source commit is not a legal certification of arbitrary packaged binaries or patched games.
