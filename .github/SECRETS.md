# GitHub Secrets

This repository does not store secret values in source control. GitHub secrets
must be added in the repository settings.

## Required Secret

### `PYPI_API_TOKEN`

Used by the GitHub Actions publish workflow to upload Limbi to PyPI with Twine.

Add it here:

1. Open the GitHub repository.
2. Go to `Settings`.
3. Open `Secrets and variables` > `Actions`.
4. Select `New repository secret`.
5. Set the name to `PYPI_API_TOKEN`.
6. Paste your PyPI API token as the value.

## Notes

- Do not commit secret values to the repository.
- The workflow reads the token as `secrets.PYPI_API_TOKEN`.
- If you rotate your PyPI token, update the GitHub secret value, not the code.
- For local testing, keep any private values in your own shell session or a
  local untracked file.
