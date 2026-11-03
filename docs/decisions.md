# Decisions

This page lists the decisions that a maintainer must know. Each entry gives the decision, the reason, the date or version, and the place in the code.
The setup, the tests, the record cache and the rules for model ids are in [AGENTS.md](../AGENTS.md). This page does not repeat them.
The guide for ramabana and Leela on the Copilot backend (`docs/copilot-downstream.md`) and the old list of ideas (`ideas.md`) are in the git history.

## Shape of the package

- **rishi is the model broker.** One `Chat` drives every backend, and every model call of ramabana and its apps goes through it. Apps such as abhyasa use ramabana, not bare rishi, so that they get its routing and fallbacks. (Oct 2026) `nbs/00_core.ipynb`.
- **Tool parsing lives in uraiyadal, pinned to one version.** Tool tags, argument reading, `unread` and `tool_parse_failed` come from urai. rishi pins an exact version, because a new urai version can change which calls run. (0.1.32, 28 Aug 2026; pinned since 0.1.48) `pyproject.toml`.
- **Hosted models go through fastllm.** `rishi.remote` follows fastllm and aidialog closely. (0.1.0) `nbs/04_remote.ipynb`.
- **Backends that wrap a tool are explicit.** `claude/`, `copilot/` and `ollama/` need a prefix, so an old model id never moves to a new backend. The cursor backend was removed in 0.1.20 (19 Aug 2026). `runtimes` in `nbs/00_core.ipynb`.

## Claude Code backend

- **Run the `claude` on `$PATH`.** The copy that the Agent SDK bundles lags behind and refuses new models. (0.1.40, Oct 2026) `cli_path` in `nbs/06_claude.ipynb`.
- **A reply stops at its first tool call.** Text after the call is dropped, and the session is marked stale. Why: the model wrote results that it did not see yet. (0.1.43, 0.1.61) `nbs/06_claude.ipynb`.
- **One retry for each wire call.** A failed connect, a stall and a dead session share one retry. A turn that already showed text is not sent again. (0.1.49 to 0.1.52) `nbs/06_claude.ipynb`.
- **A one-shot has no tools and no MCP servers.** It sets `strict_mcp_config`, but only when no enterprise MCP config exists (`managed_mcp()`). Claude Code refuses the flag on a managed machine. (0.1.62, 0.1.63, 30 Oct 2026) `MANAGED_MCP` in `nbs/06_claude.ipynb`.

## Copilot backend

- **Copilot is a `RemoteChat` with `api_name='openai_chat'`.** fastllm has no Copilot vendor, and the fixed name stops it from sending a Gemini id to Gemini. (0.1.17, 16 Aug 2026; 0.1.56) `nbs/07_copilot.ipynb`.
- **Keep the GitHub OAuth token on disk, never the Copilot token.** The Copilot token lasts about 30 minutes. `CopilotAuth` gets a new one before it expires. `copilot_login()` writes the OAuth token to `~/.config/rishi/copilot.json` with mode `0600`. Share one `CopilotAuth` across the chats of one session. `nbs/07_copilot.ipynb`.
- **No request headers that change.** fastllm keeps its HTTP client by the arguments that made it. A new header value for each call makes a new client each time. Thus rishi sends no `x-request-id`. `nbs/07_copilot.ipynb`.
- **Ask Copilot for the model list.** The list depends on the plan of the account. Hosts call `copilot_models()` and do not keep a fixed list. `nbs/07_copilot.ipynb`.

## On-device backends

- **Ollama runs from a private folder.** rishi downloads Ollama into `~/.cache/rishi/ollama` and runs `ollama serve` there, with no root. It starts a daemon only on this machine, and it gives the daemon `/dev/null` as its input. (0.1.53, 0.1.56) `LOCAL_HOSTS` in `nbs/08_ollama.ipynb`.
- **Chats that share one LiteRT engine take turns.** `engine_lock` lets one send run at a time, and frees the engine while a tool runs. Why: two sends on one GPU engine gave empty turns. (0.1.39, 28 Sep 2026) `nbs/02_litert.ipynb`.
- **A full LiteRT window is recovered for each step.** rishi drops old turns and sends the step again one time. When text already showed, it raises `ContextWindowExceededError` and sends nothing again, so no text repeats and no tool runs two times. (0.1.58, 0.1.59, 30 Oct 2026) `nbs/02_litert.ipynb`.

## One-shot calls

- **`think=False` sends no reasoning effort.** The model runs at its default. Some models refuse `'minimal'`. (0.1.66, 3 Nov 2026) `NO_THINK_EFFORT` in `nbs/04_remote.ipynb`.
- **An effort that a provider does not have goes as the nearest one.** `EFFORT_MAP` holds the map. A 400 that names the effort gets one more try with no effort. Other errors are raised. (0.1.51, 0.1.56) `nbs/04_remote.ipynb`.

## Release and docs

- **Release with `nbdev-release-gh --no-changelog --no-editor --yes`, then `nbdev-pypi`.** Write the CHANGELOG entry by hand first. Without the flags, the tool writes over the notes or stops at a prompt. On a clean tree it fails. Then make the release with `gh release create <version>`. (26 Oct 2026)
- **Give the imports of a test cell their own cell.** The docs build runs only the cells with an import, `#| export` or `show_doc`. Split only the cells that the build names: a cell that sets the environment or a fake before its import must stay as it is. Before a release push, run `uv run nbdev-proc-nbs --force`. (0.1.62 to 0.1.66, 3 Nov 2026)
