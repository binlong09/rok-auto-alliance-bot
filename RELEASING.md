# Releasing RoK Automation

The app ships as a PyInstaller onedir build (`dist\RoK Automation\`), zipped
and attached to a GitHub release. End users download the zip once; after
that, the built-in auto-updater offers each new release on startup.

## How auto-update works

1. `VERSION` (a one-line file at the repo root) is bundled into the build.
2. On startup, `src/updater.py` asks
   `https://api.github.com/repos/binlong09/rok-auto-alliance-bot/releases/latest`
   for the latest tag and compares it to the bundled `VERSION` (semver-style
   `x.y.z`; a leading `v` on the tag is fine).
3. If newer, the user sees a dialog with the release's first note line.
   Default is No - only an explicit Yes updates.
4. On Yes: the first `.zip` asset is downloaded to `%TEMP%`, extracted to a
   staging dir (skipping `instances/`, `logs/`, `config.ini`, `portable.txt`
   so user state survives), and `updater.bat` is spawned from `%TEMP%` in its
   own console. The app exits; the bat waits for the process to end,
   robocopies the staged files over the install dir, and relaunches the exe.

Users can disable the check with the `AUTO_UPDATE=off` environment variable.

## Cutting a release

1. **Bump `VERSION`** at the repo root (e.g. `1.0.6` -> `1.0.7`). Numeric
   segments only - pre-release suffixes like `1.0.7-beta` will not compare
   correctly.
2. **Commit and tag**: the tag must be `v` + `VERSION` exactly (e.g. `v1.0.7`).
   CI fails the build if the tag and `VERSION` disagree.

   ```
   git tag v1.0.7
   git push origin main v1.0.7
   ```

3. CI builds the exe (with Tesseract bundled), zips it, and creates the
   GitHub release with the zip attached. Nothing else to do.
4. **Release notes**: the first line of the release body is shown to users
   in the update dialog - CI generates notes automatically, but consider
   editing the release afterwards so the first line is informative.

## Local builds

`python build.py` reads the version from `VERSION` (override with
`--version X.Y.Z`) and produces `releases\RoK_Automation_vX.Y.Z_<date>.zip`.
Only zips attached to a GitHub release are ever offered to users.

## Files involved

| File | Purpose |
|---|---|
| `VERSION` | Single source of truth for the current version. Bump before tagging. |
| `src/updater.py` | Startup check, dialog, download, staging, spawn. |
| `updater.bat` | Out-of-process file swap + relaunch. Bundled into the build, run from `%TEMP%`. |
| `rok_automation.spec` | Bundles `VERSION` and `updater.bat` as data files. |
| `.github/workflows/build.yml` | Builds, checks tag/VERSION consistency, uploads the release zip. |

## Testing the update flow without a real release

Temporarily set `VERSION` to something lower than the latest GitHub release
(e.g. `0.0.1`), rebuild, and launch - the update dialog will appear.
Restore `VERSION` afterwards.
