#!/usr/bin/env python3
"""Lua syntax check for Claude Code PostToolUse hooks.

Reads the hook JSON from stdin, and if the edited file ends in .lua compiles it with
Lua 5.1 (via lupa). Non-.lua files and a missing lupa are silently ignored.
Exit 2 with the error on stderr so the error is fed back to Claude.
"""
import json
import pathlib
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    path = (payload.get("tool_input") or {}).get("file_path") or (payload.get("tool_response") or {}).get("filePath")
    if not path or not path.lower().endswith(".lua"):
        return 0
    try:
        from lupa.lua51 import LuaRuntime
    except ImportError:
        try:
            from lupa import LuaRuntime
        except ImportError:
            return 0
    try:
        src = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return 0
    lua = LuaRuntime()
    check = lua.eval("function(src, name) local f, err = loadstring(src, '@' .. name) return err end")
    err = check(src, path)
    if err:
        print(f"Lua syntax error: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
