"""
GDMC Exported Building Test Placer
==================================

Places one building exported by:
    export_building_json_nbt_named_villagers.py

The script lets you:
- choose any exported JSON + NBT building from ~/Downloads/gdmc_main/builds
- choose the destination origin and rotation
- place the NBT structure
- optionally include entities embedded in the NBT file
- optionally spawn the configured JSON villagers
- preview the resulting entities inside the placed building box

Requirements:
    pip install requests

Minecraft requirements:
- Minecraft is running with a world open
- GDMC HTTP Interface is available at http://localhost:9000
- Set a build area first when using withinBuildArea=true:
      /buildarea set x1 y1 z1 x2 y2 z2

Coordinate meaning:
The destination XYZ is the new position of the exported selection's minimum
corner, meaning JSON local position [0, 0, 0]. It is not necessarily the
building floor unless the original export selection started at floor level.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests


HOST = os.environ.get("GDMC_HOST", "http://localhost:9000").rstrip("/")
DIMENSION = os.environ.get("GDMC_DIMENSION", "overworld")
BUILDINGS_ROOT = Path(
    os.environ.get(
        "GDMC_BUILDINGS_ROOT",
        str(Path.home() / "Downloads" / "gdmc_main" / "builds"),
    )
)

NBT_REQUEST_TIMEOUT = 180
ENTITY_REQUEST_TIMEOUT = 90
ENTITY_BATCH_SIZE = 128
CARDINAL_DIRECTIONS = ["north", "east", "south", "west"]


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


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


def read_vec3(prompt: str) -> tuple[int, int, int]:
    while True:
        raw = input(prompt).strip()
        parts = raw.replace(",", " ").split()
        if len(parts) != 3:
            print("Enter exactly three whole numbers, for example: 120 64 -35")
            continue
        try:
            x, y, z = map(int, parts)
            return x, y, z
        except ValueError:
            print("Coordinates must be whole numbers.")


def read_rotation() -> int:
    while True:
        raw = input("Rotation 0/90/180/270 [0]: ").strip()
        if not raw:
            return 0
        try:
            rotation = int(raw) % 360
        except ValueError:
            print("Enter 0, 90, 180, or 270.")
            continue
        if rotation in {0, 90, 180, 270}:
            return rotation
        print("Enter 0, 90, 180, or 270.")


# ---------------------------------------------------------------------------
# Building discovery and validation
# ---------------------------------------------------------------------------


def discover_building_json_files(root: Path) -> list[Path]:
    """Find exported building metadata below builds/<tribe>/."""
    if not root.is_dir():
        raise FileNotFoundError(
            f"Building root does not exist: {root}\n"
            "Expected folders such as builds/plains and builds/desert."
        )

    results: list[Path] = []
    for path in sorted(root.rglob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue

        if data.get("format") != "gdmc_building_json":
            continue

        structure = data.get("structure")
        structure_file = None
        if isinstance(structure, dict):
            structure_file = structure.get("file")
        structure_file = (
            data.get("structure_file")
            or data.get("nbt_file")
            or structure_file
        )

        # This test tool is specifically for the new paired exporter.
        if structure_file:
            results.append(path)

    return results


def choose_building(paths: Sequence[Path], root: Path) -> Path:
    if not paths:
        raise FileNotFoundError(
            f"No paired JSON + NBT building exports were found below {root}."
        )

    print("\nExported buildings")
    for index, path in enumerate(paths, 1):
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = path
        print(f"  {index:2d}. {relative}")

    while True:
        raw = input(f"Choose building 1-{len(paths)}: ").strip()
        try:
            index = int(raw)
        except ValueError:
            print("Enter the number shown beside the building.")
            continue
        if 1 <= index <= len(paths):
            return paths[index - 1]
        print(f"Choose a number from 1 to {len(paths)}.")


def load_building_metadata(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("format") != "gdmc_building_json":
        raise ValueError(f"{path.name}: not a gdmc_building_json file")

    size = data.get("size")
    if not isinstance(size, list) or len(size) != 3:
        raise ValueError(f"{path.name}: size must be [x, y, z]")
    try:
        normalized_size = [int(size[0]), int(size[1]), int(size[2])]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path.name}: size values must be whole numbers") from exc
    if any(value <= 0 for value in normalized_size):
        raise ValueError(f"{path.name}: all size values must be positive")
    data["size"] = normalized_size

    structure = data.get("structure")
    if not isinstance(structure, dict):
        structure = {}
    structure_file = (
        data.get("structure_file")
        or data.get("nbt_file")
        or structure.get("file")
    )
    if not structure_file:
        raise ValueError(f"{path.name}: no paired NBT filename was recorded")

    nbt_path = path.parent / str(structure_file)
    if not nbt_path.is_file():
        raise FileNotFoundError(
            f"Paired NBT file is missing:\n  JSON: {path}\n  NBT:  {nbt_path}"
        )

    data["_json_path"] = path
    data["_nbt_path"] = nbt_path
    data["_structure_entities"] = bool(
        data.get("structure_entities", structure.get("entities", False))
    )
    return data


# ---------------------------------------------------------------------------
# Rotation and villager metadata helpers
# ---------------------------------------------------------------------------


def rotate_local_xz(
    x: int,
    z: int,
    size_x: int,
    size_z: int,
    rotation: int,
) -> tuple[int, int]:
    """Match the settlement generator's non-negative clockwise rotation."""
    turns = (rotation // 90) % 4
    if turns == 0:
        return x, z
    if turns == 1:
        return size_z - 1 - z, x
    if turns == 2:
        return size_x - 1 - x, size_z - 1 - z
    return z, size_x - 1 - x


def rotate_direction(direction: str, rotation: int) -> str:
    direction = str(direction).strip().lower()
    if direction not in CARDINAL_DIRECTIONS:
        direction = "south"
    turns = (rotation // 90) % 4
    return CARDINAL_DIRECTIONS[
        (CARDINAL_DIRECTIONS.index(direction) + turns) % 4
    ]


def rotated_dimensions(size: Sequence[int], rotation: int) -> tuple[int, int, int]:
    size_x, size_y, size_z = map(int, size)
    if (rotation // 90) % 2:
        return size_z, size_y, size_x
    return size_x, size_y, size_z


def nbt_post_origin(
    destination_origin: tuple[int, int, int],
    size: Sequence[int],
    rotation: int,
) -> tuple[int, int, int]:
    """Translate the POST origin so the rotated structure starts at destination."""
    x0, y0, z0 = destination_origin
    size_x, _size_y, size_z = map(int, size)
    turns = (rotation // 90) % 4
    if turns == 0:
        return x0, y0, z0
    if turns == 1:
        return x0 + size_z - 1, y0, z0
    if turns == 2:
        return x0 + size_x - 1, y0, z0 + size_z - 1
    return x0, y0, z0 + size_x - 1


def villager_type_for_tribe(tribe: str) -> str:
    normalized = str(tribe).strip().lower().replace("-", "_").replace(" ", "_")
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


def villager_yaw_for_facing(facing: str) -> float:
    return {
        "south": 0.0,
        "west": 90.0,
        "north": 180.0,
        "east": -90.0,
    }.get(str(facing).lower(), 0.0)


def normalize_configured_villagers(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_villagers = data.get("villagers", data.get("villager_spawns", []))
    if raw_villagers is None:
        return []
    if not isinstance(raw_villagers, list):
        raise ValueError("villagers must be a JSON list")

    villagers: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_villagers, 1):
        if not isinstance(raw, dict) or not bool(raw.get("enabled", True)):
            continue

        local = raw.get("pos")
        if not isinstance(local, list) or len(local) != 3:
            print(f"WARNING: skipping villager #{index}: pos must be [x, y, z]")
            continue
        try:
            position = [int(local[0]), int(local[1]), int(local[2])]
        except (TypeError, ValueError):
            print(f"WARNING: skipping villager #{index}: invalid position")
            continue

        facing = str(raw.get("facing", "south")).strip().lower()
        if facing not in CARDINAL_DIRECTIONS:
            facing = "south"

        profession = str(raw.get("profession", "minecraft:none")).strip().lower()
        if not profession.startswith("minecraft:"):
            profession = "minecraft:" + profession

        try:
            level = max(1, min(5, int(raw.get("level", 2))))
        except (TypeError, ValueError):
            level = 2

        villagers.append(
            {
                "name": str(raw.get("name") or f"villager_{index}"),
                "custom_name": str(raw.get("custom_name") or ""),
                "custom_name_visible": bool(raw.get("custom_name_visible", True)),
                "pos": position,
                "facing": facing,
                "profession": profession,
                "level": level,
                "type": str(raw.get("type", "auto")).strip().lower(),
                "stationary": bool(raw.get("stationary", True)),
                "persistent": bool(raw.get("persistent", True)),
            }
        )

    return villagers


def configured_villager_snbt(
    tribe: str,
    villager: dict[str, Any],
    facing: str,
) -> str:
    profession = str(villager.get("profession", "minecraft:none")).strip().lower()
    if not profession.startswith("minecraft:"):
        profession = "minecraft:" + profession

    requested_type = str(villager.get("type", "auto")).strip().lower()
    if requested_type in {"", "auto", "automatic", "tribe"}:
        villager_type = villager_type_for_tribe(tribe)
    else:
        villager_type = (
            requested_type
            if requested_type.startswith("minecraft:")
            else "minecraft:" + requested_type
        )

    level = max(1, min(5, int(villager.get("level", 2))))
    yaw = villager_yaw_for_facing(facing)

    fields = [
        (
            'VillagerData:{profession:"%s",level:%d,type:"%s"}'
            % (profession, level, villager_type)
        ),
        f"Rotation:[{yaw:.1f}f,0.0f]",
    ]

    # Minecraft Java 1.21.5+ expects an inline SNBT text component.
    custom_name = str(villager.get("custom_name") or "").strip()
    if custom_name:
        name_value = json.dumps(custom_name, ensure_ascii=False)
        fields.append(f"CustomName:{{text:{name_value}}}")
        if bool(villager.get("custom_name_visible", True)):
            fields.append("CustomNameVisible:1b")

    if level >= 2:
        fields.append("Xp:10")
    if bool(villager.get("persistent", True)):
        fields.append("PersistenceRequired:1b")
    if bool(villager.get("stationary", True)):
        fields.extend(["NoAI:1b", "Motion:[0.0d,0.0d,0.0d]"])

    return "{" + ",".join(fields) + "}"


def build_villager_instructions(
    data: dict[str, Any],
    destination_origin: tuple[int, int, int],
    rotation: int,
) -> list[dict[str, Any]]:
    size_x, _size_y, size_z = map(int, data["size"])
    origin_x, origin_y, origin_z = destination_origin
    tribe = str(data.get("tribe") or data.get("biome") or "plains").strip().lower()
    villagers = normalize_configured_villagers(data)

    instructions: list[dict[str, Any]] = []
    for villager in villagers:
        lx, ly, lz = map(int, villager["pos"])
        rx, rz = rotate_local_xz(lx, lz, size_x, size_z, rotation)
        facing = rotate_direction(str(villager.get("facing", "south")), rotation)
        world_x = origin_x + rx + 0.5
        world_y = origin_y + ly
        world_z = origin_z + rz + 0.5

        instructions.append(
            {
                "id": "minecraft:villager",
                "x": world_x,
                "y": world_y,
                "z": world_z,
                "data": configured_villager_snbt(tribe, villager, facing),
                "_description": (
                    f"{villager.get('name', 'villager')} "
                    f"custom_name={villager.get('custom_name') or '(unnamed)'!r} "
                    f"at=({world_x:.1f}, {world_y:.1f}, {world_z:.1f}) "
                    f"facing={facing} profession={villager.get('profession')} "
                    f"type={villager_type_for_tribe(tribe)}"
                ),
            }
        )

    return instructions


# ---------------------------------------------------------------------------
# GDMC HTTP operations
# ---------------------------------------------------------------------------


def check_connection() -> None:
    try:
        response = requests.options(HOST + "/", timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not connect to GDMC HTTP Interface at {HOST}.\n"
            "Make sure Minecraft is running, a world is open, and the mod is installed."
        ) from exc


def place_nbt_structure(
    data: dict[str, Any],
    destination_origin: tuple[int, int, int],
    rotation: int,
    include_nbt_entities: bool,
    within_build_area: bool,
) -> None:
    nbt_path: Path = data["_nbt_path"]
    nbt_bytes = nbt_path.read_bytes()
    if not nbt_bytes:
        raise RuntimeError(f"NBT file is empty: {nbt_path}")

    post_x, post_y, post_z = nbt_post_origin(
        destination_origin,
        data["size"],
        rotation,
    )
    turns = (rotation // 90) % 4

    params = {
        "x": post_x,
        "y": post_y,
        "z": post_z,
        "rotate": turns,
        "pivotX": 0,
        "pivotZ": 0,
        "entities": str(include_nbt_entities).lower(),
        "keepLiquids": "true",
        "doBlockUpdates": "false",
        "spawnDrops": "false",
        "withinBuildArea": str(within_build_area).lower(),
        "dimension": DIMENSION,
    }
    headers = {"Content-Type": "application/octet-stream"}
    if nbt_bytes.startswith(b"\x1f\x8b"):
        headers["Content-Encoding"] = "gzip"

    response = requests.post(
        HOST + "/structure",
        params=params,
        data=nbt_bytes,
        headers=headers,
        timeout=NBT_REQUEST_TIMEOUT,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        print("GDMC returned an error while placing the NBT structure:")
        print(response.text)
        raise

    try:
        result = response.json()
    except ValueError:
        result = None
    if isinstance(result, dict) and int(result.get("status", 1)) == 0:
        raise RuntimeError(f"GDMC reported status=0: {result}")

    print(
        f"Placed {nbt_path.name} at final origin {destination_origin}, "
        f"rotation={rotation}°, embedded_entities={include_nbt_entities}."
    )


def spawn_configured_villagers(instructions: Sequence[dict[str, Any]]) -> int:
    if not instructions:
        return 0

    placed = 0
    params = {"x": 0, "y": 0, "z": 0, "dimension": DIMENSION}

    for start in range(0, len(instructions), ENTITY_BATCH_SIZE):
        batch = instructions[start : start + ENTITY_BATCH_SIZE]
        payload = [
            {key: value for key, value in entry.items() if not key.startswith("_")}
            for entry in batch
        ]
        response = requests.put(
            HOST + "/entities",
            params=params,
            json=payload,
            timeout=ENTITY_REQUEST_TIMEOUT,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError:
            print("GDMC returned an error while spawning configured villagers:")
            print(response.text)
            raise

        try:
            results = response.json()
        except ValueError:
            results = None

        if isinstance(results, list):
            for offset, result in enumerate(results):
                description = batch[offset].get("_description", "villager")
                if isinstance(result, dict) and int(result.get("status", 1)) == 0:
                    print(f"WARNING: villager may not have spawned: {description}")
                    print(f"         GDMC result: {result}")
                else:
                    placed += 1
                    print(f"  Spawned {description}")
        else:
            placed += len(batch)
            print(
                f"  Spawned villager batch of {len(batch)} "
                f"(response format: {type(results).__name__})"
            )

    return placed


def read_entities_in_box(
    origin: tuple[int, int, int],
    size: tuple[int, int, int],
) -> list[dict[str, Any]] | None:
    params = {
        "x": origin[0],
        "y": origin[1],
        "z": origin[2],
        "dx": size[0],
        "dy": size[1],
        "dz": size[2],
        "includeData": "true",
        "dimension": DIMENSION,
    }
    try:
        response = requests.get(
            HOST + "/entities",
            params=params,
            timeout=ENTITY_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
        return result if isinstance(result, list) else None
    except (requests.RequestException, ValueError):
        return None


def entity_id_from_response(entity: dict[str, Any]) -> str:
    entity_id = entity.get("id")
    if entity_id:
        return str(entity_id)
    data = str(entity.get("data", ""))
    match = re.search(r'(?:^|[,\{])id:\"?([a-z0-9_:.\-/]+)', data)
    return match.group(1) if match else "unknown"


def print_entity_preview(entities: Iterable[dict[str, Any]]) -> None:
    entities = list(entities)
    counts = Counter(entity_id_from_response(entity) for entity in entities)
    print("\nEntities currently detected inside the placed building box:")
    if not entities:
        print("  None")
        return
    print(f"  Total: {len(entities)}")
    for entity_id, count in sorted(counts.items()):
        print(f"  {entity_id}: {count}")

    villager_entries = [
        entity for entity in entities
        if entity_id_from_response(entity).endswith(":villager")
        or entity_id_from_response(entity) == "villager"
    ]
    if villager_entries:
        print("\nVillager data preview:")
        for index, entity in enumerate(villager_entries, 1):
            x = entity.get("x", "?")
            y = entity.get("y", "?")
            z = entity.get("z", "?")
            data = str(entity.get("data", ""))
            compact = " ".join(data.split())
            if len(compact) > 260:
                compact = compact[:257] + "..."
            print(f"  {index}. position=({x}, {y}, {z}) data={compact}")


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 76)
    print("GDMC EXPORTED BUILDING TEST PLACER — JSON + NBT + VILLAGERS")
    print("=" * 76)
    print(f"GDMC host: {HOST}")
    print(f"Building root: {BUILDINGS_ROOT}")

    try:
        paths = discover_building_json_files(BUILDINGS_ROOT)
        json_path = choose_building(paths, BUILDINGS_ROOT)
        data = load_building_metadata(json_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"\nCould not load an exported building: {exc}")
        sys.exit(1)

    size = tuple(map(int, data["size"]))
    nbt_path: Path = data["_nbt_path"]
    configured_villagers = normalize_configured_villagers(data)
    source = data.get("source") if isinstance(data.get("source"), dict) else {}

    print("\nSelected export")
    print(f"  Name: {data.get('name') or json_path.stem}")
    print(f"  Tribe: {data.get('tribe') or json_path.parent.name}")
    print(f"  JSON: {json_path}")
    print(f"  NBT: {nbt_path}")
    print(f"  Exported size: {size[0]} x {size[1]} x {size[2]}")
    print(f"  Original minimum corner: {source.get('min_corner', '(unknown)')}")
    print(f"  Configured JSON villagers: {len(configured_villagers)}")
    print(f"  NBT was exported with entities: {data['_structure_entities']}")
    entity_types_preview = data.get("entity_types_preview")
    if isinstance(entity_types_preview, dict) and entity_types_preview:
        print("  NBT entity preview:")
        for entity_id, count in sorted(entity_types_preview.items()):
            print(f"    {entity_id}: {count}")

    if configured_villagers:
        print("\nConfigured villager metadata")
        tribe = str(data.get("tribe") or json_path.parent.name)
        for index, villager in enumerate(configured_villagers, 1):
            print(
                f"  {index}. custom_name={villager.get('custom_name') or '(unnamed)'!r}, "
                f"local={villager['pos']}, facing={villager['facing']}, "
                f"profession={villager['profession']}, level={villager['level']}, "
                f"type={villager_type_for_tribe(tribe)}, "
                f"stationary={villager['stationary']}"
            )

    print(
        "\nDestination XYZ means the new location of the exported minimum "
        "selection corner (local [0, 0, 0])."
    )
    destination_origin = read_vec3("Destination origin XYZ: ")
    rotation = read_rotation()
    final_size = rotated_dimensions(size, rotation)

    print("\nPlanned test placement")
    print(f"  Final origin: {destination_origin}")
    print(f"  Rotation: {rotation}° clockwise")
    print(f"  Final box size: {final_size[0]} x {final_size[1]} x {final_size[2]}")
    print(
        f"  Final box: X {destination_origin[0]}.."
        f"{destination_origin[0] + final_size[0] - 1}, "
        f"Y {destination_origin[1]}.."
        f"{destination_origin[1] + final_size[1] - 1}, "
        f"Z {destination_origin[2]}.."
        f"{destination_origin[2] + final_size[2] - 1}"
    )

    place_structure = read_yes_no("Place the NBT building now?", default=True)
    within_build_area = True
    include_nbt_entities = False
    if place_structure:
        within_build_area = read_yes_no(
            "Require the whole structure to stay inside /buildarea?",
            default=True,
        )
        if data["_structure_entities"]:
            include_nbt_entities = read_yes_no(
                "Also place entities embedded in the NBT "
                "(item frames, paintings, animals, source villagers, etc.)?",
                default=True,
            )
        else:
            print("  This NBT was exported without embedded entities.")

    spawn_villagers = False
    if configured_villagers:
        spawn_villagers = read_yes_no(
            "Spawn the configured JSON villagers after placing the building?",
            default=True,
        )
    else:
        print("  This JSON contains no configured villagers to spawn.")

    if not place_structure and not spawn_villagers:
        print("\nNothing was selected. Exiting without changing the world.")
        return

    source_entity_types = data.get("entity_types_preview")
    source_villager_count = 0
    if isinstance(source_entity_types, dict):
        for entity_id, count in source_entity_types.items():
            normalized_id = str(entity_id).lower()
            if normalized_id == "villager" or normalized_id.endswith(":villager"):
                try:
                    source_villager_count += int(count)
                except (TypeError, ValueError):
                    source_villager_count += 1

    if include_nbt_entities and spawn_villagers and source_villager_count:
        print(
            f"\nWARNING: The NBT preview contains {source_villager_count} source "
            "villager(s). Spawning the configured JSON villagers will create "
            "additional villagers."
        )
        if not read_yes_no("Continue with both villager sources?", default=False):
            print("Cancelled before placement.")
            return

    if not read_yes_no("Proceed with this test?", default=True):
        print("Cancelled before placement.")
        return

    try:
        print("\nConnecting to Minecraft...")
        check_connection()

        if place_structure:
            print("\nPlacing NBT structure...")
            place_nbt_structure(
                data,
                destination_origin,
                rotation,
                include_nbt_entities,
                within_build_area,
            )

        instructions = build_villager_instructions(
            data,
            destination_origin,
            rotation,
        )
        if spawn_villagers:
            print("\nSpawning configured villagers...")
            spawned = spawn_configured_villagers(instructions)
            print(f"Configured villagers spawned: {spawned}/{len(instructions)}")

        entities = read_entities_in_box(destination_origin, final_size)
        if entities is None:
            print(
                "\nEntity verification request was unavailable. Inspect the "
                "building directly in Minecraft."
            )
        else:
            print_entity_preview(entities)

    except (OSError, RuntimeError, requests.RequestException) as exc:
        print(f"\nTest placement failed: {exc}")
        sys.exit(1)

    print("\nTest complete! Inspect the building and villagers in Minecraft.")
    print(
        "You may run this script again with 'Place the NBT building now? = no' "
        "to test only the configured villagers, but each run adds another copy."
    )


if __name__ == "__main__":
    main()
