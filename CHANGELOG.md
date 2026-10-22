# Release notes

<!-- do not remove -->

## 0.1.55

- Pins uraiyadal 0.0.17: a stray tag no longer drops a tool call's arguments, an unread call is never run, identical calls in one reply run once, and a tag quoted in an argument splits nothing.

## 0.1.54

- remote: a tool call whose arguments fastllm cannot decode no longer ends the turn with a bare `JSONDecodeError`. A call cut off at the output cap goes back to the model with urai's `cut_msg_`, and the next step runs at `CUT_CAP_MULT` (4) times the cap, within the model's own maximum. Arguments that are not JSON go back naming the decoder's problem and position. A second failure in the turn raises `ToolCallError`, which says what happened, for example "openai/gpt-5.6's tool call was cut off at its 16384-token output limit". This covers sent and streamed turns on the Responses, chat-completions (Azure included) and Anthropic wires.
- remote: a `JSONDecodeError` that fastllm did not raise while decoding tool arguments, such as one from a proxy's HTML page, is raised unchanged.
- remote: `ask(schema=)` tries once more after a cut-off or malformed call, at the raised cap when cut off, then raises `ToolCallError`.
- remote: a `<tool_call>` block cut off in tags mode keeps `unread`, so the loop asks for it again. It ran the tool with no arguments.
- remote: with no `max_output_tokens` set, a `RemoteChat` asks for the model's own maximum output from fastllm's model table, and `DFLT_MAX_TOKENS` for a model the table does not know. `DFLT_MAX_TOKENS` is now 16,000; it was 4096 for every model, which a reasoning model's thinking could use up before it finished a tool call. An explicit `max_output_tokens` still wins.
- remote: a reply cut off at the output cap while the model was still thinking, with no text and no tool call, goes back to the model once at the raised cap, from the same one resend. A second failure raises `ToolCallError`. The turn ended on an empty answer.
- Requires uraiyadal 0.0.16.

## 0.1.53

- claude: `claude_version` runs `claude --version` with `/dev/null` as stdin. Claude Code is a Node program, and one sharing the caller's terminal can leave it non-blocking, which froze a terminal UI on its next read. The Agent SDK's own spawns of `claude` already get a pipe.
- ollama: `OllamaServer.start` gives `ollama serve` `/dev/null` as stdin, so the daemon never shares the caller's terminal.

## 0.1.52

- remote: a Gemini model named without `models/`, such as `gemini-3.5-flash` or `gemini/gemini-3.5-flash`, now works. fastllm puts the model id into Gemini's URL as given, so the request went to `v1beta/gemini-3.5-flash` and Gemini answered 404. The chat now adds `models/` on the way out, also when `vendor_name`, `api_name` or a `base_url` names the route. `model_id` stays as given. A turn's `usage['model']` now reads `models/gemini-3.5-flash`.
- claude: a failure while connecting is tried once more, with a status note to `on_stall`. On a live session that is a `CLIConnectionError`, Claude Code's initialize request timing out, or a connect that takes longer than `timeout`. On a query it is the same before any message arrives. Before, it was raised at once. A missing `claude` binary, a refusal of rishi's MCP server and any other error are still raised at once, and a cancelled turn is not retried.
- claude: each wire call has one retry, shared by a failed connect, a stall and a session that died before it said anything. A stall after a retried connect is raised, not tried again.

## 0.1.51

