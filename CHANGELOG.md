# Release notes

<!-- do not remove -->

## 0.1.57

- A failed Claude Code turn keeps its cost. `ClaudeError` has `usage`, and the chat adds that usage to `use` before the error goes up. Before, a failed run was paid for but not counted.
- A turn that Claude Code stops at its `max_budget_usd` raises `ClaudeError` with `budget=True` and says what it spent.
- `ClaudeChat.set_opts(**kw)` changes the Claude Code options of the next connect. `None` removes an option. A change ends an open session, and the next call resumes it.

## 0.1.56

- Pins uraiyadal 0.0.19. A call that lacks a required argument returns a tool error and does not run. Native arguments that urai cannot read mark the call `unread`.
- skill: `skill.md` gives `rishi` as the import path for the shared names, and its example is `from rishi import Chat, resp_text`. It imported them from `rishi.core`, which registers the backends and does not define `Chat`. Urai defines the backend-independent API.
- skill: `skill.md` lists the base install as `rishi.litert`, `rishi.remote`, `rishi.claude` and `rishi.copilot`. It lists the extras as `rishi[llama]`, `rishi[mlx]`, `rishi[mlx-vlm]` and `rishi[ollama]`. A missing extra raises an `ImportError` that names it.
- skill: the `skill.md` prose is rewritten in plain reference style. It defines the KV cache at first use. It names the callbacks that the Python-driven backends enable by default: `UsageCallback`, `ToolReminderCallback` and `SlidingWindowCallback`. It says `from rishi import *` exports urai's generic `mk_msg`, `mk_content` and `mk_msgs`.
- ollama: a call marked `unread` and a reply marked `tool_parse_failed` keep their marks. The loop asks for the call again.
- claude, ollama: urai's `parse_args` returns `None` for arguments it cannot read. Each backend renders a stored call with such arguments as an empty dict.
- llama: a streamed call whose arguments `parse_args` cannot read gets an empty dict and is marked `unread`. The reply is marked `tool_parse_failed`. The loop asks for the call again.
- copilot: `CopilotChat` takes `tool_choice`, `retries` (default 2) and `comp_kw`, and passes them to `RemoteChat`. They have the same meaning there.
- copilot: `CopilotChat` sets `api_name='openai_chat'` when it constructs the `RemoteChat`. `_kw` no longer sets `vendor_name` and `api_name` on each request. fastllm has no Copilot vendor, and the fixed `api_name` stops it routing a Gemini model id to Gemini.
- copilot: `_acomplete` refreshes the Copilot token in a worker thread. The refresh no longer blocks the event loop.
- ollama: `OllamaServer.start` raises `OllamaError` when nothing is listening at a URL that is not on this machine. rishi starts a daemon only on this machine.
- ollama: `ensure_ollama` holds `_servers_lock` while it starts a daemon. A second thread that asks for the same daemon finds the one the first thread started, and `ollama serve` is not launched twice.
- ollama: a streamed reply that ends before the daemon sends its final chunk raises `OllamaError`. Before, the turn ended on a reply that could be cut short.
- ollama: `extract_archive` always extracts tar archives with the `tar` filter. It no longer falls back to an unfiltered extract when the runtime lacks filters.
- core: `_rishi_run_python`, the Python runner that rishi registers with urai, restores the host's variables after the code raises. Before, it restored them only when the code finished.
- litert: when the context window fills mid-turn and the turn is sent again, the tool rounds of the failed attempt leave `hist` and count in `evicted`. The engine reruns those rounds. Before, they stayed in the history and in the rebuilt conversation.
- litert: a stream that its caller closes early cancels the engine's generation with `cancel_process`. Before, generation continued in the engine.
- remote: the one-shot call made with `think=False` retries without `NO_THINK_EFFORT` only when `effort_refused` is true, which means a 400 that names the effort. Any other error is raised. Before, every error was retried.

## 0.1.55

- Pins uraiyadal 0.0.17. A stray tag no longer drops a tool call's arguments. An unread call is never run. Identical calls in one reply run once. A tag quoted in an argument splits nothing.

