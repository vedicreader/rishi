# Wiring the Copilot backend into ramabana and Leela

rishi 0.1.17 adds a seventh runtime, `copilot`, in `rishi/copilot.py` (source:
`nbs/07_copilot.ipynb`). Nothing downstream breaks: no existing id changes runtime, and no public
signature changed. What follows is the work each consumer needs to make the backend reachable.

## What rishi now exports

| name | what it is |
|---|---|
| `rishi.copilot.CopilotChat` | a `RemoteChat` subclass, `_runtime = 'copilot'`, `local = False` |
| `rishi.copilot.CopilotAuth` | holds one Copilot token and re-mints it before expiry |
| `rishi.copilot.copilot_models(auth=None)` | ids this account can reach, asked of Copilot |
| `rishi.copilot.copilot_login()` | GitHub device flow, saves to `~/.config/rishi/copilot.json` |
| `rishi.copilot.copilot_oauth()` | finds a GitHub OAuth token, or raises with instructions |
| `rishi.copilot.copilot_default` | `'gpt-4.1'` |
| `rishi.core.runtimes['copilot']` | `('rishi.copilot', 'CopilotChat')` |

Install with the new extra, `rishi[copilot]`. It pulls `rishi[remote]` plus `httpx`.

Two properties matter to a caller:

- **Prefix only.** `Chat('copilot/gpt-4.1')` or `runtime='copilot'`. A bare `gpt-4.1` or
  `claude-sonnet-4.5` still resolves to `remote`, because Copilot serves other vendors' models under
  their own names and inferring it would reroute existing callers.
- **The token expires.** Copilot tokens last about half an hour. `CopilotChat` re-mints per turn
  through `CopilotAuth`, so a long session is safe. Share one `CopilotAuth` across chats to share the
  exchange.

## ramabana

Ramabana routes models through rishi, so the changes are in its routing and CLI layers rather than in
any transport code.

1. **`ramabana/runtime.py`.** Wherever the runtime names or the model alias table are enumerated, add
   `copilot`. Aliases must carry the prefix, because ramabana users type a short name:
   `'copilot-gpt41': 'copilot/gpt-4.1'`, `'copilot-sonnet': 'copilot/claude-sonnet-4.5'`. Do not add
   a bare `gpt-4.1` alias that points at copilot, or `--model gpt-4.1` becomes ambiguous with the
   hosted route.
2. **`ramabana/cli.py`.** `--model` already passes through to rishi, so a prefixed id works with no
   change. What is worth adding is a preflight, so a missing subscription fails with a sentence
   rather than a 401 mid-turn:

   ```python
   if model.startswith('copilot/'):
       from rishi.copilot import copilot_oauth
       copilot_oauth()          # raises with the env vars and `copilot_login()` in the message
   ```

   Also add a `--list-models` branch (or extend the existing one) that calls
   `rishi.copilot.copilot_models()` for the copilot runtime. Copilot's list is per-plan, so a static
   table in ramabana would be wrong for some accounts.
3. **Auth surface.** Ramabana's docs and any `RAMABANA_*` environment table should mention that
   copilot reads `GITHUB_COPILOT_OAUTH_TOKEN`, `GH_COPILOT_TOKEN`, `GH_TOKEN` or `GITHUB_TOKEN`, and
   falls back to the editor config files. If ramabana already ships a `login` verb, route
   `ramabana login copilot` to `rishi.copilot.copilot_login()`.
4. **Shared auth for multi-agent runs.** If ramabana builds several chats per session (subagents,
   a judge, a summarizer), build one `CopilotAuth` in the session object and pass `auth=` to each
   `CopilotChat`. Otherwise every chat performs its own token exchange against GitHub.
5. **Tools.** Nothing to do. `CopilotChat` inherits `RemoteChat`'s native tool channel, so
   ramabana's tool specs, approval gate and budget work unchanged. Note that tool-call quality varies
   by the model Copilot is fronting, the same caveat that applies on `remote`.
6. **`pyproject.toml`.** If ramabana pins rishi extras, add `copilot` to the set it requests.

## Leela

Leela is the browser surface rishi already talks to: `hitl_policy(modes, browser=True)` POSTs to
`$LEELA_URL/agent/approval/request` (default `http://127.0.0.1:5001`). Copilot changes nothing about
that contract, so approval keeps working the moment the backend is selectable. The work is in the
picker and in sign-in.

1. **Model picker.** Add a copilot group. Populate it from `rishi.copilot.copilot_models()` rather
   than a hardcoded list, and cache the result for the session, because the call costs a token
   exchange. Label each entry with `rishi.core.model_caps(id)`, which already handles copilot ids by
   falling through to fastllm's table, so vision-capable entries can be marked.
2. **Prefix in the value, not the label.** The picker's value must be `copilot/<id>`. Showing the
   bare id is fine, but sending it is not, because it would route to `remote` and ask for a vendor key.
3. **Sign-in.** Copilot is the first rishi backend whose credential a browser UI can usefully help
   with. Two states worth rendering:
   - *not signed in*: `copilot_oauth()` raises. Show its message, and offer a button that runs
     `copilot_login()` server-side. The device flow prints a URL and a user code, so surface both and
     poll while the user completes it in another tab.
   - *signed in*: `CopilotAuth().token()` succeeds. Show the endpoint it returned, which names the
     plan (`api.individual.githubcopilot.com` and friends).
4. **One `CopilotAuth` per kernel.** Hold it beside the kernel's chat, not per request. Every chat
   built in that kernel should be passed `auth=`.
5. **Error surface.** A 401 or 403 from the exchange raises `PermissionError` with a message about
   the subscription and the app the token came from. Render that verbatim. It is the one failure
   users will hit, and guessing at it is worse than quoting it.

## Things neither should do

- Do not cache the Copilot bearer token to disk. It is short-lived, and `CopilotAuth` re-mints it for
  free. The thing worth persisting is the GitHub OAuth token, which `copilot_login()` already writes
  to `~/.config/rishi/copilot.json` with mode `0600`.
- Do not add per-request headers of your own with changing values. fastllm caches its HTTP client on
  the arguments it was built from, so a header like a fresh request id builds a new client per call.
  rishi deliberately omits `x-request-id` for that reason.
- Do not hardcode a model list. Copilot's catalogue is per-plan and moves.
