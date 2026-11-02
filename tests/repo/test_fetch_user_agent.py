"""Every Python fetch in src/ and tools/ sends its own User-Agent (#282).

cad-agent.valpatel.com is served by Cloudflare Pages, which answers Python urllib's default User-Agent
(``Python-urllib/3.x``) with error 1010, on the cad-agent hosts and on pages.dev alike; curl, browsers and the agents'
own fetch tools get through. So code here never fetches with urllib's default: each ``urlopen``, and each ``open`` of an
opener from ``build_opener``, is in a function that sets ``User-Agent``; so is each ``http.client`` connection (which
sends none); and ``urlretrieve`` (which cannot set one) is not used. requests and httpx send their own User-Agent,
which the CDN lets through. docs/agent-prompt.txt tells agents the same.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _python_files():
    for top in ("src", "tools"):
        for path in sorted((ROOT / top).rglob("*.py")):
            if "vendor" not in path.relative_to(ROOT).parts:
                yield path


def _name(func: ast.AST) -> str:
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""


def _scopes(tree: ast.AST):
    """Each function (or the module, for top-level code), with the calls made directly in it."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def offenders(source: str, where: str = "") -> list:
    tree = ast.parse(source)
    bad = []
    for scope in _scopes(tree):
        text = ast.get_source_segment(source, scope) if not isinstance(scope, ast.Module) else source
        for node in ast.walk(scope):
            if not isinstance(node, ast.Call):
                continue
            name = _name(node.func)
            if name == "urlretrieve":
                bad.append(f"{where}:{node.lineno}: urlretrieve sends urllib's default User-Agent")
            elif name == "urlopen":
                arg = node.args[0] if node.args else None
                if arg is None or isinstance(arg, (ast.Constant, ast.JoinedStr, ast.BinOp)):
                    bad.append(f"{where}:{node.lineno}: urlopen on a bare URL sends urllib's default User-Agent")
                elif "User-Agent" not in (text or ""):
                    bad.append(f"{where}:{node.lineno}: urlopen without a User-Agent header in the same function")
            elif ((name == "open" and "build_opener" in (text or "")) or name in ("HTTPConnection", "HTTPSConnection")) \
                    and "User-Agent" not in (text or ""):
                bad.append(f"{where}:{node.lineno}: {name} without a User-Agent header in the same function")
    return sorted(set(bad))


def test_every_fetch_sends_a_user_agent():
    bad = [b for path in _python_files() for b in offenders(path.read_text(), str(path.relative_to(ROOT)))]
    assert not bad, "send a User-Agent, e.g. Request(url, headers={'User-Agent': 'cad-agent/<version>'}):\n" + "\n".join(bad)


def test_the_check_catches_the_default():
    assert offenders("import urllib.request\nurllib.request.urlopen('https://x')\n")
    assert offenders("from urllib.request import urlopen\ndef f(u):\n    return urlopen(u)\n")
    assert offenders("import urllib.request as r\nr.urlretrieve('https://x', 'f')\n")
    good = ("import urllib.request as r\ndef f(u):\n"
            "    req = r.Request(u, headers={'User-Agent': 'cad-agent/1'})\n    return r.urlopen(req)\n")
    assert offenders(good) == []
    assert offenders("import urllib.request as r\ndef f(u):\n    return r.build_opener().open(u)\n")
    assert offenders("import http.client\ndef f():\n    return http.client.HTTPSConnection('x')\n")
    assert offenders("def f(p):\n    return open(p)\n") == [], "a file open is not a fetch"


def test_agents_are_told():
    flat = " ".join((ROOT / "docs" / "agent-prompt.txt").read_text().split())
    assert "send a User-Agent header" in flat and "urllib" in flat
