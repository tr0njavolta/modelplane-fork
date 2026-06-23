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

Docs are versioned at the minor level, each version on its own subdomain, served
by a single Vercel project with one branch domain per build:

- `docs.modelplane.ai` — the canonical apex. Its home page redirects to the
  latest release, so a reader who types the bare domain lands on the latest docs.
- `vX-Y.docs.modelplane.ai` — each minor release (`v0-1`, `v0-2`, …), built from
  its `release-X.Y` branch.
- `main.docs.modelplane.ai` — the dev docs, built from `main`, so unreleased docs
  stay browsable.

Both `main.docs` and the apex are built from `main`; what tells them apart is the
baseURL. The apex build redirects because its baseURL isn't `main`'s own subdomain
(`docs/themes/geekboot/layouts/index.html`). The redirect target is the latest
release's URL, looked up in `docs/data/versions.yaml` by `latest` in
`docs/hugo.toml`.

`docs/data/versions.yaml` is the single list of every version and its URL. It
drives the version dropdown and the apex redirect, and must be identical on every
branch — `main` and all release branches — so each build offers the same switcher.

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
   On `main`, also set `latest = "0.1"` in `docs/hugo.toml` so the apex redirects
   to the new release.

3. In the Vercel dashboard, open the `modelplane-docs` project and add a branch
   domain for the release:
   - Go to Settings → Domains, add `v0-1.docs.modelplane.ai`, and assign it
     to the `release-0.1` branch.
   - Add a Production environment variable scoped to the `release-0.1` branch:
     `HUGO_BASEURL` = `https://v0-1.docs.modelplane.ai/`.
   - Trigger a redeployment of `release-0.1` and confirm the subdomain serves.

4. Merge the changes. The apex now redirects to the new release, and the version
   dropdown on every build links to it.

The `main.docs.modelplane.ai` domain and its `HUGO_BASEURL = https://main.docs.modelplane.ai/`
env var (scoped to `main`) are a one-time setup, done when the first release ships.

To fix a typo or update content in an archived version, push to the release branch.
The versioned deployment rebuilds automatically.

When a new minor ships (e.g. `v0.2.0`), repeat steps 1–4 for `release-0.2`, adding
the `v0.2` entry above `v0.1` in `versions.yaml` on every branch and bumping
`latest` to `0.2` on `main`.
