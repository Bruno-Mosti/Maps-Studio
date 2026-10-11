# Publish Maps Studio using the GitHub website (no terminal required)

## 1. Extract the source ZIP

Extract `Maps-Studio-GitHub-Ready.zip` **on your computer**. Open the extracted `Maps-Studio-GitHub-Ready` folder. You should see `README.md`, `MapsStudio.py`, `MapsStudio.spec`, `maps_studio/`, `assets/`, `tests/`, `docs/`, `.github/` and other files.

**Upload the folder's contents, not the ZIP as a single GitHub file.** In a Linux file manager press `Ctrl+H` to show hidden items such as `.github`, `.gitignore` and `.gitattributes`.

## 2. Create the repository

1. Visit <https://github.com/new> and sign in.
2. Repository name: **Maps-Studio**.
3. Choose **Private** initially while checking group/publication permissions and contributor attribution.
4. Leave **Add a README**, **Add .gitignore** and **Choose a license** unchecked/None. The ZIP already contains them.
5. Click **Create repository**.

## 3. Upload every source file and folder

1. In the newly created repo, click **uploading an existing file**, or **Add file → Upload files**.
2. Drag **the contents** of the extracted `Maps-Studio-GitHub-Ready` folder into the browser upload area, including `.github` and other dotfiles. If your browser/file manager won't accept all folders at once, upload in smaller groups. Preserve the folder structure.
3. Confirm GitHub shows paths such as `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `maps_studio/ui.py`, `assets/logo.png`, `MapsStudio.py` and `README.md`.
4. Enter a commit message such as `Initial Maps Studio v2.0.1 release source`.
5. Click **Commit changes** (to `main` for this initial upload).

GitHub browser upload has a 25 MiB per-file limit and a 100-file batch limit; this source project is smaller. If a hidden file wasn't included, upload it separately to the correct directory.

## 4. Check that the repository is healthy

1. Open the repository's **Code** tab: make sure all folders are present, especially `.github`, `maps_studio`, `assets`, and `tests`.
2. Open **Actions → Tests**. Let the Linux/Windows tests finish. Investigate any red checks before release.
3. Open **Actions → Build and release → Run workflow → Run workflow**. This creates **Windows** and **Linux** downloads as temporary **Artifacts** without publishing a release.
4. On a real Windows PC, extract the Windows artifact and launch `MapsStudio.exe`. Confirm logo/window/startup, import, editing, undo, export, and reopening. Do not confuse a Wine run with native-Windows verification.

## 5. Publish v2.0.1 from the website

After tests pass:

1. Open **Code → Releases → Draft a new release**.
2. Click **Choose a tag**, type `v2.0.1`, and select **Create new tag** targeting `main`.
3. Title: `Maps Studio v2.0.1`.
4. Enter a short release description. Until Windows has been personally tested, select **Set as a pre-release**.
5. Click **Publish release**.
6. The new version tag triggers `Build and release` automatically. The workflow now recognises that the web-created release already exists and **uploads its assets into that release** after successful native builds.
7. Return to the release page and wait until the Windows and Linux packages and `SHA256SUMS.txt` appear. If the workflow fails, inspect Actions logs instead of sharing missing files.

### Teammate download links

Public repo: `https://github.com/YOUR-USERNAME/Maps-Studio/releases/latest`.

Private repo: invite teammates using **Settings → Collaborators** and then share the repository release URL.

Windows: `MapsStudio-Windows-x64.zip` → extract → `MapsStudio.exe`.

Kubuntu/Ubuntu: `maps-studio_2.0.1_all.deb` → install → launch **Maps Studio**.

Linux x64: `MapsStudio-Linux-x64.tar.gz` → extract → run `MapsStudio/MapsStudio`.

Maps are **not** bundled with Maps Studio. Share your team's six official CSV/JSON files separately through their approved OneDrive folder. Do not upload university assessment algorithms, private chats or non-public teammates' files.

## Important migration note

Maps Studio uses `%LOCALAPPDATA%\Maps Studio\grids` on Windows and `~/.local/share/Maps Studio/grids` on Linux. If you previously used MP or the older COMP1827 Map Studio version, its data remains untouched in the old folder. Use **Import → A whole folder** to copy maps into Maps Studio when needed.
