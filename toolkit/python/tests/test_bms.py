# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Symbolic map copybooks generated from BMS source."""

import tempfile
import unittest
from pathlib import Path

from mfmap import bms

# DSATTS lists SOSI before COLOR; the copybook still puts C before M. The TITLE operands continue
# inside a quoted INITIAL that holds a comma and a blank, and the mapset label differs from the
# file name, as in a copied map.
def continued(text):
    """A line continued in column 72."""
    return text.ljust(71) + "*"


SOURCE = "\n".join([
    continued("OTHER    DFHMSD TYPE=&SYSPARM,MODE=INOUT,LANG=COBOL,STORAGE=AUTO,"),
    "               TIOAPFX=YES,DSATTS=(SOSI,COLOR)",
    "MAPA     DFHMDI SIZE=(24,80)",
    continued("TITLE    DFHMDF POS=(1,1),LENGTH=20,INITIAL='Hello, the quick brown fox w"),
    "               orld',ATTRB=PROT",
    "         DFHMDF POS=(2,1),LENGTH=5,INITIAL='Label'",
    "* a comment line",
    "ROW      DFHMDF POS=(3,1),LENGTH=4,OCCURS=2",
    "AMT      DFHMDF POS=(5,1),LENGTH=7,PICOUT='9999.99'",
    "         DFHMSD TYPE=FINAL",
])

EXPECTED = """\
       01  MAPAI.
           02  FILLER PIC X(12).
           02  TITLEL    COMP  PIC  S9(4).
           02  TITLEF    PICTURE X.
           02  FILLER REDEFINES TITLEF.
             03 TITLEA    PICTURE X.
           02  FILLER   PICTURE X(2).
           02  TITLEI  PIC X(20).
           02  DFHMS1 OCCURS 2 TIMES.
             03  ROWL    COMP  PIC  S9(4).
             03  ROWF    PICTURE X.
             03  FILLER   PICTURE X(2).
             03  ROWI  PIC X(4).
           02  AMTL    COMP  PIC  S9(4).
           02  AMTF    PICTURE X.
           02  FILLER REDEFINES AMTF.
             03 AMTA    PICTURE X.
           02  FILLER   PICTURE X(2).
           02  AMTI  PIC X(7).
       01  MAPAO REDEFINES MAPAI.
           02  FILLER PIC X(12).
           02  FILLER PICTURE X(3).
           02  TITLEC    PICTURE X.
           02  TITLEM    PICTURE X.
           02  TITLEO  PIC X(20).
           02  DFHMS2 OCCURS 2 TIMES.
             03  FILLER PICTURE X(2).
             03  ROWA    PICTURE X.
             03  ROWC    PICTURE X.
             03  ROWM    PICTURE X.
             03  ROWO  PIC X(4).
           02  FILLER PICTURE X(3).
           02  AMTC    PICTURE X.
           02  AMTM    PICTURE X.
           02  AMTO  PIC 9999.99.
"""


class BmsTest(unittest.TestCase):
    def test_writes_symbolic_map_named_after_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "src" / "MYMAP.bms"
            source.parent.mkdir()
            source.write_text(SOURCE)
            written = bms.write([str(source.parent)], str(Path(tmp) / "out"))
            self.assertEqual([p.name for p in written], ["MYMAP.cpy"])
            self.assertEqual(written[0].read_text(), EXPECTED)


if __name__ == "__main__":
    unittest.main()