## 0.1.54

- remote: a tool call whose arguments fastllm cannot decode no longer ends the turn with a bare `JSONDecodeError`. A call cut off at the output cap goes back to the model with urai's `cut_msg_`. The next step runs at `CUT_CAP_MULT` (4) times the cap, within the model's own maximum. Arguments that are not JSON go back to the model with the decoder's problem and its position. A second failure in the turn raises `ToolCallError`. Its message says what happened, for example "openai/gpt-5.6's tool call was cut off at its 16384-token output limit". This applies to sent and streamed turns on the Responses, chat-completions (Azure included) and Anthropic wires.
- remote: a `JSONDecodeError` that fastllm did not raise while decoding tool arguments, such as one from a proxy's HTML page, is raised unchanged.
- remote: `ask(schema=)` tries once more after a cut-off or malformed call, at the raised cap when the call was cut off. A second failure raises `ToolCallError`.
- remote: a `<tool_call>` block cut off in tags mode keeps `unread`, and the loop asks for it again. Before, the tool ran with no arguments.
- remote: with no `max_output_tokens` set, a `RemoteChat` asks for the model's own maximum output from fastllm's model table. For a model the table does not know, it asks for `DFLT_MAX_TOKENS`. `DFLT_MAX_TOKENS` is now 16,000. It was 4096 for every model, and a reasoning model's thinking could use all of it before the model finished a tool call. An explicit `max_output_tokens` still wins.
- remote: a reply cut off at the output cap while the model was still thinking, with no text and no tool call, goes back to the model once at the raised cap. It uses the same single resend. A second failure raises `ToolCallError`. Before, the turn ended on an empty answer.
- Requires uraiyadal 0.0.16.

## 0.1.53

- claude: `claude_version` runs `claude --version` with `/dev/null` as stdin. Claude Code is a Node program, and Node can leave a terminal it shares with the caller non-blocking. That froze a terminal UI on its next read. The Agent SDK's own spawns of `claude` already get a pipe.
- ollama: `OllamaServer.start` gives `ollama serve` `/dev/null` as stdin. The daemon never shares the caller's terminal.

## 0.1.52

- remote: a Gemini model named without `models/`, such as `gemini-3.5-flash` or `gemini/gemini-3.5-flash`, now works. fastllm puts the model id into Gemini's URL as given. The request went to `v1beta/gemini-3.5-flash` and Gemini answered 404. The chat now adds `models/` to the outgoing request, also when `vendor_name`, `api_name` or a `base_url` names the route. `model_id` stays as given. A turn's `usage['model']` now reads `models/gemini-3.5-flash`.
- claude: a failure while connecting is tried once more, with a status note to `on_stall`. On a live session the failures are a `CLIConnectionError`, Claude Code's initialize request timing out, and a connect that takes longer than `timeout`. On a query they are the same failures before any message arrives. Before, each was raised at once. A missing `claude` binary, a refusal of rishi's MCP server and any other error are still raised at once. A cancelled turn is not retried.
- claude: each wire call has one retry. A failed connect, a stall and a session that died before it said anything share that retry. A stall after a retried connect is raised and not tried again.

## 0.1.51

