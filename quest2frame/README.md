# quest2frame — native Steam Frame edition

A local, large-format interface for moving your Quest games directly to Steam Frame. This is a **2D app window in Frame's VR workspace**, not an immersive OpenXR scene. It supports headset pointers, keyboard spatial navigation, and standard gamepad D-pad / stick navigation (A selects, B dismisses dialogs). Action targets are at least 56–64 px; resolution presets avoid precision slider manipulation.

## Use on Frame

1. Open **quest2frame** in Steam. No SSH details/password are needed on Frame.
2. On first use, select **Set up tools**. The setup downloads hash-pinned ARM64 tools into `~/.local/share/quest2frame/runtime` without sudo or changes to SteamOS. The command-line equivalent is `./launch.sh --setup`.
3. Enable Quest developer mode and USB debugging. Plug Quest directly into Frame using a data-capable cable, unlock Quest, and accept the debugging prompt. Press **Scan Quest**. Only physical Quest devices are shown; Lepton/emulator connections are excluded.
4. Select a Quest package. Choose a title, 50–200% resolution, physical-controller compatibility, foveation fix, automatic artwork, and whether to add it to Steam. Click **Convert & install**.
5. Keep Quest connected through the backup stage. Conversion, signing, and installation happen on Frame. Original Quest files are never modified.
6. When ready, choose **Update Steam library**. After confirmation, a detached worker restarts Steam and closes this window to safely merge the new shortcuts/artwork. Your conversion is already saved. Reopen quest2frame afterward.

**On your Frame** discovers both this edition's games and existing installations from the Windows app. Save resolution/compatibility changes without rebuilding; restart the game to apply. Artwork can be refreshed separately. First game launch lets Lepton initialize its dedicated container.

## Automatic artwork

The app searches Steam's store catalog using the game's title and compares normalized names. It automatically selects only a high-confidence match with a clear margin over alternatives. A few known package/title mappings help ambiguous package names. When in doubt, it leaves artwork unset and offers manual search/match selection or a Steam App ID; it does not silently pick an unrelated cover. Artwork failures do not fail installation. Portrait, landscape, hero, and logo assets are downloaded directly from Steam's CDN and kept out of Git.

## Safety and limitations

- Source/backup files remain under `~/.local/share/quest2frame/games/<package>/`. Converted games are in `~/Applications/quest-frame/<package>/`, compatible with the original app. Downloads and original copyright notices are retained locally.
- Existing external Frame saves are not overwritten with older Quest saves. Reinstalling snapshots old app/baked data first. Lepton can reset private Android data when rebaking; snapshots allow manual recovery.
- Only single-APK ARM64 games are supported. Private/protected Quest saves may not transfer. OBB-copy failure stops the workflow. DRM/platform services, unusual engines, and input paths can prevent compatibility.
- Resolution scales recommended OpenXR width **and** height (150% is about 2.25× pixels), not the physical display mode. A game can ignore the recommendation.
- Physical-controller compatibility suppresses synthetic hand input. Disable it for hand-tracking games.
- Steam updates preserve unrelated shortcuts, keep timestamped backups, and refuse to guess when multiple Steam user accounts exist.
- ADB uses private server port **5038** to avoid interfering with Lepton/development sessions. USB device access still depends on the headset's host role, cable, developer settings, and permissions. The app never forces role switching or installs root udev rules. Try a different cable or powered USB-C hub if no physical device enumerates.
- The UI API binds only to `127.0.0.1`, requires a random session capability for actions/state, checks Host/Origin, rejects arbitrary paths/commands, and provides no shell endpoint. A local per-user lock prevents multiple app processes. Close operations wait for active jobs; forcibly stopping the whole Steam app may interrupt a job, retaining partial backups.
- Only use content for which you have the necessary rights. OVR Port includes entitlement-related patches; this project does not establish permission under game licenses, platform terms, or local law.

## Install / develop

Steam Frame needs Python 3.12+, Steam/Lepton, systemd user services, and the `com.google.Chrome` Flatpak. These were already present on the tested Frame. The browser uses a dedicated profile; your normal browser profile is not touched. No Python UI framework or HTTP server dependency is required.

From the existing Windows workspace:

```powershell
./quest-frame-app/build-native.ps1
python -m pip install paramiko
python quest2frame/deploy.py --host FRAME_IP --known-hosts quest-frame-app/known_hosts
```

The deployer prompts for the SSH password and refuses unknown host keys. Verify the key against the physically connected Frame using the original app first. It copies the source, shared VDF/launcher helpers, project notices, and **your locally built adapter**, fetches verified native tools, and registers quest2frame in Steam. No game binaries, passwords, signing keys, or third-party tool binaries are committed.

For manual installation, copy this directory to `~/Applications/quest2frame`, copy `quest-frame-app/steam_shortcuts.py` and `launcher.sh` into its `shared/`, place the built ARM64 adapter at `native/libopenxr_loader_generic.so`, and include the repository's license/notices. Then run `bash launch.sh --setup`. A fresh source checkout must build the adapter before use; this repo does not host a downloadable prebuilt adapter.

`tools.lock.json` pins Debian ARM64 adb/aapt/zipalign/apksigner and dependencies, Eclipse Temurin Java 21 ARM64, and OVR Port CLI 1.2.3. OVR Port's runtime version is pinned to `3.4.3-23204ea`; its own downloader provisions those libraries. Re-verify compatibility and licenses before updating pins. Debian package archives are extracted privately, not installed into SteamOS.

Run checks: `python -m unittest discover -s quest2frame -v`. Run a UI-only development server with `QUEST2FRAME_DATA` pointing at a disposable directory and `python quest2frame/server.py --no-browser --port 8765`; obtain its owner-readable launch URL from that directory's `session.json`. Never commit that session file.

## Licensing

Original source: **GPL-3.0-only**, without warranty. See the repository [LICENSE](../LICENSE), [third-party audit](../THIRD_PARTY_NOTICES.md), and [ARM-specific notices](THIRD_PARTY_NOTICES.md). The existing source-only distribution policy still applies: downloaded tools, runtime libraries, games, artwork, local adapter builds, and packaged releases are not automatically covered by the project's license.
