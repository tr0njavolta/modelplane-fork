# Releasing Modelplane

This is the maintainer process for cutting a Modelplane release and versioning
the docs. Contributing changes is covered in [CONTRIBUTING.md](CONTRIBUTING.md);
this file is only for the small set of people who publish releases.

## Releasing

Releases are cut from a release branch and published by the `CI` workflow. To
release a new minor version, e.g. `v0.1.0`:

1. From the GitHub UI, create a `release-0.1` branch from `main`.
2. Create a GitHub release targeting that branch, and let the release create the
   tag `v0.1.0`.
3. Run the `CI` workflow (Actions → CI → Run workflow) against the `v0.1.0` tag,
   setting the `tag` input to `v0.1.0`.

The `tag` input makes the workflow push the package with that exact version
rather than the dev version it derives from git metadata on ordinary runs.
Patch releases (e.g. `v0.1.1`) reuse the existing `release-0.1` branch: cut the
release from it and run the workflow against the new tag.

## Versioning the docs

Docs are versioned at the minor level, each version on its own subdomain. Two
Vercel projects serve them, and each domain serves its build's content directly —
nothing redirects:

- **dev project** (`main` branch) — serves `main.docs.modelplane.ai`, the
  unreleased docs, so work in progress stays browsable.
- **release project** (latest `release-X.Y` branch) — serves both
  `docs.modelplane.ai` (the canonical apex, always the latest release) and that
  release's permanent `vX-Y.docs.modelplane.ai` subdomain.

Older releases keep their own project on their `vX-Y.docs.modelplane.ai`
subdomain. There is no apex redirect: `docs.modelplane.ai` *is* the latest
release's build, so a reader on the bare domain gets the latest docs with the URL
unchanged. What a build serves is decided entirely by its Vercel project and
baseURL, never by the home page (`docs/themes/geekboot/layouts/index.html`).

Each project's baseURL:
- dev project → `HUGO_BASEURL = https://main.docs.modelplane.ai/` (scoped to `main`).
- release project → `docs.modelplane.ai` (leave `HUGO_BASEURL` unset in
  production so the build uses the baked `https://docs.modelplane.ai/` from
  `nix/docs.nix`). The `vX-Y` subdomain aliases the same build.
- PR previews → root-relative `HUGO_BASEURL = /`, so assets resolve against the
  preview host.
- local (`hugo server`) → `localhost` from hugo.toml's `baseURL = "/"`.

`docs/data/versions.yaml` is the single list of every version and its URL. It
drives the version dropdown and must be identical on every branch — `main` and all
release branches — so each build offers the same switcher.

One-time DNS setup (already done): a wildcard CNAME `*.docs.modelplane.ai →
cname.vercel-dns.com` covers `main.docs` and every release subdomain. No new DNS
record is needed per release.

To publish docs for a new minor release (e.g. `v0.1.0`):

1. On `release-0.1`, set `version = "0.1"` in `docs/hugo.toml`.

2. Add the release to `docs/data/versions.yaml`, newest first, on both `main` and
   `release-0.1` (keep the file identical across branches):
   ```yaml
   versions:
     - version: "main"
       url: "https://main.docs.modelplane.ai"
     - version: "0.1"
       url: "https://v0-1.docs.modelplane.ai"
   ```
   On `main`, also set `latest = "0.1"` in `docs/hugo.toml` so the version
   dropdown and the "not the latest release" banners point at the new release.

3. In the Vercel dashboard, create the release project for `release-0.1` (or
   reuse the existing one) and, under Settings → Domains, assign it both
   `docs.modelplane.ai` (the apex) and `v0-1.docs.modelplane.ai`. Leave
   `HUGO_BASEURL` unset in Production so the build bakes `https://docs.modelplane.ai/`.
   Trigger a redeployment and confirm both domains serve.

4. Merge the changes. The apex now serves the new release directly, and the
   version dropdown on every build links to it.

The dev project's `main.docs.modelplane.ai` domain and its
`HUGO_BASEURL = https://main.docs.modelplane.ai/` env var (scoped to `main`) are a
one-time setup, done when the first release ships.

To fix a typo or update content in an archived version, push to the release branch.
The versioned deployment rebuilds automatically.

When a new minor ships (e.g. `v0.2.0`):

1. Repeat steps 1–4 for `release-0.2`, adding the `v0.2` entry above `v0.1` in
   `versions.yaml` on every branch and bumping `latest` to `0.2` on `main`.
2. Move `docs.modelplane.ai` to the `release-0.2` project so the apex tracks the
   new latest.
3. On the old `release-0.1` project, set `HUGO_BASEURL = https://v0-1.docs.modelplane.ai/`
   so it stays self-canonical at its permanent subdomain now that it no longer
   owns the apex.