- claude: `ClaudeChat(tool_mode='native')` sends rishi's tools as MCP tools. The chat declares an in-process MCP server, `rishi`, with one tool per toolspec and its JSON schema. Only those tools are allowed, as `mcp__rishi__NAME`, and the schemas leave the system prompt. Each call runs through Urai's approval gate, step budget, `tool_max_len` and tool callbacks, and is written to `hist`. Calls run one at a time, in a worker thread, in the context of the thread that started the step. The silence timer waits while a tool runs. A spent budget interrupts the session, and a cancelled turn records the call as not run. The default stays `tool_mode='tags'`.
- claude: a machine whose enterprise MCP configuration refuses the server raises `ClaudeMcpRefused`, a `ClaudeError` carrying Claude Code's message. A tool name longer than 64 characters with its `mcp__rishi__` prefix raises `ValueError`.
- claude: an `effort` passed to one call now reaches a live session. A call whose `effort` differs from the one the session opened at reconnects it, resumed from `hist`. A call with no `effort` runs at the chat's own, reconnecting the same way. Before, a per-call `effort` was ignored once the session was open.
- remote: an effort level the provider's API lacks goes out as the nearest one it takes, from `EFFORT_MAP`: `max` as `xhigh` on OpenAI and Azure, and `xhigh` and `max` as `high` on Gemini. A 400 that names the effort gets the call once more without it, streamed or not, and `dropped_effort` holds the reason. While `dropped_effort` is set, the chat sends no effort.
- claude: a native call that Claude Code reports only after its handler gave up waiting keeps its text in the reply, and its id never goes to a later identical call. Only a refusal of rishi's own server, or of every dynamic MCP server, is `ClaudeMcpRefused`; another MCP server's error stays as it was. A cancelled turn cancels its pending stream read.
- remote: a streamed turn honours its own `tool_mode`. The stream was split on `<tool_call>` tags by the chat's `tool_mode`, so a turn that asked for tags showed the raw tag as prose.

## 0.1.50

- A Claude Code turn's usage keeps its thinking tokens as `reasoning_tokens`, read from `output_tokens_details.thinking_tokens`. They were dropped, so a turn that thought reported `reasoning=0`. They are still part of `completion_tokens`, as Claude Code counts them. A result that does not report them leaves `reasoning_tokens` out rather than claiming 0.

## 0.1.49

- A Claude Code turn that sends nothing for `timeout` seconds is ended and tried once more. Before, `ClaudeChat` waited 600 seconds and raised `TimeoutError`. The default limit is now 240 seconds, and token deltas keep a working turn alive. The stalled query is closed and a live session's subprocess is killed. `on_stall` gets a status note when this happens, and `warnings.warn` gets it when `on_stall` is not set.
- The retry depends on what was already shown. If nothing was shown, or only thinking, the turn is sent again from the same filed conversation. If text was shown, it is not sent again: it is filed as the reply so far, and a fresh query asks Claude Code to finish it. The turn's result is the shown text plus the continuation. There is no retry after one of Claude Code's own tools has run, because a replay would run it again. A whole tool call followed by silence ends the turn with that call.
- A second silence raises `ClaudeStall`, a `TimeoutError` that names the limit and `timeout_hint`, which says how the caller raises it. The stalled attempt sent no result, so its tokens and cost are not counted. `_oneshot` is not retried.

## 0.1.48

- Pins uraiyadal 0.0.15 exactly. Its `parse_tool_tags` strips `<parameter>` elements left outside any call, so a stray parameter no longer reaches the reply text.

## 0.1.47

- `structured` on Ollama, llama.cpp and MLX builds its schema with urai's `mk_toolspec`, as the remote backend already did. A `Literal` field reaches the model as an `enum` and a pydantic model as its own fields; through fastcore's `get_schema` they were the invalid type `"object[object, object]"` and one opaque `data` object. Requires uraiyadal 0.0.14.

## 0.1.46

- remote: Azure OpenAI's chat-completions route takes the reply cap as `max_completion_tokens`. An Azure reasoning deployment refuses `max_tokens`, so `RemoteChat(api_name='openai_chat')` on a host in `MAX_COMPLETION_HOSTS`, at present `.azure.com`, `.azure.us` and `.azure.cn`, sends `max_completion_tokens` in the body instead. The Responses route, `api_name='openai'`, and every other host are unchanged.
- The `remote` page says how to reach Azure's v1 API: `base_url` set to `https://<resource>.openai.azure.com/openai/v1`, the deployment name as the model, the key as `api_key`, and `api_name='openai'`. No `api-version` is sent.

## 0.1.45

- Three names other packages were importing are now public. `rishi.llama.get_model` and `rishi.litert.get_model` find a model file from a `model_path`, the Hugging Face cache, or a download. `rishi.litert.cached_model` looks in the cache only and returns None on a miss. `rishi.litert.EngineHold` holds a shared LiteRT engine for one send. The old names `_get_model`, `_cached_model` and `_Hold` still work.

## 0.1.44

