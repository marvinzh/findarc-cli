## PyPI Publishing

This repository publishes the `finda-cli-beta` distribution to PyPI through GitHub Actions trusted publishing.

### One-time setup

1. Create a PyPI project for `finda-cli-beta` if it does not exist yet.
2. In PyPI, add a trusted publisher for this GitHub repository.
3. In GitHub, create an environment named `pypi`.
4. Optionally add protection rules to the `pypi` environment.

### How to publish

- Manual: run the `Publish to PyPI` workflow from the GitHub Actions UI.
- Tag-based: push a tag like `v0.1.0`.

### Notes

- The workflow builds both sdist and wheel.
- The publish job uses OIDC trusted publishing, so no API token secret is required.
- The PyPI project page is `https://pypi.org/project/finda-cli-beta/`.
- The published distribution name is `finda-cli-beta`, while the Python import package and CLI command remain `finda`.
