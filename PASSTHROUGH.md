# Triangle Strategy passthrough investigation

Investigation and Triangle Strategy validation, 2026-09-27.

## Confirmed

- The user confirmed Triangle Strategy runs on Frame. No game fix was needed
  after its initial expansion-file loading stage completed.
- With OVR Port runtime `3.4.3-23204ea`, the game logs missing procedures
  `xrCreateTriangleMeshFB`, `xrDestroyTriangleMeshFB`, and
  `xrPassthroughLayerSetKeyboardHandsIntensityFB`, followed by
  `Initializing passthrough failed with error -1006`.
- A standalone capability probe of the Frame's native Linux OpenXR loader
  returned 48 extensions, with no `XR_FB_passthrough` or `XR_FB_triangle_mesh`.
  This is a native Linux result, not a completed Android-container probe.
- A background OpenVR capability probe successfully obtained
  `IVRTrackedCamera_006`. `HasCamera` returned true. All three camera frame-size
  queries returned `VRTrackedCameraError_OperationFailed`, both before and after
  acquiring a streaming-service handle. Releasing that handle returned error
  101; the probe then shut down its OpenVR connection. No camera images were
  read or saved. These results do not establish why camera access failed.
- The public `ovrport/app` source contains the patcher and a
  `force_passthrough` configuration switch, not the native runtime implementation
  responsible for the missing procedures. Enabling that switch alone does not
  provide the missing camera/compositor implementation.

## Experimental alpha-blend adapter

A subsequent native OpenXR probe successfully created an instance and queried
stereo environment blend modes. Frame returned both OPAQUE and ALPHA_BLEND.
This provides a candidate compositor path without reading raw camera frames.

`native/passthrough_bridge.c` is an experimental outer adapter around the
user-provisioned OVR Port library. It translates active full-background
reconstruction underlays into ALPHA_BLEND submissions, preserves other layers,
tracks pause/resume and destruction, and checks reported blend-mode support.
It does not implement projected meshes, keyboard masking, color effects,
fractional camera opacity, or passthrough overlays. Unsupported requests return
errors instead of fabricated successful camera/mesh results.

Build explicitly from an existing converted APK (not a raw Quest APK):

```powershell
python build_passthrough.py path/to/converted/game.apk path/to/new-output-directory
```

This requires the existing local Android toolchain, verified OpenXR headers,
and the package's existing signing key. The new directory must not exist. The
builder changes only the private copy of the original library's ELF SONAME,
adds the adapter, and aligns/signs/verifies a new APK. It does not install it,
modify the input, or enable the experiment for normal Quest2Frame conversions.
Neither original nor modified OVR Port binaries are included in Git.

Host C behavior tests (`native/test_passthrough.c`) passed on Frame. Python tests
cover the SONAME edit and ensure other matching strings remain untouched.
These tests are not proof that the physical camera background renders correctly.

The first experimental APK has been installed for a live test. The original
APK is preserved as `game.pre-passthrough.apk` in the game's deployment directory,
outside `lepton-app`. Saves, expansion files, launcher, and system camera
settings were not changed.

Live Android logs confirm `alpha blend supported=1` and
`create passthrough result=OK`. The former Insight MR initialization failure
is absent in this test. The first visual test remained black: OVRPlugin was
requesting reconstruction layers with a null passthrough parent, resulting in
`XR_ERROR_HANDLE_INVALID`. A subsequent adapter revision resolves a null parent
only if exactly one passthrough object exists in that same session. Explicit
invalid handles and ambiguous parents still fail; both cases have C tests.
The third experimental build now creates the reconstruction layer and reports
`passthrough frame active=1 layers=1 blend=3 result=0 flags=7` on the Frame.
The user confirmed that this third build displays working passthrough in
Triangle Strategy. Other games still require independent validation.

**Triangle Strategy passthrough is visually confirmed.** To roll back, close the
game and restore the preserved original APK to `lepton-app/game.apk`, then
relaunch. Do not treat removal of a log error as proof of working passthrough.

## References

- [OVR Port patcher source](https://github.com/ovrport/app)
- [Valve OpenVR API declarations](https://github.com/ValveSoftware/openvr/blob/master/headers/openvr_capi.h)
- [Frame custom-engine documentation](https://partner.steamgames.com/doc/steamhardware/steamframe/engines/custom)
- [Existing SteamVR passthrough layer](https://github.com/Rectus/openxr-steamvr-passthrough)
  describes translating camera data through OpenVR. Its existence is not evidence
  of compatibility with Frame's Android/ARM64 environment.
