from __future__ import annotations

import re
from dataclasses import dataclass


class ContentError(Exception):
    pass


_VALID_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class VariantDef:
    name: str
    when: str


@dataclass(frozen=True)
class ContentEntry:
    id: str
    content_type: str
    metadata: dict
    body: str
    variants: dict[str, str]
    variant_defs: tuple[VariantDef, ...]


def validate_content_id(content_id: str) -> None:
    if not _VALID_ID_PATTERN.match(content_id):
        raise ContentError(
            f"Invalid content ID '{content_id}': only [a-z0-9_] allowed"
        )
