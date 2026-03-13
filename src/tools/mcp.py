"""
Lumi MCP (Model Context Protocol) client.

Config lives in ~/Lumi/mcp.json:
{
  "servers": {
    "github":   {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": {"GITHUB_TOKEN": "..."}},
    "postgres": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://..."]},
    "fs":       {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user"]}
  }
}

Usage in Lumi:
  /mcp list              — show configured servers
  /mcp add <name> <cmd>  — add a server
  /mcp call <srv> <tool> [args_json]  — call a tool directly
  /mcp remove <name>     — remove a server
"""

import json
import os
import pathlib
import subprocess
import threading

CONFIG_PATH = pathlib.Path.home() / "Lumi" / "mcp.json"


# ── Config management ─────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {"servers": {}}


def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def list_servers() -> dict:
    return load_config().get("servers", {})


def add_server(name: str, command: str, args: list = None,
               env: dict = None, transport: str = "stdio"):
    cfg = load_config()
    cfg.setdefault("servers", {})[name] = {
        "command":   command,
        "args":      args or [],
        "env":       env or {},
        "transport": transport,
    }
    save_config(cfg)


def remove_server(name: str) -> bool:
    cfg = load_config()
    if name in cfg.get("servers", {}):
        del cfg["servers"][name]
        save_config(cfg)
        return True
    return False


# ── MCP stdio transport ───────────────────────────────────────────────────────

class MCPSession:
    """Manages a single MCP server subprocess over stdio."""

    def __init__(self, name: str, server_cfg: dict):
        self.name   = name
        self.cfg    = server_cfg
        self._proc  = None
        self._lock  = threading.Lock()
        self._req_id = 0

    def start(self):
        env = {**os.environ, **self.cfg.get("env", {})}
        cmd = [self.cfg["command"]] + self.cfg.get("args", [])
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )

    def stop(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass

    def _send(self, method: str, params: dict = None) -> dict:
        with self._lock:
            self._req_id += 1
            req = {
                "jsonrpc": "2.0",
                "id":      self._req_id,
                "method":  method,
                "params":  params or {},
            }
            line = json.dumps(req) + "\n"
            self._proc.stdin.write(line)
            self._proc.stdin.flush()
            # Read response
            resp_line = self._proc.stdout.readline()
            if not resp_line:
                raise RuntimeError(f"MCP server {self.name} closed unexpectedly")
            return json.loads(resp_line)

    def initialize(self) -> dict:
        return self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities":    {},
            "clientInfo":      {"name": "lumi", "version": "2.0"},
        })

    def list_tools(self) -> list:
        resp = self._send("tools/list")
        return resp.get("result", {}).get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict = None) -> str:
        resp = self._send("tools/call", {
            "name":      tool_name,
            "arguments": arguments or {},
        })
        result = resp.get("result", {})
        content = result.get("content", [])
        if isinstance(content, list):
            return "\n".join(
                c.get("text", "") for c in content if c.get("type") == "text"
            )
        return str(result)


# ── Session pool ──────────────────────────────────────────────────────────────

_sessions: dict[str, MCPSession] = {}


def get_session(name: str) -> MCPSession | None:
    if name in _sessions:
        return _sessions[name]
    servers = list_servers()
    if name not in servers:
        return None
    sess = MCPSession(name, servers[name])
    try:
        sess.start()
        sess.initialize()
        _sessions[name] = sess
        return sess
    except Exception as e:
        raise RuntimeError(f"Failed to start MCP server '{name}': {e}")


def stop_all():
    for sess in _sessions.values():
        sess.stop()
    _sessions.clear()


# ── Build tool descriptions for system prompt injection ───────────────────────

def get_tool_context() -> str:
    """Return a string describing all available MCP tools for the system prompt."""
    servers = list_servers()
    if not servers:
        return ""
    lines = ["Available MCP tools:"]
    for name, cfg in servers.items():
        try:
            sess = get_session(name)
            tools = sess.list_tools()
            for t in tools:
                desc = t.get("description", "")
                lines.append(f"  mcp:{name}/{t['name']} — {desc}")
        except Exception:
            lines.append(f"  mcp:{name}/* — (server unavailable)")
    return "\n".join(lines)


# ── Natural language tool dispatch ────────────────────────────────────────────

def try_mcp_call(tool_ref: str, args_json: str = "") -> str | None:
    """
    Call mcp:<server>/<tool> with optional JSON args.
    Returns result string or None if not found.
    """
    if not tool_ref.startswith("mcp:"):
        return None
    ref = tool_ref[4:]
    if "/" not in ref:
        return None
    server_name, tool_name = ref.split("/", 1)
    try:
        sess = get_session(server_name)
        args = json.loads(args_json) if args_json.strip() else {}
        return sess.call_tool(tool_name, args)
    except Exception as e:
        return f"MCP error: {e}"