- claude: `ClaudeChat(tool_mode='native')` sends rishi's tools as MCP tools. The chat declares an in-process MCP server, `rishi`, with one tool per toolspec and its JSON schema. Only those tools are allowed, as `mcp__rishi__NAME`. The schemas leave the system prompt. Each call runs through Urai's approval gate, step budget, `tool_max_len` and tool callbacks, and is written to `hist`. Calls run one at a time, in a worker thread, in the context of the thread that started the step. The silence timer waits while a tool runs. A spent budget interrupts the session. A cancelled turn records the call as not run. The default stays `tool_mode='tags'`.
- claude: a machine whose enterprise MCP configuration refuses the server raises `ClaudeMcpRefused`, a `ClaudeError` that carries Claude Code's message. A tool name longer than 64 characters with its `mcp__rishi__` prefix raises `ValueError`.
- claude: an `effort` passed to one call now reaches a live session. A call whose `effort` differs from the one the session opened at reconnects the session, resumed from `hist`. A call with no `effort` runs at the chat's own `effort` and reconnects the same way. Before, a per-call `effort` was ignored once the session was open.
- remote: an effort level the provider's API lacks goes out as the nearest level it takes, from `EFFORT_MAP`. `max` goes as `xhigh` on OpenAI and Azure. `xhigh` and `max` go as `high` on Gemini. A 400 that names the effort gets the call once more without it, streamed or not, and `dropped_effort` holds the reason. While `dropped_effort` is set, the chat sends no effort.
- claude: a native call that Claude Code reports only after its handler gave up waiting keeps its text in the reply. Its id never goes to a later identical call. Only a refusal of rishi's own server, or of every dynamic MCP server, raises `ClaudeMcpRefused`. Another MCP server's error stays as it was. A cancelled turn cancels its pending stream read.
- remote: a streamed turn honours its own `tool_mode`. Before, the stream used the chat's `tool_mode` to split on `<tool_call>` tags, and a turn that asked for tags showed the raw tag as prose.

## 0.1.50

- A Claude Code turn's usage keeps its thinking tokens as `reasoning_tokens`, read from `output_tokens_details.thinking_tokens`. Before, they were dropped, and a turn that thought reported `reasoning=0`. They are still part of `completion_tokens`, as Claude Code counts them. A result that does not report them leaves `reasoning_tokens` out and does not claim 0.

## 0.1.49

- A Claude Code turn that sends nothing for `timeout` seconds is ended and tried once more. Before, `ClaudeChat` waited 600 seconds and raised `TimeoutError`. The default limit is now 240 seconds. Token deltas keep a working turn alive. The stalled query is closed, and a live session's subprocess is killed. `on_stall` gets a status note when this happens. `warnings.warn` gets the note when `on_stall` is not set.
- What the retry does depends on what was already shown. If nothing was shown, or only thinking, the turn is sent again from the same filed conversation. If text was shown, the turn is not sent again. rishi files the shown text as the reply so far, and a fresh query asks Claude Code to finish it. The turn's result is the shown text plus the continuation. There is no retry after one of Claude Code's own tools has run, because a replay would run it again. A whole tool call followed by silence ends the turn with that call.
- A second silence raises `ClaudeStall`, a `TimeoutError` that names the limit and `timeout_hint`. `timeout_hint` says how the caller raises the limit. The stalled attempt sent no result. Its tokens and cost are not counted. `_oneshot` is not retried.

## 0.1.48

- Pins uraiyadal 0.0.15 exactly. Its `parse_tool_tags` strips `<parameter>` elements left outside any call. A stray parameter no longer reaches the reply text.

## 0.1.47

- `structured` on Ollama, llama.cpp and MLX builds its schema with urai's `mk_toolspec`, as the remote backend already did. A `Literal` field reaches the model as an `enum`, and a pydantic model reaches it as its own fields. Before, fastcore's `get_schema` sent a `Literal` field as the invalid type `"object[object, object]"` and a pydantic model as one opaque `data` object. Requires uraiyadal 0.0.14.

## 0.1.46

- remote: Azure OpenAI's chat-completions route takes the reply cap as `max_completion_tokens`. An Azure reasoning deployment refuses `max_tokens`. `RemoteChat(api_name='openai_chat')` on a host in `MAX_COMPLETION_HOSTS` sends `max_completion_tokens` in the body. The hosts are at present `.azure.com`, `.azure.us` and `.azure.cn`. The Responses route, `api_name='openai'`, and every other host are unchanged.
- The `remote` page says how to reach Azure's v1 API. Set `base_url` to `https://<resource>.openai.azure.com/openai/v1`, the model to the deployment name, `api_key` to the key, and `api_name='openai'`. No `api-version` is sent.

## 0.1.45

