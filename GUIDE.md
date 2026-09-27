# Quest → Frame

Launch `Launch.cmd` or run `python app.py` from the repository root. Local `tools/` and `games/` directories sit alongside `app.py`. Executables and those private/tool folders are not committed to Git. A fresh clone contains source only. An executable built for the old nested layout must be rebuilt before moving it to this root layout.

## Workflow

For multiple games, Ctrl/Shift-select packages and choose **Use selected game(s)**. The batch queue supports per-game settings and artwork, sequential conversion/installation, saved progress, and retrying failed entries. See the [batch instructions](README.md#multiple-games--batch-queue). Keep Quest connected until all requested conversions finish, then switch to Frame. Steam integration currently restarts Steam for each installed game.

0. Enter your Frame SSH host (default `frame`), port, username (`steamos`), and password. Test the connection. Only host/port/username are saved; the password stays in memory. On first connection, attach Frame over USB so the app can verify its SSH host key. Unknown or changed keys are never silently accepted.
1. Plug in Quest, unlock it, accept USB debugging, and click **Scan Quest**. Filter the installed third-party package list and select a game.
2. Choose a library title, resolution, compatibility options, and optionally the matching Steam store App ID for official artwork. Click **Back up Quest game and convert**. Leave Quest connected until conversion completes. The app copies the APK, OBB expansion files, and accessible external saves; originals remain untouched.
3. When prompted, unplug Quest and connect Frame. Click **Install on Frame**. Files transfer over USB ADB, are checksum-verified, and get a dedicated Lepton installation. SSH configures the launcher and optional Steam VR shortcut. Steam briefly closes and restarts to safely load the library changes.

The first Steam launch lets Lepton install/bake the APK into its dedicated Android container. Subsequent launches do not need this PC or either USB connection.

## Resolution and compatibility

Artwork search runs automatically when selecting a package and, if no artwork ID is chosen, again after conversion with the APK title. Choose a candidate from the dropdown to use its Steam App ID; verify the game and edition. Edit the title and click **Find artwork** to search again, or enter an ID manually. Automatic search can be disabled on the Convert tab. It sends only the title to Steam, and network failures do not block conversion.

Resolution is 50–200% of OpenXR's recommended **width and height**, clamped to runtime limits. 150% means about 2.25× as many pixels, not 1.5×. Games that ignore OpenXR's recommended size may ignore this setting. It does not change the headset display mode.

Open an existing `games/<package>/build-.../game.json`, change the scale on step 2, and use **Apply resolution / compatibility settings only** on step 3. Restart the game. No reconversion is necessary. This update uses SSH and does not need a USB connection after the SSH identity has been verified.

The Frame adapter repairs the missing Android OpenXR instance extension. Optional physical-controller compatibility suppresses synthetic hand input and presents relevant controller profiles as Touch; disable it for games that need hand tracking. The foveation option disables the unsupported Quest foveation path. These are the Tetris-derived fixes, not a guarantee for every game.

## Files, safety, and limitations

Single-game and batch install windows offer **Refresh storage** and an **Install location** dropdown. SD/removable storage is discovered from mounted devices and identified by filesystem UUID, not its label. Supported destinations are writable ext4/btrfs without `noexec`. Game files and per-game Lepton data go to the chosen drive; the stable Steam launcher and artwork stay internal. Existing games cannot silently move to another drive. See [installation instructions](README.md#3-install-and-play-on-frame) for details. No formatting or automatic mounting is performed.

- `games/<package>/backup-*`: original Quest APK/data and backup metadata.
- `games/<package>/build-*`: signed converted APK, manifest, hashes, artwork, and deployment metadata.
- On Frame: `~/Applications/quest-frame/<package>/` with `launch.sh`, `lepton-app/`, `lepton-data/`, `settings.conf`, and `launch.log`.
- Existing external Frame saves are not overwritten by older Quest saves. Existing app files and baked private data are retained in timestamped `previous-*` directories on updates. Lepton may reset private app data when rebaking an updated APK; the snapshot is available for manual recovery. Do not delete snapshots until your progress is confirmed.
- Steam shortcut edits preserve unrelated entries and create `shortcuts.vdf.backup-*`. Existing artwork is backed up before replacement. **Add / repair Steam shortcut only** retries library setup without another APK/data transfer.
- Multiple Steam accounts require manual account selection outside this initial version; the app refuses to guess.
- Only single-APK ARM64 games are supported. Split APK games fail before copying. Protected/private Quest saves cannot be copied on retail devices. Inaccessible external files produce warnings; incomplete OBB transfers stop conversion.
- OVR Port compatibility varies. Entitlement checks, platform services, multiplayer, or unusual engine/input paths can prevent a game from working. OVR Port documents entitlement-related patches; this wrapper delegates conversion to that external tool. It does not grant rights to games or establish that every conversion is permitted under applicable law or platform terms.
- Keep signing keys in `tools/ovrport-workspace/signatures` backed up. They are needed to update converted packages consistently. Don't share your personal game backups.
- Close the game before reinstalling it. Do not run multiple conversion app instances simultaneously (OVR Port shares its workspace).

## Dependencies / development

The executable bundles Python, Tk, Paramiko, and the precompiled ARM64 Frame adapter. Conversion reuses this workspace's Java 21, OVR Port CLI 1.2.3, pinned experimental OVR Port libraries `3.4.3-23204ea`, and Android SDK build-tools from `%LOCALAPPDATA%/Android/Sdk` (or `ANDROID_SDK_ROOT`). ADB must be on PATH or in the SDK's platform-tools directory. This is a working app for this configured PC, not a standalone redistribution of those external tools.

Source launch: `python -m pip install -r requirements.txt`, then `python app.py` (or `Launch.cmd`). Tests: `python -m unittest discover -s . -v` from the repository root.

The native source is `native/frame_bridge.c`. Run `./build-native.ps1` from the repository root to fetch hash-verified OpenXR headers from a pinned revision and build the adapter using Android NDK. The `.so` and downloaded headers are ignored by Git. Rebuild the `.so` after changing its source. The build selects the headers' MIT license alternative and preserves their notices.

Original project source is **GPL-3.0-only**, without warranty. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). OVR Port, Paramiko, SDK tools, runtime libraries, game content, and artwork retain their own licensing. Do not distribute the local EXE, runtime bundle, or converted APKs on the assumption that this repository's license covers them.

References: [OVR Port](https://github.com/ovrport/app), [Valve Lepton ADB guide](https://partner.steamgames.com/doc/steamhardware/steamframe/adb_lepton). Steam artwork is fetched from Valve's CDN for the App ID you enter.
