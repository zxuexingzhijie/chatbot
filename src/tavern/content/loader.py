from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml

logger = logging.getLogger(__name__)

ConditionEvaluatorFn = Callable[..., bool]


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


class ContentLoader:
    def __init__(self) -> None:
        self._entries: dict[str, ContentEntry] = {}

    @property
    def entries(self) -> dict[str, ContentEntry]:
        return self._entries

    def load_directory(self, path: Path) -> None:
        if not path.exists():
            return
        md_files = sorted(path.rglob("*.md"))

        main_files: dict[str, tuple[Path, dict, str]] = {}
        variant_files: dict[str, dict[str, str]] = {}

        for md_path in md_files:
            stem = md_path.stem
            parts = stem.split(".", 1)
            base_id = parts[0]

            validate_content_id(base_id)

            raw = md_path.read_text(encoding="utf-8")

            if len(parts) == 1:
                meta, body = _parse_frontmatter(raw)
                content_id = meta.get("id", base_id)
                validate_content_id(content_id)
                main_files[content_id] = (md_path, meta, body)
            else:
                variant_name = parts[1]
                variant_files.setdefault(base_id, {})[variant_name] = raw.strip()

        for content_id, (_, meta, body) in main_files.items():
            raw_variants = meta.pop("variants", []) or []
            variant_defs = tuple(
                VariantDef(name=v["name"], when=v["when"])
                for v in raw_variants
                if isinstance(v, dict) and "name" in v and "when" in v
            )
            content_type = meta.pop("type", "unknown")
            meta.pop("id", None)

            variants = variant_files.get(content_id, {})

            self._entries[content_id] = ContentEntry(
                id=content_id,
                content_type=content_type,
                metadata=meta,
                body=body,
                variants=variants,
                variant_defs=variant_defs,
            )

    def resolve(
        self,
        entry_id: str,
        condition_evaluator: ConditionEvaluatorFn | None = None,
        **eval_kwargs,
    ) -> str | None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return None

        if condition_evaluator is not None:
            for variant_def in entry.variant_defs:
                if condition_evaluator(variant_def.when, **eval_kwargs):
                    variant_body = entry.variants.get(variant_def.name)
                    if variant_body is not None:
                        return variant_body

        return entry.body


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw.strip()

    end_idx = raw.find("---", 3)
    if end_idx == -1:
        return {}, raw.strip()

    frontmatter_str = raw[3:end_idx].strip()
    body = raw[end_idx + 3:].strip()

    try:
        meta = yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError:
        logger.warning("Failed to parse frontmatter, treating as plain body")
        meta = {}

    return meta, body
