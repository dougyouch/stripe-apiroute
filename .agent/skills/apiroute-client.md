---
name: apiroute-client
description: Create, set up and maintain a GitHub repository that publishes apiroute-generated Python clients for an API described by OpenAPI/Swagger specs, WSDLs or a GraphQL schema (with hand-written operations). Covers gathering the specs and documentation links, the repository layout, the apis.yaml generation config, hand-written auth base classes, the README, CI/Build/Release workflows (the Build workflow regenerates and commits changes), PyPI publishing (only if the user wants it), and ongoing maintenance.
---

# apiroute client repositories

Use this skill when asked to create a client repository for an API ("make a <api>-apiroute repo", e.g. `stripe-apiroute`), or to maintain one: adding or removing an API, a spec change that broke generation, upgrading apiroute, or setting up releases.

A client repository holds generated code that is never edited by hand. It is the output of [apiroute](https://github.com/dougyouch/apiroute)'s generator (`apiroute generate openapi|wsdl|graphql`), applied to specs listed in one config file, and refreshed by a scheduled workflow. The one exception is GraphQL: its `.graphql` operation files are hand-written inputs, kept in `operations/` (see below). A worked example is **[ebay-apiroute](https://github.com/dougyouch/ebay-apiroute)**; the examples below use it, but nothing here is specific to eBay. Copy its files and adapt them rather than writing new ones; the sections below say what to change.

## 1. Gather before creating anything

Ask the user (an AskUserQuestion-style prompt with choices works well), and confirm what you find:

1. **Names:**
   - the repository (`<api>-apiroute`)
   - the PyPI name (the same)
   - the Python package (`<api>_apiroute`)
   - the GitHub owner
2. **Which APIs to cover.** Offer "everything with a published spec" as the default; lazy loading makes unused APIs free.
3. **Will it be released to PyPI?** Always ask; never assume. If yes, the repo gets `release.yml` and the user must create a PyPI pending publisher (step 6). If no, skip `release.yml`, and the README says to install from GitHub (`pip install git+https://github.com/<owner>/<repo>`).
4. **Public or private.** Releasing to PyPI implies public.
5. **Auth model:** OAuth bearer tokens, API keys, Basic auth, request signing, SOAP header credentials, or extra per-call parameters. This decides the auth base class (step 4).
6. **For a GraphQL API, which operations.** A GraphQL schema doesn't say what to fetch, so the repository holds the queries and mutations to generate. Ask what the user needs (or start from the API's documented examples), and write them as `.graphql` files. Also ask whether introspecting the schema needs a token, and the name of the environment variable that holds it.

Then find each API's machine-readable description and its documentation page:

