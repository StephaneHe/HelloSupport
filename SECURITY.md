# Security policy

## Supported versions

Only the latest release receives fixes. HelloSupport is a local demonstration project: it
calls no cloud API, stores no credentials, and only queries simulated services.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately through
GitHub: **Security → Report a vulnerability** on the
[repository page](https://github.com/StephaneHe/HelloSupport/security/advisories/new).

Include the version (`hello-support --version`), the steps to reproduce and the impact you
expect. You should get an answer within a week. Once a fix is released, the advisory is
published with credit to the reporter, unless you prefer otherwise.

## Scope

In scope, for example:

- a way to make the SQL tool write to or escape the read-only incidents database
  (see the five guards in [D-13](docs/DESIGN_DECISIONS.md));
- a way for model output or a question to execute code or reach a real system;
- the web demo exposing more than it should when started with `--host 0.0.0.0`.

Out of scope: wrong or invented answers from the language models (a known, documented
limitation), and attacks that need control of the local LM Studio server.
