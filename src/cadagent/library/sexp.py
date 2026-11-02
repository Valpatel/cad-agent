"""A small reader and writer for KiCad's S-expression files (``.kicad_mod``, ``.kicad_pcb``, ``fp-lib-table``).

Standard library only, so the footprint writer and the model audit run without KiCad or CadQuery. Adapted from
Gyropup's fuse-board generator (``hardware/fuse-board/sexp.py``, MIT, same owner). It reads what KiCad 7 to 10 write:
lists, bare atoms and double-quoted strings with backslash escapes. It is not a validator. KiCad itself is the
judge of a file, and ``kicad-cli`` or pcbnew loading the footprint is the real test.
"""
from __future__ import annotations

import re
from typing import Any, Iterator, List, Optional

TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """A bare (unquoted) atom: a keyword, a number or yes/no as KiCad wrote it."""


def parse(text: str) -> Any:
    """The top-level list of ``text``. Unbalanced parentheses raise ``ValueError``."""
    stack: List[list] = []
    cur: list = []
    pos = 0
    for m in TOKEN.finditer(text):
        pos = m.end()
        op, cl, qs, atom = m.groups()
        if op:
            stack.append(cur)
            cur = []
        elif cl:
            if not stack:
                raise ValueError(f"unbalanced ')' at character {m.start()}")
            done, cur = cur, stack.pop()
            cur.append(done)
        elif qs is not None:
            cur.append(re.sub(r'\\(.)', r'\1', qs[1:-1]))
        elif atom is not None:
            cur.append(Sym(atom))
    if stack or text[pos:].strip():
        raise ValueError("unbalanced '(' or a stray character at the end")
    return cur[0] if len(cur) == 1 else cur


def q(s: Any) -> str:
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def fmt(x: Any) -> str:
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, bool):
        return 'yes' if x else 'no'
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        s = f'{x:.6f}'.rstrip('0').rstrip('.')
        return '0' if s in ('-0', '') else s
    return q(x)


def dump(node: Any, indent: int = 0) -> str:
    """KiCad's layout: a list that holds lists opens a block, one child per line; any other list stays on one line."""
    pad = '\t' * indent
    if not isinstance(node, list):
        return pad + fmt(node)
    head = [x for x in node if not isinstance(x, list)]
    kids = [x for x in node if isinstance(x, list)]
    first_line = ' '.join(fmt(x) for x in head)
    if not kids:
        return f'{pad}({first_line})'
    inner = '\n'.join(dump(k, indent + 1) for k in kids)
    return f'{pad}({first_line}\n{inner}\n{pad})'


def find(node: list, key: str) -> List[list]:
    """The child lists of ``node`` whose head is ``key``."""
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def first(node: list, key: str) -> Optional[list]:
    r = find(node, key)
    return r[0] if r else None


def walk(node: Any, key: str) -> Iterator[list]:
    """Every list under ``node`` (at any depth) whose head is ``key``."""
    if isinstance(node, list):
        if node and node[0] == key:
            yield node
        for x in node:
            yield from walk(x, key)


def nums(node: Optional[list], n: int) -> tuple:
    """The first ``n`` numbers after the head of ``node``, e.g. ``nums((at 1 2 90), 2)`` -> ``(1.0, 2.0)``; missing
    ones are 0 (KiCad leaves a zero rotation out)."""
    vals = [float(x) for x in (node or [])[1:] if not isinstance(x, list) and _is_num(x)]
    return tuple((vals + [0.0] * n)[:n])


def _is_num(x: Any) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False
