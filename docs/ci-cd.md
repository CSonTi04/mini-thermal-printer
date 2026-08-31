# Continuous integration and delivery

GitHub Actions provides a hardware-free CI pipeline and tag-driven delivery to
GitHub Releases. Hosted runners never connect to a printer and never receive
the `--live` or `--allow-printing` consent flags.

Third-party workflow execution is limited to official `actions/*` components,
and every action is pinned to the immutable commit behind its documented
release version.

## Continuous integration

[`ci.yml`](../.github/workflows/ci.yml) runs for pull requests targeting
`master`, pushes to `master`, and manual dispatches. It performs:

1. Ruff static analysis on Python 3.12 and Ubuntu.
2. The complete non-HIL pytest suite on Python 3.11 and 3.12, on both Ubuntu
   and Windows.
3. Wheel and source-distribution builds after quality and tests pass.
4. Distribution metadata validation and an installed-wheel CLI smoke test.
5. Upload of the built distributions as a 14-day workflow artifact.

The `hil` marker is explicitly excluded in every automated test invocation.
Physical-printer scenarios remain local, attended, and separately consented as
described in [the test-rig documentation](testing.md).

## Release delivery

[`release.yml`](../.github/workflows/release.yml) runs when a tag beginning with
`v` is pushed. Before publishing anything, it checks that the tag exactly
matches `v` followed by `project.version` in `pyproject.toml`, then repeats
Ruff, the non-HIL test suite, package construction, and metadata checks.

After all checks pass, the workflow creates a GitHub Release with generated
release notes and attaches both the wheel and source distribution. It uses the
repository-scoped `GITHUB_TOKEN`; no external package-registry credential is
required or configured.

To release version `0.2.0` after its version change has passed CI and reached
`master`:

```powershell
git tag -a v0.2.0 -m "Release v0.2.0"
git push origin v0.2.0
```

Do not move or reuse a published release tag. If the package version and tag
differ, the workflow fails before building or creating a release.
