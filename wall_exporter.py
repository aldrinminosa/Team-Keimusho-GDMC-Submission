"""
GDMC Wall Module JSON Exporter — Four-Direction Version

Exports modular wall pieces from a live Minecraft world through GDPC /
the GDMC HTTP Interface.

Supported module types:
    - main_gate
    - straight_wall
    - oblique_wall
    - tower_wall

Each module is exported once, but the JSON explicitly supports:
    - north
    - east
    - south
    - west

The wall generator should rotate the saved module at placement time.

Output:
    ~/Downloads/gdmc_main/builds/walls/<tribe>/<module_name>.json

Requirements:
    pip install gdpc

Minecraft must be running with the GDMC HTTP Interface enabled.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gdpc import Editor, Rect


# ============================================================
# Configuration
# ============================================================

HOST = "http://localhost:9000"

OUTPUT_ROOT = (
    Path.home()
    / "Downloads"
    / "gdmc_main"
    / "builds"
    / "walls"
)

AIR_BLOCKS = {
    "minecraft:air",
    "minecraft:cave_air",
    "minecraft:void_air",
}

MODULE_TYPES = {
    "1": "main_gate",
    "2": "straight_wall",
    "3": "oblique_wall",
    "4": "tower_wall",
    "main_gate": "main_gate",
    "straight_wall": "straight_wall",
    "oblique_wall": "oblique_wall",
    "tower_wall": "tower_wall",
}

CARDINAL_DIRECTIONS = [
    "north",
    "east",
    "south",
    "west",
]

VALID_DIRECTIONS = {
    "north",
    "east",
    "south",
    "west",
    "up",
    "down",
    "",
}

DEFAULT_CONNECTOR_COUNTS = {
    "main_gate": 2,
    "straight_wall": 2,
    "oblique_wall": 2,
    "tower_wall": 4,
}


# ============================================================
# Input helpers
# ============================================================

def read_vec3(
    prompt: str,
    allow_empty: bool = False,
) -> tuple[int, int, int] | None:
    """Read XYZ as 'x y z' or 'x,y,z'."""
    while True:
        raw = input(prompt).strip()

        if allow_empty and raw == "":
            return None

        parts = raw.replace(",", " ").split()

        if len(parts) != 3:
            print("Enter exactly three integers, for example: 120 64 -35")
            continue

        try:
            return tuple(map(int, parts))  # type: ignore[return-value]
        except ValueError:
            print("Coordinates must be whole numbers.")


def read_non_negative_int(
    prompt: str,
    default: int = 0,
) -> int:
    while True:
        raw = input(prompt).strip()

        if raw == "":
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


def read_positive_int(
    prompt: str,
    default: int = 1,
) -> int:
    while True:
        raw = input(prompt).strip()

        if raw == "":
            return default

        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue

        if value <= 0:
            print("The number must be greater than zero.")
            continue

        return value


def read_yes_no(
    prompt: str,
    default: bool = False,
) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "

    while True:
        raw = input(prompt + suffix).strip().lower()

        if raw == "":
            return default

        if raw in {"y", "yes"}:
            return True

        if raw in {"n", "no"}:
            return False

        print("Enter y or n.")


def read_direction(
    prompt: str,
    allow_blank: bool = True,
) -> str:
    while True:
        direction = input(prompt).strip().lower()

        if direction == "" and allow_blank:
            return ""

        if direction in VALID_DIRECTIONS:
            return direction

        print(
            "Use north, east, south, west, up, down"
            + (", or leave blank." if allow_blank else ".")
        )


def read_cardinal_direction(
    prompt: str,
    default: str = "north",
) -> str:
    while True:
        raw = input(prompt).strip().lower()

        if raw == "":
            return default

        if raw in CARDINAL_DIRECTIONS:
            return raw

        print("Use north, east, south, or west.")


def read_module_type() -> str:
    print("Module type:")
    print("  1. Main gate")
    print("  2. Straight wall")
    print("  3. Oblique wall")
    print("  4. Tower wall")

    while True:
        raw = input("Choose 1-4: ").strip().lower()
        module_type = MODULE_TYPES.get(raw)

        if module_type:
            return module_type

        print("Choose 1, 2, 3, or 4.")


def sanitize_name(name: str) -> str:
    safe = re.sub(
        r"[^a-z0-9_-]+",
        "_",
        name.strip().lower(),
    ).strip("_")

    if not safe:
        raise ValueError("The name cannot be empty.")

    return safe


# ============================================================
# Coordinate and rotation helpers
# ============================================================

def ordered_corners(
    corner_a: tuple[int, int, int],
    corner_b: tuple[int, int, int],
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    min_corner = (
        min(corner_a[0], corner_b[0]),
        min(corner_a[1], corner_b[1]),
        min(corner_a[2], corner_b[2]),
    )

    max_corner = (
        max(corner_a[0], corner_b[0]),
        max(corner_a[1], corner_b[1]),
        max(corner_a[2], corner_b[2]),
    )

    return min_corner, max_corner


def local_position(
    world_position: tuple[int, int, int],
    origin: tuple[int, int, int],
) -> list[int]:
    return [
        world_position[0] - origin[0],
        world_position[1] - origin[1],
        world_position[2] - origin[2],
    ]


def vector_subtract(
    end: list[int],
    start: list[int],
) -> list[int]:
    return [
        end[0] - start[0],
        end[1] - start[1],
        end[2] - start[2],
    ]


def point_inside_selection(
    point: tuple[int, int, int],
    min_corner: tuple[int, int, int],
    max_corner: tuple[int, int, int],
) -> bool:
    return (
        min_corner[0] <= point[0] <= max_corner[0]
        and min_corner[1] <= point[1] <= max_corner[1]
        and min_corner[2] <= point[2] <= max_corner[2]
    )


def rotation_needed(
    base_facing: str,
    target_facing: str,
) -> int:
    """
    Return clockwise Y rotation in degrees.

    Example when base_facing is north:
        north -> 0
        east  -> 90
        south -> 180
        west  -> 270
    """
    base_index = CARDINAL_DIRECTIONS.index(base_facing)
    target_index = CARDINAL_DIRECTIONS.index(target_facing)
    quarter_turns = (target_index - base_index) % 4
    return quarter_turns * 90


def build_orientation_map(
    base_facing: str,
) -> dict[str, dict[str, Any]]:
    """Create explicit metadata for all four possible facings."""
    return {
        direction: {
            "facing": direction,
            "rotation": rotation_needed(
                base_facing,
                direction,
            ),
        }
        for direction in CARDINAL_DIRECTIONS
    }


# ============================================================
# Connector and waypoint input
# ============================================================

def read_wall_connectors(
    module_type: str,
    origin: tuple[int, int, int],
) -> list[dict[str, Any]]:
    default_count = DEFAULT_CONNECTOR_COUNTS[module_type]

    print()
    print("Wall connectors are snap points used to join modules.")
    print(
        "Use the same seam convention and height for every wall module."
    )

    count = read_non_negative_int(
        f"Number of wall connectors [default: {default_count}]: ",
        default=default_count,
    )

    connectors: list[dict[str, Any]] = []
    tower_names = ["north", "east", "south", "west"]

    for index in range(count):
        print(f"\nWall connector {index + 1}")

        if count == 2:
            default_name = "start" if index == 0 else "end"
        elif count == 4 and index < 4:
            default_name = tower_names[index]
        else:
            default_name = f"connector_{index + 1}"

        name = (
            input(f"  Name [{default_name}]: ").strip()
            or default_name
        )

        world_pos = read_vec3(
            "  World XYZ of snap point: "
        )
        assert world_pos is not None

        direction = read_direction(
            "  Outward direction "
            "(north/east/south/west, optional): "
        )

        width = read_positive_int(
            "  Connection width [default: 1]: ",
            default=1,
        )

        connector: dict[str, Any] = {
            "name": name,
            "type": "wall",
            "pos": local_position(
                world_pos,
                origin,
            ),
            "source_world_pos": list(world_pos),
            "width": width,
        }

        if direction:
            connector["direction"] = direction

        connectors.append(connector)

    return connectors


def read_road_waypoints(
    module_type: str,
    origin: tuple[int, int, int],
) -> list[dict[str, Any]]:
    default_count = 1 if module_type == "main_gate" else 0

    print()
    print(
        "Road waypoints are used by settlement road generation."
    )
    print(
        "A main gate normally has one road waypoint in its passage."
    )

    count = read_non_negative_int(
        f"Number of road waypoints [default: {default_count}]: ",
        default=default_count,
    )

    waypoints: list[dict[str, Any]] = []

    for index in range(count):
        print(f"\nRoad waypoint {index + 1}")

        default_name = (
            "main_gate_road"
            if index == 0
            else f"road_waypoint_{index + 1}"
        )

        name = (
            input(f"  Name [{default_name}]: ").strip()
            or default_name
        )

        world_pos = read_vec3(
            "  World XYZ of road connection point: "
        )
        assert world_pos is not None

        direction = read_direction(
            "  Road-facing direction "
            "(north/east/south/west, optional): "
        )

        waypoint: dict[str, Any] = {
            "name": name,
            "type": "road",
            "pos": local_position(
                world_pos,
                origin,
            ),
            "source_world_pos": list(world_pos),
        }

        if direction:
            waypoint["direction"] = direction

        waypoints.append(waypoint)

    return waypoints


def choose_default_pivot(
    module_type: str,
    connectors: list[dict[str, Any]],
    min_corner: tuple[int, int, int],
    max_corner: tuple[int, int, int],
) -> tuple[int, int, int]:
    """
    Gate, straight, and oblique modules default to their first connector.
    Tower modules default to the center of the bottom footprint.
    """
    if (
        module_type != "tower_wall"
        and connectors
        and "source_world_pos" in connectors[0]
    ):
        source = connectors[0]["source_world_pos"]
        return (
            int(source[0]),
            int(source[1]),
            int(source[2]),
        )

    return (
        (min_corner[0] + max_corner[0]) // 2,
        min_corner[1],
        (min_corner[2] + max_corner[2]) // 2,
    )


# ============================================================
# Block export
# ============================================================

def block_to_json(
    block: Any,
    position: list[int],
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "pos": position,
        "id": block.id,
    }

    states = dict(block.states) if block.states else {}

    if states:
        entry["states"] = states

    if block.data:
        entry["data"] = block.data

    return entry


def export_wall_module(
    editor: Editor,
    tribe: str,
    module_name: str,
    module_type: str,
    base_facing: str,
    corner_a: tuple[int, int, int],
    corner_b: tuple[int, int, int],
    pivot_world: tuple[int, int, int],
    connectors: list[dict[str, Any]],
    waypoints: list[dict[str, Any]],
    include_air: bool,
    clear_metadata_markers: bool,
) -> Path:
    min_corner, max_corner = ordered_corners(
        corner_a,
        corner_b,
    )

    min_x, min_y, min_z = min_corner
    max_x, max_y, max_z = max_corner

    size_x = max_x - min_x + 1
    size_y = max_y - min_y + 1
    size_z = max_z - min_z + 1
    volume = size_x * size_y * size_z

    metadata_world_points: set[tuple[int, int, int]] = {
        pivot_world,
    }

    for metadata in [*connectors, *waypoints]:
        source = metadata.get("source_world_pos")

        if source and len(source) == 3:
            metadata_world_points.add(
                (
                    int(source[0]),
                    int(source[1]),
                    int(source[2]),
                )
            )

    print("\nExport selection")
    print(f"  Tribe: {tribe}")
    print(f"  Module: {module_name}")
    print(f"  Type: {module_type}")
    print(f"  Base facing: {base_facing}")
    print(f"  Minimum corner: {min_corner}")
    print(f"  Maximum corner: {max_corner}")
    print(f"  Size: {size_x} x {size_y} x {size_z}")
    print(f"  Rotation pivot: {pivot_world}")
    print(f"  Wall connectors: {len(connectors)}")
    print(f"  Road waypoints: {len(waypoints)}")
    print(f"  Total positions: {volume:,}")

    try:
        selection_rect = Rect(
            (min_x, min_z),
            (size_x, size_z),
        )
        editor.loadWorldSlice(
            selection_rect,
            cache=True,
        )
        print("  WorldSlice cache loaded.")
    except Exception as exc:
        print(f"  Warning: WorldSlice loading failed: {exc}")
        print("  Continuing with direct block reads.")

    blocks: list[dict[str, Any]] = []
    scanned = 0
    next_progress = 10

    for y in range(min_y, max_y + 1):
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                scanned += 1

                world_pos = (x, y, z)
                local_pos = [
                    x - min_x,
                    y - min_y,
                    z - min_z,
                ]

                if (
                    clear_metadata_markers
                    and world_pos in metadata_world_points
                ):
                    blocks.append(
                        {
                            "pos": local_pos,
                            "id": "minecraft:air",
                        }
                    )
                else:
                    block = editor.getBlockGlobal(world_pos)
                    block_id = block.id

                    if not block_id:
                        continue

                    if block_id == "minecraft:void_air":
                        continue

                    if (
                        not include_air
                        and block_id in AIR_BLOCKS
                    ):
                        continue

                    blocks.append(
                        block_to_json(
                            block,
                            local_pos,
                        )
                    )

                progress = int(
                    scanned * 100 / volume
                )

                if progress >= next_progress:
                    print(
                        f"  Progress: {progress}% "
                        f"({scanned:,}/{volume:,})"
                    )
                    next_progress += 10

    minecraft_version = None

    try:
        minecraft_version = editor.getMinecraftVersion()
    except Exception:
        pass

    module_axis = None

    if len(connectors) >= 2:
        module_axis = vector_subtract(
            connectors[1]["pos"],
            connectors[0]["pos"],
        )

    output: dict[str, Any] = {
        "format": "gdmc_wall_module_json",
        "format_version": 2,
        "name": module_name,
        "tribe": tribe,
        "module_type": module_type,
        "minecraft_version": minecraft_version,
        "exported_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "coordinate_system": {
            "origin": "minimum_selection_corner",
            "x_positive": "east",
            "y_positive": "up",
            "z_positive": "south",
            "rotation": "clockwise_around_y",
        },
        "size": [
            size_x,
            size_y,
            size_z,
        ],
        "source": {
            "min_corner": list(min_corner),
            "max_corner": list(max_corner),
            "inclusive": True,
        },
        "origin": [0, 0, 0],
        "pivot": local_position(
            pivot_world,
            min_corner,
        ),
        "base_facing": base_facing,
        "supported_facings": [
            "north",
            "east",
            "south",
            "west",
        ],
        "allowed_rotations": [
            0,
            90,
            180,
            270,
        ],
        "orientations": build_orientation_map(
            base_facing
        ),
        "connectors": connectors,
        "waypoints": waypoints,
        "module_axis": module_axis,
        "include_air": include_air,
        "block_count": len(blocks),
        "blocks": blocks,
    }

    tribe_folder = (
        OUTPUT_ROOT
        / sanitize_name(tribe)
    )

    tribe_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"{sanitize_name(module_name)}.json"
    )

    output_path = tribe_folder / filename

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return output_path


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("=" * 72)
    print("GDMC WALL MODULE JSON EXPORTER — FOUR DIRECTIONS")
    print("=" * 72)
    print(f"GDMC host: {HOST}")
    print(f"Output root: {OUTPUT_ROOT}")
    print()
    print("Export each module only once.")
    print(
        "The resulting JSON will support north, east, south, and west."
    )
    print()
    print("Coordinates are inclusive.")
    print("Format:")
    print("  120 64 -35")
    print("or:")
    print("  120,64,-35")
    print()

    tribe_raw = (
        input("Tribe name [plains]: ").strip()
        or "plains"
    )
    tribe = sanitize_name(tribe_raw)

    module_type = read_module_type()

    default_module_name = (
        f"{tribe}_{module_type}"
    )

    module_name_raw = (
        input(
            f"Module name [{default_module_name}]: "
        ).strip()
        or default_module_name
    )
    module_name = sanitize_name(module_name_raw)

    base_facing = read_cardinal_direction(
        "Direction the module currently faces in Minecraft "
        "[north]: ",
        default="north",
    )

    corner_a = read_vec3(
        "First corner XYZ: "
    )
    corner_b = read_vec3(
        "Opposite corner XYZ: "
    )

    assert corner_a is not None
    assert corner_b is not None

    min_corner, max_corner = ordered_corners(
        corner_a,
        corner_b,
    )

    connectors = read_wall_connectors(
        module_type,
        min_corner,
    )

    waypoints = read_road_waypoints(
        module_type,
        min_corner,
    )

    suggested_pivot = choose_default_pivot(
        module_type,
        connectors,
        min_corner,
        max_corner,
    )

    print()
    print(
        "The pivot is the point around which the module rotates."
    )
    print(
        f"Press Enter to use: {suggested_pivot}"
    )

    pivot_input = read_vec3(
        "Rotation pivot world XYZ: ",
        allow_empty=True,
    )

    pivot_world = (
        pivot_input
        if pivot_input is not None
        else suggested_pivot
    )

    if not point_inside_selection(
        pivot_world,
        min_corner,
        max_corner,
    ):
        print(
            "Warning: pivot is outside the selected volume. "
            "This is allowed, but may create large placement offsets."
        )

    include_air = read_yes_no(
        "\nInclude air blocks?\n"
        "Recommended for walls so terrain and trees are cleared.",
        default=True,
    )

    clear_metadata_markers = read_yes_no(
        "\nReplace connector, waypoint, and pivot marker blocks with air?\n"
        "Choose yes only if those coordinates contain temporary markers.",
        default=False,
    )

    print("\nFour-direction rotations that will be saved:")

    for facing, metadata in build_orientation_map(
        base_facing
    ).items():
        print(
            f"  {facing}: "
            f"{metadata['rotation']} degrees"
        )

    print("\nConnecting to Minecraft...")

    try:
        editor = Editor(
            host=HOST,
            buffering=False,
            caching=True,
            cacheLimit=65_536,
            retries=4,
            timeout=30,
        )
        editor.checkConnection()
    except Exception as exc:
        print("\nCould not connect to GDMC HTTP.")
        print(f"Reason: {exc}")
        print("\nCheck that:")
        print("  1. Minecraft is running.")
        print("  2. A world is open.")
        print("  3. GDMC HTTP Interface is installed.")
        print(f"  4. The interface is available at {HOST}.")
        sys.exit(1)

    try:
        output_path = export_wall_module(
            editor=editor,
            tribe=tribe,
            module_name=module_name,
            module_type=module_type,
            base_facing=base_facing,
            corner_a=corner_a,
            corner_b=corner_b,
            pivot_world=pivot_world,
            connectors=connectors,
            waypoints=waypoints,
            include_air=include_air,
            clear_metadata_markers=clear_metadata_markers,
        )
    except KeyboardInterrupt:
        print("\nExport cancelled.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nExport failed: {exc}")
        raise

    print("\nExport complete!")
    print(f"Saved to: {output_path}")
    print()
    print("The JSON supports:")
    print("  north")
    print("  east")
    print("  south")
    print("  west")
    print()
    print(
        "The future wall generator must rotate blocks, states, pivot, "
        "connectors, and road waypoints together."
    )
    print(
        "Oblique modules are rotated but not mirrored. "
        "A left and right diagonal may require separate JSON modules."
    )


if __name__ == "__main__":
    main()
