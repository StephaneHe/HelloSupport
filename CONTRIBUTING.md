# Contributing

Thanks for your interest in HelloSupport. It is a small, personal learning project, but issues
and pull requests are welcome: bug reports, documentation fixes, new validation cases, or
measurements on other hardware or models.

## Before you start

- For anything bigger than a typo, open an issue first to agree on the approach.
- Read the [design decisions](docs/DESIGN_DECISIONS.md): most choices (local only, code-enforced
  tool policy, bounded agent loops) are deliberate and measured.
- By contributing, you agree that your work is released under the [MIT License](LICENSE) and you
  follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/StephaneHe/HelloSupport.git
cd HelloSupport
uv sync                       # Python 3.12, runtime + dev + docs dependencies
uv run pytest                 # offline test suite (no GPU, no LM Studio needed)
uv run mkdocs serve           # documentation site on http://127.0.0.1:8000
```

The end-to-end benchmark needs LM Studio and the two models (see the README, *Installation*).

## Rules for a pull request

- **One coherent change per pull request**, with a message in the imperative mood that says what
  changes and why.
- **Tests**: `uv run pytest` passes. A bug fix comes with a test that fails without the fix.
  Deterministic code is tested deterministically; model behaviour is measured with
  `hello-support bench` and the report is committed in `docs/bench/`.
- **Documentation**: `uv run mkdocs build --strict` passes (no broken link). Update the README,
  `docs/` and the relevant design decision when behaviour changes. All documentation is in English.
- **Changelog and version**: add an entry under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md)
  ([Keep a Changelog](https://keepachangelog.com/en/1.1.0/)). Releases bump the version in
  `src/hello_support/__init__.py` ([Semantic Versioning](https://semver.org/)) and are tagged `vX.Y.Z`.
- **No secrets**: never commit a key, a token or a `.env` file. Everything runs locally and needs none.

## Documentation versions

The site is published from `main` as `dev` and from each release tag as `X.Y` (alias `latest`),
by the [docs workflow](.github/workflows/docs.yml).
