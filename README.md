# Quest to Frame

A Windows wizard for backing up a locally connected Quest game, converting it with an independently installed OVR Port CLI, and deploying it to Steam Frame over ADB and SSH. Includes per-game OpenXR resolution controls and optional Steam shortcuts/artwork.

See [the app guide](GUIDE.md) for the workflow and limitations.

## Source-only repository

This repository contains our Python/C/shell source and documentation. It does **not** distribute Quest games, patched APKs, game saves, Steam artwork, signing keys, device configuration, downloaded OVR Port binaries, Android SDK/NDK, Java, Lepton, or the locally built Windows executable. `.gitignore` protects these local files without deleting them.

The existing workspace is configured to run the app. A fresh clone needs the external tools described in the app guide; this is not a self-contained installer. To compile the adapter from a fresh clone, run `./build-native.ps1` with an installed Android NDK. That script fetches the two OpenXR headers from a pinned upstream revision and verifies their SHA-256 hashes.

Run source: `python -m pip install -r requirements.txt`, then `python app.py` (or `Launch.cmd`).

Tests: `python -m unittest discover -s . -v`. Tests using private game/Steam fixtures skip when those files are unavailable.

## License

Original project source and documentation are licensed under **GPL-3.0-only**, as stated in [LICENSE](LICENSE). This is a project licensing choice, not a claim that invoking a GPL command-line tool automatically licenses every caller under GPL. Third-party materials retain their own licenses; this project's license does not grant rights to game content or artwork.

Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) before distributing anything beyond this source tree. The locally built EXE and downloaded runtime bundle are **not cleared for redistribution by this audit**.
