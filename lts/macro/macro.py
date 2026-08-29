# -*- coding: utf-8 -*-
"""LightTools MACRO (BASIC 子集) 解释器 (对标 P7 lts/macro/).
词法 + 行导向解析 + 解释执行; 通过 context 回调对接内部 API.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

TOK = re.compile(r"""
    (?P<num>\d+\.?\d*(?:[Ee][+-]?\d+)?)
  | (?P<str>\$?"(?:[^"]|"")*")
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*(?:\$)?)
  | (?P<op><=|>=|<>|<|>|[-+*/^(),#:=])
  | (?P<ws>\s+)
""", re.X)


def lex(line):
    toks = []
    for mo in TOK.finditer(line):
        kind = mo.lastgroup
        txt = mo.group()
        if kind == "ws":
            continue
        if kind == "num":
            toks.append(("NUM", float(txt)))
        elif kind == "str":
            toks.append(("STR", txt[1:-1].replace('""', '"')))
        elif kind == "id":
            toks.append(("ID", txt))
        else:
            toks.append(("OP", txt))
    return toks


def _split_lines(src):
    out = []
    for raw in src.replace(chr(13), "").split(chr(10)):
        s = raw.strip()
        if not s or s.startswith("'") or s.upper().startswith("REM"):
            continue
        out.append(s)
    return out


def _match_params(text):
    """"name(args)" -> (name, args_str) or None."""
    open_i = text.find("(")
    if open_i < 0 or not text.endswith(")"):
        return None
    name = text[:open_i].strip()
    if not name or not (name[0].isalpha() or name[0] == "_"):
        return None
    return name, text[open_i + 1:-1]


def _print_args(text):
    """PRINT 参数: 顶层逗号/分号均作分隔 (分号=相邻拼接); 跳过字符串内字符."""
    parts = []
    depth = 0
    cur = ""
    q = False
    prev = ""
    for ch in text:
        if ch == chr(34) and prev != chr(92):
            q = not q
        prev = ch
        if not q:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if ch in (",", ";") and depth == 0 and not q:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [_parse_expr(lex(p.strip())) for p in parts if p.strip()]


def _expr_args(text):
    text = (text or "").strip()
    if not text:
        return []
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [_parse_expr(lex(p.strip())) for p in parts if p.strip()]


_PREC = {"^": 2, "*": 3, "/": 3, "MOD": 4, "+": 5, "-": 5,
         "=": 6, "<>": 7, "<": 7, ">": 7, "<=": 8, ">=": 8,
         "AND": 9, "OR": 9, "NOT": 9, "XOR": 9}



def _parse_expr(tokens):
    """显式优先级递归下降 (OR < AND < 比较 < 加减 < 乘除 < 一元 < 幂 < 原子)."""
    if not tokens:
        return ("num", 0.0)
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else ("EOF", None)

    def advance():
        tok = tokens[pos[0]]
        pos[0] += 1
        return tok

    def peek_op():
        t = peek()
        return str(t[1]).upper() if t[1] is not None else ""

    def atom():
        tok = advance()
        kind, val = tok
        if kind == "NUM":
            return ("num", float(val))
        if kind == "STR":
            return ("str", str(val))
        if kind == "ID":
            name = str(val)
            if peek()[0] == "OP" and peek()[1] == "(":
                advance()
                args = []
                if peek()[1] != ")":
                    args.append(or_expr())
                    while peek()[1] == ",":
                        advance()
                        args.append(or_expr())
                if peek()[1] == ")":
                    advance()
                return ("call", name, args)
            return ("var", name)
        if kind == "OP" and val == "(":
            e = or_expr()
            if peek()[1] == ")":
                advance()
            return e
        return ("num", 0.0)

    def power():
        left = atom()
        if peek_op() == "^":
            advance()
            return ("bin", "^", left, power())
        return left

    def unary():
        if peek()[0] == "OP" and peek()[1] == "-":
            advance()
            return ("neg", unary())
        return power()

    def mul():
        left = unary()
        while peek_op() in ("*", "/", "MOD"):
            op = peek_op()
            advance()
            left = ("bin", op, left, unary())
        return left

    def add():
        left = mul()
        while peek_op() in ("+", "-"):
            op = peek_op()
            advance()
            left = ("bin", op, left, mul())
        return left

    def cmp():
        left = add()
        while peek_op() in ("=", "<>", "<", ">", "<=", ">="):
            op = peek_op()
            advance()
            left = ("bin", op, left, add())
        return left

    def and_expr():
        left = cmp()
        while peek_op() == "AND":
            advance()
            left = ("bin", "AND", left, cmp())
        return left

    def or_expr():
        left = and_expr()
        while peek_op() in ("OR", "XOR"):
            op = peek_op()
            advance()
            left = ("bin", op, left, and_expr())
        return left

    return or_expr()



class Parser:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    def parse(self):
        return self._block(set())

    def _block(self, stop):
        body = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            head = line.split()[0].upper() if line.split() else ""
            if head in stop:
                break
            before = self.i
            node = self._line(line)
            if node is not None:
                body.append(node)
            # 块构造已在 _line 内前进 self.i; 简单行才递增
            if self.i == before:
                self.i += 1
        return body


    def _line(self, line):
        head = line.split()[0].upper() if line.split() else ""
        if head == "END":
            return ("end", line.upper().split()[1]) if len(line.split()) > 1 else ("end", "IF")
        if head in ("REM", "RANDOMIZE", "DATA", "ECHO", "RESTORE", "ON"):
            return ("noop", None)
        if head == "GOTO":
            return ("goto", line[len("GOTO"):].strip().upper())
        if head == "EXIT":
            return ("exit", line.upper().split()[1] if len(line.split()) > 1 else "FOR")
        if head == "PRINT":
            nxt = line[len("PRINT"):].strip()
            if nxt.startswith("#"):
                return ("printdev", tuple(_expr_args(nxt[1:].strip())))
            return ("print", tuple(_print_args(nxt)))
        if head == "CALL":
            m = _match_params(line[len("CALL"):].strip())
            if m:
                return ("call", m[0], _expr_args(m[1]))
            return ("noop", None)
        if head == "LET":
            return self._assign(line[len("LET"):].strip())
        if head == "DIM":
            return self._dim(line)
        if head == "COMMAND":
            return ("command", tuple(_expr_args(line[len("COMMAND"):].strip())))
        if head == "SWAP":
            return ("swap", _expr_args(line[len("SWAP"):].strip()))
        if head == "IF":
            return self._if(line)
        if head == "FOR":
            return self._for(line)
        if head == "WHILE":
            cond = _parse_expr(lex(line[len("WHILE"):].strip()))
            self.i += 1
            return ("while", cond, self._block(set(["WEND"])))
        if head == "DO":
            return self._do(line)
        if head == "SELECT":
            return self._select(line)
        if head in ("SUB", "FUNCTION"):
            return self._sub(line, head == "FUNCTION")
        if line.rstrip().endswith(":") and (line.split(":", 1)[0].lstrip().split() and
                (line.split(":", 1)[0].lstrip().split()[0][0].isalpha() or line.split(":", 1)[0].lstrip().split()[0][0] == "_")):
            return ("label", line.split(":", 1)[0].lstrip()[:].upper() if False else line.split(":", 1)[0].lstrip().upper())
        # 赋值: NAME[=...] 或 NAME = ...
        if "=" in line and (line.split("=", 1)[0].strip()[0].isalpha() or line.split("=", 1)[0].strip()[0] == "_"):
            return self._assign(line)
        m = _match_params(line.strip())
        if m:
            return ("call", m[0], _expr_args(m[1]))
        return ("expr_stmt", _expr_args(line))

    def _assign(self, lhs):
        eq = lhs.find("=")
        name = lhs[:eq].strip()
        rhs = lhs[eq + 1:]
        idx = None
        if "(" in name and name.rstrip().endswith(")"):
            n2 = _match_params(name)
            if n2:
                name, idx = n2[0], n2[1].strip()
        return ("assign", name, idx, _parse_expr(lex(rhs.strip())))

    def _dim(self, line):
        dims = []
        for part in line[len("DIM"):].strip().split(","):
            part = part.strip()
            m = _match_params(part)
            if m:
                dims.append((m[0], m[1].strip()))
            else:
                dims.append((part, None))
        return ("dim", dims)

    def _if(self, line):
        s = line.strip()[len("IF"):].strip()
        if s.upper().endswith("THEN"):
            cond = s[:-4].strip()
            self.i += 1
            return self._if_block(cond)
        # 单行: cond THEN stmt [ELSE stmt]
        t = s.rfind(" THEN ")
        if t < 0:
            t = s.find(" THEN ") if " THEN " in s else -1
        if t < 0 and s.upper().endswith("THEN"):
            return self._if_block(s[:-4].strip())
        if t >= 0:
            cond = s[:t].strip()
            rest = s[t + len(" THEN "):].strip()
            simple_else = None
            if " ELSE " in rest:
                rest, simple_else = rest.split(" ELSE ", 1)
            self.i += 1
            return ("if", [(_parse_expr(lex(cond)), self._inline(rest))],
                    self._inline(simple_else) if simple_else else [])
        return self._if_block(s)

    def _inline(self, text):
        t = (text or "").strip()
        if not t:
            return []
        m = _match_params(t)
        if m and "=" not in t:
            return [("call", m[0], _expr_args(m[1]))]
        if "=" in t:
            return [self._assign(t)]
        return [("inline", t)]

    def _if_block(self, cond):
        branches = [(_parse_expr(lex(cond)), self._block(set(["ELSEIF", "ELSE", "END"])))]
        else_body = []
        while self.i < len(self.lines):
            up = self.lines[self.i].lstrip().upper()
            if up.startswith("ELSEIF"):
                l = self.lines[self.i]
                c = l.strip()[len("ELSEIF"):].strip()
                if c.upper().endswith("THEN"):
                    c = c[:-4].strip()
                self.i += 1
                branches.append((_parse_expr(lex(c)), self._block(set(["ELSEIF", "ELSE", "END"]))))
            elif up.startswith("ELSE"):
                self.i += 1
                else_body = self._block(set(["END"]))
            elif up.startswith("END"):
                self.i += 1
                break
            else:
                break
        return ("if", branches, else_body)

    def _for(self, line):
        s = line.strip()[len("FOR"):].strip()
        eq = s.find("=")
        var = s[:eq].strip()
        rest = s[eq + 1:]
        to = rest.upper().find(" TO ")
        start = rest[:to].strip()
        rem = rest[to + 4:].strip()
        step = "1"
        st = rem.upper().find(" STEP ")
        if st >= 0:
            end = rem[:st].strip()
            step = rem[st + len(" STEP "):].strip()
        else:
            end = rem.strip()
        self.i += 1
        body = self._block(set(["NEXT"]))
        if self.i < len(self.lines):
            self.i += 1
        return ("for", var, _parse_expr(lex(start)), _parse_expr(lex(end)),
                _parse_expr(lex(step)), body)

    def _do(self, line):
        up = line.strip().upper()
        until = None
        if up.startswith("DO WHILE"):
            until = ("while", _parse_expr(lex(line.strip()[8:].strip())))
        self.i += 1
        body = self._block(set(["LOOP"]))
        if self.i < len(self.lines):
            loop_line = self.lines[self.i].strip()
            self.i += 1
            if "UNTIL" in loop_line.upper():
                idx = loop_line.upper().index("UNTIL")
                until = ("until", _parse_expr(lex(loop_line[idx + 5:].strip())))
        return ("do", body, until)

    def _select(self, line):
        text = line.strip()[len("SELECT"):].strip()
        if text.upper().startswith("CASE "):
            text = text[5:].strip()
        expr = _parse_expr(lex(text))
        self.i += 1
        branches = []
        else_body = []
        cur = []
        while self.i < len(self.lines):
            l = self.lines[self.i].lstrip()
            up = l.upper()
            if up.startswith("END"):
                self.i += 1
                break
            if up.startswith("CASE ELSE"):
                self.i += 1
                else_body = self._block(set(["END"]))
                if self.i < len(self.lines) and self.lines[self.i].lstrip().upper().startswith("END"):
                    self.i += 1
                break
            if up.startswith("CASE"):
                vals = _expr_args(l[len("CASE"):].strip())
                self.i += 1
                cur = self._block(set(["CASE", "END"]))
                branches.append((vals, cur))
                continue
            cur.append(self._line(self.lines[self.i]))
            self.i += 1
        return ("select", expr, branches, else_body)

    def _sub(self, line, is_func):
        kw = "FUNCTION" if is_func else "SUB"
        m = _match_params(line.strip()[len(kw):].strip())
        name = m[0]
        params = [p.strip() for p in (m[1] or "").split(",") if p.strip()]
        self.i += 1
        body = self._block(set(["END"]))
        if self.i < len(self.lines):
            self.i += 1
        return ("func" if is_func else "sub", name, params, body)


class MacroContext:
    def __init__(self):
        self.issue = lambda cmd: None
        self.dbget = lambda key, elem: 0.0
        self.dbset = lambda key, elem, v: 0
        self.print = lambda text: None
        self.version = lambda: "9.1.0"


class MacroInterpreter:
    def __init__(self, context):
        self.ctx = context
        self.env = {}
        self.arr = {}
        self.funcs = {}
        self._stdout = []

    def run(self, source):
        prog = Parser(_split_lines(source)).parse()
        for node in prog:
            if isinstance(node, tuple) and node and node[0] in ("sub", "func"):
                self.funcs[str(node[1]).upper()] = node
        self._exec(prog, self.env)
        return chr(10).join(self._stdout)

    def _eval(self, node, env=None):
        if not isinstance(node, tuple) or not node:
            return 0.0
        env = env if env is not None else getattr(self, "_cur_env", self.env)
        t = node[0]
        if t == "num":
            return float(node[1])
        if t == "str":
            return str(node[1])
        if t == "var":
            return env.get(node[1], 0.0)
        if t == "neg":
            return -float(self._eval(node[1], env))
        if t == "call":
            args = [self._eval(a, env) for a in node[2]]
            return self._call(node[1], args, env)
        if t == "bin":
            op = node[1].upper()
            return self._binop(op, self._eval(node[2], env), self._eval(node[3], env))
        return 0.0

    def _binop(self, op, a, b):
        if op == "+":
            return float(a) + float(b)
        if op == "-":
            return float(a) - float(b)
        if op == "*":
            return float(a) * float(b)
        if op == "/":
            return float(a) / float(b) if float(b) else 0.0
        if op == "^":
            return float(a) ** float(b)
        if op == "MOD":
            return float(a) % float(b) if float(b) else 0.0
        if op == "=":
            return 1.0 if float(a) == float(b) else 0.0
        if op == "<>":
            return 1.0 if float(a) != float(b) else 0.0
        if op == "<":
            return 1.0 if a < b else 0.0
        if op == ">":
            return 1.0 if a > b else 0.0
        if op == "<=":
            return 1.0 if a <= b else 0.0
        if op == ">=":
            return 1.0 if a >= b else 0.0
        if op == "AND":
            return 1.0 if (float(a) != 0 and float(b) != 0) else 0.0
        if op == "OR":
            return 1.0 if (float(a) != 0 or float(b) != 0) else 0.0
        if op == "XOR":
            return 1.0 if (float(a) != 0) != (float(b) != 0) else 0.0
        return 0.0

    def _call(self, name, args, env=None):
        env = env if env is not None else getattr(self, "_cur_env", self.env)
        up = name.upper()
        m = {
            "ABS": lambda: abs(float(args[0])),
            "SIN": lambda: math.sin(float(args[0])),
            "COS": lambda: math.cos(float(args[0])),
            "TAN": lambda: math.tan(float(args[0])),
            "ATN": lambda: math.atan(float(args[0])),
            "SQR": lambda: math.sqrt(float(args[0])),
            "EXP": lambda: math.exp(float(args[0])),
            "LOG": lambda: math.log(float(args[0])) if float(args[0]) > 0 else 0.0,
            "LOG10": lambda: math.log10(float(args[0])) if float(args[0]) > 0 else 0.0,
            "INT": lambda: float(math.floor(float(args[0]))),
            "FLOOR": lambda: float(math.floor(float(args[0]))),
            "CEIL": lambda: float(math.ceil(float(args[0]))),
            "RAD": lambda: math.radians(float(args[0])),
            "DEG": lambda: math.degrees(float(args[0])),
            "SGN": lambda: float(1 if float(args[0]) > 0 else (-1 if float(args[0]) < 0 else 0)),
            "MAX": lambda: max(float(args[0]), float(args[1])),
            "MIN": lambda: min(float(args[0]), float(args[1])),
            "POW": lambda: float(args[0]) ** float(args[1]),
            "LEN": lambda: float(len(str(args[0]))),
            "LEFT$": lambda: str(args[0])[:int(args[1])],
            "RIGHT$": lambda: (str(args[0])[-int(args[1]):] if int(args[1]) else ""),
            "MID$": lambda: self._mid(str(args[0]), args[1], args[2] if len(args) > 2 else len(str(args[0]))),
            "ASC": lambda: float(ord(str(args[0])[0])),
            "CHR$": lambda: chr(int(args[0])),
            "INSTR": lambda: float(str(args[0]).find(str(args[1])) + 1),
            "STR$": lambda: (str(int(args[0])) if float(args[0]) == int(float(args[0])) else str(args[0])),
            "VAL": lambda: self._val(str(args[0])),
            "LTDBGET": lambda: self.ctx.dbget(str(args[0]), str(args[1])),
            "LTDBGET$": lambda: self.ctx.dbget(str(args[0]), str(args[1])),
            "LTDBSET": lambda: self.ctx.dbset(str(args[0]), str(args[1]), args[2] if len(args) > 2 else 0.0),
            "LTDBSETI": lambda: self.ctx.dbset(str(args[0]), str(args[1]), args[2] if len(args) > 2 else 0.0),
            "LTVERSION$": lambda: self.ctx.version(),
            "LTGETSTAT": lambda: 0.0,
            "LTEVAL": lambda: self._eval(args[0]) if args else 0.0,
            "LTCHECKVAR": lambda: 1.0,
            "RND": lambda: float(abs(math.sin(12345.6789 * (args[0] if args else 1) * 100)) % 1.0),
        }
        if name in self.arr and args:
            # 数组索引引用 arr(i)
            return float(self.arr[name][int(self._eval(args[0])) % len(self.arr[name])])
        if name in self.arr and args:
            return float(self.arr[name][int(self._eval(args[0], env)) % len(self.arr[name])])
        if up in m:
            return m[up]()
        f = self.funcs.get(up)
        if f is not None:
            local = dict(env)
            for pp, aa in zip(f[2], args):
                local[pp] = aa
            ret = [0.0]
            self._exec(f[3], local, ret)
            if ret[0]:
                return ret[0]
            return local.get(f[1], 0.0)
        return 0.0

    def _mid(self, s, a, b):
        i0 = int(a) - 1
        return s[i0:i0 + int(b) or len(s)]

    def _val(self, s):
        try:
            return float(s.strip())
        except Exception:
            return 0.0

    def _exec(self, nodes, env, ret=None):
        self._cur_env = env if env is not None else self.env
        i = 0
        while i < len(nodes):
            node = nodes[i]
            if isinstance(node, tuple) and node:
                t = node[0]
                if t == "assign":
                    name, idx = node[1], node[2]
                    val = self._eval(node[3])
                    if idx is not None:
                        arr = self.arr.setdefault(name, [0.0] * 100)
                        arr[int(self._eval(idx)) % len(arr)] = val
                    else:
                        env[name] = val
                elif t == "dim":
                    for (name, size) in node[1]:
                        n = int(self._eval(size)) if size else 10
                        self.arr[name] = [0.0] * max(n, 1)
                elif t == "if":
                    taken = False
                    for (cond, body) in node[1]:
                        if cond is not None and self._eval(cond) != 0.0:
                            self._exec(body, env, ret)
                            taken = True
                            break
                    if not taken:
                        self._exec(node[2], env, ret)
                elif t == "for":
                    var, start, end, step, body = node[1], node[2], node[3], node[4], node[5]
                    s = float(self._eval(start))
                    e = float(self._eval(end))
                    st = float(self._eval(step))
                    val = s
                    while (val <= e and st > 0) or (val >= e and st < 0):
                        env[var] = val
                        self._exec(body, env, ret)
                        if ret is not None and ret[0]:
                            return
                        val += st
                elif t == "while":
                    guard = 0
                    while self._eval(node[1]) != 0.0 and guard < 100000:
                        self._exec(node[2], env, ret)
                        if ret is not None and ret[0]:
                            return
                        guard += 1
                elif t == "do":
                    guard = 0
                    while guard < 100000:
                        self._exec(node[1], env, ret)
                        if ret is not None and ret[0]:
                            return
                        if node[2] is not None:
                            kind, cond = node[2]
                            if self._eval(cond) != 0.0:
                                break
                        guard += 1
                elif t == "select":
                    v = self._eval(node[1])
                    hit = False
                    for (vals, body) in node[2]:
                        for vv in vals:
                            if float(self._eval(vv)) == v:
                                self._exec(body, env, ret)
                                hit = True
                                break
                        if hit:
                            break
                    if not hit:
                        self._exec(node[3], env, ret)
                elif t == "call":
                    args = [self._eval(a) for a in node[2]]
                    self._call(node[1], args)
                elif t == "print":
                    txt = "".join(self._fmt(self._eval(a)) for a in node[1])
                    self._stdout.append(txt)
                    self.ctx.print(txt)
                elif t == "printdev":
                    self._stdout.append("")
                elif t == "command":
                    self.ctx.issue("".join(self._fmt(self._eval(a)) for a in node[1]).strip())
                elif t == "goto":
                    label = node[1]
                    j = i + 1
                    while j < len(nodes):
                        n2 = nodes[j]
                        if isinstance(n2, tuple) and n2 and n2[0] == "label" and n2[1].upper() == label:
                            i = j
                            break
                        j += 1
                elif t == "return":
                    if node[1] and ret is not None:
                        ret[0] = self._eval(node[1][0])
                    if ret is not None:
                        return
                elif t == "exit":
                    return
                elif t == "swap":
                    if len(node[1]) == 2:
                        env[node[1][0]], env[node[1][1]] = env.get(node[1][1], 0.0), env.get(node[1][0], 0.0)
            i += 1

    def _fmt(self, v):
        if isinstance(v, str):
            return v
        f = float(v)
        return str(int(f)) if f == int(f) else "%.6g" % f


def run_macro(source, context):
    return MacroInterpreter(context).run(source)

