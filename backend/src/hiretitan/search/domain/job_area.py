"""Which areas a job title counts in: front end, back end, QA (feature 002b, FR-017; research R6).

Pure. Words are read from the title, lower-cased, with anything that is not a letter or digit
as a separator (``Front-End`` and ``Vue.js`` split into words). ``Go`` counts as back end only
when it is written with a capital in the original title and is not part of ``Go-To-Market``.
A title naming a non-engineering job (designer, recruiter, sales, marketing, writer) counts
nowhere unless it also has an engineering word (engineer, developer, sdet).
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import Final, Literal

Area = Literal["frontend", "backend", "qa"]

_WORDS: Final = re.compile(r"[A-Za-z0-9]+")
_FRONTEND: Final = frozenset({"frontend", "react", "angular", "vue", "ui"})
_BACKEND: Final = frozenset({"backend", "api", "python", "java", "golang", "node", "server"})
_QA: Final = frozenset({"qa", "sdet", "test", "tester", "testing", "quality"})
_EXCLUDED: Final = frozenset({"designer", "recruiter", "sales", "marketing", "writer"})
_ENGINEERING: Final = frozenset({"engineer", "developer", "sdet"})


def areas_of(title: str) -> frozenset[Area]:
    original = _WORDS.findall(title)
    words = [w.lower() for w in original]
    found = set(words)
    if found & _EXCLUDED and not found & _ENGINEERING:
        return frozenset()
    areas: set[Area] = set()
    pairs = set(pairwise(words))
    if found & _FRONTEND or ("front", "end") in pairs:
        areas.add("frontend")
    if found & _BACKEND or ("back", "end") in pairs:
        areas.add("backend")
    if found & _QA:
        areas.add("qa")
    if "fullstack" in found or ("full", "stack") in pairs:
        areas |= {"frontend", "backend"}
    for index, word in enumerate(original):
        if word == "Go" and words[index + 1 : index + 3] != ["to", "market"]:
            areas.add("backend")
    return frozenset(areas)
