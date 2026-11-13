CRAFTING_DISCIPLINES = [
    "Armorsmith",
    "Artificer",
    "Chef",
    "Huntsman",
    "Jeweler",
    "Leatherworker",
    "Scribe",
    "Tailor",
    "Weaponsmith",
    "Unassigned",
]


def format_coins(copper: int | None) -> str:
    """Format copper amount into Guild Wars 2 gold, silver, copper string."""
    if copper is None:
        return "0c"
    negative = copper < 0
    c = abs(int(copper))
    gold = c // 10000
    silver = (c % 10000) // 100
    copper_rem = c % 100

    parts: list[str] = []
    if gold > 0:
        parts.append(f"{gold}g")
    if silver > 0 or gold > 0:
        parts.append(f"{silver}s")
    parts.append(f"{copper_rem}c")

    res = " ".join(parts)
    return f"-{res}" if negative else res