- Three names other packages were importing are now public. `rishi.llama.get_model` and `rishi.litert.get_model` find a model file from a `model_path`, the Hugging Face cache or a download. `rishi.litert.cached_model` looks in the cache only and returns None on a miss. `rishi.litert.EngineHold` holds a shared LiteRT engine for one send. The old names `_get_model`, `_cached_model` and `_Hold` still work.

## 0.1.44

- claude: the audio error names the backends that take audio: `rishi.remote` with an audio model, `rishi.litert`, `rishi.llama` with an audio `mmproj`, and `rishi.mlx` with mlx-vlm. It used to suggest `rishi.ollama`, which also refuses audio. The message is `NO_AUDIO`.
- litert: works with litert-lm-api 0.18, which renamed `Role.MODEL`'s value from `'model'` to `'assistant'`. Building a message with role `'model'` failed there.
- `rishi[dev]` is an extra, and the `dev` group points at it. CI and the docs build install the backends and tools the notebooks need.

## 0.1.43

- claude: a reply stops at its first tool call. Before, a model could write a call and keep going in the same response, as though the call had answered, with more calls and then findings it never saw. Claude Code's `result` holds only the last text block. The calls were lost, and the invented findings reached the caller as the answer. `_drain` now stops at the first text block that holds a call, readable or not. Nothing after it is shown or kept. The turn's text is what came before the stop, and the call runs.
- When text was dropped after a call, the live session is marked stale. The next turn refiles the conversation from `hist` and does not keep the dropped text.

## 0.1.42

- claude: a Claude Code result `The model's tool call could not be parsed` is marked `tool_parse_failed`. The loop asks for the call again, once per turn. Before, it raised `ClaudeError` and ended the turn. A second such result in the same turn raises `ClaudeError` ending `(no resend left)`. `norm_claude(d, model, asked)` takes whether the resend was already asked. `TOOL_PARSE_ERR` holds the matched text.

## 0.1.41

- A Claude reply that holds a `<tool_call>` nothing could read is marked `tool_parse_failed`, and the loop asks for the call again. Before, `norm_claude` dropped the flag and the turn ended on the prose before the call.
- Requires uraiyadal 0.0.12, which reads Claude's `<invoke name=...>` dialect.

## 0.1.40

- claude: run the `claude` on `$PATH` (`cli_path=shutil.which(bin)`) and not the Agent SDK's bundled copy. The bundled copy lags Claude Code releases and refuses newer models (`Claude Code 2.1.248 does not support this model`). Without a `claude` on `$PATH` the SDK uses its bundled copy.

## 0.1.39

- litert: chats that share one engine take turns on it (`engine_lock`) and release it while a tool runs. Two concurrent sends on one GPU engine returned an empty turn and raised WebGPU validation errors. They also slowed every decode step past constrained decoding's fixed 10 s logits-buffer lock (`DEADLINE_EXCEEDED ... Failed to lock custom tensor buffer`). This showed up first on gemma-12b. A second chat that steps onto the engine from the thread that already holds it raises `EngineBusy`. Before, that thread hung.

## 0.1.38

- claude: transcript tool calls are refiled as `<tool_call>` text. A resumed session keeps using tools.
- llama, mlx, ollama: responses drain through uraiyadal `stream_resp`.
- `split_model_path` and `RishiToolLoop` are public.
- skill.md: names the approval API as it exists, `hitl_policy(modes, http=True)` and `URAI_APPROVAL_URL`.
- Requires uraiyadal>=0.0.7.

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
anthropic messages can have empty text blocks

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

