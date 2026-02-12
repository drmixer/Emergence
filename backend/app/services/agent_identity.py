"""Deterministic agent identity helpers."""

from __future__ import annotations

from typing import Iterable


IMMUTABLE_AGENT_CODENAMES: tuple[str, ...] = (
    "Tensor",
    "Vector",
    "Matrix",
    "Kernel",
    "Lambda",
    "Sigma",
    "Delta",
    "Axiom",
    "Cipher",
    "Syntax",
    "Node",
    "Orbit",
    "Helix",
    "Quanta",
    "Vertex",
    "Circuit",
    "Pixel",
    "Fractal",
    "Scalar",
    "Nexus",
    "Logic",
    "Nova",
    "Flux",
    "Prime",
    "Arc",
    "Prism",
    "Lattice",
    "Beacon",
    "Proto",
    "Chronon",
    "Relay",
    "Specter",
    "Glyph",
    "Synth",
    "Tempo",
    "Channel",
    "Segment",
    "Pivot",
    "Meridian",
    "Cascade",
    "Lumen",
    "Paradox",
    "Eigen",
    "Spectra",
    "Contour",
    "Monad",
    "Aegis",
    "Entropy",
    "Atlas",
    "Apex",
)


def _safe_agent_number(agent_number: int | str) -> int:
    try:
        parsed = int(agent_number)
    except Exception:
        parsed = 0
    return max(1, parsed)


def immutable_alias_for_agent_number(agent_number: int | str) -> str:
    """Return deterministic immutable codename for a canonical agent number."""
    number = _safe_agent_number(agent_number)
    codename = IMMUTABLE_AGENT_CODENAMES[(number - 1) % len(IMMUTABLE_AGENT_CODENAMES)]
    return f"{codename}-{number:02d}"


def aliases_unique_for_numbers(agent_numbers: Iterable[int | str]) -> bool:
    numbers = list(agent_numbers)
    aliases = {immutable_alias_for_agent_number(number) for number in numbers}
    return len(aliases) == len(numbers)