- claude: the audio error names backends that take audio: `rishi.remote` with an audio model, `rishi.litert`, `rishi.llama` with an audio `mmproj`, or `rishi.mlx` with mlx-vlm. It used to suggest `rishi.ollama`, which refuses audio too. The message is `NO_AUDIO`.
- litert: works with litert-lm-api 0.18, which renamed `Role.MODEL`'s value from `'model'` to `'assistant'`. Building a message with role `'model'` failed there.
- `rishi[dev]` is an extra, and the `dev` group points at it, so CI and the docs build install the backends and tools the notebooks need.

## 0.1.43

- claude: a reply stops at its first tool call. A model could write a call and keep going in the same response, as though the call had answered: more calls, then findings it never saw. Claude Code's `result` holds only the last text block, so the calls were lost and the invented findings reached the caller as the answer. `_drain` now stops at the first text block holding a call, readable or not. Nothing after it is shown or kept, and the turn's text is what came before the stop, so the call runs.
- When text was dropped after a call, the live session is marked stale, so the next turn refiles the conversation from `hist` rather than keep the dropped text.

## 0.1.42

- claude: a Claude Code result `The model's tool call could not be parsed` is marked `tool_parse_failed`, so the loop asks for the call again, once per turn. It raised `ClaudeError` and ended the turn. A second such result in the same turn raises `ClaudeError` ending `(no resend left)`. `norm_claude(d, model, asked)` takes whether the resend was already asked. `TOOL_PARSE_ERR` holds the matched text.

## 0.1.41

- A Claude reply holding a `<tool_call>` nothing could read is marked `tool_parse_failed`, so the loop asks for the call again. `norm_claude` used to drop the flag, and the turn ended on the prose before the call.
- Requires uraiyadal 0.0.12, which reads Claude's `<invoke name=...>` dialect.

## 0.1.40
- claude: run the `claude` on `$PATH` (`cli_path=shutil.which(bin)`), not the Agent SDK's bundled copy. The bundled copy lags Claude Code releases and refuses newer models (`Claude Code 2.1.248 does not support this model`). Without a `claude` on `$PATH` the SDK uses its bundled copy

