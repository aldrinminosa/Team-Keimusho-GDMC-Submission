"""
GDMC Building JSON + NBT Exporter with Named Configured Villagers

Exports a building as a paired asset:

    <building_name>.json  -> settlement metadata, waypoints and configured villagers
    <building_name>.nbt   -> complete Minecraft structure and optional saved entities

Configured villagers are NOT copied from the source world. Instead, their local
spawn position, facing, profession and optional custom name are saved in JSON.
The settlement generator creates one configured villager for every placed copy
of the building. The villager's visual type is chosen automatically from the
building tribe.

Output folder:
    ~/Downloads/gdmc_main/builds/<tribe>/

Requirements:
    pip install requests

Minecraft must be running with the GDMC HTTP Interface enabled.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


HOST = "http://localhost:9000"
DIMENSION = "overworld"
OUTPUT_ROOT = Path.home() / "Downloads" / "gdmc_main" / "builds"

CARDINAL_DIRECTIONS = {"north", "east", "south", "west"}
VALID_DIRECTIONS = CARDINAL_DIRECTIONS | {"up", "down", ""}

VILLAGER_PROFESSIONS = {
    "none",
    "nitwit",
    "armorer",
    "butcher",
    "cartographer",
    "cleric",
    "farmer",
    "fisherman",
    "fletcher",
    "leatherworker",
    "librarian",
    "mason",
    "shepherd",
    "toolsmith",
    "weaponsmith",
}

PROFESSION_ALIASES = {
    "unemployed": "none",
    "no profession": "none",
    "no_profession": "none",
    "weapon smith": "weaponsmith",
    "weapon_smith": "weaponsmith",
    "tool smith": "toolsmith",
    "tool_smith": "toolsmith",
    "leather worker": "leatherworker",
    "leather_worker": "leatherworker",
}


def sanitize_name(value: str) -> str:
    safe = re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_")
    if not safe:
        raise ValueError("The name cannot be empty.")
    return safe


def minecraft_id(value: str) -> str:
    value = value.strip().lower()
    return value if ":" in value else f"minecraft:{value}"


def villager_type_for_tribe(tribe: str) -> str:
    """Resolve a Minecraft villager appearance from a settlement tribe name."""
    normalized = tribe.strip().lower().replace("-", "_").replace(" ", "_")
    if "desert" in normalized or "badlands" in normalized:
        return "minecraft:desert"
    if "savanna" in normalized:
        return "minecraft:savanna"
    if "snow" in normalized or "frozen" in normalized or "ice" in normalized:
        return "minecraft:snow"
    if "taiga" in normalized:
        return "minecraft:taiga"
    if "jungle" in normalized:
        return "minecraft:jungle"
    if "swamp" in normalized or "mangrove" in normalized:
        return "minecraft:swamp"
    return "minecraft:plains"


def read_vec3(
    prompt: str,
    allow_empty: bool = False,
) -> tuple[int, int, int] | None:
    while True:
        raw = input(prompt).strip()
        if allow_empty and not raw:
            return None

        parts = raw.replace(",", " ").split()
        if len(parts) != 3:
            print("Enter exactly three integers, for example: 120 64 -35")
            continue

        try:
            x, y, z = map(int, parts)
            return x, y, z
        except ValueError:
            print("Coordinates must be whole numbers.")


def read_non_negative_int(prompt: str, default: int = 0) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue
        if value < 0:
            print("The number cannot be negative.")
            continue
        return value


def read_bounded_int(prompt: str, minimum: int, maximum: int, default: int) -> int:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"Enter a whole number from {minimum} to {maximum}.")
            continue
        if minimum <= value <= maximum:
            return value
        print(f"Enter a whole number from {minimum} to {maximum}.")


def read_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        raw = input(prompt + suffix).strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Enter y or n.")


def read_direction(prompt: str) -> str:
    while True:
        direction = input(prompt).strip().lower()
        if direction in VALID_DIRECTIONS:
            return direction
        print("Use north, east, south, west, up, down, or leave blank.")


def read_cardinal_direction(prompt: str, default: str = "south") -> str:
    while True:
        direction = input(prompt).strip().lower() or default
        if direction in CARDINAL_DIRECTIONS:
            return direction
        print("Use north, east, south, or west.")


def read_profession(default: str = "none") -> str:
    print(
        "  Professions: none, nitwit, armorer, butcher, cartographer, cleric,\n"
        "               farmer, fisherman, fletcher, leatherworker, librarian,\n"
        "               mason, shepherd, toolsmith, weaponsmith"
    )
    while True:
        raw = input(f"  Profession [{default}]: ").strip().lower() or default
        raw = PROFESSION_ALIASES.get(raw, raw).replace("minecraft:", "")
        if raw in VILLAGER_PROFESSIONS:
            return minecraft_id(raw)
        print("  Unknown profession. Choose one from the displayed list.")


def ordered_corners(
    first: tuple[int, int, int],
    second: tuple[int, int, int],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    return (
        (
            min(first[0], second[0]),
            min(first[1], second[1]),
            min(first[2], second[2]),
        ),
        (
            max(first[0], second[0]),
            max(first[1], second[1]),
            max(first[2], second[2]),
        ),
    )


def local_position(
    world_position: tuple[int, int, int],
    origin: tuple[int, int, int],
) -> list[int]:
    return [
        world_position[0] - origin[0],
        world_position[1] - origin[1],
        world_position[2] - origin[2],
    ]


def position_inside_selection(
    position: tuple[int, int, int],
    min_corner: tuple[int, int, int],
    max_corner: tuple[int, int, int],
) -> bool:
    return all(
        minimum <= value <= maximum
        for value, minimum, maximum in zip(position, min_corner, max_corner)
    )


def read_waypoints(origin: tuple[int, int, int]) -> list[dict[str, Any]]:
    count = read_non_negative_int(
        "Number of building waypoints [default: 1]: ",
        default=1,
    )

    waypoints: list[dict[str, Any]] = []

    for index in range(count):
        print(f"\nWaypoint {index + 1}")
        default_name = "main_entrance" if index == 0 else f"waypoint_{index + 1}"
        name = input(f"  Name [{default_name}]: ").strip() or default_name
        # Building waypoints are always road connections.
        # The tribe folder tells the generator which road palette/style to use.
        waypoint_type = "road"

        world_position = read_vec3("  World XYZ of the connection block: ")
        assert world_position is not None

        direction = read_direction(
            "  Direction it faces (north/east/south/west, optional): "
        )

        waypoint: dict[str, Any] = {
            "name": name,
            "type": waypoint_type,
            "pos": local_position(world_position, origin),
            "source_world_pos": list(world_position),
        }
        if direction:
            waypoint["direction"] = direction

        waypoints.append(waypoint)

    return waypoints


def read_villager_spawns(
    tribe: str,
    min_corner: tuple[int, int, int],
    max_corner: tuple[int, int, int],
) -> list[dict[str, Any]]:
    """Read zero or more villagers that should spawn with each building copy."""
    print("\nConfigured villagers")
    print(
        "These villagers are saved as JSON spawn metadata, not copied from the "
        "source-world NBT."
    )
    count = read_non_negative_int(
        "Number of villagers this building should spawn [default: 0]: ",
        default=0,
    )
    if count == 0:
        print("  No configured villager will be spawned for this building.")
        return []

    automatic_type = villager_type_for_tribe(tribe)
    print(f"  Automatic villager type for tribe '{tribe}': {automatic_type}")

    villagers: list[dict[str, Any]] = []
    for index in range(count):
        print(f"\nVillager {index + 1}")
        while True:
            world_position = read_vec3(
                "  World XYZ of the block where the villager's feet should stand: "
            )
            assert world_position is not None
            if position_inside_selection(world_position, min_corner, max_corner):
                break
            print(
                "  That position is outside the exported selection. Choose a "
                "position inside the building box."
            )

        custom_name = input(
            "  Custom villager name (blank = unnamed): "
        ).strip()
        custom_name_visible = False
        if custom_name:
            custom_name_visible = read_yes_no(
                "  Always show the custom name above the villager?",
                default=True,
            )

        facing = read_cardinal_direction(
            "  Initial facing [south]: ",
            default="south",
        )
        profession = read_profession(default="none")
        level = read_bounded_int(
            "  Villager level 1-5 [2]: ",
            1,
            5,
            default=2,
        )
        stationary = read_yes_no(
            "  Keep the villager fixed at this position and facing direction?",
            default=True,
        )

        villagers.append(
            {
                "name": f"villager_{index + 1}",
                "custom_name": custom_name,
                "custom_name_visible": custom_name_visible,
                "enabled": True,
                "pos": local_position(world_position, min_corner),
                "source_world_pos": list(world_position),
                "facing": facing,
                "profession": profession,
                "level": level,
                "type": "auto",
                "resolved_type_preview": automatic_type,
                "stationary": stationary,
                "persistent": True,
            }
        )

    return villagers


def check_connection() -> dict[str, Any]:
    try:
        response = requests.options(HOST + "/", timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not connect to the GDMC HTTP Interface at " + HOST
        ) from exc

    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def read_entity_summary(
    min_corner: tuple[int, int, int],
    size: tuple[int, int, int],
) -> tuple[int | None, dict[str, int]]:
    """Best-effort preview of entities that will be embedded in the NBT file."""
    params = {
        "x": min_corner[0],
        "y": min_corner[1],
        "z": min_corner[2],
        "dx": size[0],
        "dy": size[1],
        "dz": size[2],
        "includeData": "true",
        "dimension": DIMENSION,
    }

    try:
        response = requests.get(HOST + "/entities", params=params, timeout=30)
        response.raise_for_status()
        entities = response.json()
        if not isinstance(entities, list):
            return None, {}

        counts: Counter[str] = Counter()
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("id")
            if not entity_id:
                data = str(entity.get("data", ""))
                match = re.search(r'(?:^|[,\{])id:\"?([a-z0-9_:.\-/]+)', data)
                entity_id = match.group(1) if match else "unknown"
            counts[str(entity_id)] += 1

        return len(entities), dict(sorted(counts.items()))
    except (requests.RequestException, ValueError):
        return None, {}


def export_nbt_structure(
    output_path: Path,
    min_corner: tuple[int, int, int],
    size: tuple[int, int, int],
    include_entities: bool,
) -> int:
    """Download an uncompressed binary NBT structure from GDMC-HTTP."""
    params = {
        "x": min_corner[0],
        "y": min_corner[1],
        "z": min_corner[2],
        "dx": size[0],
        "dy": size[1],
        "dz": size[2],
        "entities": str(include_entities).lower(),
        "dimension": DIMENSION,
        "withinBuildArea": "false",
    }
    headers = {
        "Accept": "application/octet-stream",
        "Accept-Encoding": "*",
    }

    response = requests.get(
        HOST + "/structure",
        params=params,
        headers=headers,
        timeout=180,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        print("GDMC returned an error while exporting the NBT structure:")
        print(response.text)
        raise

    if not response.content:
        raise RuntimeError("GDMC returned an empty NBT structure file.")

    output_path.write_bytes(response.content)
    return len(response.content)


def main() -> None:
    print("=" * 72)
    print("GDMC BUILDING JSON + NBT EXPORTER — CONFIGURED VILLAGERS")
    print("=" * 72)
    print(f"GDMC host: {HOST}")
    print()
    print("The JSON stores metadata, road waypoints and configured villagers.")
    print("Road waypoint type is automatic; road appearance comes from the tribe.")
    print("The NBT stores the complete structure and optional source entities.")
    print()

    tribe = sanitize_name(input("Tribe name [plains]: ").strip() or "plains")
    building_name = sanitize_name(input("Building name: ").strip())

    first_corner = read_vec3("First corner XYZ: ")
    second_corner = read_vec3("Opposite corner XYZ: ")
    assert first_corner is not None
    assert second_corner is not None

    min_corner, max_corner = ordered_corners(first_corner, second_corner)
    size = (
        max_corner[0] - min_corner[0] + 1,
        max_corner[1] - min_corner[1] + 1,
        max_corner[2] - min_corner[2] + 1,
    )

    print(f"\nSelection origin: {min_corner}")
    print(f"Selection maximum: {max_corner}")
    print(f"Selection size: {size[0]} x {size[1]} x {size[2]}")
    print("Waypoints may be inside or outside the selection.")

    waypoints = read_waypoints(min_corner)
    villager_spawns = read_villager_spawns(tribe, min_corner, max_corner)

    include_entities = read_yes_no(
        "\nInclude source entities such as item frames, paintings, armor stands "
        "and mobs in the NBT?",
        default=True,
    )

    print("\nConnecting to Minecraft...")
    try:
        server_info = check_connection()
    except RuntimeError as exc:
        print(exc)
        print("Check that Minecraft is open and GDMC-HTTP is running on port 9000.")
        sys.exit(1)

    entity_count: int | None = 0
    entity_types: dict[str, int] = {}
    if include_entities:
        entity_count, entity_types = read_entity_summary(min_corner, size)
        if entity_count is None:
            print("Entity preview was unavailable, but NBT export will continue.")
        else:
            print(f"Entities inside selection: {entity_count}")
            for entity_id, count in entity_types.items():
                print(f"  {entity_id}: {count}")

            source_villagers = sum(
                count
                for entity_id, count in entity_types.items()
                if entity_id.endswith(":villager") or entity_id == "villager"
            )
            if source_villagers and villager_spawns:
                print()
                print(
                    "WARNING: The selection already contains source-world "
                    f"villagers ({source_villagers}) AND you configured JSON "
                    "villagers. Both would spawn, causing duplicates."
                )
                if not read_yes_no(
                    "Continue and intentionally keep both kinds of villagers?",
                    default=False,
                ):
                    print(
                        "Export cancelled. Remove the source villagers, or export "
                        "NBT entities without them, then run again."
                    )
                    sys.exit(1)

            if entity_count:
                print(
                    "WARNING: Every included source entity is copied. Remove "
                    "dropped items or unrelated mobs before exporting."
                )

    output_dir = OUTPUT_ROOT / tribe
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{building_name}.json"
    nbt_path = output_dir / f"{building_name}.nbt"

    print("\nExporting NBT structure...")
    try:
        nbt_size = export_nbt_structure(
            nbt_path,
            min_corner,
            size,
            include_entities,
        )
    except Exception as exc:
        print(f"NBT export failed: {exc}")
        sys.exit(1)

    metadata: dict[str, Any] = {
        "format": "gdmc_building_json",
        "format_version": 3,
        "name": building_name,
        "tribe": tribe,
        "minecraft_version": (
            server_info.get("minecraftVersion")
            or server_info.get("MinecraftVersion")
            or server_info.get("version")
        ),
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "coordinate_system": {
            "origin": "minimum_selection_corner",
            "x_positive": "east",
            "y_positive": "up",
            "z_positive": "south",
            "rotation": "clockwise_around_y",
        },
        "size": list(size),
        "source": {
            "min_corner": list(min_corner),
            "max_corner": list(max_corner),
            "inclusive": True,
        },
        "origin": [0, 0, 0],
        "waypoints": waypoints,
        "villagers": villager_spawns,
        "villager_type_rule": {
            "mode": "automatic_from_tribe",
            "tribe": tribe,
            "resolved_preview": villager_type_for_tribe(tribe),
        },
        "structure": {
            "file": nbt_path.name,
            "format": "minecraft_structure_nbt",
            "compression": "uncompressed",
            "entities": include_entities,
            "rotation_pivot": [0, 0, 0],
            "byte_size": nbt_size,
        },
        "entity_count_preview": entity_count,
        "entity_types_preview": entity_types,
        "blocks": [],
    }

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=2, ensure_ascii=False)

    print("\nExport complete!")
    print(f"JSON metadata: {json_path}")
    print(f"NBT structure: {nbt_path}")
    print(f"NBT size: {nbt_size:,} bytes")
    print(f"Configured villagers per placed building: {len(villager_spawns)}")
    if villager_spawns:
        print(
            "Automatic villager appearance: "
            f"{villager_type_for_tribe(tribe)} from tribe '{tribe}'"
        )
        for villager in villager_spawns:
            print(
                f"  {villager['name']}: "
                f"custom_name={villager.get('custom_name') or '(unnamed)'!r}, "
                f"local={villager['pos']}, "
                f"facing={villager['facing']}, "
                f"profession={villager['profession']}, "
                f"level={villager['level']}, "
                f"stationary={villager['stationary']}"
            )


if __name__ == "__main__":
    main()
