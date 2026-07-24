"""Drive Block's `buzz-agent` with a rishi model, and watch it edit a real file.

The chain is: buzz-agent (ACP over stdio) -> rishi's OpenAI-compatible endpoint ->
tool calls -> buzz-dev-mcp (MCP over stdio) -> the filesystem.

By default the "model" is a `ScriptedEngine`, so the whole path can be checked in a
couple of seconds without loading a couple of gigabytes of weights - every other hop
is the real binary. Pass `--real` to serve an actual gemma instead.

    python examples/buzz_agent_e2e.py                 # scripted model, real everything else
    python examples/buzz_agent_e2e.py --real          # a real local gemma drives it

Build the two binaries first (from a buzz checkout):

    cargo build -p buzz-agent -p buzz-dev-mcp

and either put them on PATH or set BUZZ_AGENT_BIN / BUZZ_DEV_MCP_BIN.
"""
import argparse, json, os, queue, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

from rishi.serve import serve, ScriptedEngine, mk_reply

PROMPT = 'Look at the workspace and rename the greeting to "buzz".'


def find_bin(env_var, name):
    "The binary named by `env_var`, else `name` on PATH."
    p = os.environ.get(env_var) or shutil.which(name)
    if not p or not Path(p).exists():
        sys.exit(f"{name} not found: build it with `cargo build -p {name}`, "
                 f"then put it on PATH or set {env_var}")
    return str(p)


class Acp:
    "A minimal ACP client: enough JSON-RPC to open a session and send one prompt."
    def __init__(self, cmd, env):
        self.proc = subprocess.Popen([cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        self.q = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout: self.q.put(line)
        self.q.put(None)

    def send(self, **o):
        self.proc.stdin.write(json.dumps({'jsonrpc': '2.0', **o}) + '\n'); self.proc.stdin.flush()

    def wait(self, id, timeout=600):
        "Pump notifications (printing what the agent is doing) until reply `id` arrives."
        end = time.monotonic() + timeout
        while True:
            line = self.q.get(timeout=max(0., end - time.monotonic()))
            if line is None: raise RuntimeError('buzz-agent exited')
            o = json.loads(line)
            u = (o.get('params') or {}).get('update') or {}
            k = u.get('sessionUpdate')
            if k == 'tool_call':
                print(f"  -> {u.get('title')} {json.dumps(u.get('rawInput'))[:100]}")
            elif k == 'tool_call_update' and u.get('status') == 'completed':
                print(f"     {json.dumps(u.get('content'))[:110]}")
            elif k == 'agent_message_chunk':
                print(f"  says: {(u.get('content') or {}).get('text', '')[:200]}")
            if o.get('id') == id: return o

    def close(self):
        try: self.proc.stdin.close(); self.proc.wait(timeout=10)
        except Exception: self.proc.kill()


def mk_engine(real, model_id, cache_dir):
    "Either a real litert engine, or a scripted stand-in that fakes three turns."
    if real:
        from rishi.core import Chat
        return Chat.create_engine(model_id, multimodal=False, cache_dir=cache_dir)
    return ScriptedEngine([
        mk_reply(tool_calls=[('dev__shell', {'command': 'ls -1 && wc -l app.py'})]),
        mk_reply(tool_calls=[('dev__str_replace', {'path': 'app.py',
                                                   'old_str': '"world"', 'new_str': '"buzz"'})]),
        mk_reply('Renamed the greeting to "buzz" in app.py.'),
    ])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--real', action='store_true', help='serve a real gemma instead of a scripted model')
    p.add_argument('--model-id', default='litert-community/gemma-4-E2B-it-litert-lm')
    p.add_argument('--cache-dir', default='.cache/litertlm')
    p.add_argument('--port', type=int, default=8231)
    p.add_argument('--rounds', default='8', help='BUZZ_AGENT_MAX_ROUNDS')
    a = p.parse_args()

    agent, devmcp = find_bin('BUZZ_AGENT_BIN', 'buzz-agent'), find_bin('BUZZ_DEV_MCP_BIN', 'buzz-dev-mcp')
    ws = Path(tempfile.mkdtemp(prefix='rishi-buzz-'))
    (ws / 'app.py').write_text('def greet():\n    return "world"\n')
    print(f'workspace {ws}\n  app.py: {(ws / "app.py").read_text().strip()!r}\n')

    srv = serve(engine=mk_engine(a.real, a.model_id, a.cache_dir), model=a.model_id,
                port=a.port, background=True)
    print(f'rishi endpoint: http://127.0.0.1:{a.port}/v1')

    cli = Acp(agent, {**os.environ,
                      'BUZZ_AGENT_PROVIDER': 'openai', 'OPENAI_COMPAT_API': 'chat',
                      'OPENAI_COMPAT_API_KEY': 'local', 'OPENAI_COMPAT_MODEL': a.model_id,
                      'OPENAI_COMPAT_BASE_URL': f'http://127.0.0.1:{a.port}/v1',
                      'BUZZ_AGENT_MAX_ROUNDS': a.rounds})
    try:
        cli.send(id=1, method='initialize', params={'protocolVersion': 1, 'clientCapabilities': {}})
        info = cli.wait(1)['result'].get('agentInfo', {})
        print(f"agent: {info.get('name')} {info.get('version')}")

        cli.send(id=2, method='session/new', params={'cwd': str(ws), 'mcpServers': [
            {'name': 'dev', 'command': devmcp, 'args': [], 'env': []}]})
        sid = cli.wait(2)['result']['sessionId']
        print(f'session: {sid}\n\nprompt: {PROMPT}')

        cli.send(id=3, method='session/prompt',
                 params={'sessionId': sid, 'prompt': [{'type': 'text', 'text': PROMPT}]})
        print(f"\nstopReason: {cli.wait(3)['result']['stopReason']}")
    finally:
        cli.close(); srv.shutdown(); srv.server_close()

    out = (ws / 'app.py').read_text()
    print(f'\napp.py is now:\n{out}')
    print('the edit is real' if '"buzz"' in out else 'the file was not edited')


if __name__ == '__main__':
    main()