## 0.1.39
- litert: chats sharing one engine take turns on it (`engine_lock`), letting go while a tool runs. Two
  concurrent sends on one GPU engine returned an empty turn, raised WebGPU validation errors, and slowed
  every decode step past constrained decoding's fixed 10 s logits-buffer lock (`DEADLINE_EXCEEDED ...
  Failed to lock custom tensor buffer`), which showed up first on gemma-12b. A second chat stepping onto
  the engine from the thread that already holds it raises `EngineBusy` rather than hanging that thread

## 0.1.38
- claude: refile transcript tool calls as `<tool_call>` text, so a resumed session keeps using tools
- llama, mlx, ollama: drain responses through uraiyadal `stream_resp`
- `split_model_path` and `RishiToolLoop` are public
- skill.md: name the approval API as it exists, `hitl_policy(modes, http=True)` and `URAI_APPROVAL_URL`
- requires uraiyadal>=0.0.7

## 0.1.36
fastspec update

## 0.1.35
codex needs streaming for all models

## 0.1.34
structured calls also check context fit in litert

## 0.1.33
litert models should error out loudly

## 0.1.32
rishi rewrite with uraiyadal dependencies.

## 0.1.31
discard special builds for litert

## 0.1.30
litert fixes for speculative decoding

## 0.1.29
codex requires stream=True for one shot

## 0.1.28
claude tags fixes

## 0.1.27
claude cli addition and context compaction for ollama and local models

## 0.1.26
claude model context fixes

## 0.1.25
remove claude cli. reuse llmsurgery

## 0.1.24
anthropic messages can sometimes have empty text blocks

## 0.1.23
tool loop fixes to align aidialog tool part with rishi's

## 0.1.22
setting claude context early to stop pooling everytime

## 0.1.21
fixes claude wait

## 0.1.20
remove cursor, use claude sdk for claude chat. remove fastllm claude

## 0.1.19
ollama and agent cancel changes

## 0.1.18
copilot models and trust store

## 0.1.17
github copilot backend, and a prose and comment pass over every notebook

## 0.1.16
cursor and claude sdk to bypass mcp

## 0.1.15
litert, mlx, llama share the same engine and fixes for cursor and claude

## 0.1.14
bug fix

## 0.1.13
support image and video generation

## 0.1.12
estimate tokens for cursor and claude

## 0.1.11
release

## 0.1.10
adding claude code and connecting cursor models to non mcp routes

## 0.1.8
release

## 0.1.7

Fixed

- Every hosted turn failed with `TypeError: unsupported operand type(s) for +: 'float' and 'Timeout'`,
  a message naming neither library involved. `fastllm` builds `mk_client`'s default timeout with the
  httpx *it* imported, which is not always the one `fastspec`'s `OpenAPIClient` runs on: where
  fastspec is on httpx2 the object reached `anyio.fail_after` unconverted and was added to a float.
  The timeout is now rebuilt with whichever httpx the client's own module imported, keeping its
  values, so it is right in both installs and a no-op once the types agree.

- litert models with tools failed to load: `Engine.create_conversation` used to take
  `enable_constrained_decoding=True` and now takes `constrained_decoding_config`, so a caller
  passing the old name through `conv_kw` got a `TypeError` naming an argument they never chose to
  send. `LitertChat` gains `constrain=None|True|False`: on by default when the chat has tools,
  forced either way, and a `constrained_decoding_config` supplied through `conv_kw` is left alone.
  The old name is still accepted and translated, with a `DeprecationWarning`. Decided when the
  conversation is built, so tools added later through `reconfigure` are covered too.

## 0.1.6
cursor models

## 0.1.5
release

## 0.1.4
nb cleanup

## 0.1.3

Cursor models added . can be accessed through sdk and cli

Two public doors onto things every harness was already doing through private attributes.

**`Chat.oneshot(prompt, sp, think=, max_tokens=)`.** The stateless one-shot the cheap jobs around
a chat are made of - a label, a summary, a completion to insert. The public surface stopped at
`classify` and `structured`, so every other caller reached for `_oneshot`, and `_oneshot` took
neither a token cap nor a way to ask the model not to deliberate.

`think=False` is the part that matters. A cheap job's whole budget can be 32 tokens, and a
reasoning model will spend all of them thinking - leaving no answer to strip the thinking off of.
Each backend now has a way to ask: `/no_think` in the system prompt (llama), `enable_thinking=False`
in the chat template (mlx), a conversation built without a thinking channel (litert), and the
lowest `reasoning_effort` the API takes (remote, `NO_THINK_EFFORT`, asked again without it if the
provider spells it differently). `think=True` insists wherever a backend has a switch to insist
with; a hosted model has none, so it keeps whatever `reasoning_effort` the chat was built with.
`None` leaves the model's default alone. `classify`, `grades` and the summarizing callback ask for
`think=False` themselves now.

**`Chat.reconfigure(sp=, tools=)`.** Change the system prompt and the tool list on a live
conversation, keeping its history - what a harness needs when a skill is discovered, a folder is
opened, or an extension loads mid-session. There was no way to say it, so callers set `_sys_pre`,
`toolspecs` and `ns` by hand and then called `_recreate_conv`: four private names, three of which
only some backends have, each behind a `hasattr` because of it. Backends supply the two halves
through `_set_sp` and `_set_tools`, so a backend that grows new state stays Rishi's business
rather than a silent no-op in somebody else's harness.

**`rishi.cursor`: Cursor's models through the CLI.** `CursorChat` drives `cursor-agent` headless, so
`Chat('cursor/cursor-grok-4.5-high')` is a chat like any other - streaming, thinking, usage, and tools
through the tag protocol, since the CLI hands back text and never a structured call. It cannot be a
`RemoteChat`: `cursor-agent` has an endpoint, but it is Cursor's own wire and there is nothing for
fastllm to bind to.

There are two paths to Cursor, because there are two credentials. The CLI path shells out per turn and
needs only `cursor-agent login`; it costs about nine seconds a turn, of which six are the CLI starting
up - measured, and identical in a large repo and an empty directory, so it is init and not scanning.
The SDK path (`pip install 'rishi[cursor]'`, `$CURSOR_API_KEY` from the Cursor dashboard) holds one
`cursor_sdk` agent for the life of the chat and pays that startup once instead of once per turn.
`sdk=None` picks the SDK when there is a key and the package, and the CLI otherwise.

A live agent has its own memory of the conversation, so only the unsent tail goes out - the question
and any tool result, never the agent's own replies, which it already knows. That memory is a lie the
moment rishi's history moves underneath it, so `_recreate_conv` - the hook eviction and `reconfigure`
already call - closes the agent, and the next turn builds a fresh one and re-sends the history as it
now stands. Drift is not managed, it is made impossible.

Two defaults are deliberate. `mode='ask'` and `sandbox='enabled'`, because `-p` on its own gives
cursor-agent write and shell access to the working directory, and a second agent loose inside rishi's
tool loop is not what asking a model a question should mean. And `CursorChat.local` is `False`: the
binary is local, the model is not, and anything deciding what is safe to send on the strength of
"the runtime is not `remote`" needs to be told otherwise about this one.

**`RecordCache` and `CachedChat`, and a recording CI can replay.** `RecordCache` records what an
expensive call returned to a diskcache directory on the first run and replays it on every run after -
`cache(key, f)`, a `key(*parts)` that hashes, and nothing else, so another package can wrap its own
backend in it without inheriting any of `Chat`'s assumptions. `CachedChat` is that primitive wrapped
around a `Chat`. A replay builds no engine, so it costs
nothing, needs no GPU, and can never start a download - which is what lets the examples in the README
actually run in CI rather than sitting behind `#| eval: false`. A miss needs `$RISHI_RECORD_CHAT`,
so a stale recording fails loudly instead of turning a CI job into a two-gigabyte download, and an
exception is recorded like any other reply, because a backend that rejects its own tool call is
exactly what the code around it has to handle.

