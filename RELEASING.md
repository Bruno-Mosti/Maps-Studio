# Maps Studio releases

**For first-time website-only publishing, follow [docs/GITHUB_UPLOAD_GUIDE.md](docs/GITHUB_UPLOAD_GUIDE.md).**

The `.github/workflows/ci.yml` workflow tests Maps Studio on Windows and Linux when the `main` branch is updated.

The `.github/workflows/release.yml` workflow runs in two modes:

- **Actions → Build and release → Run workflow:** build native Windows/Linux files as artifacts without a public release.
- **Version tag `v2.0.1` or later:** run the native builds and attach packages and checksums to the tag's release; if a release was already created through the GitHub website, upload the assets to it.

Before sharing the release, ensure the Windows `.exe` has been tested on a real Windows PC. The generated packages are not digitally code-signed.

## Subsequent versions

1. Update `VERSION` in `maps_studio/__init__.py` and the version in `pyproject.toml`.
2. Add a matching entry to `CHANGELOG.md`.
3. Upload/commit the changed files using the GitHub website or a Git client.
4. Let the Tests workflow complete, build/check on Windows, and publish a new tag through the website.
5. Do not reuse already published version tags for modified binaries.
