# Copyright (c) 2026 Amp.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
"""Open questions for a person: what the source cannot answer, with what the agent found and the
default it is going ahead with. They live in ``<store>/questions.json``; the agent adds them with
``cobolgraph question`` and a person answers them on the Notes tab or through the agent."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

QUESTIONS = "questions.json"


def load(store: str | os.PathLike) -> list[dict]:
    path = Path(store) / QUESTIONS
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def save(store: str | os.PathLike, questions: list[dict]) -> None:
    path = Path(store) / QUESTIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(questions, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def ask(store: str | os.PathLike, question: str, found: Optional[str] = None,
        default: Optional[str] = None, affects: Optional[str] = None) -> dict:
    """Add a question and return it with its new ID."""
    questions = load(store)
    number = max((int(q["id"][1:]) for q in questions), default=0) + 1
    entry = {"id": f"Q{number}", "question": question.strip(), "found": found, "default": default,
             "affects": affects, "asked": time.strftime("%Y-%m-%d %H:%M"), "answer": None}
    save(store, questions + [entry])
    return entry


def answer(store: str | os.PathLike, qid: str, text: str, by: str) -> dict:
    """Record an answer, replacing any earlier one. An empty answer reopens the question."""
    questions = load(store)
    for q in questions:
        if q["id"].lower() == qid.strip().lower():
            q["answer"] = text.strip() or None
            q["answered"] = time.strftime("%Y-%m-%d %H:%M") if q["answer"] else None
            q["by"] = by if q["answer"] else None
            save(store, questions)
            return q
    raise KeyError(f"no question {qid}")


def markdown(questions: list[dict]) -> list[str]:
    """Open questions first, then answered ones, as Markdown."""
    open_ = [q for q in questions if not q.get("answer")]
    out = ["## Open Questions\n"]
    if not questions:
        return out + ["_None yet. The agent adds them with `cobolgraph question`._\n"]
    out.append(f"{len(open_)} open, {len(questions) - len(open_)} answered. The agent goes ahead with "
               "the default for each open question; an answer changes the plan.\n")
    for q in open_ + [q for q in questions if q.get("answer")]:
        out.append(f"- **{q['id']}** {q['question']}")
        for label, key in (("Found", "found"), ("Default", "default"), ("Affects", "affects"),
                           ("Answer", "answer")):
            if q.get(key):
                out.append(f"  - {label}: {q[key]}")
    return out + [""]
