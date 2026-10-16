# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""REST APIs and the web pages that call them.

From OpenAPI documents (``openapi:`` with ``paths:``): each operation as ``api:METHOD /path``. From
IBM z/OS Connect projects: each operation's ``operation.yaml`` (in ``operations/<encoded
path>/<method>/``) names its z/OS asset (``zasset:``), and each asset's ``zosAsset.yaml`` names the
CICS program it links to (``program:``, with its ``transid``) or the IMS transaction it starts
(``transactionCode:``). From JavaScript: functions whose body builds a URL in a template literal
(``${base}/accounts/${id}``) with an optional ``method: 'POST'``, matched to the API's paths by
their fixed segments, and each page or script that calls those functions (``client.group.fn(``),
as ``page:path``. A called function that builds no URL is an unresolved call, noted with the error
it throws.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import unquote

from . import Context, Entity, Fact, Relationship

NAME = "web"
METHODS = ("get", "put", "post", "delete", "patch", "head", "options")
PATH_KEY = re.compile(r"^  (/\S*):\s*$")
METHOD_KEY = re.compile(r"^    (" + "|".join(METHODS) + r"):\s*$")
OPERATION_ID = re.compile(r"^\s+operationId:\s*['\"]?([\w.-]+)")
YAML_VALUE = r"^\s*{}:\s*['\"]?([^'\"\n#]+?)['\"]?\s*$"
FUNCTION = re.compile(r"^\s*(?:async\s+)?(?:function\s+)?(?!(?:if|for|while|switch|catch|with|return)\b)"
                      r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", re.M)
URL = re.compile(r"`\$\{[^}]*\}(/[^`?]*)")
HTTP_METHOD = re.compile(r"\bmethod\s*:\s*['\"](\w+)['\"]")
THROW = re.compile(r"\bthrow\s+new\s+\w*Error\(\s*['\"`]([^'\"`]*)")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def shape(path: str) -> tuple:
    """A path's segments with parameters (``{id}`` or ``${id}``) as ``{}``."""
    return tuple("{}" if "{" in seg else seg for seg in path.strip("/").split("/"))


def value(text: str, key: str) -> Optional[str]:
    m = re.search(YAML_VALUE.format(key), text, re.M)
    return m.group(1).strip() if m else None


def resolve(ctx: Context) -> Iterator[Fact]:
    apis = {}  # (METHOD, shape) -> endpoint
    for path, text in ctx.files(lambda p: p.suffix.lower() in (".yaml", ".yml")):
        if re.search(r"^openapi:", text, re.M) and re.search(r"^paths:", text, re.M):
            current = None
            lines = text.splitlines()
            for number, line in enumerate(lines, 1):
                if m := PATH_KEY.match(line):
                    current = m.group(1)
                elif (m := METHOD_KEY.match(line)) and current:
                    endpoint = f"api:{m.group(1).upper()} {current}"
                    apis[(m.group(1).upper(), shape(current))] = endpoint
                    op = next((o.group(1) for o in map(OPERATION_ID.match, lines[number:number + 12]) if o), None)
                    yield Entity(endpoint, "defined", op, str(path), number)
        elif path.name == "operation.yaml" and (asset := value(text, "zasset")):
            method, encoded = path.parent.name.upper(), path.parent.parent.name
            yield Relationship("invokes", f"api:{method} {unquote(encoded)}", f"zosasset:{asset.upper()}",
                               "declared", asset, path=str(path), line=line_of(text, text.find("zasset")))
        elif path.name == "zosAsset.yaml":
            asset = f"zosasset:{path.parent.name.upper()}"
            yield Entity(asset, "defined", value(text, "description"), str(path), 1)
            if program := value(text, "program"):
                transid = value(text, "transid")
                yield Relationship("links", asset, f"program:{program.upper()}", "declared", program,
                                   f"CICS, transid {transid}" if transid else "CICS", str(path),
                                   line_of(text, text.find("program:")))
            if tran := value(text, "transactionCode"):
                yield Relationship("starts", asset, f"transaction:{tran.upper()}", "declared", tran, "IMS",
                                   str(path), line_of(text, text.find("transactionCode:")))
    # JavaScript API clients: function name -> [(METHOD, url, line)] or the error it throws.
    clients, scripts = {}, list(ctx.files(lambda p: p.suffix.lower() in (".js", ".mjs", ".html", ".htm")))
    for path, text in scripts:
        if "fetch(" not in text or path.suffix.lower() not in (".js", ".mjs"):
            continue
        starts = list(FUNCTION.finditer(text))
        for i, f in enumerate(starts):
            body = text[f.start(): starts[i + 1].start() if i + 1 < len(starts) else len(text)]
            urls = [(m.group(1), f.start() + m.start()) for m in URL.finditer(body)]
            methods = {m.upper() for m in HTTP_METHOD.findall(body)}
            if urls:
                method = methods.pop() if len(methods) == 1 else None
                clients[f.group(1)] = (path, [(method or window_method(body, f.start(), off, urls), url,
                                               line_of(text, off)) for url, off in urls])
            elif (thrown := THROW.search(body)) and f.group(1) not in clients:
                clients[f.group(1)] = (path, thrown.group(1))
    if not clients:
        return
    call = re.compile(r"\b[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.(" + "|".join(map(re.escape, clients)) + r")\s*\(")
    for path, text in scripts:
        if any(path == c[0] for c in clients.values()):
            continue  # the client itself
        page = f"page:{relative(ctx, path)}"
        for m in call.finditer(text):
            if text[max(0, m.start() - 5): m.start()].endswith("this") or text[m.start():].startswith("this."):
                continue
            client_path, found = clients[m.group(1)]
            line = line_of(text, m.start())
            if isinstance(found, str):
                yield Relationship("calls", page, None, "unresolved", m.group(0).rstrip("( "),
                                   f"{m.group(1)} builds no URL; it throws: {found}", str(path), line)
                continue
            for method, url, url_line in found:
                endpoint = apis.get((method or "GET", shape(url)))
                note = f"{m.group(1)} ({client_path.name}:{url_line})"
                if endpoint:
                    yield Relationship("calls", page, endpoint, "literal", url, note, str(path), line)
                else:
                    yield Relationship("calls", page, f"api:{method or 'GET'} {url}", "literal", url,
                                       note + "; no such API operation", str(path), line)


def window_method(body: str, start: int, offset: int, urls: list) -> Optional[str]:
    """The method after this URL and before the next one, when a function's URLs use different ones."""
    later = [o for _, o in urls if o > offset]
    window = body[offset - start: (later[0] if later else start + len(body)) - start]
    m = HTTP_METHOD.search(window)
    return m.group(1).upper() if m else None


def relative(ctx: Context, path: Path) -> str:
    try:
        return str(path.relative_to(ctx.root))
    except ValueError:
        return str(path)
