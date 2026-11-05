"""Which fields differ between the current profile and a new one (FR-014). Pure.

List items are matched by identity of content, never by position or id (a re-extraction
mints new ids): experience by (employer, title), education by (institution, qualification),
projects and certifications by name. Matching ignores case and spacing. Paths look like
``contact.name`` or ``experience[Acme | Engineer].title``; ``skills`` compare as a set.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from hiretitan.profile.domain.content import (
    Certification,
    Education,
    Experience,
    ProfileContent,
    Project,
    skill_key,
)


def _norm(value: str | None) -> str:
    return skill_key(value or "")


def _label(*parts: str | None) -> str:
    return " | ".join(p.strip() for p in parts if p and p.strip())


def _compare_items[T](
    prefix: str,
    old: Sequence[T],
    new: Sequence[T],
    key: Callable[[T], tuple[str, ...]],
    label: Callable[[T], str],
    fields: Sequence[str],
    second_key_field: str | None = None,
) -> list[str]:
    """Pair items by the full key, then pair leftovers that share the first key part (the
    same employer or institution with a changed title or qualification)."""
    old_left = {key(item): item for item in old}
    new_left = {key(item): item for item in new}
    pairs: list[tuple[T, T, bool]] = []  # (before, after, matched loosely)
    for k in [k for k in new_left if k in old_left]:
        pairs.append((old_left.pop(k), new_left.pop(k), False))
    if second_key_field is not None:
        for new_key in list(new_left):
            partner = next((k for k in old_left if k[0] == new_key[0]), None)
            if partner is not None:
                pairs.append((old_left.pop(partner), new_left.pop(new_key), True))

    paths = [f"{prefix}[{label(item)}]" for item in old_left.values()]  # removed
    paths += [f"{prefix}[{label(item)}]" for item in new_left.values()]  # added
    for before, after, loose in pairs:
        names = [second_key_field, *fields] if loose and second_key_field else fields
        for name in names:
            if _comparable(getattr(before, name)) != _comparable(getattr(after, name)):
                paths.append(f"{prefix}[{label(before)}].{name}")
    return sorted(paths, key=lambda path: path.split("]")[0])


def _comparable(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, tuple):
        return tuple(_comparable(v) for v in value)
    return value


def changed_paths(current: ProfileContent, new: ProfileContent) -> list[str]:
    paths: list[str] = []
    for name in ("name", "email", "phone", "location"):
        if _comparable(getattr(current.contact, name)) != _comparable(getattr(new.contact, name)):
            paths.append(f"contact.{name}")
    if current.contact.links != new.contact.links:
        paths.append("contact.links")
    for name in ("headline", "summary"):
        if _comparable(getattr(current, name)) != _comparable(getattr(new, name)):
            paths.append(name)

    paths += _compare_items(
        "experience",
        current.experience,
        new.experience,
        key=lambda e: (_norm(e.employer), _norm(e.title)),
        label=lambda e: _label(e.employer, e.title),
        fields=("location", "start", "end", "current", "bullets"),
        second_key_field="title",
    )
    paths += _compare_items(
        "education",
        current.education,
        new.education,
        key=lambda e: (_norm(e.institution), _norm(e.qualification)),
        label=lambda e: _label(e.institution, e.qualification),
        fields=("field_of_study", "start", "end", "grade"),
        second_key_field="qualification",
    )
    if {skill_key(s) for s in current.skills} != {skill_key(s) for s in new.skills}:
        paths.append("skills")
    paths += _compare_items(
        "projects",
        current.projects,
        new.projects,
        key=lambda p: (_norm(p.name),),
        label=lambda p: p.name.strip(),
        fields=("description", "technologies", "link"),
    )
    paths += _compare_items(
        "certifications",
        current.certifications,
        new.certifications,
        key=lambda c: (_norm(c.name),),
        label=lambda c: c.name.strip(),
        fields=("issuer", "date"),
    )
    return paths


__all__ = ["Certification", "Education", "Experience", "Project", "changed_paths"]