- **Download every spec and check its content, not the HTTP status.** Some sites (eBay's, for example) answer unknown URLs with a normal 200 page. A spec must parse as JSON/YAML with an `openapi` or `swagger` key, or as XML with `definitions` (WSDL).
- **For GraphQL, introspect the endpoint** with `apiroute fetch-schema <endpoint> -o /tmp/x.graphql -H "Authorization: Bearer $TOKEN"`. Some APIs also publish the schema as a file (GitHub's `schema.docs.graphql`), which works without a token.
- **Treat documentation links the same way.** Some sites serve an error page to `curl` but the real page to browsers. A page's `<title>` that says "Error" or "Not Found" means "try another URL or a web search", not "it doesn't exist". Every API in the README table needs a working documentation link.
- **Probe URL patterns** when a site publishes many specs (eBay, as an example: `/api-docs/master/<group>/<api>/openapi/3/<group>_<api>_<version>_oas3.json`), but keep only the ones whose content validates.
- **Generate each spec into a scratch directory** before committing to it: `apiroute generate openapi <url> -o /tmp/x --models`, or for GraphQL `apiroute generate graphql /tmp/x.graphql --operations <dir> -o /tmp/x --models`, which reports every operation that doesn't match the schema as `file:line:column`. Note any spec the generator can't handle, and either fix apiroute or leave that API out, telling the user which.

## 2. Repository layout

```text
<repo>/
  apis.yaml                     the source of truth: one entry per API (hand-written)
  specs/                        committed copies of the specs (written by --fetch; SDL for GraphQL)
  operations/<api>/             GraphQL operations, one folder per API (hand-written)
  scripts/generate.py           fetch specs, run apiroute generate, write the README table
  scripts/next_release.py       each release's version, notes and changelog entry, from the commits (if releasing)
  src/<package>/
    __init__.py                 package docstring (hand-written)
    auth.py                     auth base classes the generated clients extend (hand-written)
    <group>/__init__.py         written by scripts/generate.py
    <group>/<api>/              generated by apiroute (never edited)
  tests/                        config checks, auth behaviour, one call per protocol
  .github/workflows/            ci.yml, build.yml, release.yml (if releasing)
  AGENT.md  CLAUDE.md           agent guidance; CLAUDE.md imports AGENT.md with "@AGENT.md"
  .agent/skills/apiroute-client.md   this skill (copy it into the new repository)
  README.md  CHANGELOG.md  LICENSE  pyproject.toml  uv.lock
```

`apis.yaml`, one entry per API (shown with ebay-apiroute's values as an example):

```yaml
package: ebay_apiroute
apis:
  - name: sell_inventory            # unique; also the spec file name in specs/
    title: Inventory API            # shown in the README table
    format: openapi                 # openapi (covers Swagger 2.0) or wsdl
    spec: https://.../sell_inventory_v1_oas3.json
    docs: https://developer.ebay.com/api-docs/sell/static/api-inventory.html
    module: sell.inventory          # -> src/ebay_apiroute/sell/inventory/
    client: SellInventoryApi
    base_class: ebay_apiroute.auth:EbayAuth   # optional; owns auth
    models: true                    # optional, default true: the typed .models layer
    nullable_fields: false          # optional: --nullable-fields, when the spec says fields are never null but the API sends null
    operation_names: specs/sell_inventory.names.json   # optional: --operation-names, operation ID -> dotted section.method
  - name: github                    # a GraphQL API
    title: GitHub GraphQL API
    format: graphql
    spec: https://api.github.com/graphql      # introspected by --fetch into specs/github.graphql
    spec_headers:                   # optional, for introspection; values name environment variables
      Authorization: "Bearer ${GITHUB_TOKEN}"
    operations: operations/github   # hand-written .graphql files; subfolders become sections
    endpoint: https://api.github.com/graphql  # --endpoint: base_url and path
    scalars:                        # optional --scalar mappings
      DateTime: datetime:datetime
    persisted_queries: false        # optional: --persisted-queries, for servers with APQ
    docs: https://docs.github.com/en/graphql
    module: github
    client: GitHubApi
    base_class: github_apiroute.auth:GitHubAuth
```

`scripts/generate.py`: copy an existing one, such as [ebay-apiroute's](https://github.com/dougyouch/ebay-apiroute/blob/main/scripts/generate.py). It does the following:

- `--fetch` downloads each spec, validates it, and re-indents JSON (keeping key order) so diffs stay readable. For `format: graphql` it runs `apiroute fetch-schema <spec> -o specs/<name>.graphql`, expanding `${VAR}` in `spec_headers` from the environment and passing each as `-H`. Never write a token to a file.
- It runs `apiroute generate <format> specs/<name> -o src/<package>/<module> --client-name ... --models --base-class ...` for each API, adding `--nullable-fields` when an API sets `nullable_fields`, and `--operations`, `--endpoint`, `--scalar` and `--persisted-queries` for GraphQL. [github-apiroute's script](https://github.com/dougyouch/github-apiroute/blob/main/scripts/generate.py) has the GraphQL support; ebay-apiroute's predates it.
- It writes the group packages' `__init__.py`, marked "Generated by scripts/generate.py".
- It rewrites the README table between `<!-- apis:start -->` and `<!-- apis:end -->`.
- `--only NAME` limits the run to the named APIs.
- When a spec's tags and operationIds make poor names, pass `--operation-names` a JSON map of operation ID to dotted name (`customers.create`, `issuing.cards.list`): sections nest. Keep the map in `specs/` so its diffs are reviewed with the spec's. If the spec carries better names in vendor extensions, have `generate.py` write the map from them on every run; [stripe-apiroute](https://github.com/dougyouch/stripe-apiroute) builds it from Stripe's `x-stripeOperations`.

ebay-apiroute's script also has an eBay-specific `_write_trading_version`. Drop it, or adapt it if your auth class must read a value from a spec.

`pyproject.toml`:
- Depend on `apiroute>=<current>` (add `apiroute[soap]` when any API is a WSDL; GraphQL clients need nothing extra at run time) and `pydantic>=2.6` (generated models fail on pydantic 2.1–2.5). Put `apiroute[codegen]`, `pytest` and `ruff` in the `dev` dependency group.
- Set ruff's `line-length = 100` and `extend-exclude = ["specs"]`.
- Keep `specs/` out of the sdist.
- If releasing, take the version from the git tag: `dynamic = ["version"]`, `requires = ["hatchling", "hatch-vcs"]` and `[tool.hatch.version] source = "vcs"`. Nothing in the repository holds the version; a release commits only its CHANGELOG.md entry.

## 3. Generate, lint, import

```bash
uv sync
uv run python scripts/generate.py --fetch
uv run ruff check . && uv run ruff format --check .   # generated code passes both
```

Then import every module and build every model, on the lowest and highest supported Python versions. A Python 3.10 import catches annotation problems that 3.14's deferred annotations hide. The checks live in `tests/test_apis_config.py`:

- every `apis.yaml` entry has a spec file, a documentation link, an importable client and the configured base class
- every route compiles

## 4. Auth base class (hand-written, in `auth.py`)

Every generated root client extends the `base_class` from `apis.yaml`, and apiroute then generates no auth of its own. Write the class once, by subclassing `apiroute.Client`. Sections inherit its `headers` and `query_params`, and they use its hooks.

| Need | How |
| --- | --- |
| Bearer token | `headers = {"Authorization": lambda self: f"Bearer {self.current_token()}" if self._token else None}`; accept a string or a function returning one (for refreshing OAuth helpers) |
| API key in a header or query | an entry in `headers` or `query_params` reading an attribute |
| Request signing | `on_request(self, request)` returning `dataclasses.replace(request, headers=...)` |
| Per-call parameters | `on_request`, with `request.operation` (the spec's operationId or WSDL operation name) |
| Retrying safe operations | apiroute 2 only retries `GET`, `HEAD` and `OPTIONS` after a read timeout. Override `idempotent(self, request)` to return `True` for operations that are safe to repeat, by `request.operation` (a SOAP API's `Get*` calls) or `request.method`, and `None` for the rest. Set `idempotency_key = "Idempotency-Key"` instead for APIs that honor that header |
| SOAP header credentials | `soap_header(self, operation) -> dict`, in the same xmltodict shape as bodies |
| Sandbox or region hosts | an `__init__` flag that sets `kwargs["base_url"]` from `type(self)._config.base_url` |

Test each behaviour in `tests/` with `apiroute.testing`: inside `with mock_transport() as mock:`, call the client and assert on `mock.last`, which records the operation, the header or parameter on the wire, the sandbox host, and a SOAP header if any. Match responses by operation with `mock.on(operation=...)`.

## 5. README (generate it as part of setup)

It must have:
- a one-paragraph description with CI and Build badges
- installation instructions (PyPI, or from GitHub when not releasing)
- usage per protocol: dict and typed calls, `.aio`, auth arguments and sandbox
- **links to the API's documentation and its auth or token guide**
- the generated API table, with a docs link per API
- **how the repository stays up to date:**
  - the Build schedule
  - the `specs/` snapshot and `git log -p specs/`
  - apiroute as the generator
  - the commit types and the releases they produce
  - what CI checks
- development commands, and how to add an API

Use an existing client repository's README (ebay-apiroute's, for example) as the template.

## 6. Workflows

Copy them from an existing client repository ([github-apiroute](https://github.com/dougyouch/github-apiroute), for example) and change the names, the PyPI project and the schedule.

- **`ci.yml`** runs on pull requests and `workflow_call` (release.yml runs it before every release):
  - Lint: `ruff check` and `ruff format --check`.
  - `generated-is-current`: runs `scripts/generate.py` without `--fetch` and fails on any `git status` difference. This catches hand edits, and specs out of step with the code.
  - Tests on every supported Python version.
- **`build.yml`** runs on a schedule and `workflow_dispatch`:
  1. `uv lock --upgrade-package apiroute`, then `uv sync`.
  2. `scripts/generate.py --fetch`.
  3. Lint and test.
  4. If `git status` shows changes, commit and push to main:
     - `feat(specs): update clients from <API>'s latest specs` when `specs/` changed (a minor release)
     - otherwise `fix(codegen): regenerate clients with apiroute <version>` (a patch)

  It needs `permissions: contents: write`. If `main` is protected, give the workflow a bypass or have it open a PR instead. A GraphQL API whose introspection needs a token gets it from a repository secret, exposed to the fetch step as the environment variable `spec_headers` names.
- **`release.yml`**, only if the user said yes to PyPI, releases every push to main; there's no release PR. It runs CI, then `scripts/next_release.py` works out the version from the conventional commits since the last `vX.Y.Z` tag (`feat!:` or a `BREAKING CHANGE:` footer: major, `feat:` minor, anything else patch) and the notes. It commits the notes to CHANGELOG.md as `chore(release): vX.Y.Z` (which the next release's notes leave out), tags that commit and pushes both at once, then builds (hatch-vcs reads the version from the tag), publishes with `uv publish --trusted-publishing always` in the `pypi` environment, and creates the GitHub release with the notes and distributions. Each step skips what's already done (the tag, the PyPI version, the release), so rerunning a failed release finishes it, and a run on an already-tagged commit changes nothing. A run whose commit is no longer main's newest leaves the release to the newer push, which includes it. The release commit is pushed with `GITHUB_TOKEN`, so it triggers nothing; `main` may forbid force pushes but must accept the workflow's fast-forward push. Besides `push` and `workflow_dispatch`, trigger it on `workflow_run` of Build: commits pushed with `GITHUB_TOKEN` don't trigger other workflows. Copy apiroute's or github-apiroute's `release.yml` and `scripts/next_release.py`.

Each repository needs these GitHub and PyPI settings:

- Delete branches on merge: `gh repo edit --delete-branch-on-merge`.
- If releasing:
  - The user creates a PyPI **pending publisher**: the project name, the repository owner and name, workflow `release.yml`, environment `pypi`.
  - The first push to main releases `0.1.0` (no tag yet); every later push releases the next version.

## 7. Maintenance

- **Routine:** none. Build commits changes, and every commit on main is tested, tagged and published on its own. The tests are the gate, so keep them meaningful: config checks, auth behaviour, and one call per protocol.
- **A spec change breaks generation:** Build fails before committing, and the last good code stays on main. Reproduce with `scripts/generate.py --fetch --only <name>`, then fix apiroute (preferred) or the auth class. Never patch `specs/` or generated files by hand.
- **A GraphQL schema change breaks an operation:** Build fails listing each broken operation as `file:line:column`. The operations are yours: update them in `operations/<api>/` (a renamed or removed field), regenerate and commit (`feat!:` if a released method's result changed shape). Deprecation warnings in the Build log say what to move off before the API removes it.
- **Add a GraphQL operation:** add a `.graphql` file (or a query to one), `generate.py --only <name>`, test and commit (`feat:`).
- **Lists:** for a Relay connection the user wants in full, put `@paginate` on the connection field and give the operation a `$after: String` variable. The generated method then iterates every item across pages. Leave it off where one page (with `totalCount`) is what's wanted, because adding it later changes the method's return type.
- **Add an API:** add an `apis.yaml` entry, verifying its spec and docs as in step 1, then `generate.py --fetch --only <name>`, then test and commit (`feat:`).
- **Remove an API:** delete its entry, its spec and its folder, then regenerate and commit (`feat!:` if it was released).
- **apiroute adds a feature you need:** release apiroute, raise the minimum in `pyproject.toml`, `uv lock`, regenerate, commit.

## 8. Before handing over

- [ ] Every API has a working spec and a working docs link (checked by content, not by status).
- [ ] `ruff check`, `ruff format --check`, the tests, and a Python 3.10 import of every module all pass.
- [ ] CI, Build (run it once by hand) and, if releasing, Release are green.
- [ ] Branch auto-delete is on. If releasing, the pending publisher exists, or the user knows to create it.
- [ ] README, AGENT.md, CLAUDE.md (importing AGENT.md) and this skill are in the repository.