The key is a `sha256` of what a reply depends on - `KEY_VERSION`, the model, the briefing, the tool
names, and who said what so far - and not of the bookkeeping that rides along, so a reply that gains
a `usage` field or a thinking channel still replays. Once a repo commits a recording the shape of
that key is public API: `KEY_VERSION` is the deliberate way to break it, and it invalidates
everything, everywhere, on purpose.

**Tag-protocol tools on hosted models.** `RemoteChat(tool_mode='tags')` puts the tool schemas
in the system prompt via the new `tag_tools_sp`, sends nothing in the wire's tool field, and
reads the calls back out of the reply text. `norm_completion` now parses `<tool_call>` blocks
exactly as `core.norm_resp` already did for the OpenAI-shaped path, and the stream splits them
out through `StreamSplit` so a call never renders as prose on its way to becoming a call.

This is for a transport whose tool channel is closed rather than absent. Claude Code declares
tools as an in-process MCP server, and an enterprise-managed configuration forbids every
dynamic MCP server there is -- so a policy about MCP silently became a model with no tools.
The system prompt is the one channel no such policy can close. `tool_mode='native'` is still
the default and still better wherever it works: validated schemas, structured calls back, and
no dependence on the model minding its punctuation.

## 0.1.2
release

## 0.1.1
backends are split in pyproject. new ScalingWindowCallbck to autocompress. RLock and max parallel tool calls

## 0.1.0

Two new backends - MLX on Apple silicon and hosted models via fastllm - plus the shared tool loop
and context-window management that go with them.

