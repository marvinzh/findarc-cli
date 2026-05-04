## TestPyPI Publishing

This repository publishes the `findarc` package to TestPyPI through GitHub Actions trusted publishing.

### One-time setup

1. Create a TestPyPI project for `findarc` if it does not exist yet.
2. In TestPyPI, add a trusted publisher for this GitHub repository.
3. In GitHub, create an environment named `testpypi`.
4. Optionally add protection rules to the `testpypi` environment.

### How to publish

- Manual: run the `Publish to TestPyPI` workflow from the GitHub Actions UI.
- Tag-based: push a tag like `v0.1.0`.

### Notes

- The workflow builds both sdist and wheel.
- The publish job uses OIDC trusted publishing, so no API token secret is required.
- The package page URL is expected to be `https://test.pypi.org/p/findarc`.