- Every hosted turn failed with `TypeError: unsupported operand type(s) for +: 'float' and 'Timeout'`. The message names neither library involved. `fastllm` builds `mk_client`'s default timeout with the httpx that `fastllm` imported. That is not always the httpx that `fastspec`'s `OpenAPIClient` runs on. Where fastspec is on httpx2, the timeout object reached `anyio.fail_after` unconverted and was added to a float. The timeout is now rebuilt with the httpx that the client's own module imported, and it keeps its values. This is correct in both installs and changes nothing once the types agree.
- litert models with tools failed to load. `Engine.create_conversation` used to take `enable_constrained_decoding=True` and now takes `constrained_decoding_config`. A caller that passed the old name through `conv_kw` got a `TypeError` that named an argument they never chose to send. `LitertChat` takes a new argument, `constrain=None|True|False`. It is on by default when the chat has tools, and it can be forced either way. A `constrained_decoding_config` supplied through `conv_kw` is left alone. The old name is still accepted and translated, with a `DeprecationWarning`. The decision is made when the conversation is built, so tools added later through `reconfigure` are covered too.

## 0.1.6
cursor models

## 0.1.5
release

## 0.1.4
nb cleanup

## 0.1.3

- Cursor models are added. They are reachable through the SDK and the CLI.
- `Chat.oneshot(prompt, sp, think=, max_tokens=)` is a public stateless one-shot for the cheap jobs around a chat, such as a label, a summary or a completion to insert. Before, the public surface stopped at `classify` and `structured`, and every other caller used `_oneshot`. `_oneshot` took neither a token cap nor a way to ask the model not to deliberate.
- `think=False` asks the model not to deliberate. A cheap job's whole budget can be 32 tokens, and a reasoning model spends all of them thinking, which leaves no answer. Each backend has its own way to ask: `/no_think` in the system prompt (llama), `enable_thinking=False` in the chat template (mlx), a conversation built without a thinking channel (litert), and the lowest `reasoning_effort` the API takes (remote, `NO_THINK_EFFORT`, asked again without it if the provider spells it differently).
- `think=True` insists wherever a backend has a switch to insist with. A hosted model has no such switch. It keeps the `reasoning_effort` the chat was built with. `None` leaves the model's default alone. `classify`, `grades` and the summarizing callback now ask for `think=False` themselves.
- `Chat.reconfigure(sp=, tools=)` changes the system prompt and the tool list on a live conversation and keeps its history. A harness needs this when a skill is discovered, a folder is opened or an extension loads mid-session. Before, callers set `_sys_pre`, `toolspecs` and `ns` by hand and then called `_recreate_conv`. That was four private names, three of which only some backends have, each behind a `hasattr`. Backends supply the two halves through `_set_sp` and `_set_tools`. A backend that grows new state is handled there and does not become a silent no-op in somebody else's harness.
- `rishi.cursor`: `CursorChat` drives `cursor-agent` headless, so `Chat('cursor/cursor-grok-4.5-high')` is a chat like any other, with streaming, thinking, usage and tools. Tools go through the tag protocol, because the CLI returns text and never a structured call. It cannot be a `RemoteChat`. `cursor-agent` has an endpoint, but it is Cursor's own wire and fastllm has nothing to bind to.
- Two paths reach Cursor, because there are two credentials. The CLI path shells out per turn and needs only `cursor-agent login`. It costs about nine seconds a turn, and six of those are the CLI starting up. That was measured. It is the same in a large repo and in an empty directory, so it is startup and not scanning.
- The Cursor SDK path (`pip install 'rishi[cursor]'`, `$CURSOR_API_KEY` from the Cursor dashboard) holds one `cursor_sdk` agent for the life of the chat and pays that startup once. `sdk=None` picks the SDK when there is a key and the package, and the CLI otherwise.
- A live Cursor agent keeps its own memory of the conversation, so only the unsent tail goes out: the question and any tool result, never the agent's own replies. When rishi's history changes, that memory is wrong. `_recreate_conv`, the hook that eviction and `reconfigure` already call, closes the agent. The next turn builds a fresh agent and sends the history as it now stands. The agent cannot drift from the history.
- Two `CursorChat` defaults are deliberate: `mode='ask'` and `sandbox='enabled'`. `-p` on its own gives `cursor-agent` write and shell access to the working directory. A second agent inside rishi's tool loop is not what asking a model a question means.
- `CursorChat.local` is `False`. The binary is local and the model is not. Code that decides what is safe to send because the runtime is not `remote` needs `local` to be `False` here.
- `RecordCache` records what an expensive call returned to a diskcache directory on the first run and replays it on every later run. Its API is `cache(key, f)` and a `key(*parts)` that hashes. Another package can wrap its own backend in it without inheriting any of `Chat`'s assumptions. `CachedChat` wraps `RecordCache` around a `Chat`.
- A `CachedChat` replay builds no engine, costs nothing, needs no GPU and cannot start a download. The README examples therefore run in CI and no longer sit behind `#| eval: false`. A miss needs `$RISHI_RECORD_CHAT`. A stale recording therefore fails loudly and cannot turn a CI job into a two-gigabyte download. An exception is recorded like any other reply, because code around a backend must handle a backend that rejects its own tool call.
- The `RecordCache` key is a `sha256` of what a reply depends on: `KEY_VERSION`, the model, the briefing, the tool names, and who said what so far. It does not hash the bookkeeping that comes with a reply. A reply that gains a `usage` field or a thinking channel still replays. Once a repo commits a recording, the key's format is public API. `KEY_VERSION` is the deliberate way to break it, and changing it invalidates every recording.
- `RemoteChat(tool_mode='tags')` puts the tool schemas in the system prompt through the new `tag_tools_sp`, sends nothing in the wire's tool field, and reads the calls from the reply text. `norm_completion` now parses `<tool_call>` blocks as `core.norm_resp` already did for the OpenAI-shaped path. The stream splits them out through `StreamSplit`, so a call never renders as prose.
- Tags mode is for a transport whose tool channel is closed, not absent. Claude Code declares tools as an in-process MCP server, and an enterprise-managed configuration forbids every dynamic MCP server. A policy about MCP then silently left the model with no tools. The system prompt is the one channel that no such policy can close. `tool_mode='native'` is still the default, and it is better where it works. It has validated schemas and structured calls back, and it does not depend on the model getting its punctuation right.

