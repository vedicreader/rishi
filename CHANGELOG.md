# Release notes

<!-- do not remove -->

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
