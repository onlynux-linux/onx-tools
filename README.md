# Onlynux ONX tools

Generate independent, shell-based **ONXBUILD** recipes using Gentoo as the primary packaging knowledge source, then build native **.onx** packages with **Tatami**.

Project builds and recipe generation run in GitHub Actions. Upstream compilation runs as an unprivileged user in disposable Linux containers with networking disabled.

## Implemented

- Pinned Gentoo checkout and Portage metadata evaluation, including inherited metadata.
- Explicit reviewed upstream adapters; no copied ebuild phases or distribution patches.
- Conditional dependency parsing, explicit name mapping, supported version constraints.
- Recursive recipe generation and dependency-first builds with cycle/missing-provider errors.
- Upstream-only adapters with reviewed instructions and pinned SHA512.
- Source verification, archive traversal protection, upstream test phases.
- Native packaging and verification through `tatami mkpkg` and `tatami verify`.
- Actual install smoke tests and downloadable development ONX artifacts.
- Build-verified recipes recorded under `generated/` for synchronization to `onlynux-linux/onlynux-recipes`.

Initial adapters: **gzip and sed**. This is a foundation for the requested base system, not a claim that the full system is bootstrapped.

## Commands on a GitHub runner

```sh
python -m onx.cli import gzip sed \
  --policy policies/base.json --gentoo /path/to/pinned/gentoo --output recipes
python -m onx.cli lint recipes
python -m onx.cli plan gzip --recipes recipes
python -m onx.cli build gzip --recipes recipes --work build-output \
  --image onx-build:ci --allow-unsigned
```

Targets recursively import/build their dependencies. Packages explicitly declared in `bootstrap.json` are supplied by the build image. The actual versions are checked during each build.

## ONXBUILD

Recipes contain shell variables and `configure()`, `build()`, `check()`, `package()` functions. A JSON comment carries machine-readable metadata without executing shell. v0.1 requires exactly generated recipes: edit policy/adapters and regenerate rather than change a phase without updating the model.

Dependencies: `builddeps` (host tools), `targetdeps` (target headers/libraries), `checkdeps`, `rundeps`. Native builds only; cross compilation is not implemented.

The binary format is delegated to the existing Tatami implementation. Output:
`ARCH/NAME-VERSION-rRELEASE.onx`. No new archive layout is invented.

## Gentoo and vanilla

Portage is used on disposable runners to obtain metadata. Emitted recipes do not need Portage.
Reviewed adapters use upstream build systems and document dependency overrides, including removed distro integration. Gentoo revisions are provenance; Onlynux releases are separate.

Slots, USE-qualified atoms, blockers, alternatives, REQUIRED_USE and post/install dependencies require reviewed policy. Unsupported cases stop. Generic imports remain drafts until reviewed.

Source SHA512 is verified against the pinned Gentoo Manifest. This checks consistency with that snapshot. Upstream signature verification is not yet implemented.

For packages absent from Gentoo, set `provider: "upstream"`, pin version/URL/SHA512, add `references`, reviewed dependencies and build options. The same recursive planner is used. Upstream prose is not automatically converted into executable commands.

## Bootstrap and release boundaries

CI uses Ubuntu 24.04 with GNU tools, glibc and GCC as a bootstrap image. It is not a self-hosted Onlynux release root. Actual versions are included in build reports. Empty provider receipts exist only in disposable containers and are never published. Self-hosted releases require Onlynux glibc/toolchain stages and a pinned image digest.

Outputs are **unsigned development packages**, not production releases. ELF dependencies are recorded for audit; the runtime graph remains reviewed explicit metadata. Dynamic plugins and script dependencies cannot all be inferred from ELF.

No universal ebuild translator, automatic patch adoption, cross-architecture matrix, package splitting or complete base system is claimed.

The public tool does not read or expose the private recipe repository. Initial recipes are independently generated from public inputs.

## Tests

Python 3.12+: `python -m unittest discover -s tests -v`.
Portage is only required for Gentoo imports. CI pins Gentoo, Portage and Tatami revisions.

Original code: GPL-3.0-or-later. Source packages retain upstream licenses. Gentoo ebuild code is not copied.

## Draft a new Gentoo package

```sh
python -m onx.cli propose app-arch/gzip-1.14 \\
  --gentoo /path/to/gentoo --policy policies/base.json --output proposed
```

This command creates `drafts/gzip/ONXBUILD` and a report preserving the original metadata, selected features and every unresolved dependency. It never executes Gentoo build phases. Review the upstream instructions and add an adapter to `policies/base.json` before importing/building the dependency closure. `--use=+flag` or `--use=-flag` selects explicit feature overrides. Complex source sets require an explicit adapter.

The **Propose Gentoo ONXBUILD** workflow accepts a pinned Gentoo CPV in the GitHub Actions UI and returns an `onx-draft` artifact. It does not promote drafts into the tested recipe repository.
