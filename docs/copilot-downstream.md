# Wiring the Copilot backend into ramabana and Leela

rishi 0.1.17 adds a seventh runtime, `copilot`, in `rishi/copilot.py` (source: `nbs/07_copilot.ipynb`). No existing id changes runtime, and no public signature changed. This page lists the work each consumer needs to do to reach the backend.

## What rishi exports

| name | what it is |
|---|---|
| `rishi.copilot.CopilotChat` | a `RemoteChat` subclass, `_runtime = 'copilot'`, `local = False` |
| `rishi.copilot.CopilotAuth` | holds one Copilot token and re-mints it before expiry |
| `rishi.copilot.copilot_models(auth=None)` | ids this account can reach, asked of Copilot |
| `rishi.copilot.copilot_login()` | GitHub device flow, saves to `~/.config/rishi/copilot.json` |
| `rishi.copilot.copilot_oauth()` | finds a GitHub OAuth token, or raises with instructions |
| `rishi.copilot.copilot_default` | `'gpt-4.1'` |
| `rishi.core.runtimes['copilot']` | the `Runtime` record for `rishi.copilot.CopilotChat` |

Plain `rishi` includes Copilot, `remote` and `httpx`. No extra is required.

A caller needs to know two things:

- **Prefix only.** Use `Chat('copilot/gpt-4.1')` or `runtime='copilot'`. A bare `gpt-4.1` or `claude-sonnet-4.5` still resolves to `remote`. Copilot serves models of other vendors under their own names. Inferring Copilot from those names would reroute existing callers.
- **The token expires.** Copilot tokens last about half an hour. `CopilotChat` re-mints the token through `CopilotAuth` before it expires. A long session continues. Share one `CopilotAuth` across chats to share the token exchange.

## ramabana

Ramabana routes models through rishi. The changes are in its routing and CLI layers. No transport code changes.

1. **`ramabana/runtime.py`.** Add `copilot` wherever the code lists runtime names or the model alias table. Aliases must carry the prefix, because ramabana users type a short name: `'copilot-gpt41': 'copilot/gpt-4.1'` and `'copilot-sonnet': 'copilot/claude-sonnet-4.5'`. Do not add a bare `gpt-4.1` alias that points at copilot. `--model gpt-4.1` would then be ambiguous with the hosted route.
2. **`ramabana/cli.py`.** `--model` passes its value to rishi. A prefixed model id needs no CLI change. Add a preflight check. A missing subscription then fails with a clear message and not with a 401 during a turn:

   ```python
   if model.startswith('copilot/'):
       from rishi.copilot import copilot_oauth
       copilot_oauth()          # raises with the env vars and `copilot_login()` in the message
   ```

   Also add a `--list-models` branch, or extend the existing one, that calls `rishi.copilot.copilot_models()` for the copilot runtime. Copilot's list depends on the plan, so a static table in ramabana is wrong for some accounts.
3. **Auth surface.** Document in ramabana's docs, and in any `RAMABANA_*` environment table, how copilot finds a token. It reads `GITHUB_COPILOT_OAUTH_TOKEN` or `GH_COPILOT_TOKEN` first. It then reads the editor config files. It reads `GH_TOKEN` or `GITHUB_TOKEN` last, because Copilot does not accept a personal access token, and such a token may be in one of them. If ramabana has a `login` verb, route `ramabana login copilot` to `rishi.copilot.copilot_login()`.
4. **Shared auth for multi-agent runs.** If ramabana builds several chats per session (subagents, a judge, a summarizer), build one `CopilotAuth` in the session object and pass `auth=` to each `CopilotChat`. Without it, every chat does its own token exchange with GitHub.
5. **Tools.** No work is needed. `CopilotChat` inherits the native tool channel of `RemoteChat`. The ramabana tool specs, approval gate and budget work unchanged. Tool-call quality depends on the model that Copilot serves, as it does on `remote`.
6. **`pyproject.toml`.** Depend on plain `rishi`. Do not add or pin a `copilot` extra.

## Leela

Leela is the browser surface that rishi already talks to. `hitl_policy(modes, http=True)` sends a POST to `/agent/approval/request` on the URL in `URAI_APPROVAL_URL` (default `http://127.0.0.1:5001`). Copilot does not change this contract. Approval works as soon as the backend can be selected. The work is in the model picker and in sign-in.

1. **Model picker.** Add a copilot group. Fill it from `rishi.copilot.copilot_models()`, not from a hardcoded list. Cache the result for the session, because the call costs a token exchange. Label each entry with `rishi.core.model_caps(id)`. For copilot ids it uses the fastllm table. You can mark the entries that accept images.
2. **Prefix in the value.** The picker value must be `copilot/` followed by the model id, such as `copilot/gpt-4.1`. The label may show the bare id. Sending the bare id routes the request to `remote`, which asks for a vendor key.
3. **Sign-in.** Copilot is the first rishi backend whose credential a browser UI can help with. Render two states:
   - *Not signed in*: `copilot_oauth()` raises. Show its message and offer a button that runs `copilot_login()` on the server. The device flow prints a URL and a user code. Show both and poll while the user completes the sign-in in another tab.
   - *Signed in*: `CopilotAuth().token()` succeeds. Show the endpoint that it returned. The endpoint names the plan (`api.individual.githubcopilot.com` and similar).
4. **One `CopilotAuth` for each kernel.** A kernel is the Python process that runs the code of one Leela notebook. Keep the `CopilotAuth` next to the chat of the kernel, not per request. Pass `auth=` to every chat built in that kernel.
5. **Error surface.** A 401, 403 or 404 from the token exchange raises `PermissionError`. Its message names the subscription and the app that the token came from. Render the original `PermissionError` message as it is.

## What neither consumer should do

- Do not cache the Copilot bearer token on disk. It is short-lived. `CopilotAuth.token()` requests a new Copilot token from the GitHub OAuth token when the cached one is near expiry. Persist the GitHub OAuth token. `copilot_login()` already writes it to `~/.config/rishi/copilot.json` with mode `0600`.
- Do not add per-request headers of your own with changing values. fastllm caches its HTTP client on the arguments that built it. A header such as a new request id builds a new client for each call. rishi omits `x-request-id` for this reason.
- Do not hardcode a model list. The Copilot catalogue depends on the plan and changes over time.
