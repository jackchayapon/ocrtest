# External Provider runtime recovery

PR16 introduced server-side credential encryption. The first Railway build at `c37d1e76a3a3f6a0e91b4e0a5bded616c650f7b8` failed startup with `ModuleNotFoundError` for `cryptography`. The Dockerfile installs `requirements-runtime-lock.txt`, while the feature added the dependency only to `requirements.txt`. The previous application remained available and the Vercel production-domain promotion was held.

The focused recovery pins `cryptography==50.0.2`, `cffi==2.1.1` and `pycparser==3.12` in the runtime lock. The development lock includes the same runtime file. A regression checks that every application requirement has a compatible runtime pin and that Docker uses that file.

Executed recovery verification on13November2026 includes the full Backend suite with761passed,0failed/errors/skipped and child exit0, including isolated local PostgreSQL, encryption, External Provider security, Paddle/CDGS mocks, Job recovery and schema checks. Ruff, diff and secret scans passed. The previous232-test full Playwright suite and separate mixed browser integration remain applicable because this recovery changes dependencies and a dependency test only.

The actual `backend/Dockerfile` built for Linux/Python3.12. Its image `sha256:869d1ef398c4e546415cbdd775fa1daef23d3e076693ba6fc479e6b9544ea2aa` imported `cryptography.fernet`, passed `pip check`, started FastAPI, and returned HTTP200 from health, Pipeline and shared provider catalogs using disposable local SQLite. All92 application source hashes matched the candidate. The local smoke used512,000,000bytes,1CPU and no swap with no observed OOM kill. This short startup check establishes packaging/startup compatibility and does not measure OCR workload capacity.

Migration0013 remains additive. Backend rollback must retain its migration file so Alembic recognizes a database already at0013. Keep the provider table and server encryption key during recovery. See the tested recovery steps in [the shared release runbook](external-ocr-shared-release.md).

Recovery deploys through a separate reviewed hotfix PR. Verify Railway startup, health and revision0013 before promoting a compatible READY Vercel build. Record the actual deployment IDs after rollout. Evidence for this recovery is stored separately in ignored `.runtime/production-recovery/`.
