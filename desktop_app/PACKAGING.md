# Packaging the Auto Review desktop app

> These steps are **NOT verified in CI** — they must be run **on your machine**
> (a real Windows or macOS box with a display). The Python pieces (installable
> package, settings/keychain, the consent manifest) ARE unit-tested; the
> installer, the GUI window, and macOS signing are not.

## Windows
1. From `desktop_app/`: `packaging\build.ps1`
2. Smoke-test: launch `dist\AutoReview\AutoReview.exe`. A window titled
   "Auto Review" should open and show the empty library.

## macOS (outline)
1. `pip install -e . && pip install pyinstaller`
2. `pyinstaller packaging/autoreview.spec --noconfirm`
3. Code-sign + notarize the `.app` (requires an Apple Developer ID):
   `codesign --deep --force --options runtime --sign "Developer ID Application: ..." dist/AutoReview.app`
   then `xcrun notarytool submit ...` and `xcrun stapler staple`.

## Install consent (both OSes)
At setup, show the user `GET /settings/setup-manifest` (the consent summary):
the lightweight deps that will be installed, and that Docling / the Sci-Hub and
screenshot plugins are heavy/optional and installed on demand later. Declining
means the app can't run.

## What still needs doing before distribution
- Run the GUI smoke test above on a clean machine.
- macOS: real Developer ID signing + notarization.
- Bundle/relocate the Document Decomposer engine (`Document_Decomposer/`), which
  the app imports via `engine_bridge` - currently it expects the monorepo layout.
