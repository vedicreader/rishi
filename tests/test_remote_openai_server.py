#!/usr/bin/env python
"""`rishi.remote` against a local OpenAI-compatible server, in the shape mlx-serve serves.

The question this answers is whether a local server on the OpenAI wire is a usable backend for
rishi without a new backend module. It is: pass `base_url` and any non-empty `api_key` and leave
`vendor_name` alone, which is what puts fastllm on its `custom` vendor and the chat-completions
API. Passing `vendor_name='openai'` does NOT work - the vendor's own row overrides `api_name` and
sends the request to the Responses API instead.

The server here is a stub, not mlx-serve: it pins the wire contract (fields, streaming frames,
tool-call round trip, `prompt_tokens_details.cached_tokens`), not any real model's behaviour.

The streaming cases print an httpcore2 "generator didn't stop after athrow()" traceback on
teardown. It comes after the response has been read and every assertion has passed, when the stub
drops the connection; whether a long-lived real server provokes it too is not settled here.

    python tests/test_remote_openai_server.py    # or: pytest tests/test_remote_openai_server.py
"""
import http.server, json, socket, threading

from rishi import Chat, resp_text
from urai import thought

#: what the next request should be answered with, as a list of `choices[0].message` bodies
SCRIPT = []
SEEN = []


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        d = json.dumps(obj).encode()
        self.send_response(code); self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(d))); self.end_headers(); self.wfile.write(d)

    def _sse(self, frames):
        self.send_response(200); self.send_header('content-type', 'text/event-stream')
        self.send_header('cache-control', 'no-cache'); self.send_header('connection', 'close')
        self.end_headers()
        for f in frames: self.wfile.write(f'data: {json.dumps(f)}\n\n'.encode())
        self.wfile.write(b'data: [DONE]\n\n')

    def do_GET(self):
        self._json({'object': 'list', 'data': [{'id': 'mlx-serve', 'object': 'model',
                                                'context_length': 32768, 'max_model_len': 32768}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('content-length', 0))) or b'{}')
        SEEN.append(body)
        msg = SCRIPT.pop(0) if SCRIPT else {'role': 'assistant', 'content': 'pong'}
        usage = {'prompt_tokens': 11, 'completion_tokens': 3, 'total_tokens': 14,
                 'prompt_tokens_details': {'cached_tokens': 8}}
        base = {'id': 'chatcmpl-1', 'created': 0, 'model': body.get('model', 'mlx-serve')}
        if not body.get('stream'):
            return self._json({**base, 'object': 'chat.completion', 'usage': usage,
                               'choices': [{'index': 0, 'message': msg,
                                            'finish_reason': 'tool_calls' if msg.get('tool_calls') else 'stop'}]})
        frames = [{**base, 'object': 'chat.completion.chunk',
                   'choices': [{'index': 0, 'delta': {'role': 'assistant'}}]}]
        for piece in (msg.get('content') or ''):
            frames.append({**base, 'object': 'chat.completion.chunk',
                           'choices': [{'index': 0, 'delta': {'content': piece}}]})
        frames.append({**base, 'object': 'chat.completion.chunk', 'usage': usage,
                       'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
        self._sse(frames)


class Server:
    "The stub server, on a port nobody else holds."
    def __enter__(self):
        s = socket.socket(); s.bind(('127.0.0.1', 0)); self.port = s.getsockname()[1]; s.close()
        self.srv = http.server.ThreadingHTTPServer(('127.0.0.1', self.port), _Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        SCRIPT.clear(); SEEN.clear()
        return self
    def __exit__(self, *a): self.srv.shutdown(); self.srv.server_close()
    @property
    def url(self): return f'http://127.0.0.1:{self.port}/v1'


def mk(server, **kw):
    "A chat on the local server. No vendor_name: that is the whole trick."
    return Chat('mlx-serve', runtime='remote', base_url=server.url, api_key='local', **kw)


def add(a: int, b: int) -> int:
    "Add two numbers."
    return a + b


def test_a_plain_turn_round_trips_over_the_local_wire():
    with Server() as s:
        r = mk(s)('ping')
        assert resp_text(r) == 'pong'
        assert SEEN[0]['messages'] == [{'role': 'user', 'content': 'ping'}]
        assert SEEN[0]['model'] == 'mlx-serve'


def test_cached_prompt_tokens_are_read_back():
    "mlx-serve always sends prompt_tokens_details.cached_tokens; a prefix cache is invisible without it."
    with Server() as s:
        r = mk(s)('ping')
        assert r['usage']['cached_tokens'] == 8, r['usage']
        assert r['usage']['total_tokens'] == 14


def test_a_native_tool_call_runs_and_the_result_goes_back():
    with Server() as s:
        SCRIPT.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call_1', 'type': 'function',
             'function': {'name': 'add', 'arguments': '{"a": 1, "b": 2}'}}]})
        SCRIPT.append({'role': 'assistant', 'content': 'It is 3.'})
        c = mk(s, tools=[add])
        assert resp_text(c('what is 1+2?')) == 'It is 3.'
        assert [m['role'] for m in c.hist] == ['user', 'assistant', 'tool', 'assistant']
        assert c.hist[2]['content'] == '3'
        assert any(m.get('role') == 'tool' for m in SEEN[1]['messages']), 'the result never reached the server'


def test_arguments_the_server_spells_as_strings_are_fitted_to_the_schema():
    "The coercion chokepoint has to cover this backend too, not only the ones that parse text."
    with Server() as s:
        SCRIPT.append({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'call_1', 'type': 'function',
             'function': {'name': 'add', 'arguments': '{"a": "1", "b": "2"}'}}]})
        SCRIPT.append({'role': 'assistant', 'content': 'It is 3.'})
        c = mk(s, tools=[add])
        c('what is 1+2?')
        assert c.hist[1]['tool_calls'][0]['function']['arguments'] == {'a': 1, 'b': 2}
        assert c.hist[2]['content'] == '3'


def test_a_streamed_turn_arrives_in_pieces_and_totals_the_same():
    with Server() as s:
        SCRIPT.append({'role': 'assistant', 'content': 'pong'})
        c = mk(s)
        out = ''.join(c('ping', stream=True))
        assert 'pong' in out
        assert SEEN[0]['stream'] is True
        assert c.use.total_tokens == 14, c.use


def test_a_stream_and_a_non_stream_answer_are_the_same_text():
    with Server() as s:
        SCRIPT.append({'role': 'assistant', 'content': 'the same bytes'})
        streamed = ''.join(mk(s)('ping', stream=True)).strip()
        SCRIPT.append({'role': 'assistant', 'content': 'the same bytes'})
        plain = resp_text(mk(s)('ping')).strip()
        assert streamed == plain, f'{streamed!r} != {plain!r}'


def test_reasoning_content_is_reported_if_the_wire_carries_it():
    "mlx-serve delivers thinking as `reasoning_content`. This records what rishi does with it today."
    with Server() as s:
        SCRIPT.append({'role': 'assistant', 'content': 'the answer',
                       'reasoning_content': 'weighing it up'})
        r = mk(s)('ping')
        assert resp_text(r) == 'the answer'
        print('    reasoning_content ->', repr(thought(r)))


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for f in fns: f(); print('ok', f.__name__)
    print(f'{len(fns)} passed')
