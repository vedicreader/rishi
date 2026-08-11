# Release notes

<!-- do not remove -->

## Unreleased

Two public doors onto things every harness was already doing through private attributes.

**`Chat.oneshot(prompt, sp, think=, max_tokens=)`.** The stateless one-shot the cheap jobs around
a chat are made of - a label, a summary, a completion to insert. The public surface stopped at
`classify` and `structured`, so every other caller reached for `_oneshot`, and `_oneshot` took
neither a token cap nor a way to ask the model not to deliberate.

`think=False` is the part that matters. A cheap job's whole budget can be 32 tokens, and a
reasoning model will spend all of them thinking - leaving no answer to strip the thinking off of.
Each backend now has a way to ask: `/no_think` in the system prompt (llama), `enable_thinking=False`
in the chat template (mlx), a conversation built without a thinking channel (litert), and the
lowest `reasoning_effort` the API takes (remote, `NO_THINK_EFFORT`, retried without it if the
provider spells it differently). `think=True` insists, `None` leaves the model's default alone.
`classify`, `grades` and the summarizing callback ask for `think=False` themselves now.

**`Chat.reconfigure(sp=, tools=)`.** Change the system prompt and the tool list on a live
conversation, keeping its history - what a harness needs when a skill is discovered, a folder is
opened, or an extension loads mid-session. There was no way to say it, so callers set `_sys_pre`,
`toolspecs` and `ns` by hand and then called `_recreate_conv`: four private names, three of which
only some backends have, each behind a `hasattr` because of it. Backends supply the two halves
through `_set_sp` and `_set_tools`, so a backend that grows new state stays Rishi's business
rather than a silent no-op in somebody else's harness.

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