**`rishi.mlx`.** The same `Chat` API over [mlx-lm](https://github.com/ml-explore/mlx-lm), routed
automatically from an `mlx-community` model id. It is the only backend that keeps its KV cache alive
between turns: each turn is tokenized, compared against what the cache already holds, trimmed where
the two diverge, and only the new tail is prefilled - reported as `use.cached_tokens`.
`save_cache`/`load_cache` persist a warmed cache across sessions. Also `kv_bits` for a quantized KV
cache, `draft_model` for speculative decoding, and `adapter_path` for LoRA adapters.

Vision and audio models are routed to `MlxVlmChat` (via
[mlx-vlm](https://github.com/Blaizzy/mlx-vlm), `pip install 'rishi[mlx-vlm]'`) by reading the repo's
`config.json`; `vlm=True`/`False` overrides. A text-only MLX model given an image now raises a
`TypeError` that names the extra to install rather than dropping the image silently.

**Backends are now opt-in.** `pip install rishi` no longer pulls litert-lm-api or
llama-cpp-python; install what you need with `pip install 'rishi[litert]'`, `'rishi[llama]'`,
`'rishi[mlx]'`, `'rishi[remote]'`, or `'rishi[all]'`. `import rishi` works with any subset installed, and `Chat(model)` imports the backend
it needs on demand. Asking for a backend that isn't installed now names the extra to install.

**A shared tool loop.** `ToolLoopMixin` in `rishi.core` owns the Python-side tool loop for every
backend that receives tool calls as data (llama, MLX, remote):

- `max_steps` is now a real budget, and is enforced on **litert** too - previously litert ignored it
  entirely, so a chat with tools had no cap. Past the cap, calls are denied, the model is told why,
  and one `final_prompt` round asks for a prose answer so the turn ends with an answer instead of a
  loop. Note `max_steps` now counts tool *calls* rather than tool *rounds*.
- `parallel_tools=True` runs independent calls from one model turn concurrently. Approval stays
  sequential, so HITL prompts keep their order and the budget counts each call once; history is
  identical either way. Not supported on litert, which runs its loop inside the engine.
- A context window that fills up mid-turn is now recovered: the oldest tool results in `hist` are
  shrunk, backend state is rebuilt, and the model is asked to summarize. Only if that retry also
  fails does it raise the new `ContextWindowExceededError`.

**llama KV-cache visibility and persistence.** llama.cpp already reuses its KV cache across turns
(`Llama.generate` trims to the longest common prefix), so multi-turn chat never re-prefilled - but
nothing said so, and several rishi paths silently threw the prefix away. `use.cached_tokens` now
reports reuse on llama as well as MLX, and is zeroed exactly when rishi invalidates the prefix: a
one-shot on the shared engine (`classify`/`structured`/`check`, a shared `engine=`, a `judge=` on the
same engine), a rewritten history (eviction or context recovery), or a turn carrying media. New
`preserve_cache=True` saves and restores the llama state around one-shots rather than losing it, and
`save_cache`/`load_cache` persist the context to disk under the same names `rishi.mlx` uses.

**Context-window management.** `SlidingWindowCallback` keeps a long conversation from ever hitting
the wall: before each turn it checks `pct_full` and, past a threshold, drops whole message groups from
the middle of `hist` - keeping the earliest turns and the live thread - then has the backend rebuild
from the shortened history. A tool call and its results are one group and are never split, and the
system prompt is never at risk because it lives outside `hist`. `summarize=True` replaces the dropped
middle with a model-written summary. Opt in via `cbs=[SlidingWindowCallback()]`; eviction is lossy, so
it is not on by default. The policy is also usable directly as `evict_middle`/`msg_groups`.

This is aimed at litert in particular, where litert-lm has no automatic KV-cache recycling
([gallery#856](https://github.com/google-ai-edge/gallery/issues/856)): a full cache OOMs on GPU/NPU
and sends the CPU path into an infinite repetition loop instead of raising. `LitertChat` can now
rebuild its `Conversation` from `hist` (`_recreate_conv`), re-applying the system prompt, and if the
window does fill mid-turn it evicts and retries once before raising `ContextWindowExceededError`.
It previously had no context recovery at all.

**`rishi.remote`.** Hosted models - Anthropic, OpenAI, Gemini, DeepSeek, Moonshot, OpenRouter -
through [fastllm](https://github.com/AnswerDotAI/fastllm)'s `acomplete`, routed on the model name
(`Chat('claude-sonnet-4-5')`). It reuses `ToolLoopMixin`, so approval, the budget, parallel tools and
the callbacks behave exactly as on the local backends; the async wire call is bridged with `run_coro`
and the new `sync_iter`. `tool_choice` and `reasoning_effort` are passed through natively, and
provider-run tools arrive with `server=True` and are never executed locally. History converts both
ways between rishi's canonical dicts and fastllm's `Msg`/`Part`, carrying images and audio as data
URLs, so a local conversation can move to a hosted model and back without losing anything.

**Closing fastllm gaps.** `chat(msg, stream='raw')` yields the underlying chunk dicts instead of
rendered markdown, for consumers that want the text/thinking/tool-call structure (`stream=True` is
unchanged). `ToolCall` builds a canonical tool call as a `dict` subclass with `.name`/`.arguments`
accessors and a `server` flag for provider-run tools, which the loop records but never executes
locally. `mk_tool_res_msg`/`mk_tool_res_msgs` are exported for driving a tool loop by hand.

**Shared OpenAI-style layer.** The message, tool-schema, think/tool-tag parsing, streaming-split and
usage/reminder callback helpers moved from `rishi.llama` into `rishi.core`, where MLX can share them.
They keep their old names in `rishi.llama`, and `rishi.llama`'s public API is unchanged.

## 0.0.4
llama cpp support addedadded

## 0.0.2
examples added


## 0.0.1
initial stateful chat for litert models