## 0.1.2
release

## 0.1.1
backends are split in pyproject. new ScalingWindowCallbck to autocompress. RLock and max parallel tool calls

## 0.1.0

- Two backends are new: MLX on Apple silicon, and hosted models through fastllm. A shared tool loop and context-window management come with them.
- `rishi.mlx` is the same `Chat` API over [mlx-lm](https://github.com/ml-explore/mlx-lm), routed from an `mlx-community` model id. It is the only backend that keeps its KV cache alive between turns. Each turn is tokenized and compared with what the cache holds. rishi trims the cache where the two differ and prefills only the new tail. The reuse is reported as `use.cached_tokens`.
- mlx: `save_cache` and `load_cache` persist a warmed cache across sessions. `kv_bits` quantizes the KV cache, `draft_model` turns on speculative decoding, and `adapter_path` loads LoRA adapters.
- mlx: vision and audio models are routed to `MlxVlmChat` (through [mlx-vlm](https://github.com/Blaizzy/mlx-vlm), `pip install 'rishi[mlx-vlm]'`) by reading the repo's `config.json`. `vlm=True` or `vlm=False` overrides the routing. A text-only MLX model given an image now raises a `TypeError` that names the extra to install. Before, it dropped the image silently.
- Backends are opt-in. `pip install rishi` no longer installs litert-lm-api or llama-cpp-python. Install what you need with `pip install 'rishi[litert]'`, `'rishi[llama]'`, `'rishi[mlx]'`, `'rishi[remote]'` or `'rishi[all]'`. `import rishi` works with any subset installed, and `Chat(model)` imports the backend it needs on demand. Asking for a backend that is not installed now names the extra to install.
- `ToolLoopMixin` in `rishi.core` owns the Python-side tool loop for every backend that receives tool calls as data: llama, MLX and remote.
- tool loop: `max_steps` is a real budget and is enforced on litert too. Before, litert ignored it and a chat with tools had no cap. Past the cap, calls are denied and the model is told why. One `final_prompt` round asks for a prose answer, so the turn ends with an answer and not a loop. `max_steps` now counts tool calls and not tool rounds.
- tool loop: `parallel_tools=True` runs independent calls from one model turn concurrently. Approval stays sequential. HITL prompts keep their order, the budget counts each call once, and the history is the same either way. litert does not support `parallel_tools`, because it runs its loop inside the engine.
- tool loop: a context window that fills mid-turn is now recovered. rishi shrinks the oldest tool results in `hist`, rebuilds backend state and asks the model to summarize. If that retry also fails, rishi raises the new `ContextWindowExceededError`.
- llama: llama.cpp already reuses its KV cache across turns (`Llama.generate` trims to the longest common prefix), so multi-turn chat never re-prefilled. Nothing said so, and several rishi paths discarded the prefix. `use.cached_tokens` now reports reuse on llama as well as MLX.
- llama: `use.cached_tokens` is zeroed exactly when rishi invalidates the prefix. That happens on a one-shot on the shared engine (`classify`, `structured`, `check`, a shared `engine=`, a `judge=` on the same engine), on a rewritten history (eviction or context recovery), and on a turn that carries media.
- llama: `preserve_cache=True` saves and restores the llama state around one-shots. `save_cache` and `load_cache` persist the context to disk under the names `rishi.mlx` uses.
- `SlidingWindowCallback` keeps a long conversation from hitting the context limit. Before each turn it checks `pct_full`. Past a threshold, it drops whole message groups from the middle of `hist`, keeps the earliest turns and the live thread, and has the backend rebuild from the shortened history. A tool call and its results are one group and are never split. The system prompt is never dropped, because it lives outside `hist`.
- `SlidingWindowCallback(summarize=True)` replaces the dropped middle with a model-written summary. Opt in with `cbs=[SlidingWindowCallback()]`. Eviction is lossy, so it is not on by default. The policy is also available directly as `evict_middle` and `msg_groups`.
- litert: litert-lm has no automatic KV-cache recycling ([gallery#856](https://github.com/google-ai-edge/gallery/issues/856)). A full cache runs out of memory on GPU and NPU, and sends the CPU path into an infinite repetition loop instead of raising. `LitertChat` can now rebuild its `Conversation` from `hist` (`_recreate_conv`) and re-apply the system prompt. If the window fills mid-turn, it evicts and retries once before it raises `ContextWindowExceededError`. Before, litert had no context recovery.
- `rishi.remote` runs hosted models (Anthropic, OpenAI, Gemini, DeepSeek, Moonshot, OpenRouter) through [fastllm](https://github.com/AnswerDotAI/fastllm)'s `acomplete`, routed on the model name (`Chat('claude-sonnet-4-5')`). It reuses `ToolLoopMixin`. Approval, the budget, parallel tools and the callbacks behave as on the local backends. `run_coro` and the new `sync_iter` bridge the async wire call.
- remote: `tool_choice` and `reasoning_effort` pass through natively. Provider-run tools arrive with `server=True` and are never executed locally. History converts both ways between rishi's canonical dicts and fastllm's `Msg` and `Part`, with images and audio as data URLs. A local conversation can move to a hosted model and back without loss.
- `chat(msg, stream='raw')` yields the underlying chunk dicts and not rendered markdown. It is for consumers that want the text, thinking and tool-call structure. `stream=True` is unchanged.
- `ToolCall` builds a canonical tool call as a `dict` subclass with `.name` and `.arguments` accessors and a `server` flag for provider-run tools. The loop records such a call and never executes it locally. `mk_tool_res_msg` and `mk_tool_res_msgs` are exported for driving a tool loop by hand.
- The message, tool-schema, think and tool-tag parsing, streaming-split and usage and reminder callback helpers moved from `rishi.llama` to `rishi.core`, where MLX shares them. They keep their old names in `rishi.llama`. The public API of `rishi.llama` is unchanged.

## 0.0.4
llama cpp support added

## 0.0.2
examples added


## 0.0.1
initial stateful chat for litert models
