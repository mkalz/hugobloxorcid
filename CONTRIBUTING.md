# Contributing

Thanks for your interest in improving the HugoBlox ORCID Importer.

## Development

```bash
python -m pip install -e .[pdf]
python -m compileall src
python scripts/orcid_import.py --help
```

## Guidelines

- keep changes small and focused
- prefer standard-library solutions where practical
- preserve HugoBlox-compatible front matter output
- verify CLI behavior before opening a PR

## Pull requests

Please include:

- a short summary of the change
- example command(s) used for verification
- any expected output differences

## Release process

- update version in `pyproject.toml` and `src/hugobloxorcid/__init__.py`
- update `CHANGELOG.md`
- publish a GitHub release
- run or re-run the `Publish to PyPI` workflow after the PyPI trusted publisher is configured
