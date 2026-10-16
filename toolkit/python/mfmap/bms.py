# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Write COBOL symbolic map copybooks from BMS map source, for builds that do not keep them.

``generate`` follows the layout the BMS assembler writes for ``LANG=COBOL``: per map an input
structure ``<map>I`` and an output structure ``<map>O`` that redefines it, a 12-byte filler for
``TIOAPFX=YES``, and per named field the L, F and A subfields, one byte for each attribute in
``DSATTS`` (suffixes C, P, H, V, U, M, T in that order) and the I and O data fields, with
``PICIN`` and ``PICOUT`` when given. A field with ``OCCURS`` becomes a ``DFHMSn`` group that
occurs that many times. Byte offsets match the assembler's for these options; check them against
your build's copybooks before relying on them for anything but names and lengths.
"""

from __future__ import annotations

import re
from pathlib import Path

ATTRIBUTES = [("COLOR", "C"), ("PS", "P"), ("HILIGHT", "H"), ("VALIDN", "V"),
              ("OUTLINE", "U"), ("SOSI", "M"), ("TRANSP", "T")]
OPERAND = re.compile(r"([A-Z]+)=('(?:[^']|'')*'|\([^)]*\)|[^,]*)")


def statements(text: str):
    """Yield (label, macro, operands) for each macro, joining continuation lines."""
    label = macro = None
    operands = ""
    continued = False
    for line in text.splitlines():
        if not continued and line.startswith("*"):
            continue
        body, more = line[:71], len(line) > 71 and line[71] != " "
        if continued:
            # inside a quoted string the text runs to column 71; otherwise drop the padding
            operands += body[15:] if operands.count("'") % 2 else body[15:].strip()
        else:
            parts = body.split(None, 2) if not body.startswith(" ") else [None, *body.split(None, 1)]
            if len(parts) < 2:
                continue
            label, macro = parts[0], parts[1].upper()
            operands = parts[2].strip() if len(parts) > 2 else ""
        continued = more
        if not continued:
            # operands end at the first blank outside quotes
            out, quoted = [], False
            for ch in operands:
                if ch == "'":
                    quoted = not quoted
                if ch == " " and not quoted:
                    break
                out.append(ch)
            yield label, macro, dict(OPERAND.findall("".join(out).upper()))


def attribute_suffixes(value: str | None) -> list[str]:
    names = set(re.findall(r"[A-Z]+", value or ""))
    return [suffix for name, suffix in ATTRIBUTES if name in names]


def generate(text: str) -> str:
    """Return the COBOL symbolic map copybook for one mapset's BMS source."""
    prefix, dsatts, maps = True, [], []
    for label, macro, ops in statements(text):
        if macro == "DFHMSD" and ops.get("TYPE") != "FINAL":
            prefix = ops.get("TIOAPFX", "YES") == "YES"
            dsatts = attribute_suffixes(ops.get("DSATTS"))
            if not dsatts and ops.get("EXTATT") == "YES":
                dsatts = ["C", "P", "H"]
        elif macro == "DFHMDI":
            maps.append((label.upper(), attribute_suffixes(ops.get("DSATTS")) or dsatts, []))
        elif macro == "DFHMDF" and label and maps:
            pic = lambda key: ops[key].strip("'") if key in ops else None
            maps[-1][2].append((label.upper(), int(ops.get("LENGTH") or 1), int(ops.get("OCCURS") or 1),
                                pic("PICIN"), pic("PICOUT")))
    lines, group = [], 0
    for name, attrs, fields in maps:
        extra = len(attrs)
        inp = [f"       01  {name}I."]
        out = [f"       01  {name}O REDEFINES {name}I."]
        if prefix:
            inp.append("           02  FILLER PIC X(12).")
            out.append("           02  FILLER PIC X(12).")
        for field, length, occurs, picin, picout in fields:
            data_in = f"PIC {picin}" if picin else f"PIC X({length})"
            data_out = f"PIC {picout}" if picout else f"PIC X({length})"
            if occurs > 1:
                group += 1
                inp += [f"           02  DFHMS{group} OCCURS {occurs} TIMES.",
                        f"             03  {field}L    COMP  PIC  S9(4).",
                        f"             03  {field}F    PICTURE X."]
                if extra:
                    inp.append(f"             03  FILLER   PICTURE X({extra}).")
                inp.append(f"             03  {field}I  {data_in}.")
                group += 1
                out += [f"           02  DFHMS{group} OCCURS {occurs} TIMES.",
                        "             03  FILLER PICTURE X(2).",
                        f"             03  {field}A    PICTURE X."]
                out += [f"             03  {field}{s}    PICTURE X." for s in attrs]
                out.append(f"             03  {field}O  {data_out}.")
            else:
                inp += [f"           02  {field}L    COMP  PIC  S9(4).",
                        f"           02  {field}F    PICTURE X.",
                        f"           02  FILLER REDEFINES {field}F.",
                        f"             03 {field}A    PICTURE X."]
                if extra:
                    inp.append(f"           02  FILLER   PICTURE X({extra}).")
                inp.append(f"           02  {field}I  {data_in}.")
                out.append("           02  FILLER PICTURE X(3).")
                out += [f"           02  {field}{s}    PICTURE X." for s in attrs]
                out.append(f"           02  {field}O  {data_out}.")
        lines += inp + out
    return "\n".join(lines) + "\n"


def write(sources: list[str], out: str) -> list[Path]:
    """Write ``<name>.cpy`` into ``out`` for every ``<name>.bms`` file under the sources. The
    copybook is named after the file, as builds name the generated member after the source member,
    not after the DFHMSD label."""
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for source in sources:
        path = Path(source)
        for bms in sorted(path.rglob("*") if path.is_dir() else [path]):
            if bms.suffix.lower() != ".bms":
                continue
            written.append(target / f"{bms.stem.upper()}.cpy")
            written[-1].write_text(generate(bms.read_text(errors="replace")))
    return written
