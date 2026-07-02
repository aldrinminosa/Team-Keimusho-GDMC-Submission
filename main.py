
"""
GDMC Multi-Tribe World Generator V37

World mode for large build areas such as 1000x1000:
- Scans the full build area in biome tiles instead of treating it as one tribe.
- Detects large connected Plains, Desert, Savanna, and Taiga regions.
- Selects one deep, high-purity site per available tribe by default.
- Generates each settlement inside an isolated local sub-area.
- Prevents buildings, roads, decorations, and wall supports from crossing into
  another tribe's biome.
- Uses the correct landmark, building folder, road style, wall library, banners,
  NBT structures, saved mobs, and configured villagers for every tribe.
- Forms and seals the complete settlement terrain before selecting or placing buildings.
- Fills ravines and shallow cave openings, smooths mountains, and preserves untouched trees.
- Caps each settlement at a safe number of repeatable buildings for performance.
- Continues to the next tribe if one selected settlement cannot be generated.
- Keeps every settlement wall contour connected, including across water.
- Drains enclosed water and fills road/wall subgrades with biome ground.
- Detects mountain mass inside each settlement, cuts it into broad grass-covered terraces,
  and generates buildings, roads, and walls from the regraded terrain.
- Gently terraces the complete settlement interior instead of deeply cutting each plot.
- Uses fill-first grass terrain, covers local holes/cave mouths, and preserves untouched trees.
- Places wall modules above terrain and fills supports instead of excavating hillsides.
- Reclaims water during terrain formation and packs every wall-over-water footprint to solid biome ground.
- Removes the complete logs-and-leaves structure of any natural tree damaged by terrain cuts.
- Removes complete trees intersecting building footprints and local structure-clearance margins.
- Clears every terrain-cut and building-clearance column upward to the build-area sky limit.
- Plans the final buildings first, then reforms only an organic settlement footprint.
- Removes trees as whole trunk-based components and assigns leaves to their nearest tree.
- Replants biome-matched saplings in verified open spaces after settlement completion and immediately attempts to grow them.
- Places wall contours 5-8 blocks from outer structures, inside the formed terrain.
- Prevents the fallback connector wall from becoming a second parallel wall beside modules.
- Locks every road branch to the exact saved Y level of both connected building waypoints.

Single-tribe mode remains available.

Requirements:
    pip install requests

In Minecraft first, select the complete large area:
    /buildarea set x1 y1 z1 x2 y2 z2

Generate all detected tribes:
    python main.py world

Generate only one tribe:
    python main.py plains
    python main.py desert
    python main.py savanna
    python main.py taiga
"""

from __future__ import annotations

import heapq
import json
import math
import os
import sys
import random
import statistics
import warnings
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# Hide the harmless RequestsDependencyWarning some Windows setups show.
warnings.filterwarnings("ignore", message="urllib3.*doesn.*match.*")
warnings.filterwarnings("ignore", message=".*chardet.*charset_normalizer.*")
warnings.filterwarnings("ignore", message=".*RequestsDependencyWarning.*")

import requests

HOST = "http://localhost:9000"
DIMENSION = "overworld"

# ------------------------------------------------------------
# Main settings you may edit quickly
# ------------------------------------------------------------

SEED = 20260605


# ============================================================
# MAIN SETTINGS
# Edit this section to control every tribe from one place.
# ============================================================
# Building rules:
# - building_total = None: the values in building_ratios are exact copy counts.
#   The default {"*": 1} therefore generates one copy of every normal type.
# - building_total = an integer: building_ratios become relative weights whose
#   final counts add up to that total. Positive types receive at least one copy
#   when the requested total is large enough.
# - Ratio keys may be a full filename, filename stem, exported asset name, or a
#   distinctive filename fragment. "*" is the fallback for unmatched types.
#
# Example for a 12-building Plains settlement:
#   "building_total": 12,
#   "building_ratios": {"house": 4, "farm": 2, "storage": 1, "*": 1},
#
# Wall patterns use the generated banner/light variants. Repeating
# ["banner", "light", "light"] displays one banner every three modules.
TRIBE_GENERATION_SETTINGS: Dict[str, Dict[str, Any]] = {
    "plains": {
        "building_total": None,
        "building_ratios": {"*": 1},
        "ensure_each_type": True,
        "building_spacing": 4,
        "compact_radius": 48,
        "maximum_radius": 72,
        "radius_step": 8,
        "cluster_link_distance": 22,
        "terrain_score_weight": 0.35,
        "nearest_building_weight": 11.0,
        "bounds_growth_weight": 0.20,
        "landmark_distance_weight": 0.55,
        "world_safety_cap": 48,
        "wall_building_clearance": 1,
        "straight_wall_pattern": ["banner", "light", "light"],
        "oblique_wall_pattern": ["light", "light", "light", "banner"],
    },
    "desert": {
        "building_total": None,
        "building_ratios": {"*": 1},
        "ensure_each_type": True,
        "building_spacing": 4,
        "compact_radius": 48,
        "maximum_radius": 72,
        "radius_step": 8,
        "cluster_link_distance": 22,
        "terrain_score_weight": 0.35,
        "nearest_building_weight": 11.0,
        "bounds_growth_weight": 0.20,
        "landmark_distance_weight": 0.55,
        "world_safety_cap": 48,
        "wall_building_clearance": 1,
        "straight_wall_pattern": ["banner", "light", "light"],
        "oblique_wall_pattern": ["light", "light", "light", "banner"],
    },
    "savanna": {
        "building_total": None,
        "building_ratios": {"*": 1},
        "ensure_each_type": True,
        "building_spacing": 4,
        "compact_radius": 48,
        "maximum_radius": 72,
        "radius_step": 8,
        "cluster_link_distance": 22,
        "terrain_score_weight": 0.35,
        "nearest_building_weight": 11.0,
        "bounds_growth_weight": 0.20,
        "landmark_distance_weight": 0.55,
        "world_safety_cap": 48,
        "wall_building_clearance": 1,
        "straight_wall_pattern": ["banner", "light", "light"],
        "oblique_wall_pattern": ["light", "light", "light", "banner"],
    },
    "taiga": {
        "building_total": None,
        "building_ratios": {"*": 1},
        "ensure_each_type": True,
        "building_spacing": 4,
        "compact_radius": 48,
        "maximum_radius": 72,
        "radius_step": 8,
        "cluster_link_distance": 22,
        "terrain_score_weight": 0.35,
        "nearest_building_weight": 11.0,
        "bounds_growth_weight": 0.20,
        "landmark_distance_weight": 0.55,
        "world_safety_cap": 48,
        "wall_building_clearance": 1,
        "straight_wall_pattern": ["banner", "light", "light"],
        # The current Taiga oblique export has no banner. The loader safely
        # substitutes its light variant for the unavailable banner entry.
        "oblique_wall_pattern": ["light", "light", "light", "banner"],
    },
}

# Legacy square-foundation settings are kept only because a few old helper
# functions still reference them. V11 places real rectangular JSON buildings.
HOUSE_COUNT = 10
HOUSE_SIZE_OPTIONS = [7, 8, 9, 10]
ALTAR_SIZE = 15

# ---------------------------------------------------------------------------
# Landmark placement
# ---------------------------------------------------------------------------

# This building is unique and becomes the settlement/road-network hub.
LANDMARK_FILENAME = "plains_gatheringhall.json"

# None means ask every run. At the prompt:
#   - enter X Z or X Y Z to request a location;
#   - press Enter to choose a terrain-aware random location.
# Set a tuple such as (-120, 240) to skip the prompt entirely.
LANDMARK_CENTER: Optional[Tuple[int, int]] = None
AUTO_CENTER_LANDMARK = True
LANDMARK_SEARCH_RADIUS_FROM_REQUEST = 24
RANDOM_LANDMARK_CANDIDATE_COUNT = 2500

# ---------------------------------------------------------------------------
# Automatic normal-building generation
# ---------------------------------------------------------------------------

# The generator discovers every gdmc_building_json file in BUILDINGS_DIR.
# LANDMARK_FILENAME is placed exactly once. Every other building type may be
# repeated automatically until no more valid non-overlapping plots can fit.
AUTO_FILL_BUILDINGS = True

# Keep enough empty area around the generated buildings for walls and towers.
# This limits only proximity to the /buildarea edge, not the number of buildings.
AUTO_BUILDING_EDGE_RESERVE = 26

# Larger values make counts between building types more even. There is no
# hardcoded ratio and no hardcoded total count.
AUTO_BUILDING_BALANCE_PENALTY = 36.0
AUTO_BUILDING_RANDOMNESS = 14.0

# V16 balanced generation: every placement round attempts each discovered
# building type once. Generation stops when a round can no longer place enough
# different types, preventing small markets/watchtowers from filling leftovers.
AUTO_BUILDING_MIN_ROUND_COVERAGE = 0.60
AUTO_BUILDING_CANDIDATE_SCAN_LIMIT = 5000
AUTO_BUILDING_FINAL_COUNT_SPREAD = 1

# 0 means unlimited. World mode sets a safe per-settlement cap so a 1000x1000
# task does not create hundreds of structures in one biome region.
AUTO_BUILDING_MAX_TOTAL = int(os.environ.get("GDMC_MAX_BUILDINGS_PER_SETTLEMENT", "0"))

# None means normal buildings may use the whole safe build area.
SETTLEMENT_BUILDING_RADIUS: Optional[float] = None

# JSON building library. The environment variable is convenient for testing;
# normally the default Downloads/gdmc_main/builds folder is used.
BUILDINGS_DIR = Path(
    os.environ.get(
        "GDMC_BUILDINGS_DIR",
        str(Path.home() / "Downloads" / "gdmc_main" / "builds"),
    )
)
BUILDING_SPACING = 6
BUILDING_MAX_FLATTEN = 5
RELAXED_BUILDING_MAX_FLATTEN = 8
BUILDING_CLEAR_EXTRA_HEIGHT = 3
ROAD_CONNECTION_GAP = 1

# V24 settlement terrain policy.
# Normal ground keeps the gentle fill-first behavior from V23. Mountain mass
# inside the settlement envelope is treated separately: it may be cut deeply
# into broad terraces, then capped with dirt + grass so exposed stone does not
# remain under or between buildings.
BUILDING_MAX_CUT_DOWN = max(
    0, int(os.environ.get("GDMC_BUILDING_MAX_CUT", "24"))
)
BUILDING_MAX_FILL_UP = max(
    1, int(os.environ.get("GDMC_BUILDING_MAX_FILL", "8"))
)

GENTLE_SETTLEMENT_TERRAIN = os.environ.get(
    "GDMC_GENTLE_SETTLEMENT_TERRAIN", "1"
).strip().lower() in {"1", "true", "yes"}
SETTLEMENT_TERRAIN_MARGIN = max(
    0, int(os.environ.get("GDMC_SETTLEMENT_TERRAIN_MARGIN", "5"))
)
SETTLEMENT_SMOOTH_RADIUS = max(
    2, int(os.environ.get("GDMC_SETTLEMENT_SMOOTH_RADIUS", "5"))
)
SETTLEMENT_BUILDING_BLEND_RADIUS = max(
    2, int(os.environ.get("GDMC_SETTLEMENT_BLEND_RADIUS", "8"))
)
SETTLEMENT_MAX_CUT_DOWN = max(
    0, int(os.environ.get("GDMC_SETTLEMENT_MAX_CUT", "1"))
)
SETTLEMENT_MAX_FILL_UP = max(
    1, int(os.environ.get("GDMC_SETTLEMENT_MAX_FILL", "3"))
)
SETTLEMENT_HOLE_DEPTH_TRIGGER = max(
    2, int(os.environ.get("GDMC_SETTLEMENT_HOLE_TRIGGER", "3"))
)
SETTLEMENT_HOLE_FILL_LIMIT = max(
    SETTLEMENT_MAX_FILL_UP,
    int(os.environ.get("GDMC_SETTLEMENT_HOLE_FILL_LIMIT", "10")),
)
SETTLEMENT_TREE_SPIKE_THRESHOLD = max(
    2, int(os.environ.get("GDMC_TREE_SPIKE_THRESHOLD", "3"))
)
SETTLEMENT_TREE_PROTECTION_RADIUS = max(
    0, int(os.environ.get("GDMC_TREE_PROTECTION_RADIUS", "2"))
)

# Mountain-only flattening. These cuts are intentionally much stronger than
# normal smoothing, but they are blended toward the settlement boundary so the
# result is a broad grassy terrace rather than a vertical square quarry.
FLATTEN_SETTLEMENT_MOUNTAINS = os.environ.get(
    "GDMC_FLATTEN_SETTLEMENT_MOUNTAINS", "1"
).strip().lower() in {"1", "true", "yes"}
MOUNTAIN_ABOVE_GRADE_TRIGGER = max(
    3, int(os.environ.get("GDMC_MOUNTAIN_ABOVE_GRADE", "5"))
)
MOUNTAIN_LOCAL_RELIEF_TRIGGER = max(
    4, int(os.environ.get("GDMC_MOUNTAIN_RELIEF", "7"))
)
MOUNTAIN_MAX_CUT_DOWN = max(
    MOUNTAIN_ABOVE_GRADE_TRIGGER,
    int(os.environ.get("GDMC_MOUNTAIN_MAX_CUT", "32")),
)
MOUNTAIN_BLEND_WIDTH = max(
    4, int(os.environ.get("GDMC_MOUNTAIN_BLEND_WIDTH", "12"))
)
MOUNTAIN_TERRACE_VARIATION = max(
    0, min(2, int(os.environ.get("GDMC_MOUNTAIN_TERRACE_VARIATION", "1")))
)
MOUNTAIN_PLOT_LEVEL_SPREAD = max(
    0, min(3, int(os.environ.get("GDMC_MOUNTAIN_PLOT_LEVEL_SPREAD", "1")))
)

# ---------------------------------------------------------------------------
# V26 terrain-first settlement formation
# ---------------------------------------------------------------------------

# Terrain is physically written to Minecraft before landmark/building selection.
# The heightmaps are then re-read so every later system sees the formed ground.
TERRAIN_FORM_FIRST = os.environ.get(
    "GDMC_TERRAIN_FORM_FIRST", "1"
).strip().lower() in {"1", "true", "yes"}

# World-mode settlements use almost their complete isolated local area. In
# single-tribe mode, this limits the shaped area around the requested center.
TERRAIN_FIRST_EDGE_INSET = max(
    4, int(os.environ.get("GDMC_TERRAIN_FIRST_EDGE_INSET", "6"))
)
TERRAIN_FIRST_MAX_HALF_SIZE = max(
    70, int(os.environ.get("GDMC_TERRAIN_FIRST_MAX_HALF_SIZE", "110"))
)
TERRAIN_FIRST_BLEND_WIDTH = max(
    6, int(os.environ.get("GDMC_TERRAIN_FIRST_BLEND_WIDTH", "14"))
)
TERRAIN_FIRST_SMOOTH_RADIUS = max(
    4, int(os.environ.get("GDMC_TERRAIN_FIRST_SMOOTH_RADIUS", "7"))
)

# Deep open terrain depressions are filled completely toward the shared grade.
# This is deliberately much larger than the old 10-block local-hole limit.
TERRAIN_FIRST_RAVINE_TRIGGER = max(
    3, int(os.environ.get("GDMC_TERRAIN_FIRST_RAVINE_TRIGGER", "4"))
)
TERRAIN_FIRST_MAX_FILL = max(
    16, int(os.environ.get("GDMC_TERRAIN_FIRST_MAX_FILL", "64"))
)
TERRAIN_FIRST_MAX_CUT = max(
    8, int(os.environ.get("GDMC_TERRAIN_FIRST_MAX_CUT", "36"))
)

# A solid biome-matched layer is written below the finished surface. This seals
# shallow cave mouths and guarantees that later roads/buildings are not above air.
TERRAIN_FIRST_SOLID_DEPTH = max(
    4, int(os.environ.get("GDMC_TERRAIN_FIRST_SOLID_DEPTH", "8"))
)
TERRAIN_FIRST_TERRACE_VARIATION = max(
    0, min(2, int(os.environ.get("GDMC_TERRAIN_FIRST_TERRACE_VARIATION", "1")))
)

# V27 water/tree cleanup. Every water column selected for terrain formation is
# reclaimed completely to at least its old water surface. If terrain cutting
# intersects a natural tree, the complete connected log structure and its leaf
# crown are removed rather than leaving floating or half-cut trees.
TERRAIN_FIRST_RECLAIM_WATER = os.environ.get(
    "GDMC_TERRAIN_FIRST_RECLAIM_WATER", "1"
).strip().lower() in {"1", "true", "yes"}
TERRAIN_FIRST_REMOVE_DAMAGED_TREES = os.environ.get(
    "GDMC_REMOVE_DAMAGED_TREES", "1"
).strip().lower() in {"1", "true", "yes"}
TERRAIN_DAMAGED_TREE_SCAN_RADIUS = max(
    6, int(os.environ.get("GDMC_DAMAGED_TREE_SCAN_RADIUS", "14"))
)
TERRAIN_DAMAGED_TREE_LEAF_RADIUS = max(
    4, int(os.environ.get("GDMC_DAMAGED_TREE_LEAF_RADIUS", "9"))
)
TERRAIN_DAMAGED_TREE_EXTRA_HEIGHT = max(
    16, int(os.environ.get("GDMC_DAMAGED_TREE_EXTRA_HEIGHT", "48"))
)
TERRAIN_DAMAGED_TREE_BLOCK_TILE = max(
    8, int(os.environ.get("GDMC_DAMAGED_TREE_BLOCK_TILE", "24"))
)

# V29 sky-clear policy. Lowered terrain columns and all building-clearance
# columns are cleared to the build-area sky limit. Tree-protected terrain that
# is not modified remains untouched.
TERRAIN_CLEAR_CUT_COLUMNS_TO_SKY = os.environ.get(
    "GDMC_TERRAIN_CLEAR_TO_SKY", "1"
).strip().lower() in {"1", "true", "yes"}
BUILDING_CLEAR_COLUMNS_TO_SKY = os.environ.get(
    "GDMC_BUILDING_CLEAR_TO_SKY", "1"
).strip().lower() in {"1", "true", "yes"}
TERRAIN_DAMAGED_TREE_IMPACT_RADIUS = max(
    1, int(os.environ.get("GDMC_DAMAGED_TREE_IMPACT_RADIUS", "2"))
)


# V30 post-terrain audit. After the physical terrain pass, the generator re-reads
# Minecraft, fixes any remaining depressions or high chunks, reinforces the
# subgrade, and performs a second damaged-tree scan beyond the settlement edge.
TERRAIN_POST_AUDIT_ENABLED = os.environ.get(
    "GDMC_POST_TERRAIN_AUDIT", "1"
).strip().lower() in {"1", "true", "yes"}
TERRAIN_POST_AUDIT_PASSES = max(
    1, min(3, int(os.environ.get("GDMC_POST_TERRAIN_AUDIT_PASSES", "2")))
)
TERRAIN_POST_SOLID_DEPTH = max(
    TERRAIN_FIRST_SOLID_DEPTH,
    int(os.environ.get("GDMC_POST_TERRAIN_SOLID_DEPTH", "16")),
)
TERRAIN_POST_CHUNK_TOLERANCE = max(
    0, int(os.environ.get("GDMC_POST_TERRAIN_CHUNK_TOLERANCE", "0"))
)
TERRAIN_POST_TREE_SCAN_MARGIN = max(
    TERRAIN_DAMAGED_TREE_SCAN_RADIUS,
    int(os.environ.get("GDMC_POST_TERRAIN_TREE_MARGIN", "20")),
)
TERRAIN_POST_TREE_TOUCH_RADIUS = max(
    TERRAIN_DAMAGED_TREE_IMPACT_RADIUS,
    int(os.environ.get("GDMC_POST_TERRAIN_TREE_TOUCH_RADIUS", "5")),
)
TERRAIN_POST_ORPHAN_LEAF_RADIUS = max(
    TERRAIN_DAMAGED_TREE_LEAF_RADIUS,
    int(os.environ.get("GDMC_POST_TERRAIN_ORPHAN_LEAF_RADIUS", "10")),
)


# V31 structure-aware final terrain lock. The early broad pass makes the biome
# region usable; after the actual buildings are selected, this second physical
# pass reshapes the real settlement envelope around their final Y levels. This
# prevents structures from being embedded in slopes and removes terrain islands
# caused by preserving individual tree columns during the early pass.
FINAL_TERRAIN_CONFORM_ENABLED = os.environ.get(
    "GDMC_FINAL_TERRAIN_CONFORM", "1"
).strip().lower() in {"1", "true", "yes"}
FINAL_TERRAIN_BUILDING_PAD_MARGIN = max(
    2, int(os.environ.get("GDMC_FINAL_BUILDING_PAD_MARGIN", "4"))
)
FINAL_TERRAIN_WALL_SAFE_MARGIN = max(
    8, int(os.environ.get("GDMC_FINAL_WALL_SAFE_MARGIN", "11"))
)
FINAL_TERRAIN_EDGE_BLEND = max(
    4, int(os.environ.get("GDMC_FINAL_TERRAIN_EDGE_BLEND", "8"))
)
FINAL_TERRAIN_SOLID_DEPTH = max(
    TERRAIN_POST_SOLID_DEPTH,
    int(os.environ.get("GDMC_FINAL_TERRAIN_SOLID_DEPTH", "16")),
)
FINAL_TERRAIN_TREE_TOUCH_RADIUS = max(
    2, int(os.environ.get("GDMC_FINAL_TERRAIN_TREE_TOUCH_RADIUS", "4"))
)
FINAL_TERRAIN_VERIFY_PASSES = max(
    1, min(3, int(os.environ.get("GDMC_FINAL_TERRAIN_VERIFY_PASSES", "2")))
)

# ---------------------------------------------------------------------------
# Modular settlement walls
# ---------------------------------------------------------------------------

GENERATE_WALLS = True
WALL_TRIBE = "plains"

# One JSON file containing all four wall modules.
# Create it with export_all_wall_modules_to_one_json.py.
WALL_LIBRARY_FILE = Path(
    os.environ.get(
        "GDMC_WALL_LIBRARY_FILE",
        str(
            Path.home()
            / "Downloads"
            / "gdmc_main"
            / "walls"
            / WALL_TRIBE
            / f"{WALL_TRIBE}_wall_library.json"
        ),
    )
)

# Every generated side uses one shared ground level. This prevents one module
# from inheriting a connector Y that makes the next module float or sink.
WALL_LEVEL_EACH_SIDE = True

# IMPORTANT FOR MODULAR WALLS:
# Exported air blocks can erase neighboring modules and the blocks supporting
# wall banners when modules touch or overlap. Terrain clearing is already done
# in prepare_wall_supports(), so wall placement skips JSON air entries.
WALL_SKIP_JSON_AIR_BLOCKS = True

# Place banners after all wall supports/structures with updates enabled.
# This makes wall banners attach to their support blocks while preserving NBT.
WALL_BANNER_DO_BLOCK_UPDATES = True

# Print transformed banner coordinates and fail loudly if the wall plan contains
# modules but no banner blocks survive filtering.
WALL_PRINT_BANNER_COORDINATES = True
WALL_WARN_IF_NO_BANNERS = True

# V29: keep the wall near the outer structures and inside the terrain-first
# plateau. The nearest visible wall block is constrained to a 5-8 block gap;
# the connector contour includes a small allowance for thick modules.
WALL_MIN_BUILDING_GAP = max(
    5,
    min(8, int(os.environ.get("GDMC_WALL_MIN_BUILDING_GAP", "6"))),
)
WALL_MODULE_INWARD_ALLOWANCE = max(
    1,
    min(3, int(os.environ.get("GDMC_WALL_OVERHANG_ALLOWANCE", "2"))),
)
WALL_PERIMETER_MARGIN = max(
    WALL_MIN_BUILDING_GAP + WALL_MODULE_INWARD_ALLOWANCE,
    int(os.environ.get("GDMC_WALL_MARGIN", "8")),
)

# The wall-side water test looks for actual water within this many blocks of
# the planned side. A river/water run disables that entire side.
WALL_WATER_AVOID_DISTANCE = 4
WALL_SIDE_MIN_WATER_RUN = 3
WALL_SIDE_WATER_RATIO_THRESHOLD = 0.05

# Exactly one gate is placed on every generated dry side. The random gate
# position is kept away from the corner towers.
WALL_GATE_MIN_FRACTION = 0.18
WALL_GATE_MAX_FRACTION = 0.82
WALL_GATE_POSITION_ATTEMPTS = 80

# Terrain and module-chain tolerances.
WALL_MAX_FLATTEN = 3
WALL_RELAXED_MAX_FLATTEN = 5
WALL_MAX_PERPENDICULAR_DRIFT = 3
WALL_MAX_MODULES_PER_CHAIN = 96
WALL_END_GAP_TOLERANCE = 3
WALL_ALLOWED_SEAM_OVERLAP_XZ = 8
WALL_BUILDING_CLEARANCE = max(0, WALL_MIN_BUILDING_GAP - 1)
WALL_TREE_CLEAR_HEIGHT = 18
WALL_TOWER_SEARCH_RADIUS = 4

# Straight pieces are preferred. Oblique pieces are used when their connector
# geometry or vertical change fits the terrain better.
WALL_OBLIQUE_PENALTY = 5.0

# V16 wall contour and terrain-following behavior.
WALL_MAX_SEAM_STEP = 1
WALL_SEAM_STEP_PENALTY = 18.0
WALL_SEAM_FILL_BLOCK = "minecraft:stone_bricks"
WALL_CONTOUR_DIAGONAL_MARGIN_SCALE = 1.41421356237
WALL_MIN_SEGMENT_LENGTH = 5
WALL_OUTWARD_FACING_PENALTY = 600.0
WALL_MAX_CONTOUR_TOWERS = 8

# V25 connected-wall and reclaimed-water policy. Modular assets are still used
# wherever they fit, while a biome-matched fallback base closes every accidental
# connector/end gap. Gate passage cells remain open.
WALL_FORCE_CONTINUOUS = os.environ.get(
    "GDMC_WALL_FORCE_CONTINUOUS", "1"
).strip().lower() in {"1", "true", "yes"}
# Treat contour points near an exported module as covered. This prevents the
# connector fallback from drawing a second parallel wall when the visible body
# of a module is offset slightly from its connector centerline.
WALL_FALLBACK_MODULE_COVER_RADIUS = max(
    1, int(os.environ.get("GDMC_WALL_FALLBACK_COVER_RADIUS", "4"))
)
WALL_FALLBACK_ATTACHMENT_RADIUS = max(
    WALL_FALLBACK_MODULE_COVER_RADIUS + 1,
    int(os.environ.get("GDMC_WALL_FALLBACK_ATTACH_RADIUS", "9")),
)
WALL_CONNECTION_FILL_HEIGHT = max(
    2, int(os.environ.get("GDMC_WALL_CONNECTION_HEIGHT", "3"))
)
WALL_FOUNDATION_DEPTH = max(
    2, int(os.environ.get("GDMC_WALL_FOUNDATION_DEPTH", "3"))
)
WALL_DRAIN_ENCLOSED_WATER = os.environ.get(
    "GDMC_WALL_DRAIN_WATER", "1"
).strip().lower() in {"1", "true", "yes"}

# Every non-bridge road gets a compact solid subgrade. This prevents roads from
# spanning cave mouths or shallow air pockets with visible air underneath.
ROAD_SUBGRADE_DEPTH = max(
    2, int(os.environ.get("GDMC_ROAD_SUBGRADE_DEPTH", "3"))
)

# There are currently only plains buildings, so keep road materials and lamps
# consistently plains even if the selected area touches another biome.
FORCE_ROAD_STYLE_GROUP: Optional[str] = "plains"
STRICT_PLAINS_BIOME = False

# V7: place doors one block outside the colored house foundation so they
# face the altar from the exterior half of the doorway.
PLACE_DOORS_OUTSIDE_FOUNDATION = True
DOOR_SUPPORT_BLOCK_USES_HOUSE_WOOL = True

# Higher = accepts rougher terrain and cuts/fills more.
ALTAR_MAX_FLATTEN = 5
HOUSE_MAX_FLATTEN = 5
ROAD_MAX_FLATTEN = 2

# Roads avoid cells whose height jumps above this from one path cell to the next.
ROAD_MAX_STEP_HEIGHT = 2
ROAD_WIDTH = 3
WATER_BUFFER = 4
# GDMC/Minecraft heightmaps can differ by 1 block even on normal land.
# Only classify as water when liquid surface is meaningfully above the floor.
WATER_HEIGHT_DIFF_THRESHOLD = 2
# Safety fallback: if almost the whole build area is detected as water, use a stricter threshold.
AUTO_FIX_FALSE_WATER_DETECTION = True

# Keep roads away from very high areas compared with the build area's normal height.
MOUNTAIN_ABOVE_MEDIAN_SOFT = 8
MOUNTAIN_ABOVE_MEDIAN_HARD = 16

# If the first house pass cannot find enough houses, the script relaxes plot flatness a little.
RELAX_IF_NEEDED = True
RELAXED_HOUSE_MAX_FLATTEN = 7

# Set True if you want only wool/doors/foundation and no roads.
DISABLE_ROADS = False

# Performance / safety.
BATCH_SIZE = 2500
WITHIN_BUILD_AREA = True
WITHIN_BUILD_AREA_READS = False
DO_BLOCK_UPDATES = True
CLEAR_AIR_ABOVE_FOUNDATIONS = 6
CLEAR_AIR_ABOVE_ROADS = 4
HEIGHTMAP_TYPE = "MOTION_BLOCKING_NO_PLANTS"

# Tree clearing. V9 IMPORTANT:
# Do NOT clear the whole rectangle between all plots. That creates a huge empty patch.
# Instead, clear only a small local margin around each altar/house foundation, plus a narrow road corridor.
CLEAR_TREES_IN_SETTLEMENT_BOUNDS = False
SETTLEMENT_TREE_CLEAR_MARGIN = 0      # unused when CLEAR_TREES_IN_SETTLEMENT_BOUNDS is False
TREE_CLEAR_MARGIN_AROUND_HOUSES = 1   # only immediate structure clearance
TREE_CLEAR_MARGIN_AROUND_ALTAR = 2    # preserve nearby untouched trees

# V28 building/tree and waypoint-road fixes.
BUILDING_TREE_CLEAR_MARGIN = max(
    TREE_CLEAR_MARGIN_AROUND_HOUSES,
    int(os.environ.get("GDMC_BUILDING_TREE_CLEAR_MARGIN", "4")),
)
LANDMARK_TREE_CLEAR_MARGIN = max(
    TREE_CLEAR_MARGIN_AROUND_ALTAR,
    int(os.environ.get("GDMC_LANDMARK_TREE_CLEAR_MARGIN", "5")),
)
ROAD_LOCK_TO_WAYPOINT_Y = os.environ.get(
    "GDMC_ROAD_LOCK_TO_WAYPOINT_Y", "1"
).strip().lower() in {"1", "true", "yes"}
TREE_CLEAR_HEIGHT = 24
CLEAR_TREES_AROUND_ROADS = True
ROAD_TREE_CLEAR_MARGIN = 1            # narrow corridor only; avoids removing large forest areas

# Road decorations and lighting.
LAMP_MIN_SPACING = 9
LAMP_MAX_SPACING = 13
DECORATION_STEP = 2
# V8: keep side decorations close to the road edge instead of drifting far away.
# For 3-wide roads this means decorations are usually 2 blocks from center:
# [deco] [road edge] [road center] [road edge] [deco]
DECORATION_SIDE_OFFSET = 1
# How far from the ideal side position we may search if the exact side block is occupied.
DECORATION_EXTRA_SEARCH = 1
# Decorations/lamps are only accepted when the terrain can be flattened to road level
# without looking like a pillar or a hole.
DECO_MAX_FLATTEN_DIFF_FROM_ROAD = 2
FLATTEN_DECO_SPOTS_TO_ROAD_LEVEL = True
USE_SOUL_LANTERNS_IN_SNOW = True

# V3 visual/path fixes.
# Bigger patch size means road block mixtures look like natural worn patches instead of a checkerboard.
ROAD_PATCH_SIZE = 11
# V7: material assignment uses grown clusters.
# This keeps your requested ratios exactly, but avoids checkerboard/square patch roads.
FILL_DIAGONAL_ROAD_HOLES = False
PRINT_ROAD_BLOCK_RATIO_STATS = True
# Use iron bars as lamp hangers because some GDMC/Minecraft versions do not visually connect chain -> lantern reliably.
USE_IRON_BARS_FOR_LAMP_HANGERS = True
MIN_LAMP_DISTANCE_BETWEEN_POSTS = 8
LAMP_SKIP_START_BLOCKS = 6
LAMP_SKIP_END_BLOCKS = 4
# Avoid ridge tops / rough cells. If too few roads generate, raise RIDGE_LOCAL_RELIEF_HARD by 1-2.
RIDGE_LOCAL_RELIEF_SOFT = 3
RIDGE_LOCAL_RELIEF_HARD = 7
# Water is allowed only as a bridge path, with a high pathfinding penalty.
BRIDGE_OVER_WATER = True
BRIDGE_SUPPORT_INTERVAL = 5
BRIDGE_RAILS = True
# V4/V5: scan actual water blocks near sea level so we do not mistake ocean for land.
SEA_SURFACE_BLOCK_Y = 62
USE_EXACT_SEA_LEVEL_WATER_SCAN = True
WATER_SCAN_RADIUS_Y = 4
WATER_SCAN_TILE_SIZE = 96
# Keep bridge decks visually at sea level instead of rising with smoothed road height.
BRIDGE_DECK_AT_SEA_LEVEL = True
# Higher = A* only crosses water when it really needs a bridge.
WATER_PATH_PENALTY = 140.0

Pos2D = Tuple[int, int]
Dir2D = Tuple[int, int]
Rect = Tuple[int, int, int, int]

WATER_BIOME_KEYWORDS = ("ocean", "river")
WATER_BLOCK_IDS = {
    "minecraft:water",
    "minecraft:kelp",
    "minecraft:kelp_plant",
    "minecraft:seagrass",
    "minecraft:tall_seagrass",
    "minecraft:bubble_column",
}


# ------------------------------------------------------------
# GDMC HTTP helpers
# ------------------------------------------------------------

def http_get(path: str, params: Optional[dict] = None):
    url = f"{HOST}{path}"
    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(
            "Could not connect to GDMC HTTP at localhost:9000.\n"
            "Make sure Minecraft is open, your world is loaded, and GDMC HTTP Interface is installed."
        ) from e
    except requests.HTTPError as e:
        print("GDMC HTTP error:")
        print(r.text)
        raise e


def put_blocks(blocks: List[dict], do_block_updates: Optional[bool] = None) -> None:
    if not blocks:
        print("No blocks to place.")
        return

    if do_block_updates is None:
        do_block_updates = DO_BLOCK_UPDATES

    params = {
        "x": 0,
        "y": 0,
        "z": 0,
        "dimension": DIMENSION,
        "withinBuildArea": str(WITHIN_BUILD_AREA).lower(),
        "doBlockUpdates": str(do_block_updates).lower(),
        "spawnDrops": "false",
    }

    for i in range(0, len(blocks), BATCH_SIZE):
        chunk = blocks[i:i + BATCH_SIZE]
        r = requests.put(f"{HOST}/blocks", params=params, json=chunk, timeout=90)
        try:
            r.raise_for_status()
        except requests.HTTPError:
            print("GDMC returned an error while placing blocks:")
            print(r.text)
            raise
        print(f"Placed {min(i + BATCH_SIZE, len(blocks))}/{len(blocks)} blocks")


def b(block_id: str, x: int, y: int, z: int,
      state: Optional[dict] = None, data: Optional[str] = None) -> dict:
    if not block_id.startswith("minecraft:"):
        block_id = "minecraft:" + block_id
    obj = {"id": block_id, "x": int(x), "y": int(y), "z": int(z)}
    if state:
        obj["state"] = {str(k): str(v) for k, v in state.items()}
    if data:
        obj["data"] = data
    return obj


def get_build_area() -> dict:
    ba = http_get("/buildarea")
    raw_x1, raw_x2 = sorted((int(ba["xFrom"]), int(ba["xTo"])))
    raw_y1, raw_y2 = sorted((int(ba["yFrom"]), int(ba["yTo"])))
    raw_z1, raw_z2 = sorted((int(ba["zFrom"]), int(ba["zTo"])))

    # In many GDMC setups, the upper x/z behaves like an exclusive edge for area reads.
    x2 = raw_x2 - 1 if raw_x2 > raw_x1 else raw_x2
    z2 = raw_z2 - 1 if raw_z2 > raw_z1 else raw_z2

    area = {
        "x1": raw_x1,
        "x2": x2,
        "y1": raw_y1,
        "y2": raw_y2,
        "z1": raw_z1,
        "z2": z2,
    }
    print(f"Build area safe bounds: x {area['x1']}..{area['x2']}, z {area['z1']}..{area['z2']}")
    return area


def in_build_area_xz(ba: dict, x: int, z: int, margin: int = 0) -> bool:
    return (ba["x1"] + margin <= x <= ba["x2"] - margin and
            ba["z1"] + margin <= z <= ba["z2"] - margin)


def in_build_area_xyz(ba: dict, x: int, y: int, z: int) -> bool:
    return (ba["x1"] <= x <= ba["x2"] and
            ba["y1"] <= y <= ba["y2"] and
            ba["z1"] <= z <= ba["z2"])


def get_height_lookup(min_x: int, max_x: int, min_z: int, max_z: int,
                      heightmap_type: str = HEIGHTMAP_TYPE) -> Dict[Pos2D, int]:
    dx = max_x - min_x + 1
    dz = max_z - min_z + 1
    params = {
        "x": min_x,
        "z": min_z,
        "dx": dx,
        "dz": dz,
        "type": heightmap_type,
        "dimension": DIMENSION,
        "withinBuildArea": str(WITHIN_BUILD_AREA_READS).lower(),
    }
    hm = http_get("/heightmap", params=params)
    heights: Dict[Pos2D, int] = {}

    if len(hm) == dx and len(hm[0]) == dz:
        for ix in range(dx):
            for iz in range(dz):
                heights[(min_x + ix, min_z + iz)] = int(hm[ix][iz])
    elif len(hm) == dz and len(hm[0]) == dx:
        for iz in range(dz):
            for ix in range(dx):
                heights[(min_x + ix, min_z + iz)] = int(hm[iz][ix])
    else:
        raise ValueError(f"Unexpected heightmap size: got {len(hm)}x{len(hm[0])}, expected {dx}x{dz}")
    return heights


def get_biome_lookup(min_x: int, max_x: int, min_z: int, max_z: int, y: int) -> Dict[Pos2D, str]:
    dx = max_x - min_x + 1
    dz = max_z - min_z + 1
    params = {
        "x": min_x,
        "y": y,
        "z": min_z,
        "dx": dx,
        "dy": 1,
        "dz": dz,
        "dimension": DIMENSION,
        "withinBuildArea": str(WITHIN_BUILD_AREA_READS).lower(),
    }
    data = http_get("/biomes", params=params)
    lookup: Dict[Pos2D, str] = {}
    for entry in data:
        lookup[(int(entry["x"]), int(entry["z"]))] = entry.get("id", "minecraft:plains")
    return lookup



# ------------------------------------------------------------
# Landmark coordinate input
# ------------------------------------------------------------

def prompt_landmark_center(ba: dict) -> Optional[Pos2D]:
    """Return a requested XZ coordinate, or None for random placement."""
    if LANDMARK_CENTER is not None:
        x, z = LANDMARK_CENTER
        print(f"Using configured landmark center XZ: ({x}, {z})")
        return int(x), int(z)

    required_margin = 12

    while True:
        raw = input(
            "Landmark coordinate (X Z or X Y Z; blank = random valid location): "
        ).strip()
        if not raw:
            print("No landmark coordinate entered: choosing a random valid location.")
            return None

        parts = raw.replace(",", " ").split()
        if len(parts) not in (2, 3):
            print("Enter X Z or X Y Z, for example: 120 -45 or 120 70 -45")
            continue
        try:
            values = [int(v) for v in parts]
        except ValueError:
            print("Coordinates must be whole numbers.")
            continue

        if len(values) == 2:
            x, z = values
        else:
            x, _ignored_y, z = values
            print("Y was accepted as a reference; ground height is detected automatically.")

        if not in_build_area_xz(ba, x, z, margin=required_margin):
            print(
                f"That point is too close to/outside the build-area edge. "
                f"Safe X is {ba['x1'] + required_margin}..{ba['x2'] - required_margin}; "
                f"safe Z is {ba['z1'] + required_margin}..{ba['z2'] - required_margin}."
            )
            continue
        return x, z


def road_style_group_at(pos: Pos2D, biome_lookup: Dict[Pos2D, str]) -> str:
    if FORCE_ROAD_STYLE_GROUP:
        return FORCE_ROAD_STYLE_GROUP
    return biome_to_group(biome_lookup.get(pos, "minecraft:plains"))


# ------------------------------------------------------------
# Biome road styles
# ------------------------------------------------------------

@dataclass
class RoadStyle:
    road_blocks: List[Tuple[str, float]]
    decorations: List[Tuple[str, float]]


STYLES: Dict[str, RoadStyle] = {
    "desert": RoadStyle(
        road_blocks=[
            ("minecraft:dirt_path", 0.60),
            ("minecraft:birch_planks", 0.40),
        ],
        decorations=[
            ("air", 0.40),
            ("cactus", 0.10),
            ("campfire", 0.10),
            ("birch_fence", 0.10),
            ("decorated_pot", 0.10),
            ("potted_cactus", 0.10),
            ("lamp_post", 0.10),
        ],
    ),
    "plains": RoadStyle(
        road_blocks=[
            ("minecraft:dirt_path", 0.60),
            ("minecraft:coarse_dirt", 0.40),
        ],
        decorations=[
            ("air", 0.30),
            ("oak_fence", 0.15),
            ("oak_leaves", 0.10),
            ("mossy_cobblestone", 0.15),
            ("mossy_cobblestone_slab", 0.10),
            ("cobblestone_slab", 0.10),
            ("lamp_post", 0.10),
        ],
    ),
    "savanna": RoadStyle(
        road_blocks=[
            ("minecraft:coarse_dirt", 0.60),
            ("minecraft:packed_mud", 0.40),
        ],
        decorations=[
            ("air", 0.40),
            ("acacia_leaves", 0.10),
            ("campfire", 0.10),
            ("red_sandstone", 0.10),
            ("red_sandstone_slab", 0.10),
            ("acacia_fence", 0.10),
            ("lamp_post", 0.10),
        ],
    ),
    "snow": RoadStyle(
        road_blocks=[
            ("minecraft:cobblestone", 0.70),
            ("minecraft:gravel", 0.30),
        ],
        decorations=[
            ("air", 0.40),
            ("oak_leaves", 0.10),
            ("oak_fence", 0.10),
            ("soul_campfire", 0.10),
            # Interpreted as 0.05 each so the snow roads do not become almost all stone.
            ("stone_bricks", 0.05),
            ("stone_brick_slab", 0.05),
            ("mossy_stone_bricks", 0.05),
            ("mossy_stone_brick_slab", 0.05),
            ("lamp_post", 0.10),
        ],
    ),
    "taiga": RoadStyle(
        road_blocks=[
            ("minecraft:coarse_dirt", 0.60),
            ("minecraft:podzol", 0.40),
        ],
        decorations=[
            ("air", 0.50),
            ("campfire", 0.10),
            ("spruce_slab", 0.10),
            ("spruce_log_horizontal", 0.10),
            ("jack_o_lantern", 0.10),
            ("lamp_post", 0.10),
        ],
    ),
}


BIOME_GROUP_KEYWORDS = {
    "desert": ["desert", "badlands", "eroded_badlands", "wooded_badlands"],
    "savanna": ["savanna", "savanna_plateau", "windswept_savanna"],
    "snow": ["snowy", "ice_spikes", "frozen", "grove", "jagged_peaks", "frozen_peaks"],
    "taiga": ["taiga", "old_growth_pine", "old_growth_spruce"],
    "plains": [
        "plains", "sunflower_plains", "meadow", "forest", "birch_forest", "flower_forest",
        "dark_forest", "cherry_grove", "windswept_forest", "windswept_hills", "stony_peaks",
    ],
}


def biome_to_group(biome_id: str) -> str:
    name = biome_id.replace("minecraft:", "")
    for group, keywords in BIOME_GROUP_KEYWORDS.items():
        if any(k in name for k in keywords):
            return group
    return "plains"


# ------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------

def sign(n: int) -> int:
    return (n > 0) - (n < 0)


def stable_rng(seed: int, x: int, z: int, salt: int = 0) -> random.Random:
    h = (x * 73428767) ^ (z * 912931) ^ (seed * 19349663) ^ (salt * 83492791)
    return random.Random(h)


def weighted_choice(items: List[Tuple[str, float]], rng: random.Random) -> str:
    total = sum(max(0.0, w) for _, w in items)
    if total <= 0:
        return items[0][0]
    r = rng.random() * total
    acc = 0.0
    for name, weight in items:
        acc += max(0.0, weight)
        if r <= acc:
            return name
    return items[-1][0]


def road_block_for(group: str, x: int, z: int, seed: int) -> str:
    """Fallback road material choice.

    V5 normally assigns road materials globally inside assign_road_materials()
    so the final road follows your 0.6/0.4, 0.7/0.3, etc. ratios much better.
    This fallback is still kept for safety and uses patch-level choices, never
    per-block random noise, so it will not create a checkerboard.
    """
    style = STYLES.get(group, STYLES["plains"])
    options = style.road_blocks
    if len(options) <= 1:
        return options[0][0]
    patch_x = math.floor(x / ROAD_PATCH_SIZE)
    patch_z = math.floor(z / ROAD_PATCH_SIZE)
    rng = stable_rng(seed, patch_x, patch_z, 77)
    return weighted_choice(options, rng)


def organic_material_score(x: int, z: int, seed: int, group_salt: int) -> float:
    """Low-frequency score for natural road wear.

    Sorting cells by this score gives connected-looking streaks/blobs instead of
    alternating per-block noise. The final counts are still selected to match the
    specified ratios, e.g. 60/40 or 70/30.
    """
    rng = stable_rng(seed, group_salt, 0, 240)
    p1 = rng.random() * math.tau
    p2 = rng.random() * math.tau
    p3 = rng.random() * math.tau
    # Three smooth waves at different angles. These are intentionally low
    # frequency so the secondary block appears as road-wear patches, not a grid.
    return (
        0.55 * math.sin(x * 0.17 + z * 0.09 + p1) +
        0.35 * math.sin(x * -0.06 + z * 0.19 + p2) +
        0.10 * math.sin((x + z) * 0.31 + p3)
    )


def grow_cluster_selection(cells: List[Pos2D], target_count: int, seed: int, salt: int) -> Set[Pos2D]:
    """Select exactly target_count cells as connected-looking clusters.

    This is for road material distribution: it avoids checkerboard noise, but it
    still follows ratios such as 60/40 or 70/30 almost exactly.
    """
    if target_count <= 0:
        return set()
    if target_count >= len(cells):
        return set(cells)

    cell_set = set(cells)
    selected: Set[Pos2D] = set()
    rng = random.Random(seed + salt * 1000003 + len(cells) * 9176)
    cells_sorted = sorted(cells)

    # More seeds = more small natural worn patches; fewer seeds = one giant blob.
    seed_count = max(1, min(target_count, target_count // 18 + 1))
    seed_points = rng.sample(cells_sorted, min(seed_count, len(cells_sorted)))
    frontier: List[Tuple[float, Pos2D]] = []

    def add_seed(pt: Pos2D) -> None:
        if pt in selected:
            return
        selected.add(pt)
        x, z = pt
        for dx, dz in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            nb = (x + dx, z + dz)
            if nb in cell_set and nb not in selected:
                # Low-frequency score keeps clusters somewhat elongated along roads.
                score = rng.random() + 0.25 * abs(math.sin((x + z + salt) * 0.21))
                heapq.heappush(frontier, (score, nb))

    for sp in seed_points:
        if len(selected) >= target_count:
            break
        add_seed(sp)

    while len(selected) < target_count:
        if not frontier:
            remaining = [c for c in cells_sorted if c not in selected]
            if not remaining:
                break
            add_seed(rng.choice(remaining))
            continue
        _score, pt = heapq.heappop(frontier)
        if pt in selected:
            continue
        add_seed(pt)

    # Exact rounding guard.
    if len(selected) > target_count:
        selected = set(sorted(selected)[:target_count])
    elif len(selected) < target_count:
        for pt in cells_sorted:
            if len(selected) >= target_count:
                break
            selected.add(pt)
    return selected


def assign_road_materials(
    road_cells: "OrderedDict[Pos2D, Tuple[int, str, bool]]",
    seed: int,
) -> Dict[Pos2D, str]:
    """Assign road blocks while preserving each tribe's requested ratio.

    V7 rule:
    - all road cells are filled, never decoration air;
    - block counts follow the style ratios exactly after rounding;
    - secondary materials grow as connected worn patches, not checkerboard noise.
    """
    materials: Dict[Pos2D, str] = {}
    group_cells: Dict[str, List[Pos2D]] = {}

    for pos, (_y, group, is_bridge) in road_cells.items():
        if is_bridge:
            continue
        group_cells.setdefault(group, []).append(pos)

    for group, cells in group_cells.items():
        style = STYLES.get(group, STYLES["plains"])
        options = [(bid, max(0.0, weight)) for bid, weight in style.road_blocks if weight > 0]
        if not options:
            continue
        if len(options) == 1:
            for p in cells:
                materials[p] = options[0][0]
            continue

        total_weight = sum(w for _, w in options)
        if total_weight <= 0:
            for p in cells:
                materials[p] = options[0][0]
            continue

        desired_counts = [int(round(len(cells) * w / total_weight)) for _, w in options]
        desired_counts[0] += len(cells) - sum(desired_counts)

        primary = options[0][0]
        for p in cells:
            materials[p] = primary

        available = set(cells)
        group_salt = sum(ord(ch) for ch in group)
        for opt_index, (block_id, _weight) in enumerate(options[1:], start=1):
            count = max(0, min(desired_counts[opt_index], len(available)))
            chosen = grow_cluster_selection(sorted(available), count, seed, group_salt + opt_index * 97)
            for pnt in chosen:
                materials[pnt] = block_id
            available -= chosen

        if PRINT_ROAD_BLOCK_RATIO_STATS:
            counts = Counter(materials[p] for p in cells if p in materials)
            targets = {bid: desired_counts[i] for i, (bid, _w) in enumerate(options)}
            print(f"Road material ratio for {group}: {dict(counts)} target={targets}")

    return materials

def manhattan(a: Pos2D, c: Pos2D) -> int:
    return abs(a[0] - c[0]) + abs(a[1] - c[1])


def euclid(a: Pos2D, c: Pos2D) -> float:
    return math.sqrt((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2)


def rect_for_center(center: Pos2D, size: int) -> Rect:
    cx, cz = center
    x0 = cx - size // 2
    z0 = cz - size // 2
    return x0, z0, x0 + size - 1, z0 + size - 1


def rect_for_center_dimensions(center: Pos2D, width: int, depth: int) -> Rect:
    """Create an inclusive X/Z rectangle for rectangular JSON buildings."""
    cx, cz = center
    x0 = cx - width // 2
    z0 = cz - depth // 2
    return x0, z0, x0 + width - 1, z0 + depth - 1


def rect_cells(rect: Rect) -> Iterable[Pos2D]:
    x0, z0, x1, z1 = rect
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            yield x, z


def rect_with_margin(rect: Rect, margin: int) -> Rect:
    x0, z0, x1, z1 = rect
    return x0 - margin, z0 - margin, x1 + margin, z1 + margin


def rects_overlap(a: Rect, c: Rect, margin: int = 0) -> bool:
    ax0, az0, ax1, az1 = rect_with_margin(a, margin)
    cx0, cz0, cx1, cz1 = c
    return not (ax1 < cx0 or cx1 < ax0 or az1 < cz0 or cz1 < az0)


def rect_inside_build_area(rect: Rect, ba: dict, margin: int = 0) -> bool:
    x0, z0, x1, z1 = rect_with_margin(rect, margin)
    return (ba["x1"] <= x0 <= ba["x2"] and ba["x1"] <= x1 <= ba["x2"] and
            ba["z1"] <= z0 <= ba["z2"] and ba["z1"] <= z1 <= ba["z2"])


def direction_to_facing(dx: int, dz: int) -> str:
    if abs(dx) >= abs(dz):
        return "east" if dx > 0 else "west"
    return "south" if dz > 0 else "north"


def facing_to_vec(facing: str) -> Dir2D:
    return {
        "north": (0, -1),
        "south": (0, 1),
        "west": (-1, 0),
        "east": (1, 0),
    }[facing]


def normalized_dir(a: Pos2D, c: Pos2D) -> Dir2D:
    return sign(c[0] - a[0]), sign(c[1] - a[1])


def local_direction(path: List[Pos2D], i: int) -> Dir2D:
    if len(path) == 1:
        return (1, 0)
    if i == 0:
        return normalized_dir(path[i], path[i + 1])
    if i == len(path) - 1:
        return normalized_dir(path[i - 1], path[i])
    return normalized_dir(path[i - 1], path[i + 1])


def road_offsets(direction: Dir2D, width: int = ROAD_WIDTH) -> List[Pos2D]:
    """Return the road footprint around a path center.

    V6 uses clean strips instead of big filled squares. Big square footprints made
    curves and diagonal roads look like checkered plazas. A normal road remains a
    3-wide strip; only sharp turn cells get a compact 5-wide corner pad.
    """
    dx, dz = direction
    if dx == 0 and dz == 0:
        dx = 1
    half = width // 2

    # For diagonal directions, choose the visually dominant cardinal normal.
    # This creates a connected stair-step road without 5x5 blobs.
    if dx != 0 and dz != 0:
        if abs(dx) >= abs(dz):
            nx, nz = 0, 1
        else:
            nx, nz = 1, 0
    else:
        nx, nz = -dz, dx

    return [(nx * k, nz * k) for k in range(-half, half + 1)]

def road_width_for_path(path: List[Pos2D], i: int) -> int:
    """Use 3-wide roads normally and 5-wide only at sharp corner cells.

    Earlier versions made all diagonal sections 5-wide, which looked too bulky
    and produced checkered-looking road blobs. This keeps the road closer to the
    small test designs: mostly 3 blocks wide, with only small 5-block corner pads.
    """
    if len(path) < 3:
        return ROAD_WIDTH
    if 0 < i < len(path) - 1:
        before = normalized_dir(path[i - 1], path[i])
        after = normalized_dir(path[i], path[i + 1])
        if before != after:
            return 5
    return ROAD_WIDTH

def side_vectors(direction: Dir2D) -> Tuple[Dir2D, Dir2D]:
    dx, dz = direction
    if dx == 0 and dz == 0:
        dx = 1
    left = (-dz, dx)
    right = (dz, -dx)
    return left, right


def facing_from_dir(direction: Dir2D) -> str:
    dx, dz = direction
    if abs(dx) >= abs(dz):
        return "east" if dx >= 0 else "west"
    return "south" if dz >= 0 else "north"


def axis_from_dir(direction: Dir2D) -> str:
    dx, dz = direction
    return "x" if abs(dx) >= abs(dz) else "z"


def slab_state(kind: str = "bottom") -> dict:
    return {"type": kind, "waterlogged": "false"}


def leaves_state() -> dict:
    return {"persistent": "true", "distance": "1"}


def trapdoor_bottom_state(facing: str = "north") -> dict:
    # Bottom-half trapdoors sit flush with bottom slabs/crossbars.
    return {"facing": facing, "half": "bottom", "open": "false", "waterlogged": "false"}


def trapdoor_top_state(facing: str = "north") -> dict:
    return {"facing": facing, "half": "top", "open": "false", "waterlogged": "false"}


def trapdoor_side_state(facing: str) -> dict:
    return {"facing": facing, "half": "bottom", "open": "true", "waterlogged": "false"}


def chain_state() -> dict:
    return {"axis": "y", "waterlogged": "false"}


def iron_bars_state() -> dict:
    # Defaults keep the bar as a clean vertical-looking hanger unless it touches another connectable block.
    return {"waterlogged": "false"}


def add_vertical_hanger(blocks: List[dict], x: int, y: int, z: int) -> None:
    if USE_IRON_BARS_FOR_LAMP_HANGERS:
        blocks.append(b("iron_bars", x, y, z, iron_bars_state()))
    else:
        blocks.append(b("chain", x, y, z, chain_state()))


def hanging_lantern_state() -> dict:
    return {"hanging": "true", "waterlogged": "false"}


def dominant_cardinal(direction: Dir2D) -> Dir2D:
    dx, dz = direction
    if abs(dx) >= abs(dz):
        return (sign(dx) or 1, 0)
    return (0, sign(dz) or 1)


def crossbar_vectors_parallel_to_road(road_dir: Dir2D) -> Tuple[Dir2D, Dir2D]:
    fwd = dominant_cardinal(road_dir)
    return fwd, (-fwd[0], -fwd[1])


def add_crossbar_with_chains(blocks: List[dict], x: int, top_y: int, z: int,
                             road_dir: Dir2D, center_block: str,
                             side_block: str, left_chain: int, right_chain: int,
                             lantern_id: str = "lantern",
                             center_state: Optional[dict] = None,
                             side_state: Optional[dict] = None) -> None:
    forward, backward = crossbar_vectors_parallel_to_road(road_dir)
    axis = axis_from_dir(forward)

    if center_state is None and ("log" in center_block or "wood" in center_block):
        center_state = {"axis": axis}
    if center_state is None and "slab" in center_block:
        center_state = slab_state()

    blocks.append(b(center_block, x, top_y, z, center_state))

    for vec, chain_len in [(forward, left_chain), (backward, right_chain)]:
        sx, sz = x + vec[0], z + vec[1]
        this_side_state = side_state
        if this_side_state is None and "slab" in side_block:
            this_side_state = slab_state()
        elif this_side_state is None and "trapdoor" in side_block:
            this_side_state = trapdoor_bottom_state(facing_from_dir(vec))
        elif this_side_state is not None and "trapdoor" in side_block:
            this_side_state = dict(this_side_state)
            this_side_state["facing"] = facing_from_dir(vec)

        blocks.append(b(side_block, sx, top_y, sz, this_side_state))
        for j in range(chain_len):
            add_vertical_hanger(blocks, sx, top_y - 1 - j, sz)
        blocks.append(b(lantern_id, sx, top_y - 1 - chain_len, sz, hanging_lantern_state()))


def add_wrapped_log_fences(blocks: List[dict], x: int, y: int, z: int, fence_id: str) -> None:
    for ox, oz in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        blocks.append(b(fence_id, x + ox, y, z + oz))


def add_wrapped_log_trapdoors(blocks: List[dict], x: int, y: int, z: int, trapdoor_id: str) -> None:
    blocks.append(b(trapdoor_id, x + 1, y, z, trapdoor_side_state("west")))
    blocks.append(b(trapdoor_id, x - 1, y, z, trapdoor_side_state("east")))
    blocks.append(b(trapdoor_id, x, y, z + 1, trapdoor_side_state("north")))
    blocks.append(b(trapdoor_id, x, y, z - 1, trapdoor_side_state("south")))


def add_lamp_post(blocks: List[dict], group: str, x: int, y: int, z: int, road_dir: Dir2D) -> None:
    group = group.lower()

    if group == "desert":
        pole = ["sandstone_wall", "sandstone_wall", "birch_fence", "birch_fence", "birch_fence"]
        for i, block_id in enumerate(pole):
            blocks.append(b(block_id, x, y + i, z))
        add_crossbar_with_chains(
            blocks, x, y + len(pole), z, road_dir,
            center_block="sandstone_slab", side_block="birch_trapdoor",
            left_chain=1, right_chain=2, lantern_id="lantern",
            center_state=slab_state(), side_state=trapdoor_bottom_state(),
        )

    elif group == "plains":
        pole = ["stone_brick_wall", "oak_fence", "oak_fence", "oak_fence", "oak_fence"]
        for i, block_id in enumerate(pole):
            blocks.append(b(block_id, x, y + i, z))
        add_crossbar_with_chains(
            blocks, x, y + len(pole), z, road_dir,
            center_block="oak_slab", side_block="spruce_trapdoor",
            left_chain=1, right_chain=2, lantern_id="lantern",
            center_state=slab_state(), side_state=trapdoor_bottom_state(),
        )

    elif group == "savanna":
        blocks.append(b("acacia_log", x, y, z, {"axis": "y"}))
        add_wrapped_log_fences(blocks, x, y, z, "acacia_fence")
        pole = ["acacia_fence", "acacia_fence", "acacia_fence", "red_sandstone_wall"]
        for i, block_id in enumerate(pole, start=1):
            blocks.append(b(block_id, x, y + i, z))
        add_crossbar_with_chains(
            blocks, x, y + 1 + len(pole), z, road_dir,
            center_block="red_sandstone", side_block="acacia_trapdoor",
            left_chain=1, right_chain=1, lantern_id="lantern",
            side_state=trapdoor_bottom_state(),
        )

    elif group == "snow":
        lantern = "soul_lantern" if USE_SOUL_LANTERNS_IN_SNOW else "lantern"
        pole = ["oak_log", "stone_brick_wall", "oak_fence", "oak_fence", "stone_brick_wall"]
        for i, block_id in enumerate(pole):
            state = {"axis": "y"} if block_id == "oak_log" else None
            blocks.append(b(block_id, x, y + i, z, state))

        top_y = y + len(pole)
        forward, backward = crossbar_vectors_parallel_to_road(road_dir)
        axis = axis_from_dir(forward)

        # V7 snow top fix:
        # - center oak log is always horizontal along the road/crossbar axis;
        # - top trapdoor uses half=bottom in the block above, so it sits on the log
        #   instead of floating high above it;
        # - front/back trapdoors are added as side panels on the log.
        blocks.append(b("oak_log", x, top_y, z, {"axis": axis}))
        blocks.append(b("oak_trapdoor", x, top_y + 1, z, trapdoor_bottom_state(facing_from_dir(forward))))

        for vec in [forward, backward]:
            sx, sz = x + vec[0], z + vec[1]
            blocks.append(b("oak_trapdoor", sx, top_y, sz, trapdoor_bottom_state(facing_from_dir(vec))))
            for j in range(2):
                add_vertical_hanger(blocks, sx, top_y - 1 - j, sz)
            blocks.append(b(lantern, sx, top_y - 3, sz, hanging_lantern_state()))

        # Trapdoors on the front/back sides of the top oak log.
        side_a, side_b = side_vectors(forward)
        for side in [side_a, side_b]:
            sx, sz = x + side[0], z + side[1]
            # Face back toward the log, same logic as wrapped trapdoors.
            blocks.append(b("oak_trapdoor", sx, top_y, sz, trapdoor_side_state(facing_from_dir((-side[0], -side[1])))))


    elif group == "taiga":
        blocks.append(b("spruce_log", x, y, z, {"axis": "y"}))
        add_wrapped_log_trapdoors(blocks, x, y, z, "spruce_trapdoor")
        pole = ["nether_brick_wall", "spruce_fence", "spruce_fence", "spruce_fence"]
        for i, block_id in enumerate(pole, start=1):
            blocks.append(b(block_id, x, y + i, z))
        add_crossbar_with_chains(
            blocks, x, y + 1 + len(pole), z, road_dir,
            center_block="stripped_spruce_log", side_block="spruce_slab",
            left_chain=1, right_chain=2, lantern_id="lantern",
            center_state={"axis": axis_from_dir(crossbar_vectors_parallel_to_road(road_dir)[0])},
            side_state=slab_state(),
        )

    else:
        add_lamp_post(blocks, "plains", x, y, z, road_dir)


def add_decoration(blocks: List[dict], group: str, deco: str,
                   x: int, y: int, z: int, road_dir: Dir2D, seed: int) -> None:
    if deco in ("air", "nothing"):
        return

    rng = stable_rng(seed, x, z, 33)
    facing = facing_from_dir(road_dir)

    if deco == "lamp_post":
        add_lamp_post(blocks, group, x, y, z, road_dir)
    elif deco == "cactus":
        blocks.append(b("sand", x, y - 1, z))
        blocks.append(b("cactus", x, y, z))
    elif deco == "campfire":
        blocks.append(b("campfire", x, y, z, {"facing": facing, "lit": "true", "signal_fire": "false", "waterlogged": "false"}))
    elif deco == "soul_campfire":
        blocks.append(b("soul_campfire", x, y, z, {"facing": facing, "lit": "true", "signal_fire": "false", "waterlogged": "false"}))
    elif deco == "birch_fence":
        blocks.append(b("birch_fence", x, y, z))
    elif deco == "oak_fence":
        blocks.append(b("oak_fence", x, y, z))
    elif deco == "acacia_fence":
        blocks.append(b("acacia_fence", x, y, z))
    elif deco == "decorated_pot":
        blocks.append(b("decorated_pot", x, y, z))
    elif deco == "potted_cactus":
        blocks.append(b("potted_cactus", x, y, z))
    elif deco == "oak_leaves":
        blocks.append(b("oak_leaves", x, y, z, leaves_state()))
    elif deco == "acacia_leaves":
        blocks.append(b("acacia_leaves", x, y, z, leaves_state()))
    elif deco == "mossy_cobblestone":
        blocks.append(b("mossy_cobblestone", x, y, z))
    elif deco == "mossy_cobblestone_slab":
        blocks.append(b("mossy_cobblestone_slab", x, y, z, slab_state()))
    elif deco == "cobblestone_slab":
        blocks.append(b("cobblestone_slab", x, y, z, slab_state()))
    elif deco == "red_sandstone":
        blocks.append(b("red_sandstone", x, y, z))
    elif deco == "red_sandstone_slab":
        blocks.append(b("red_sandstone_slab", x, y, z, slab_state()))
    elif deco == "stone_bricks":
        blocks.append(b("stone_bricks", x, y, z))
    elif deco == "stone_brick_slab":
        blocks.append(b("stone_brick_slab", x, y, z, slab_state()))
    elif deco == "mossy_stone_bricks":
        blocks.append(b("mossy_stone_bricks", x, y, z))
    elif deco == "mossy_stone_brick_slab":
        blocks.append(b("mossy_stone_brick_slab", x, y, z, slab_state()))
    elif deco == "spruce_slab":
        blocks.append(b("spruce_slab", x, y, z, slab_state()))
    elif deco == "spruce_log_horizontal":
        axis = "x" if rng.random() < 0.5 else "z"
        blocks.append(b("spruce_log", x, y, z, {"axis": axis}))
    elif deco == "jack_o_lantern":
        blocks.append(b("jack_o_lantern", x, y, z, {"facing": facing}))
    else:
        print(f"Warning: unknown decoration '{deco}'")


# ------------------------------------------------------------
# Terrain / water
# ------------------------------------------------------------

def is_water_biome(biome_id: str) -> bool:
    b_id = (biome_id or "").lower()
    return any(word in b_id for word in WATER_BIOME_KEYWORDS)


def is_water_cell(pos: Pos2D, surface_heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
                  threshold: int = WATER_HEIGHT_DIFF_THRESHOLD,
                  biome_lookup: Optional[Dict[Pos2D, str]] = None) -> bool:
    # MOTION_BLOCKING includes liquid surface, while OCEAN_FLOOR ignores liquid.
    # Heightmap differences alone are unreliable near beaches, so V4 combines:
    #   1) ocean/river biome hints,
    #   2) normal heightmap difference,
    #   3) a sea-level heuristic,
    #   4) optional exact block scan added in build_water_sets().
    if pos not in surface_heights or pos not in floor_heights:
        return True

    surface_top = surface_heights[pos] - 1
    floor_top = floor_heights[pos] - 1
    diff = surface_heights[pos] - floor_heights[pos]

    if biome_lookup is not None and is_water_biome(biome_lookup.get(pos, "")):
        # Mark ocean/river biome at sea-level-ish height as unsafe for plots.
        # This prevents altars/houses from being selected on top of ocean.
        if surface_top <= SEA_SURFACE_BLOCK_Y + 2:
            return True

    if diff >= threshold:
        return True

    # Normal ocean/rivers are at sea level. If the surface is sea-level and the
    # floor is below it, this is almost certainly water even when heightmaps disagree.
    if floor_top < surface_top and surface_top <= SEA_SURFACE_BLOCK_Y + 1:
        return True

    return False


def get_exact_sea_level_water_cells(ba: dict) -> Set[Pos2D]:
    """Read actual water/kelp/seagrass blocks near sea level using GET /blocks.

    This is slower than heightmaps, but it is much more reliable for oceans and
    prevents the generator from flattening roads/foundations over water.
    It scans only 2-3 horizontal layers, tiled to avoid huge HTTP responses.
    """
    if not USE_EXACT_SEA_LEVEL_WATER_SCAN:
        return set()

    ys = range(SEA_SURFACE_BLOCK_Y - WATER_SCAN_RADIUS_Y, SEA_SURFACE_BLOCK_Y + WATER_SCAN_RADIUS_Y + 1)
    found: Set[Pos2D] = set()
    tile = max(16, WATER_SCAN_TILE_SIZE)

    for y in ys:
        for x0 in range(ba["x1"], ba["x2"] + 1, tile):
            x1 = min(ba["x2"], x0 + tile - 1)
            for z0 in range(ba["z1"], ba["z2"] + 1, tile):
                z1 = min(ba["z2"], z0 + tile - 1)
                params = {
                    "x": x0,
                    "y": y,
                    "z": z0,
                    "dx": x1 - x0 + 1,
                    "dy": 1,
                    "dz": z1 - z0 + 1,
                    "dimension": DIMENSION,
                    "withinBuildArea": str(WITHIN_BUILD_AREA_READS).lower(),
                }
                try:
                    data = http_get("/blocks", params=params)
                except Exception as e:
                    print(f"Exact water scan failed at y={y}, x={x0}..{x1}, z={z0}..{z1}: {e}")
                    print("Continuing with heightmap/biome water detection only.")
                    return found

                for entry in data:
                    if entry.get("id") in WATER_BLOCK_IDS:
                        found.add((int(entry["x"]), int(entry["z"])))

    return found


def build_water_sets(surface_heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
                     ba: dict, buffer: int = WATER_BUFFER,
                     biome_lookup: Optional[Dict[Pos2D, str]] = None) -> Tuple[Set[Pos2D], Set[Pos2D]]:
    def make_water(threshold: int) -> Set[Pos2D]:
        return {pos for pos in surface_heights
                if is_water_cell(pos, surface_heights, floor_heights, threshold, biome_lookup)}

    threshold = WATER_HEIGHT_DIFF_THRESHOLD
    water = make_water(threshold)

    exact_water = get_exact_sea_level_water_cells(ba)
    if exact_water:
        print(f"Exact sea-level water scan found {len(exact_water)} cells.")
        water |= exact_water

    total = max(1, len(surface_heights))
    if AUTO_FIX_FALSE_WATER_DETECTION and len(water) / total > 0.85 and not exact_water:
        # Only use this fallback when exact water scanning is unavailable.
        # With exact scan enabled, a high water ratio can be a real ocean build area.
        for stricter in (3, 4, 5):
            test = make_water(stricter)
            if len(test) / total < 0.35:
                print(
                    f"Water detection looked too high ({len(water)}/{total}). "
                    f"Using stricter water threshold {stricter}."
                )
                water = test
                threshold = stricter
                break
        else:
            print(
                f"Warning: {len(water)}/{total} cells still look like water. "
                "This build area may be mostly ocean/river, or heightmaps may be unusual."
            )

    blocked = set(water)
    if buffer > 0:
        for x, z in list(water):
            for ox in range(-buffer, buffer + 1):
                for oz in range(-buffer, buffer + 1):
                    if abs(ox) + abs(oz) <= buffer:
                        px, pz = x + ox, z + oz
                        if in_build_area_xz(ba, px, pz, margin=1):
                            blocked.add((px, pz))
    return water, blocked


def surface_top_y(pos: Pos2D, heights: Dict[Pos2D, int], overrides: Optional[Dict[Pos2D, int]] = None) -> int:
    # Heightmap gives the first free y above the terrain. Surface top block is height - 1.
    if overrides and pos in overrides:
        return overrides[pos]
    return heights.get(pos, 65) - 1


# ------------------------------------------------------------
# Plot model and plot search
# ------------------------------------------------------------

@dataclass
class BuildingAsset:
    name: str
    path: Path
    size_x: int
    size_y: int
    size_z: int
    blocks: List[dict]
    waypoints: List[dict]
    include_air: bool
    tribe: str
    villager_spawns: List[dict]
    nbt_path: Optional[Path] = None
    structure_entities: bool = False


@dataclass
class Plot:
    kind: str
    size: int
    center: Pos2D
    rect: Rect
    target_top_y: int
    wool: str
    door_pos: Optional[Pos2D] = None
    door_facing: Optional[str] = None
    door_front: Optional[Pos2D] = None

    # V10 JSON-building fields. They stay None for the altar/legacy plots.
    asset: Optional[BuildingAsset] = None
    rotation: int = 0
    origin: Optional[Tuple[int, int, int]] = None
    entrance_world: Optional[Tuple[int, int, int]] = None
    rotated_width: Optional[int] = None
    rotated_depth: Optional[int] = None


@dataclass
class RoadPath:
    """One X/Z road branch with exact endpoint surface elevations."""
    cells: List[Pos2D]
    start_y: int
    end_y: int
    start_name: str = "landmark_waypoint"
    end_name: str = "building_waypoint"


HOUSE_WOOL = {
    7: "orange_wool",
    8: "red_wool",
    9: "blue_wool",
    10: "green_wool",
}



CARDINAL_DIRECTIONS = ["north", "east", "south", "west"]
AIR_IDS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


def load_building_asset(path: Path) -> BuildingAsset:
    """Load a legacy JSON building or a preferred JSON+NBT pair."""
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("format") != "gdmc_building_json":
        raise ValueError(f"{path.name}: unsupported or missing format")

    size = data.get("size")
    if not isinstance(size, list) or len(size) != 3:
        raise ValueError(f"{path.name}: size must be [x, y, z]")

    waypoints = list(data.get("waypoints") or [])
    if not waypoints:
        raise ValueError(f"{path.name}: contains no road waypoint")

    blocks = list(data.get("blocks") or [])

    # V19 paired-asset metadata. Both the simple top-level form and a nested
    # structure object are accepted so future exporters remain compatible.
    structure_meta = data.get("structure")
    if not isinstance(structure_meta, dict):
        structure_meta = {}
    structure_file = (
        data.get("structure_file")
        or data.get("nbt_file")
        or structure_meta.get("file")
    )

    nbt_path: Optional[Path] = None
    if structure_file:
        candidate = path.parent / str(structure_file)
        if candidate.is_file():
            nbt_path = candidate
        elif not blocks:
            raise FileNotFoundError(
                f"{path.name}: paired NBT file is missing: {candidate}"
            )
        else:
            print(
                f"WARNING: {path.name}: paired NBT file is missing: "
                f"{candidate}; using legacy JSON blocks instead."
            )

    if not blocks and nbt_path is None:
        raise ValueError(
            f"{path.name}: contains neither JSON blocks nor a usable NBT pair"
        )

    structure_entities = bool(
        data.get(
            "structure_entities",
            structure_meta.get("entities", False),
        )
    )

    tribe = str(
        data.get("tribe")
        or data.get("biome")
        or path.parent.name
        or "plains"
    ).strip().lower()

    raw_villagers = data.get("villagers", data.get("villager_spawns", []))
    if raw_villagers is None:
        raw_villagers = []
    if not isinstance(raw_villagers, list):
        raise ValueError(f"{path.name}: villagers must be a JSON list")

    villager_spawns: List[dict] = []
    for villager_index, raw in enumerate(raw_villagers, 1):
        if not isinstance(raw, dict):
            print(
                f"WARNING: {path.name}: ignoring villager #{villager_index}; "
                "entry is not an object."
            )
            continue
        if not bool(raw.get("enabled", True)):
            continue

        local = raw.get("pos")
        if not isinstance(local, list) or len(local) != 3:
            print(
                f"WARNING: {path.name}: ignoring villager #{villager_index}; "
                "pos must be [x, y, z]."
            )
            continue

        try:
            position = [int(local[0]), int(local[1]), int(local[2])]
        except (TypeError, ValueError):
            print(
                f"WARNING: {path.name}: ignoring villager #{villager_index}; "
                "pos values must be whole numbers."
            )
            continue

        facing = str(raw.get("facing", "south")).strip().lower()
        if facing not in CARDINAL_DIRECTIONS:
            print(
                f"WARNING: {path.name}: villager #{villager_index} has invalid "
                f"facing {facing!r}; using south."
            )
            facing = "south"

        profession = str(raw.get("profession", "minecraft:none")).strip().lower()
        if not profession.startswith("minecraft:"):
            profession = "minecraft:" + profession

        try:
            level = max(1, min(5, int(raw.get("level", 2))))
        except (TypeError, ValueError):
            level = 2

        villager_spawns.append(
            {
                "name": str(raw.get("name") or f"villager_{villager_index}"),
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

    return BuildingAsset(
        name=str(data.get("name") or path.stem),
        path=path,
        size_x=int(size[0]),
        size_y=int(size[1]),
        size_z=int(size[2]),
        blocks=blocks,
        waypoints=waypoints,
        include_air=bool(data.get("include_air", False)),
        tribe=tribe,
        villager_spawns=villager_spawns,
        nbt_path=nbt_path,
        structure_entities=structure_entities,
    )


def load_plains_building_assets() -> List[BuildingAsset]:
    """Discover all reusable building JSON files without a filename list."""
    if not BUILDINGS_DIR.is_dir():
        raise FileNotFoundError(
            f"Building folder does not exist: {BUILDINGS_DIR}"
        )

    assets: List[BuildingAsset] = []
    skipped: List[str] = []

    for path in sorted(BUILDINGS_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as file:
                header = json.load(file)
            if header.get("format") != "gdmc_building_json":
                skipped.append(path.name)
                continue
            assets.append(load_building_asset(path))
        except Exception as exc:
            print(f"WARNING: skipping {path.name}: {exc}")

    if not assets:
        raise FileNotFoundError(
            f"No gdmc_building_json files were found in {BUILDINGS_DIR}."
        )

    if not any(asset.path.name == LANDMARK_FILENAME for asset in assets):
        raise FileNotFoundError(
            f"The unique central landmark is missing: "
            f"{BUILDINGS_DIR / LANDMARK_FILENAME}"
        )

    print(f"Discovered {len(assets)} building assets in {BUILDINGS_DIR}")
    for asset in assets:
        wp = asset.waypoints[0]
        role = "CENTRAL LANDMARK" if asset.path.name == LANDMARK_FILENAME else "repeatable"
        print(
            f"  {asset.path.name}: {role}, "
            f"{asset.size_x}x{asset.size_y}x{asset.size_z}, "
            f"blocks={len(asset.blocks)}, waypoint={wp.get('pos')}, "
            f"front={wp.get('direction', 'north')}"
        )

    if skipped:
        print(
            "Ignored non-building JSON files in the builds folder: "
            + ", ".join(skipped)
        )

    return assets


def rotate_direction(direction: str, rotation: int) -> str:
    direction = str(direction).lower()
    if direction not in CARDINAL_DIRECTIONS:
        return direction
    turns = (rotation // 90) % 4
    return CARDINAL_DIRECTIONS[(CARDINAL_DIRECTIONS.index(direction) + turns) % 4]


def rotation_to_face(original_direction: str, desired_direction: str) -> int:
    original = str(original_direction).lower()
    desired = str(desired_direction).lower()
    if original not in CARDINAL_DIRECTIONS or desired not in CARDINAL_DIRECTIONS:
        return 0
    turns = (
        CARDINAL_DIRECTIONS.index(desired)
        - CARDINAL_DIRECTIONS.index(original)
    ) % 4
    return turns * 90


def rotated_dimensions(asset: BuildingAsset, rotation: int) -> Tuple[int, int]:
    if (rotation // 90) % 2:
        return asset.size_z, asset.size_x
    return asset.size_x, asset.size_z


def rotate_local_xz(x: int, z: int, size_x: int, size_z: int,
                    rotation: int) -> Tuple[int, int]:
    """Rotate clockwise around Y while keeping coordinates non-negative."""
    turns = (rotation // 90) % 4
    if turns == 0:
        return x, z
    if turns == 1:
        return size_z - 1 - z, x
    if turns == 2:
        return size_x - 1 - x, size_z - 1 - z
    return z, size_x - 1 - x


def rotate_block_states(states: Optional[dict], rotation: int) -> dict:
    """Rotate common Java block states used by the exported plains builds."""
    if not states:
        return {}

    turns = (rotation // 90) % 4
    if turns == 0:
        return {str(k): str(v) for k, v in states.items()}

    rotated: Dict[str, str] = {}
    for key, value in states.items():
        key_s = str(key)
        value_s = str(value)

        # Fences, walls, panes, and similar blocks use direction names as keys.
        if key_s in CARDINAL_DIRECTIONS:
            key_s = rotate_direction(key_s, rotation)

        if key_s == "facing" and value_s in CARDINAL_DIRECTIONS:
            value_s = rotate_direction(value_s, rotation)
        elif key_s == "axis" and value_s in ("x", "z") and turns % 2 == 1:
            value_s = "z" if value_s == "x" else "x"
        elif key_s == "rotation":
            try:
                value_s = str((int(value_s) + turns * 4) % 16)
            except ValueError:
                pass

        rotated[key_s] = value_s
    return rotated


def transform_waypoint(asset: BuildingAsset, waypoint: dict, rect: Rect,
                       target_top_y: int, rotation: int) -> Tuple[int, int, int, str]:
    local = waypoint.get("pos", [0, 1, 0])
    lx, ly, lz = int(local[0]), int(local[1]), int(local[2])
    rx, rz = rotate_local_xz(lx, lz, asset.size_x, asset.size_z, rotation)
    x0, z0, _x1, _z1 = rect
    facing = rotate_direction(waypoint.get("direction", "north"), rotation)
    return x0 + rx, target_top_y + ly, z0 + rz, facing


def outside_road_connection(rect: Rect, entrance_xz: Pos2D,
                            facing: str) -> Pos2D:
    """Project the saved entrance waypoint to just outside its facing edge."""
    x0, z0, x1, z1 = rect
    ex, ez = entrance_xz
    ex = min(max(ex, x0), x1)
    ez = min(max(ez, z0), z1)

    if facing == "north":
        return ex, z0 - ROAD_CONNECTION_GAP
    if facing == "south":
        return ex, z1 + ROAD_CONNECTION_GAP
    if facing == "west":
        return x0 - ROAD_CONNECTION_GAP, ez
    return x1 + ROAD_CONNECTION_GAP, ez


def evaluate_rectangular_plot(center: Pos2D, width: int, depth: int, ba: dict,
                              heights: Dict[Pos2D, int], water_cells: Set[Pos2D],
                              occupied_rects: Sequence[Rect], max_flatten: int,
                              prefer: Pos2D, min_distance: float,
                              overlap_margin: int,
                              build_area_margin: int = 2) -> Optional[Tuple[float, int, Rect]]:
    rect = rect_for_center_dimensions(center, width, depth)
    if not rect_inside_build_area(rect, ba, margin=build_area_margin):
        return None
    if any(rects_overlap(rect, other, margin=overlap_margin) for other in occupied_rects):
        return None
    if euclid(center, prefer) < min_distance:
        return None
    if (
        SETTLEMENT_BUILDING_RADIUS is not None
        and euclid(center, prefer) > SETTLEMENT_BUILDING_RADIUS
    ):
        return None

    cells = list(rect_cells(rect))
    if any(cell in water_cells or cell not in heights for cell in cells):
        return None

    tops = [surface_top_y(cell, heights) for cell in cells]
    low, high = min(tops), max(tops)

    # Fill-first foundation level. Never lower a pad more than the configured
    # cut limit; raise low cells instead. Sites requiring an excessive earthen
    # platform are rejected so buildings still follow the landscape.
    median_top = int(round(statistics.median(tops)))
    target = max(median_top, high - BUILDING_MAX_CUT_DOWN)
    maximum_cut = max(0, high - target)
    maximum_fill = max(0, target - low)
    max_dev = max(maximum_cut, maximum_fill)
    if (
        maximum_cut > BUILDING_MAX_CUT_DOWN
        or maximum_fill > BUILDING_MAX_FILL_UP
        or high - low > max_flatten * 2
    ):
        return None

    score = (
        (high - low) * 95
        + maximum_cut * 180
        + maximum_fill * 42
        + (sum(abs(top - target) for top in tops) / len(tops)) * 20
        + euclid(center, prefer) * 0.35
    )
    score += max(0, target - GLOBAL_MEDIAN_TOP_Y - MOUNTAIN_ABOVE_MEDIAN_SOFT) * 50
    return score, target, rect


def _requested_landmark_candidates(requested: Pos2D, radius: int) -> List[Pos2D]:
    """Candidate centers ordered from the requested coordinate outward."""
    rx, rz = requested
    candidates: List[Pos2D] = [(rx, rz)]
    for distance in range(1, radius + 1):
        ring: List[Pos2D] = []
        for dx in range(-distance, distance + 1):
            ring.append((rx + dx, rz - distance))
            ring.append((rx + dx, rz + distance))
        for dz in range(-distance + 1, distance):
            ring.append((rx - distance, rz + dz))
            ring.append((rx + distance, rz + dz))
        candidates.extend(ring)
    return list(dict.fromkeys(candidates))


def _random_landmark_candidates(ba: dict, asset: BuildingAsset, seed: int) -> List[Pos2D]:
    """Generate deterministic random landmark centers inside the build area."""
    rng = random.Random(seed + 17011)
    max_width = max(asset.size_x, asset.size_z)
    margin = max_width // 2 + BUILDING_SPACING + 4
    min_x, max_x = ba["x1"] + margin, ba["x2"] - margin
    min_z, max_z = ba["z1"] + margin, ba["z2"] - margin
    if min_x > max_x or min_z > max_z:
        return []

    candidates: List[Pos2D] = []
    seen: Set[Pos2D] = set()
    for _ in range(RANDOM_LANDMARK_CANDIDATE_COUNT):
        point = (rng.randint(min_x, max_x), rng.randint(min_z, max_z))
        if point not in seen:
            seen.add(point)
            candidates.append(point)

    # Grid fallback guarantees coverage in narrow or unlucky build areas.
    for x in range(min_x, max_x + 1, 5):
        for z in range(min_z, max_z + 1, 5):
            point = (x, z)
            if point not in seen:
                seen.add(point)
                candidates.append(point)
    return candidates


def make_json_plot(asset: BuildingAsset, center: Pos2D, target: int,
                   rect: Rect, rotation: int, kind: str = "building") -> Plot:
    """Create a Plot and transform its primary JSON road waypoint."""
    waypoint = asset.waypoints[0]
    width, depth = rotated_dimensions(asset, rotation)
    entrance_x, entrance_y, entrance_z, entrance_facing = transform_waypoint(
        asset, waypoint, rect, target, rotation
    )
    road_front = outside_road_connection(
        rect, (entrance_x, entrance_z), entrance_facing
    )
    x0, z0, _x1, _z1 = rect
    return Plot(
        kind=kind,
        size=max(width, depth),
        center=center,
        rect=rect,
        target_top_y=target,
        wool="grass_block",
        door_pos=(entrance_x, entrance_z),
        door_facing=entrance_facing,
        door_front=road_front,
        asset=asset,
        rotation=rotation,
        origin=(x0, target, z0),
        entrance_world=(entrance_x, entrance_y, entrance_z),
        rotated_width=width,
        rotated_depth=depth,
    )


def find_landmark_plot(ba: dict, heights: Dict[Pos2D, int],
                       water_cells: Set[Pos2D], asset: BuildingAsset,
                       requested: Optional[Pos2D], seed: int) -> Plot:
    """Place the unique landmark near a request or at a random valid location."""
    rng = random.Random(seed + 2909)
    requested_mode = requested is not None
    if requested_mode:
        assert requested is not None
        candidates = _requested_landmark_candidates(
            requested, LANDMARK_SEARCH_RADIUS_FROM_REQUEST
        )
        prefer = requested
    else:
        candidates = _random_landmark_candidates(ba, asset, seed)
        prefer = ((ba["x1"] + ba["x2"]) // 2, (ba["z1"] + ba["z2"]) // 2)
        rng.shuffle(candidates)

    valid: List[Tuple[float, Pos2D, int, Rect, int]] = []
    rotations = [0, 90, 180, 270]

    for candidate_index, candidate in enumerate(candidates):
        for rotation in rotations:
            width, depth = rotated_dimensions(asset, rotation)
            result = evaluate_rectangular_plot(
                candidate, width, depth, ba, heights, water_cells,
                occupied_rects=[],
                max_flatten=BUILDING_MAX_FLATTEN,
                prefer=prefer if requested_mode else candidate,
                min_distance=0,
                overlap_margin=0,
            )
            if result is None and RELAX_IF_NEEDED:
                result = evaluate_rectangular_plot(
                    candidate, width, depth, ba, heights, water_cells,
                    occupied_rects=[],
                    max_flatten=RELAXED_BUILDING_MAX_FLATTEN,
                    prefer=prefer if requested_mode else candidate,
                    min_distance=0,
                    overlap_margin=0,
                )
            if result is None:
                continue

            score, target, rect = result
            if requested_mode:
                score += euclid(candidate, prefer) * 500.0
            else:
                # Keep terrain quality important, but choose randomly among a
                # collection of good valid options rather than always centering.
                score += stable_rng(seed, candidate[0], candidate[1], rotation).random() * 20
            valid.append((score, candidate, target, rect, rotation))

            # A requested point should strongly prefer the nearest valid ring.
            if requested_mode and candidate_index > 0 and len(valid) >= 8:
                break
        if requested_mode and candidate_index > 0 and len(valid) >= 8:
            break
        if not requested_mode and len(valid) >= 120:
            break

    if not valid:
        mode = f"near {requested}" if requested_mode else "at a random build-area location"
        raise RuntimeError(
            f"Could not find a valid plot for landmark {asset.name} {mode}. "
            "Use a larger/flatter build area or raise BUILDING_MAX_FLATTEN."
        )

    valid.sort(key=lambda item: item[0])
    if requested_mode:
        chosen = valid[0]
    else:
        top = valid[:min(24, len(valid))]
        chosen = rng.choice(top)

    _score, center, target, rect, rotation = chosen
    plot = make_json_plot(asset, center, target, rect, rotation, kind="landmark")
    placement_mode = "requested" if requested_mode else "random"
    print(
        f"Selected unique landmark ({placement_mode}): {asset.name}, "
        f"center={plot.center}, size={plot.rotated_width}x{plot.rotated_depth}, "
        f"rotation={plot.rotation}°, entrance={plot.entrance_world}, "
        f"road hub={plot.door_front}"
    )
    return plot


def find_json_building_plots(ba: dict, heights: Dict[Pos2D, int],
                             water_cells: Set[Pos2D], altar: Plot,
                             assets: Sequence[BuildingAsset], seed: int) -> List[Plot]:
    rng = random.Random(seed)
    candidates = generate_house_candidates(ba, altar.center, rng)
    candidates = [
        p for p in candidates
        if euclid(p, altar.center) <= SETTLEMENT_BUILDING_RADIUS
    ]

    plots: List[Plot] = []
    occupied: List[Rect] = [altar.rect]

    for asset_index, asset in enumerate(assets):
        best: Optional[Tuple[float, Pos2D, int, Rect, int, str]] = None
        waypoint = asset.waypoints[0]
        original_facing = waypoint.get("direction", "north")

        for candidate in candidates:
            desired_facing = direction_to_facing(
                altar.center[0] - candidate[0],
                altar.center[1] - candidate[1],
            )
            rotation = rotation_to_face(original_facing, desired_facing)
            width, depth = rotated_dimensions(asset, rotation)
            min_distance = ALTAR_SIZE / 2 + max(width, depth) / 2 + 7

            result = evaluate_rectangular_plot(
                candidate, width, depth, ba, heights, water_cells,
                occupied, BUILDING_MAX_FLATTEN, altar.center,
                min_distance, BUILDING_SPACING,
            )
            if result is None and RELAX_IF_NEEDED:
                result = evaluate_rectangular_plot(
                    candidate, width, depth, ba, heights, water_cells,
                    occupied, RELAXED_BUILDING_MAX_FLATTEN, altar.center,
                    min_distance, BUILDING_SPACING,
                )
            if result is None:
                continue

            score, target, rect = result
            score += stable_rng(seed + asset_index * 997, candidate[0], candidate[1], rotation).random() * 12
            if best is None or score < best[0]:
                best = (score, candidate, target, rect, rotation, desired_facing)

        if best is None:
            print(f"WARNING: Could not find a plot for {asset.name}")
            continue

        _score, center, target, rect, rotation, desired_facing = best
        width, depth = rotated_dimensions(asset, rotation)
        entrance_x, entrance_y, entrance_z, entrance_facing = transform_waypoint(
            asset, waypoint, rect, target, rotation
        )
        road_front = outside_road_connection(
            rect, (entrance_x, entrance_z), entrance_facing
        )
        x0, z0, _x1, _z1 = rect

        plot = Plot(
            kind="building",
            size=max(width, depth),
            center=center,
            rect=rect,
            target_top_y=target,
            wool="grass_block",
            door_pos=(entrance_x, entrance_z),
            door_facing=entrance_facing,
            door_front=road_front,
            asset=asset,
            rotation=rotation,
            origin=(x0, target, z0),
            entrance_world=(entrance_x, entrance_y, entrance_z),
            rotated_width=width,
            rotated_depth=depth,
        )
        plots.append(plot)
        occupied.append(rect)

        # Remove nearby candidate centers using the real selected footprint.
        candidates = [
            p for p in candidates
            if not rects_overlap(
                rect_for_center_dimensions(p, width, depth),
                rect,
                margin=BUILDING_SPACING + 2,
            )
        ]

        print(
            f"Selected {asset.name}: center={center}, size={width}x{depth}, "
            f"rotation={rotation}°, entrance={plot.entrance_world}, "
            f"road connection={road_front}"
        )

    return plots



def find_auto_building_plots(
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    altar: Plot,
    assets: Sequence[BuildingAsset],
    seed: int,
) -> List[Plot]:
    """Fill valid terrain automatically with repeated discovered buildings.

    There is no requested count. The finite build area, water, terrain,
    building spacing, and wall-edge reserve determine the final number.
    """
    if not assets:
        print("No repeatable normal-building assets were discovered.")
        return []

    rng = random.Random(seed + 45017)
    raw_candidates = generate_house_candidates(ba, altar.center, rng)

    # Remove duplicate candidate centers while preserving their radial order.
    seen_candidates: Set[Pos2D] = set()
    candidates: List[Pos2D] = []
    for point in raw_candidates:
        if point in seen_candidates:
            continue
        seen_candidates.add(point)
        candidates.append(point)

    # Shuffle within distance bands so each run is deterministic but organic.
    candidates.sort(
        key=lambda point: (
            int(euclid(point, altar.center) // 7),
            stable_rng(seed, point[0], point[1], 991).random(),
        )
    )

    plots: List[Plot] = []
    occupied: List[Rect] = [altar.rect]
    usage_counts: Counter[str] = Counter()

    for candidate_index, candidate in enumerate(candidates):
        choices: List[
            Tuple[
                float,
                BuildingAsset,
                int,
                int,
                Rect,
                str,
            ]
        ] = []

        # Prefer underused structures. On ties, try larger assets first so
        # large buildings are not starved by smaller ones.
        asset_order = sorted(
            assets,
            key=lambda asset: (
                usage_counts[asset.path.name],
                -(asset.size_x * asset.size_z),
                stable_rng(
                    seed + candidate_index,
                    candidate[0],
                    candidate[1],
                    sum(ord(ch) for ch in asset.path.name),
                ).random(),
            ),
        )

        for asset in asset_order:
            waypoint = asset.waypoints[0]
            original_facing = waypoint.get("direction", "north")
            desired_facing = direction_to_facing(
                altar.center[0] - candidate[0],
                altar.center[1] - candidate[1],
            )
            rotation = rotation_to_face(
                original_facing,
                desired_facing,
            )
            width, depth = rotated_dimensions(asset, rotation)
            min_distance = (
                max(
                    altar.rotated_width or altar.size,
                    altar.rotated_depth or altar.size,
                )
                / 2
                + max(width, depth) / 2
                + BUILDING_SPACING
                + 2
            )

            result = evaluate_rectangular_plot(
                candidate,
                width,
                depth,
                ba,
                heights,
                water_cells,
                occupied,
                BUILDING_MAX_FLATTEN,
                altar.center,
                min_distance,
                BUILDING_SPACING,
                build_area_margin=AUTO_BUILDING_EDGE_RESERVE,
            )

            if result is None and RELAX_IF_NEEDED:
                result = evaluate_rectangular_plot(
                    candidate,
                    width,
                    depth,
                    ba,
                    heights,
                    water_cells,
                    occupied,
                    RELAXED_BUILDING_MAX_FLATTEN,
                    altar.center,
                    min_distance,
                    BUILDING_SPACING,
                    build_area_margin=AUTO_BUILDING_EDGE_RESERVE,
                )

            if result is None:
                continue

            terrain_score, target, rect = result
            balance_penalty = (
                usage_counts[asset.path.name]
                * AUTO_BUILDING_BALANCE_PENALTY
            )
            randomness = stable_rng(
                seed + candidate_index * 17,
                candidate[0],
                candidate[1],
                sum(ord(ch) for ch in asset.path.name),
            ).random() * AUTO_BUILDING_RANDOMNESS

            choices.append(
                (
                    terrain_score + balance_penalty + randomness,
                    asset,
                    target,
                    rotation,
                    rect,
                    desired_facing,
                )
            )

        if not choices:
            continue

        choices.sort(key=lambda item: item[0])
        _score, asset, target, rotation, rect, _desired_facing = choices[0]
        plot = make_json_plot(
            asset,
            candidate,
            target,
            rect,
            rotation,
            kind="building",
        )
        plots.append(plot)
        occupied.append(rect)
        usage_counts[asset.path.name] += 1

        print(
            f"Auto building {len(plots):03d}: {asset.name}, "
            f"center={candidate}, size={plot.rotated_width}x{plot.rotated_depth}, "
            f"rotation={rotation}°, road={plot.door_front}"
        )

    print(
        f"Automatic building fill exhausted the valid candidate plots: "
        f"placed {len(plots)} repeatable buildings."
    )
    print("Automatic building type counts:")
    for asset in sorted(assets, key=lambda item: item.path.name):
        print(
            f"  {asset.path.name}: {usage_counts.get(asset.path.name, 0)}"
        )

    return plots


def evaluate_plot(center: Pos2D, size: int, ba: dict,
                  heights: Dict[Pos2D, int], water_cells: Set[Pos2D],
                  occupied_rects: Sequence[Rect], max_flatten: int,
                  prefer: Optional[Pos2D] = None,
                  min_distance_from: Optional[Tuple[Pos2D, int]] = None,
                  overlap_margin: int = 5) -> Optional[Tuple[float, int]]:
    rect = rect_for_center(center, size)
    if not rect_inside_build_area(rect, ba, margin=2):
        return None
    if any(rects_overlap(rect, r, margin=overlap_margin) for r in occupied_rects):
        return None
    if min_distance_from is not None:
        p, dist = min_distance_from
        if euclid(center, p) < dist:
            return None

    cells = list(rect_cells(rect))
    if any(c in water_cells for c in cells):
        return None
    if any(c not in heights for c in cells):
        return None

    tops = [surface_top_y(c, heights) for c in cells]
    low, high = min(tops), max(tops)
    target = int(round(statistics.median(tops)))
    max_dev = max(abs(t - target) for t in tops)
    if max_dev > max_flatten or high - low > max_flatten * 2:
        return None

    # Prefer flat, central, not-too-high areas.
    score = (high - low) * 90 + max_dev * 45 + sum(abs(t - target) for t in tops) / len(tops) * 20
    if prefer is not None:
        score += euclid(center, prefer) * 0.25
    score += max(0, target - GLOBAL_MEDIAN_TOP_Y - MOUNTAIN_ABOVE_MEDIAN_SOFT) * 50
    return score, target


# This is filled in main after reading the heightmap.
GLOBAL_MEDIAN_TOP_Y = 64


def find_altar_plot(ba: dict, heights: Dict[Pos2D, int],
                    water_cells: Set[Pos2D], requested_center: Pos2D) -> Plot:
    prefer = requested_center

    exact = evaluate_plot(
        prefer, ALTAR_SIZE, ba, heights, water_cells,
        occupied_rects=[], max_flatten=ALTAR_MAX_FLATTEN,
        prefer=prefer, overlap_margin=0,
    )
    if exact is not None:
        _score, target = exact
        return Plot(
            "altar", ALTAR_SIZE, prefer,
            rect_for_center(prefer, ALTAR_SIZE), target, "yellow_wool"
        )

    candidates: List[Pos2D] = []
    margin = ALTAR_SIZE // 2 + 3
    px, pz = prefer
    for radius in range(1, ALTAR_SEARCH_RADIUS_FROM_REQUEST + 1):
        # Ring search keeps the result close to the coordinate the user chose.
        for dx in range(-radius, radius + 1):
            for dz in (-radius, radius):
                p = (px + dx, pz + dz)
                if in_build_area_xz(ba, p[0], p[1], margin=margin):
                    candidates.append(p)
        for dz in range(-radius + 1, radius):
            for dx in (-radius, radius):
                p = (px + dx, pz + dz)
                if in_build_area_xz(ba, p[0], p[1], margin=margin):
                    candidates.append(p)

    seen: Set[Pos2D] = set()
    unique_candidates = [p for p in candidates if not (p in seen or seen.add(p))]

    best: Optional[Tuple[float, Pos2D, int]] = None
    for p in unique_candidates:
        result = evaluate_plot(
            p, ALTAR_SIZE, ba, heights, water_cells,
            occupied_rects=[], max_flatten=ALTAR_MAX_FLATTEN,
            prefer=prefer, overlap_margin=0,
        )
        if result is None:
            continue
        score, target = result
        score += euclid(p, prefer) * 30
        if best is None or score < best[0]:
            best = (score, p, target)

    if best is None:
        raise RuntimeError(
            f"Could not find a valid 15x15 altar within "
            f"{ALTAR_SEARCH_RADIUS_FROM_REQUEST} blocks of {requested_center}. "
            "Choose a flatter/drier coordinate or increase ALTAR_MAX_FLATTEN."
        )

    _, center, target = best
    print(f"Requested center {requested_center} was unsuitable; using nearby altar center {center}.")
    return Plot(
        "altar", ALTAR_SIZE, center,
        rect_for_center(center, ALTAR_SIZE), target, "yellow_wool"
    )


def choose_house_door(plot: Plot, altar_center: Pos2D) -> None:
    """Choose a door on the side facing the altar.

    V7 places the actual door one block OUTSIDE the colored foundation. This
    makes the door face the altar from the exterior side instead of being inset
    into the inside half of the house/foundation block.
    """
    x0, z0, x1, z1 = plot.rect
    cx, cz = plot.center
    ax, az = altar_center
    dx, dz = ax - cx, az - cz
    facing = direction_to_facing(dx, dz)

    if facing == "west":
        edge = (x0, cz)
    elif facing == "east":
        edge = (x1, cz)
    elif facing == "north":
        edge = (cx, z0)
    else:
        edge = (cx, z1)

    vec = facing_to_vec(facing)
    if PLACE_DOORS_OUTSIDE_FOUNDATION:
        door = (edge[0] + vec[0], edge[1] + vec[1])
        road_waypoint = (door[0] + vec[0], door[1] + vec[1])
    else:
        door = edge
        road_waypoint = (door[0] + vec[0], door[1] + vec[1])

    plot.door_pos = door
    plot.door_facing = facing
    plot.door_front = road_waypoint

def generate_house_candidates(ba: dict, altar_center: Pos2D, rng: random.Random) -> List[Pos2D]:
    ax, az = altar_center
    max_radius = max(20, min(ba["x2"] - ba["x1"], ba["z2"] - ba["z1"]) // 2 - 8)
    min_radius = ALTAR_SIZE // 2 + 12

    candidates: List[Pos2D] = []
    for r in range(min_radius, max_radius + 1, 4):
        angles = list(range(0, 360, 12))
        rng.shuffle(angles)
        for a in angles:
            rad = math.radians(a + rng.uniform(-4, 4))
            x = int(round(ax + math.cos(rad) * (r + rng.uniform(-2, 2))))
            z = int(round(az + math.sin(rad) * (r + rng.uniform(-2, 2))))
            if in_build_area_xz(ba, x, z, margin=8):
                candidates.append((x, z))

    # Add grid fallback points so it still works in long/thin build areas.
    for x in range(ba["x1"] + 10, ba["x2"] - 9, 5):
        for z in range(ba["z1"] + 10, ba["z2"] - 9, 5):
            if euclid((x, z), altar_center) >= min_radius:
                candidates.append((x, z))

    rng.shuffle(candidates)
    candidates.sort(key=lambda p: euclid(p, altar_center))
    return candidates


def find_house_plots(ba: dict, heights: Dict[Pos2D, int], water_cells: Set[Pos2D],
                     altar: Plot, count: int, seed: int) -> List[Plot]:
    rng = random.Random(seed)
    houses: List[Plot] = []
    occupied: List[Rect] = [altar.rect]
    candidates = generate_house_candidates(ba, altar.center, rng)

    def search_one(size: int, max_flatten: int) -> Optional[Plot]:
        best: Optional[Tuple[float, Pos2D, int]] = None
        for p in candidates:
            # Keep houses around the altar, not too far unless the map forces it.
            min_dist = ALTAR_SIZE // 2 + size // 2 + 7
            result = evaluate_plot(
                p, size, ba, heights, water_cells, occupied,
                max_flatten=max_flatten,
                prefer=altar.center,
                min_distance_from=(altar.center, min_dist),
                overlap_margin=6,
            )
            if result is None:
                continue
            score, target = result
            # Add a small random tie-breaker for variety.
            score += stable_rng(seed, p[0], p[1], size).random() * 15
            if best is None or score < best[0]:
                best = (score, p, target)
        if best is None:
            return None
        _, center, target = best
        plot = Plot("house", size, center, rect_for_center(center, size), target, HOUSE_WOOL[size])
        choose_house_door(plot, altar.center)
        return plot

    attempts = 0
    while len(houses) < count and attempts < count * 4:
        attempts += 1
        size = rng.choice(HOUSE_SIZE_OPTIONS)
        plot = search_one(size, HOUSE_MAX_FLATTEN)
        if plot is None and RELAX_IF_NEEDED:
            plot = search_one(size, RELAXED_HOUSE_MAX_FLATTEN)
        if plot is None:
            continue
        houses.append(plot)
        occupied.append(plot.rect)
        # Remove candidates inside/near this plot to speed up later searches.
        candidates = [p for p in candidates if not rects_overlap(rect_for_center(p, size), plot.rect, margin=8)]

    return houses


# ------------------------------------------------------------
# Tree clearing
# ------------------------------------------------------------

def clear_air_column(blocks: List[dict], x: int, z: int, base_top_y: int, ba: dict,
                     height: int = TREE_CLEAR_HEIGHT) -> None:
    if not in_build_area_xz(ba, x, z):
        return
    y_start = max(ba["y1"], base_top_y + 1)
    y_end = min(ba["y2"], base_top_y + height)
    for y in range(y_start, y_end + 1):
        blocks.append(b("air", x, y, z))


def ground_top_for_clearance(pos: Pos2D, heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int]) -> int:
    # Use the lower of the surface and ocean-floor heightmaps so tree tops do not become
    # the base of our clearing column. This is also safer around shallow water.
    candidates = []
    if pos in heights:
        candidates.append(heights[pos] - 1)
    if pos in floor_heights:
        candidates.append(floor_heights[pos] - 1)
    return min(candidates) if candidates else GLOBAL_MEDIAN_TOP_Y


def clear_trees_for_plot(blocks: List[dict], plot: Plot, ba: dict, water_cells: Optional[Set[Pos2D]] = None, margin: int = TREE_CLEAR_MARGIN_AROUND_HOUSES) -> None:
    rect = rect_with_margin(plot.rect, margin)
    x0, z0, x1, z1 = rect
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if in_build_area_xz(ba, x, z):
                if water_cells is not None and (x, z) in water_cells:
                    continue
                clear_height = (
                    max(0, ba["y2"] - plot.target_top_y)
                    if BUILDING_CLEAR_COLUMNS_TO_SKY
                    else TREE_CLEAR_HEIGHT
                )
                clear_air_column(
                    blocks,
                    x,
                    z,
                    plot.target_top_y,
                    ba,
                    height=clear_height,
                )


def clear_trees_in_settlement_bounds(blocks: List[dict], plots: Sequence[Plot],
                                     heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
                                     ba: dict, water_cells: Optional[Set[Pos2D]] = None,
                                     margin: int = SETTLEMENT_TREE_CLEAR_MARGIN) -> int:
    if not plots:
        return 0
    x0 = min(p.rect[0] for p in plots) - margin
    z0 = min(p.rect[1] for p in plots) - margin
    x1 = max(p.rect[2] for p in plots) + margin
    z1 = max(p.rect[3] for p in plots) + margin
    x0 = max(ba["x1"], x0)
    z0 = max(ba["z1"], z0)
    x1 = min(ba["x2"], x1)
    z1 = min(ba["z2"], z1)

    count = 0
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if water_cells is not None and (x, z) in water_cells:
                continue
            top = ground_top_for_clearance((x, z), heights, floor_heights)
            clear_air_column(blocks, x, z, top, ba)
            count += 1
    return count


def clear_trees_around_road_cells(blocks: List[dict], road_cells: Iterable[Pos2D],
                                  ba: dict, heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
                                  blocked_building_cells: Set[Pos2D],
                                  water_cells: Optional[Set[Pos2D]] = None,
                                  margin: int = ROAD_TREE_CLEAR_MARGIN) -> int:
    cells: Set[Pos2D] = set()
    for x, z in road_cells:
        for ox in range(-margin, margin + 1):
            for oz in range(-margin, margin + 1):
                if abs(ox) + abs(oz) <= margin:
                    p = (x + ox, z + oz)
                    if p not in blocked_building_cells and in_build_area_xz(ba, p[0], p[1]):
                        if water_cells is not None and p in water_cells:
                            continue
                        cells.add(p)
    for p in cells:
        if water_cells is not None and p in water_cells:
            continue
        top = ground_top_for_clearance(p, heights, floor_heights)
        clear_air_column(blocks, p[0], p[1], top, ba)
    return len(cells)


# ------------------------------------------------------------
# Flattening / marking
# ------------------------------------------------------------

def _clipped_rect(rect: Rect, ba: dict) -> Rect:
    return (
        max(ba["x1"], rect[0]),
        max(ba["z1"], rect[1]),
        min(ba["x2"], rect[2]),
        min(ba["z2"], rect[3]),
    )


def _settlement_terrain_rect(
    plots: Sequence[Plot],
    ba: dict,
    wall_perimeter: Optional[Rect],
) -> Rect:
    """Area gently regraded as one settlement, not isolated plot rectangles."""
    if wall_perimeter is not None:
        return _clipped_rect(
            rect_with_margin(wall_perimeter, SETTLEMENT_TERRAIN_MARGIN), ba
        )
    x0 = min(plot.rect[0] for plot in plots)
    z0 = min(plot.rect[1] for plot in plots)
    x1 = max(plot.rect[2] for plot in plots)
    z1 = max(plot.rect[3] for plot in plots)
    return _clipped_rect(
        rect_with_margin(
            (x0, z0, x1, z1),
            WALL_PERIMETER_MARGIN + SETTLEMENT_TERRAIN_MARGIN,
        ),
        ba,
    )


def _distance_to_rect(pos: Pos2D, rect: Rect) -> int:
    x, z = pos
    x0, z0, x1, z1 = rect
    dx = x0 - x if x < x0 else x - x1 if x > x1 else 0
    dz = z0 - z if z < z0 else z - z1 if z > z1 else 0
    return max(dx, dz)


def _terrain_ground_top(
    pos: Pos2D,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
) -> int:
    values: List[int] = []
    if pos in heights:
        values.append(heights[pos] - 1)
    if pos in floor_heights:
        values.append(floor_heights[pos] - 1)
    return min(values) if values else GLOBAL_MEDIAN_TOP_Y


def _settlement_surface_block() -> str:
    # Grass prevents exposed stone in vegetated settlements. Desert keeps a
    # natural sand surface instead of turning an entire desert green.
    return "sand" if ACTIVE_TRIBE == "desert" else "grass_block"


def _tree_and_ridge_protected_cells(
    terrain_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    blocked: Set[Pos2D],
    building_cells: Set[Pos2D],
) -> Set[Pos2D]:
    """Protect likely tree crowns/roots, but do not protect mountain ridges.

    V23 also protected local height spikes, which caused actual mountain mass to
    survive the settlement regrading. V24 uses the difference between the two
    no-plant heightmaps as the conservative tree signal. Sharp rock ridges are
    therefore available for mountain flattening.
    """
    x0, z0, x1, z1 = terrain_rect
    seeds: Set[Pos2D] = set()
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            pos = (x, z)
            if pos in blocked or pos in building_cells or pos not in heights:
                continue
            visible_top = heights[pos] - 1
            ground_top = floor_heights.get(pos, heights[pos]) - 1
            if visible_top - ground_top >= SETTLEMENT_TREE_SPIKE_THRESHOLD:
                seeds.add(pos)

    protected: Set[Pos2D] = set()
    radius = SETTLEMENT_TREE_PROTECTION_RADIUS
    for x, z in seeds:
        for ox in range(-radius, radius + 1):
            for oz in range(-radius, radius + 1):
                if max(abs(ox), abs(oz)) <= radius:
                    pos = (x + ox, z + oz)
                    if (
                        x0 <= pos[0] <= x1
                        and z0 <= pos[1] <= z1
                        and pos not in building_cells
                    ):
                        protected.add(pos)
    return protected


def _percentile_int(values: Sequence[int], fraction: float) -> int:
    if not values:
        return GLOBAL_MEDIAN_TOP_Y
    ordered = sorted(int(value) for value in values)
    index = int(round((len(ordered) - 1) * max(0.0, min(1.0, fraction))))
    return ordered[index]


def _update_plot_height(plot: Plot, new_top_y: int) -> None:
    """Move a selected building vertically without changing its X/Z placement."""
    old_top_y = plot.target_top_y
    if new_top_y == old_top_y:
        return
    delta = int(new_top_y - old_top_y)
    plot.target_top_y = int(new_top_y)
    if plot.origin is not None:
        plot.origin = (plot.origin[0], plot.origin[1] + delta, plot.origin[2])
    if plot.entrance_world is not None:
        plot.entrance_world = (
            plot.entrance_world[0],
            plot.entrance_world[1] + delta,
            plot.entrance_world[2],
        )


def normalize_plot_levels_for_mountain_flatten(
    plots: Sequence[Plot],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
) -> int:
    """Bring mountain buildings onto one low, slightly terraced settlement grade.

    The grade is biased toward the lower-middle terrain and lower selected plot
    elevations. Buildings may differ by one block so the settlement remains
    natural, but a building selected high on a ridge is lowered before any NBT,
    villagers, roads, or walls are generated.
    """
    if not plots:
        return GLOBAL_MEDIAN_TOP_Y

    x0 = max(ba["x1"], min(plot.rect[0] for plot in plots) - WALL_PERIMETER_MARGIN)
    z0 = max(ba["z1"], min(plot.rect[1] for plot in plots) - WALL_PERIMETER_MARGIN)
    x1 = min(ba["x2"], max(plot.rect[2] for plot in plots) + WALL_PERIMETER_MARGIN)
    z1 = min(ba["z2"], max(plot.rect[3] for plot in plots) + WALL_PERIMETER_MARGIN)

    terrain_samples: List[int] = []
    for x in range(x0, x1 + 1, 3):
        for z in range(z0, z1 + 1, 3):
            pos = (x, z)
            if pos in heights:
                terrain_samples.append(_terrain_ground_top(pos, heights, floor_heights))

    plot_levels = [plot.target_top_y for plot in plots]
    lower_plot = _percentile_int(plot_levels, 0.35)
    lower_ground = _percentile_int(terrain_samples, 0.38)
    base_grade = int(round(statistics.median([lower_plot, lower_ground])))

    # Avoid an extreme downward jump if the chosen region is an elevated plateau.
    base_grade = max(min(plot_levels) - 2, base_grade)
    base_grade = min(_percentile_int(plot_levels, 0.55), base_grade)

    for index, plot in enumerate(plots):
        # Keep a tiny deterministic terrace variation, never a mountain-sized
        # vertical split between neighboring structures.
        variation = 0
        if MOUNTAIN_PLOT_LEVEL_SPREAD > 0 and plot.kind != "landmark":
            variation = stable_rng(
                SEED,
                plot.center[0],
                plot.center[1],
                2401 + index,
            ).randint(0, MOUNTAIN_PLOT_LEVEL_SPREAD)
        desired = base_grade + variation
        _update_plot_height(plot, desired)

    return base_grade


def plan_gentle_settlement_terrain(
    plots: Sequence[Plot],
    ba: dict,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    blocked: Set[Pos2D],
    wall_perimeter: Optional[Rect],
    settlement_grade: Optional[int] = None,
) -> Tuple[Dict[Pos2D, int], Set[Pos2D], Set[Pos2D], Rect, int]:
    """Create one regraded settlement surface with mountain terraces.

    Normal ground is only smoothed gently. Cells that rise well above the shared
    settlement grade, or form strong local relief, are treated as mountain mass.
    Those cells may be cut deeply, are blended toward the outer boundary, and
    are always recapped with grass during application.
    """
    if not plots or not GENTLE_SETTLEMENT_TERRAIN:
        empty_rect = (ba["x1"], ba["z1"], ba["x1"], ba["z1"])
        grade = GLOBAL_MEDIAN_TOP_Y if settlement_grade is None else settlement_grade
        return {}, set(), set(), empty_rect, grade

    terrain_rect = _settlement_terrain_rect(plots, ba, wall_perimeter)
    building_cells: Set[Pos2D] = set()
    for plot in plots:
        building_cells.update(rect_cells(plot.rect))

    x0, z0, x1, z1 = terrain_rect
    ground: Dict[Pos2D, int] = {}
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            pos = (x, z)
            if pos in blocked or pos not in heights:
                continue
            ground[pos] = _terrain_ground_top(pos, heights, floor_heights)

    if settlement_grade is None:
        settlement_grade = int(round(statistics.median(
            [plot.target_top_y for plot in plots]
        )))

    protected = _tree_and_ridge_protected_cells(
        terrain_rect, heights, floor_heights, blocked, building_cells
    )

    mountain_cells: Set[Pos2D] = set()
    if FLATTEN_SETTLEMENT_MOUNTAINS:
        relief_radius = max(3, SETTLEMENT_SMOOTH_RADIUS)
        for (x, z), existing in ground.items():
            if (x, z) in building_cells:
                # Building footprints are flattened by their own final pad pass.
                continue
            samples: List[int] = []
            for ox in range(-relief_radius, relief_radius + 1, 2):
                for oz in range(-relief_radius, relief_radius + 1, 2):
                    sample = (x + ox, z + oz)
                    if sample in ground:
                        samples.append(ground[sample])
            local_low = _percentile_int(samples, 0.25) if samples else existing
            relief = existing - local_low
            if (
                existing >= settlement_grade + MOUNTAIN_ABOVE_GRADE_TRIGGER
                or relief >= MOUNTAIN_LOCAL_RELIEF_TRIGGER
            ):
                mountain_cells.add((x, z))

        # Trees on a mountain cut cannot remain at their old elevation without
        # floating. Preserve trees elsewhere, but let mountain cells be cleared.
        protected -= mountain_cells

    targets: Dict[Pos2D, int] = {}
    sample_step = 2
    radius = SETTLEMENT_SMOOTH_RADIUS

    for pos, existing in ground.items():
        if pos in building_cells or pos in protected:
            continue
        x, z = pos

        if pos in mountain_cells:
            variation = 0
            if MOUNTAIN_TERRACE_VARIATION > 0:
                variation = stable_rng(
                    SEED, x // 10, z // 10, 3191
                ).randint(0, MOUNTAIN_TERRACE_VARIATION)
            plateau = settlement_grade + variation

            # Preserve a natural transition at the settlement edge. Interior
            # mountain mass reaches the terrace; the outer ring approaches the
            # original terrain gradually instead of forming a vertical quarry.
            edge_distance = min(x - x0, x1 - x, z - z0, z1 - z)
            blend = min(1.0, max(0.0, edge_distance / MOUNTAIN_BLEND_WIDTH))
            target = int(round(existing * (1.0 - blend) + plateau * blend))
            target = max(existing - MOUNTAIN_MAX_CUT_DOWN, target)
            target = min(target, existing)
            if target != existing:
                targets[pos] = target
            continue

        samples: List[int] = []
        for ox in range(-radius, radius + 1, sample_step):
            for oz in range(-radius, radius + 1, sample_step):
                sample = (x + ox, z + oz)
                if sample in ground and sample not in protected:
                    samples.append(ground[sample])
        if len(samples) < 4:
            continue

        local_median = int(round(statistics.median(samples)))
        if local_median - existing >= SETTLEMENT_HOLE_DEPTH_TRIGGER:
            target = min(local_median, existing + SETTLEMENT_HOLE_FILL_LIMIT)
        else:
            target = int(round(existing * 0.45 + local_median * 0.55))

        nearest_plot: Optional[Plot] = None
        nearest_distance = SETTLEMENT_BUILDING_BLEND_RADIUS + 1
        for plot in plots:
            distance = _distance_to_rect(pos, plot.rect)
            if 0 < distance < nearest_distance:
                nearest_distance = distance
                nearest_plot = plot
        if nearest_plot is not None and nearest_distance <= SETTLEMENT_BUILDING_BLEND_RADIUS:
            weight = (
                SETTLEMENT_BUILDING_BLEND_RADIUS - nearest_distance + 1
            ) / (SETTLEMENT_BUILDING_BLEND_RADIUS + 1)
            target = int(round(
                target * (1.0 - weight)
                + nearest_plot.target_top_y * weight
            ))

        maximum_fill = (
            SETTLEMENT_HOLE_FILL_LIMIT
            if local_median - existing >= SETTLEMENT_HOLE_DEPTH_TRIGGER
            else SETTLEMENT_MAX_FILL_UP
        )
        target = max(
            existing - SETTLEMENT_MAX_CUT_DOWN,
            min(existing + maximum_fill, target),
        )
        if target != existing:
            targets[pos] = target

    return targets, protected, mountain_cells, terrain_rect, settlement_grade


def apply_gentle_settlement_terrain(
    blocks: List[dict],
    targets: Dict[Pos2D, int],
    mountain_cells: Set[Pos2D],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
    height_overrides: Dict[Pos2D, int],
) -> Tuple[int, int, int, int]:
    """Queue gentle terrain plus deep grass-covered mountain cuts."""
    normal_surface_block = _settlement_surface_block()
    cut_columns = 0
    mountain_cut_columns = 0
    filled_columns = 0
    hole_columns = 0

    for (x, z), target_top_y in sorted(targets.items()):
        existing_top = _terrain_ground_top((x, z), heights, floor_heights)
        visible_top = heights.get((x, z), existing_top + 1) - 1
        delta = target_top_y - existing_top
        is_mountain_cut = (x, z) in mountain_cells and delta < 0

        if delta > 0:
            filled_columns += 1
            if delta >= SETTLEMENT_HOLE_DEPTH_TRIGGER:
                hole_columns += 1
            for y in range(existing_top + 1, target_top_y):
                if in_build_area_xyz(ba, x, y, z):
                    blocks.append(b("dirt", x, y, z))
        elif delta < 0:
            cut_columns += 1
            if is_mountain_cut:
                mountain_cut_columns += 1
                # Remove the complete mountain/tree column above the new grade.
                clear_end = min(ba["y2"], max(existing_top, visible_top) + 2)
            else:
                # Normal terrain cuts remain shallow.
                clear_end = min(ba["y2"], existing_top + 1)
            for y in range(target_top_y + 1, clear_end + 1):
                blocks.append(b("air", x, y, z))

        surface_block = "grass_block" if is_mountain_cut else normal_surface_block
        if in_build_area_xyz(ba, x, target_top_y - 1, z):
            blocks.append(b("dirt", x, target_top_y - 1, z))
        if in_build_area_xyz(ba, x, target_top_y, z):
            blocks.append(b(surface_block, x, target_top_y, z))
        height_overrides[(x, z)] = target_top_y

    return cut_columns, mountain_cut_columns, filled_columns, hole_columns


def add_flattened_surface(blocks: List[dict], x: int, z: int, target_top_y: int,
                          surface_block: str, heights: Dict[Pos2D, int], ba: dict,
                          clear_above: int) -> None:
    existing_top = surface_top_y((x, z), heights)

    # Cut down if terrain is higher than target.
    if existing_top > target_top_y:
        for y in range(target_top_y + 1, existing_top + clear_above + 1):
            blocks.append(b("air", x, y, z))

    # Fill up if terrain is lower than target. Keep the visible top as wool/road.
    if existing_top < target_top_y:
        fill_from = existing_top + 1
        for y in range(fill_from, target_top_y):
            if in_build_area_xyz(ba, x, y, z):
                blocks.append(b("dirt", x, y, z))

    blocks.append(b(surface_block, x, target_top_y, z))
    for y in range(target_top_y + 1, target_top_y + clear_above + 1):
        blocks.append(b("air", x, y, z))


def mark_plot(blocks: List[dict], plot: Plot, heights: Dict[Pos2D, int], ba: dict,
              height_overrides: Dict[Pos2D, int]) -> None:
    for x, z in rect_cells(plot.rect):
        add_flattened_surface(blocks, x, z, plot.target_top_y, plot.wool, heights, ba, CLEAR_AIR_ABOVE_FOUNDATIONS)
        height_overrides[(x, z)] = plot.target_top_y



def prepare_json_building_plot(blocks: List[dict], plot: Plot,
                               heights: Dict[Pos2D, int], ba: dict,
                               height_overrides: Dict[Pos2D, int]) -> None:
    """Flatten/fill the real rectangular footprint without wool markers."""
    clear_height = (
        (plot.asset.size_y if plot.asset else CLEAR_AIR_ABOVE_FOUNDATIONS)
        + BUILDING_CLEAR_EXTRA_HEIGHT
    )
    if BUILDING_CLEAR_COLUMNS_TO_SKY:
        clear_height = max(clear_height, ba["y2"] - plot.target_top_y)
    for x, z in rect_cells(plot.rect):
        add_flattened_surface(
            blocks, x, z, plot.target_top_y, _terrain_first_surface_block(),
            heights, ba, clear_height,
        )
        height_overrides[(x, z)] = plot.target_top_y


def place_json_building(blocks: List[dict], plot: Plot) -> int:
    """Append one rotated JSON building to the outgoing GDMC block list."""
    if plot.asset is None or plot.origin is None:
        return 0

    asset = plot.asset
    origin_x, origin_y, origin_z = plot.origin
    placed = 0

    # Exporter order is already y-major. Sorting again makes support blocks come
    # before doors, beds, crops, torches, and upper layers after rotation.
    entries = sorted(
        asset.blocks,
        key=lambda entry: (
            int(entry.get("pos", [0, 0, 0])[1]),
            int(entry.get("pos", [0, 0, 0])[2]),
            int(entry.get("pos", [0, 0, 0])[0]),
        ),
    )

    for entry in entries:
        local = entry.get("pos", [0, 0, 0])
        lx, ly, lz = int(local[0]), int(local[1]), int(local[2])
        rx, rz = rotate_local_xz(
            lx, lz, asset.size_x, asset.size_z, plot.rotation
        )
        block_id = str(entry.get("id", "minecraft:air"))
        states = rotate_block_states(entry.get("states"), plot.rotation)
        data = entry.get("data")
        blocks.append(
            b(
                block_id,
                origin_x + rx,
                origin_y + ly,
                origin_z + rz,
                states,
                str(data) if data else None,
            )
        )
        placed += 1
    return placed


def add_house_door(blocks: List[dict], plot: Plot) -> None:
    if not plot.door_pos or not plot.door_facing:
        return
    x, z = plot.door_pos
    y = plot.target_top_y + 1
    facing = plot.door_facing

    # Give the exterior door a solid threshold/support block. This is placed
    # after roads, so the door does not get deleted by road air-clearing.
    if DOOR_SUPPORT_BLOCK_USES_HOUSE_WOOL:
        blocks.append(b(plot.wool, x, y - 1, z))

    base_state = {
        "facing": facing,
        "hinge": "left",
        "open": "false",
        "powered": "false",
    }
    lower = dict(base_state)
    lower["half"] = "lower"
    upper = dict(base_state)
    upper["half"] = "upper"
    blocks.append(b("oak_door", x, y, z, lower))
    blocks.append(b("oak_door", x, y + 1, z, upper))

def altar_exit_toward(altar: Plot, target: Pos2D) -> Pos2D:
    ax, az = altar.center
    dx, dz = target[0] - ax, target[1] - az
    facing = direction_to_facing(dx, dz)
    x0, z0, x1, z1 = altar.rect
    if facing == "east":
        return x1 + 2, az
    if facing == "west":
        return x0 - 2, az
    if facing == "south":
        return ax, z1 + 2
    return ax, z0 - 2


# ------------------------------------------------------------
# Bridge helpers
# ------------------------------------------------------------

def bridge_deck_block(group: str) -> str:
    return {
        "desert": "birch_planks",
        "plains": "oak_planks",
        "savanna": "acacia_planks",
        "snow": "spruce_planks",
        "taiga": "spruce_planks",
    }.get(group, "oak_planks")


def bridge_rail_block(group: str) -> str:
    return {
        "desert": "birch_fence",
        "plains": "oak_fence",
        "savanna": "acacia_fence",
        "snow": "spruce_fence",
        "taiga": "spruce_fence",
    }.get(group, "oak_fence")


def bridge_support_block(group: str) -> str:
    return {
        "desert": "sandstone_wall",
        "plains": "cobblestone_wall",
        "savanna": "red_sandstone_wall",
        "snow": "stone_brick_wall",
        "taiga": "spruce_fence",
    }.get(group, "oak_fence")


def add_bridge_surface(blocks: List[dict], x: int, z: int, target_top_y: int, group: str,
                       heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
                       ba: dict, clear_above: int) -> None:
    """Place a simple bridge deck without filling the water below with dirt."""
    blocks.append(b(bridge_deck_block(group), x, target_top_y, z))

    # Clear air above the bridge deck. Do not clear below; that preserves water.
    for y in range(target_top_y + 1, target_top_y + clear_above + 1):
        blocks.append(b("air", x, y, z))

    # Occasional supports down to the ocean floor.
    if ((x * 31 + z * 17) % BRIDGE_SUPPORT_INTERVAL) == 0:
        floor_top = surface_top_y((x, z), floor_heights)
        support = bridge_support_block(group)
        for y in range(floor_top + 1, target_top_y):
            if in_build_area_xyz(ba, x, y, z):
                blocks.append(b(support, x, y, z))


def bridge_target_y(pos: Pos2D, heights: Dict[Pos2D, int], height_overrides: Dict[Pos2D, int]) -> int:
    """Choose bridge deck height.

    V3 let smoothed road height pull bridges upward, which produced tall ocean
    viaducts. V4 keeps normal sea crossings at sea level, while still allowing
    unusual higher rivers/waterfalls to use their actual surface.
    """
    water_top = surface_top_y(pos, heights, height_overrides)
    if BRIDGE_DECK_AT_SEA_LEVEL and abs(water_top - SEA_SURFACE_BLOCK_Y) <= 3:
        return SEA_SURFACE_BLOCK_Y
    return water_top


def far_from_positions(pos: Pos2D, positions: Set[Pos2D], min_dist: int) -> bool:
    return all(euclid(pos, p) >= min_dist for p in positions)


def local_terrain_relief(pos: Pos2D, heights: Dict[Pos2D, int], water_cells: Set[Pos2D]) -> int:
    """How ridge-like/rough a 3x3 neighborhood is. Water is ignored."""
    x, z = pos
    vals: List[int] = []
    for ox in [-1, 0, 1]:
        for oz in [-1, 0, 1]:
            p = (x + ox, z + oz)
            if p in heights and p not in water_cells:
                vals.append(surface_top_y(p, heights))
    if len(vals) < 3:
        return 0
    return max(vals) - min(vals)


# ------------------------------------------------------------
# Road pathfinding and road placement
# ------------------------------------------------------------

def nearest_allowed_point(target: Pos2D, ba: dict, blocked: Set[Pos2D],
                          heights: Dict[Pos2D, int], max_radius: int = 30) -> Pos2D:
    tx, tz = target
    tx = max(ba["x1"] + 2, min(ba["x2"] - 2, tx))
    tz = max(ba["z1"] + 2, min(ba["z2"] - 2, tz))
    if (tx, tz) in heights and (tx, tz) not in blocked:
        return tx, tz

    for r in range(1, max_radius + 1):
        for ox in range(-r, r + 1):
            for oz in (-r, r):
                p = (tx + ox, tz + oz)
                if in_build_area_xz(ba, p[0], p[1], margin=2) and p in heights and p not in blocked:
                    return p
        for oz in range(-r + 1, r):
            for ox in (-r, r):
                p = (tx + ox, tz + oz)
                if in_build_area_xz(ba, p[0], p[1], margin=2) and p in heights and p not in blocked:
                    return p
    return tx, tz


def astar_path(start: Pos2D, goal: Pos2D, ba: dict,
               heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
               blocked: Set[Pos2D], water_cells: Set[Pos2D],
               height_overrides: Dict[Pos2D, int], seed: int) -> List[Pos2D]:
    start = nearest_allowed_point(start, ba, blocked, heights)
    goal = nearest_allowed_point(goal, ba, blocked, heights)
    blocked = set(blocked)
    blocked.discard(start)
    blocked.discard(goal)

    def h(p: Pos2D) -> float:
        return abs(p[0] - goal[0]) + abs(p[1] - goal[1])

    def height_top(p: Pos2D) -> int:
        # For water cells, route at the water surface; placement later turns this into a bridge deck.
        return surface_top_y(p, heights, height_overrides)

    def noise_cost(x: int, z: int) -> float:
        return stable_rng(seed, x // 5, z // 5, 203).random() * 0.15

    neighbors = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
    open_heap = [(h(start), 0.0, start)]
    came_from: Dict[Pos2D, Optional[Pos2D]] = {start: None}
    g_score: Dict[Pos2D, float] = {start: 0.0}
    max_visits = max(25000, min(250000, len(heights) * 2))
    visited = 0

    while open_heap and visited < max_visits:
        _, current_cost, current = heapq.heappop(open_heap)
        visited += 1
        if current == goal:
            break
        if current_cost > g_score.get(current, 10**12):
            continue

        cx, cz = current
        cy = height_top(current)
        for dx, dz in neighbors:
            np = (cx + dx, cz + dz)
            nx, nz = np
            if not in_build_area_xz(ba, nx, nz, margin=2):
                continue
            if np not in heights or np in blocked:
                continue
            current_is_water = current in water_cells
            next_is_water = np in water_cells
            ny = height_top(np)
            height_diff = abs(ny - cy)

            # Avoid ridge tops and rough mountain cells. Water is handled as bridge instead.
            relief = local_terrain_relief(np, heights, water_cells)
            if not next_is_water and relief > RIDGE_LOCAL_RELIEF_HARD:
                continue
            if not current_is_water and not next_is_water and height_diff > ROAD_MAX_STEP_HEIGHT:
                continue
            if not next_is_water and ny > GLOBAL_MEDIAN_TOP_Y + MOUNTAIN_ABOVE_MEDIAN_HARD:
                continue

            diagonal = dx != 0 and dz != 0
            step = 1.42 if diagonal else 1.0
            mountain_penalty = max(0, ny - GLOBAL_MEDIAN_TOP_Y - MOUNTAIN_ABOVE_MEDIAN_SOFT) * 7.0
            ridge_penalty = max(0, relief - RIDGE_LOCAL_RELIEF_SOFT) * 5.0
            water_penalty = WATER_PATH_PENALTY if next_is_water else 0.0
            tentative = current_cost + step + height_diff * 8.0 + mountain_penalty + ridge_penalty + water_penalty + noise_cost(nx, nz)
            if tentative < g_score.get(np, 10**12):
                came_from[np] = current
                g_score[np] = tentative
                heapq.heappush(open_heap, (tentative + h(np), tentative, np))

    if goal not in came_from:
        print(f"WARNING: A* could not find a safe low-slope path from {start} to {goal}; skipping this branch instead of drawing a ridge road.")
        return []

    path: List[Pos2D] = []
    cur: Optional[Pos2D] = goal
    while cur is not None:
        path.append(cur)
        cur = came_from[cur]
    path.reverse()
    path = straighten_water_runs(path, ba, heights, blocked, water_cells)
    return path


def line_2d(a: Pos2D, c: Pos2D) -> List[Pos2D]:
    x0, z0 = a
    x1, z1 = c
    points: List[Pos2D] = []
    dx = abs(x1 - x0)
    dz = abs(z1 - z0)
    sx = 1 if x0 < x1 else -1
    sz = 1 if z0 < z1 else -1
    err = dx - dz
    while True:
        points.append((x0, z0))
        if x0 == x1 and z0 == z1:
            break
        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            x0 += sx
        if e2 < dx:
            err += dx
            z0 += sz
    return points


def straighten_water_runs(path: List[Pos2D], ba: dict, heights: Dict[Pos2D, int],
                          blocked: Set[Pos2D], water_cells: Set[Pos2D]) -> List[Pos2D]:
    """Make bridge portions straighter.

    A* can make small zig-zags across water. This replaces each continuous water
    run with a direct line between the shoreline entry and exit. That makes the
    bridge look intentional instead of patchy/curved.
    """
    if len(path) < 4:
        return path

    out: List[Pos2D] = []
    i = 0
    n = len(path)
    while i < n:
        if path[i] not in water_cells:
            out.append(path[i])
            i += 1
            continue

        start = i
        while i < n and path[i] in water_cells:
            i += 1
        end = i - 1

        # Include one land cell on each side when possible, so bridge meets shore cleanly.
        a_i = max(0, start - 1)
        b_i = min(n - 1, end + 1)
        candidate = line_2d(path[a_i], path[b_i])

        valid = True
        for j, pnt in enumerate(candidate):
            x, z = pnt
            if not in_build_area_xz(ba, x, z, margin=1) or pnt not in heights:
                valid = False
                break
            if pnt in blocked and pnt not in (path[a_i], path[b_i]):
                valid = False
                break

        if valid and len(candidate) <= max(3, int(euclid(path[a_i], path[b_i]) * 1.8) + 3):
            # Avoid duplicating the shoreline cell already in out.
            if out and candidate and out[-1] == candidate[0]:
                out.extend(candidate[1:])
            else:
                out.extend(candidate)
        else:
            # Fall back to original water run.
            original = path[a_i:b_i + 1]
            if out and original and out[-1] == original[0]:
                out.extend(original[1:])
            else:
                out.extend(original)

    # Remove immediate duplicates.
    deduped: List[Pos2D] = []
    for pnt in out:
        if not deduped or deduped[-1] != pnt:
            deduped.append(pnt)
    return deduped


def smooth_path_tops(
    path: List[Pos2D],
    heights: Dict[Pos2D, int],
    height_overrides: Dict[Pos2D, int],
    start_y: Optional[int] = None,
    end_y: Optional[int] = None,
) -> List[int]:
    """Smooth road Y while locking both endpoints to saved waypoint Y."""
    raw = [surface_top_y(p, heights, height_overrides) for p in path]
    if not raw:
        return []

    smoothed: List[int] = []
    for i in range(len(raw)):
        lo = max(0, i - 2)
        hi = min(len(raw), i + 3)
        target = int(round(statistics.median(raw[lo:hi])))
        target = max(
            raw[i] - ROAD_MAX_FLATTEN,
            min(raw[i] + ROAD_MAX_FLATTEN, target),
        )
        smoothed.append(target)

    if ROAD_LOCK_TO_WAYPOINT_Y and start_y is not None and end_y is not None:
        start_y = int(start_y)
        end_y = int(end_y)
        count = len(smoothed)

        if count == 1:
            return [start_y]

        if abs(end_y - start_y) <= count - 1:
            # Clamp each cell into the range that can still reach both endpoint
            # anchors with one-block elevation changes.
            for i in range(count):
                remaining = count - 1 - i
                low = max(start_y - i, end_y - remaining)
                high = min(start_y + i, end_y + remaining)
                smoothed[i] = max(low, min(high, smoothed[i]))

            for _ in range(4):
                smoothed[0] = start_y
                for i in range(1, count):
                    smoothed[i] = max(
                        smoothed[i - 1] - 1,
                        min(smoothed[i - 1] + 1, smoothed[i]),
                    )
                smoothed[-1] = end_y
                for i in range(count - 2, -1, -1):
                    smoothed[i] = max(
                        smoothed[i + 1] - 1,
                        min(smoothed[i + 1] + 1, smoothed[i]),
                    )
            smoothed[0] = start_y
            smoothed[-1] = end_y
        else:
            print(
                f"WARNING: road branch has {count} cells but waypoint Y differs "
                f"by {abs(end_y - start_y)}. Exact endpoint Y is preserved, "
                "so part of the road may be steeper than one block."
            )
            for i in range(count):
                t = i / (count - 1)
                smoothed[i] = int(round(start_y + (end_y - start_y) * t))
            smoothed[0] = start_y
            smoothed[-1] = end_y
        return smoothed

    # Legacy mode.
    for i in range(1, len(smoothed)):
        if smoothed[i] > smoothed[i - 1] + 1:
            smoothed[i] = smoothed[i - 1] + 1
        elif smoothed[i] < smoothed[i - 1] - 1:
            smoothed[i] = smoothed[i - 1] - 1
    for i in range(len(smoothed) - 2, -1, -1):
        if smoothed[i] > smoothed[i + 1] + 1:
            smoothed[i] = smoothed[i + 1] + 1
        elif smoothed[i] < smoothed[i + 1] - 1:
            smoothed[i] = smoothed[i + 1] - 1
    return smoothed


def make_building_blocked_set(plots: Sequence[Plot], water_blocked: Set[Pos2D]) -> Set[Pos2D]:
    blocked = set(water_blocked)
    for plot in plots:
        for c in rect_cells(plot.rect):
            blocked.add(c)
    return blocked


def build_road_network(
    altar: Plot,
    houses: Sequence[Plot],
    ba: dict,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    height_overrides: Dict[Pos2D, int],
    seed: int,
    water_cells: Set[Pos2D],
    extra_blocked: Optional[Set[Pos2D]] = None,
) -> List[RoadPath]:
    """Create road branches with exact saved waypoint endpoint elevations."""
    blocked = make_building_blocked_set([altar] + list(houses), set())
    if extra_blocked:
        blocked.update(extra_blocked)
    paths: List[RoadPath] = []

    start_point = (
        altar.door_front
        if altar.kind == "landmark" and altar.door_front
        else None
    )
    start_y = (
        int(altar.entrance_world[1])
        if altar.entrance_world is not None
        else int(altar.target_top_y)
    )

    for idx, house in enumerate(houses):
        if house.door_front is None:
            continue

        start = (
            start_point
            if start_point is not None
            else altar_exit_toward(altar, house.door_front)
        )
        goal = house.door_front
        end_y = (
            int(house.entrance_world[1])
            if house.entrance_world is not None
            else int(house.target_top_y)
        )

        blocked.discard(start)
        blocked.discard(goal)
        cells = astar_path(
            start,
            goal,
            ba,
            heights,
            floor_heights,
            blocked,
            water_cells,
            height_overrides,
            seed + idx * 137,
        )
        if len(cells) >= 2:
            branch = RoadPath(
                cells=cells,
                start_y=start_y,
                end_y=end_y,
                start_name=(
                    altar.asset.name if altar.asset is not None else "landmark"
                ),
                end_name=(
                    house.asset.name if house.asset is not None
                    else f"building_{idx + 1}"
                ),
            )
            paths.append(branch)
            print(
                f"  road Y anchors: {branch.start_name}=Y{branch.start_y} -> "
                f"{branch.end_name}=Y{branch.end_y}"
            )
    return paths


def primary_road_block_for_group(group: str) -> str:
    style = STYLES.get(group, STYLES["plains"])
    if style.road_blocks:
        return style.road_blocks[0][0]
    return "dirt_path"


def deco_road_top_y(center: Pos2D,
                    road_cells: "OrderedDict[Pos2D, Tuple[int, str, bool]]",
                    heights: Dict[Pos2D, int],
                    height_overrides: Dict[Pos2D, int]) -> int:
    """Road-level Y used for lamps/decorations beside a road cell.

    V8: side objects should not follow lower natural terrain beside the road.
    They should sit on a small shoulder at the same level as the nearby road.
    """
    if center in road_cells:
        return road_cells[center][0]
    return surface_top_y(center, heights, height_overrides)


def road_cell_is_bridge(center: Pos2D, road_cells: "OrderedDict[Pos2D, Tuple[int, str, bool]]") -> bool:
    return bool(center in road_cells and road_cells[center][2])


def find_deco_spot(center: Pos2D, direction: Dir2D, side: Dir2D, offset: int,
                   ba: dict, heights: Dict[Pos2D, int],
                   road_cells: Set[Pos2D], used: Set[Pos2D],
                   blocked_building_cells: Set[Pos2D], water_cells: Set[Pos2D],
                   target_road_top_y: int) -> Optional[Pos2D]:
    # V8: keep decorations close to the road. Only search a very small distance
    # outward if the intended shoulder block is already occupied.
    for extra in range(0, DECORATION_EXTRA_SEARCH + 1):
        x = center[0] + side[0] * (offset + extra)
        z = center[1] + side[1] * (offset + extra)
        p = (x, z)
        if not in_build_area_xz(ba, x, z, margin=1):
            continue
        if p in road_cells or p in used or p in blocked_building_cells or p in water_cells:
            continue
        if p not in heights:
            continue

        # Reject spots that would need a tall support column or a deep cut.
        natural_top_y = surface_top_y(p, heights)
        if abs(natural_top_y - target_road_top_y) > DECO_MAX_FLATTEN_DIFF_FROM_ROAD:
            continue
        return p
    return None


def prepare_deco_spot_surface(blocks: List[dict], group: str, x: int, z: int,
                              target_top_y: int, heights: Dict[Pos2D, int],
                              ba: dict, water_cells: Set[Pos2D]) -> bool:
    """Make a small road-level shoulder before placing a lamp/decoration.

    This fixes decorations appearing one or more blocks below the road and also
    prevents far floating decorations on steep side terrain.
    """
    if (x, z) in water_cells:
        return False
    if not FLATTEN_DECO_SPOTS_TO_ROAD_LEVEL:
        return True
    surface_block = primary_road_block_for_group(group)
    add_flattened_surface(blocks, x, z, target_top_y, surface_block, heights, ba, CLEAR_AIR_ABOVE_ROADS)
    return True



def road_subgrade_block(group: str) -> str:
    """Biome ground packed directly beneath a normal road surface."""
    return "minecraft:sand" if str(group).lower() == "desert" else "minecraft:dirt"


def add_road_subgrade(
    blocks: List[dict],
    x: int,
    z: int,
    target_top_y: int,
    group: str,
    ba: dict,
) -> int:
    """Guarantee that the blocks immediately below a road are never air."""
    block_id = road_subgrade_block(group)
    placed = 0
    y_start = max(ba["y1"], target_top_y - ROAD_SUBGRADE_DEPTH)
    for y in range(y_start, target_top_y):
        if in_build_area_xyz(ba, x, y, z):
            blocks.append(b(block_id, x, y, z))
            placed += 1
    return placed


def place_roads(blocks: List[dict], paths: Sequence[RoadPath], ba: dict,
                heights: Dict[Pos2D, int], floor_heights: Dict[Pos2D, int],
                biome_lookup: Dict[Pos2D, str],
                height_overrides: Dict[Pos2D, int], blocked_building_cells: Set[Pos2D],
                water_cells: Set[Pos2D], seed: int) -> None:
    road_cells: "OrderedDict[Pos2D, Tuple[int, str, bool]]" = OrderedDict()
    road_cell_set: Set[Pos2D] = set()
    bridge_rails: "OrderedDict[Pos2D, Tuple[int, str]]" = OrderedDict()

    # 1) Decide road footprint first. Width becomes 5 on turns/diagonals.
    endpoint_anchor_cells: Dict[Pos2D, Tuple[int, str, bool]] = {}
    for path_index, road_path in enumerate(paths):
        path = road_path.cells
        tops = smooth_path_tops(
            path,
            heights,
            height_overrides,
            road_path.start_y,
            road_path.end_y,
        )
        for i, center in enumerate(path):
            direction = local_direction(path, i)
            width = road_width_for_path(path, i)
            center_is_bridge = center in water_cells
            for ox, oz in road_offsets(direction, width):
                x, z = center[0] + ox, center[1] + oz
                p = (x, z)
                if not in_build_area_xz(ba, x, z, margin=1):
                    continue
                if p in blocked_building_cells:
                    continue
                group = road_style_group_at(p, biome_lookup)
                is_bridge = BRIDGE_OVER_WATER and (center_is_bridge or p in water_cells)
                target_y = tops[i]
                if is_bridge:
                    # V5: if the path center is water, keep the entire road-width bridge cross-section
                    # at the same sea/water level. This prevents uneven or missing-looking bridge tiles.
                    target_y = bridge_target_y(center if center_is_bridge else p, heights, height_overrides)
                road_cells[p] = (target_y, group, is_bridge)
                road_cell_set.add(p)
                if i == 0 or i == len(path) - 1:
                    endpoint_anchor_cells[p] = (target_y, group, is_bridge)

            # Add simple rail candidates at the outer sides of bridge centers.
            if BRIDGE_RAILS and center_is_bridge:
                center_deck_y = bridge_target_y(center, heights, height_overrides)
                left, right = side_vectors(direction)
                for side in [left, right]:
                    rx = center[0] + side[0] * (width // 2 + 1)
                    rz = center[1] + side[1] * (width // 2 + 1)
                    rp = (rx, rz)
                    if in_build_area_xz(ba, rx, rz, margin=1) and rp not in blocked_building_cells:
                        group = road_style_group_at(center, biome_lookup)
                        bridge_rails[rp] = (center_deck_y, group)

    # Exact waypoint endpoint Y wins over any overlapping road branch.
    for pos, anchored in endpoint_anchor_cells.items():
        road_cells[pos] = anchored

    # 2) Clear trees around the final road/deco corridor before placing road blocks.
    if CLEAR_TREES_AROUND_ROADS:
        cleared = clear_trees_around_road_cells(
            blocks, road_cell_set, ba, heights, floor_heights, blocked_building_cells, water_cells, ROAD_TREE_CLEAR_MARGIN
        )
        print(f"Road tree-clearing cells: {cleared}")

    # 3) Place road surface. Water cells become bridge deck, not dirt-filled road.
    # V5 assigns materials once globally so the road follows your block ratios without per-cell noise.
    road_materials = assign_road_materials(road_cells, seed)
    bridge_cell_count = 0
    for (x, z), (target_top_y, group, is_bridge) in road_cells.items():
        if is_bridge:
            add_bridge_surface(blocks, x, z, target_top_y, group, heights, floor_heights, ba, CLEAR_AIR_ABOVE_ROADS)
            bridge_cell_count += 1
        else:
            road_block = road_materials.get((x, z), road_block_for(group, x, z, seed))
            add_road_subgrade(blocks, x, z, target_top_y, group, ba)
            add_flattened_surface(blocks, x, z, target_top_y, road_block, heights, ba, CLEAR_AIR_ABOVE_ROADS)
        height_overrides[(x, z)] = target_top_y

    for (x, z), (target_top_y, group) in bridge_rails.items():
        if (x, z) not in road_cell_set and in_build_area_xz(ba, x, z, margin=1):
            # Small side deck under the fence so rails do not float.
            blocks.append(b(bridge_deck_block(group), x, target_top_y, z))
            blocks.append(b(bridge_rail_block(group), x, target_top_y + 1, z))

    # 4) Guaranteed lamp posts every 12-15 blocks on each road branch, but globally de-clustered.
    used_deco_positions: Set[Pos2D] = set()
    lamp_positions: Set[Pos2D] = set()
    lamp_count = 0
    deco_count = 0

    for path_index, road_path in enumerate(paths):
        path = road_path.cells
        if len(path) < LAMP_SKIP_START_BLOCKS + LAMP_SKIP_END_BLOCKS + 4:
            continue

        rng = random.Random(seed + 5000 + path_index)
        start_i = min(LAMP_SKIP_START_BLOCKS, max(1, len(path) // 4))
        end_i = max(start_i + 1, len(path) - LAMP_SKIP_END_BLOCKS)
        i = rng.randint(start_i, min(end_i, start_i + 5))
        side_toggle = 1
        branch_lamps = 0

        while i < end_i:
            center = path[i]
            direction = local_direction(path, i)
            width = road_width_for_path(path, i)
            if road_cell_is_bridge(center, road_cells):
                i += rng.randint(LAMP_MIN_SPACING, LAMP_MAX_SPACING)
                continue
            target_road_y = deco_road_top_y(center, road_cells, heights, height_overrides)
            left, right = side_vectors(direction)
            sides = [left, right] if side_toggle > 0 else [right, left]
            side_toggle *= -1

            for side in sides:
                spot = find_deco_spot(
                    center, direction, side, width // 2 + DECORATION_SIDE_OFFSET, ba, heights, road_cell_set,
                    used_deco_positions, blocked_building_cells, water_cells, target_road_y
                )
                if spot is None:
                    continue
                if not far_from_positions(spot, lamp_positions, MIN_LAMP_DISTANCE_BETWEEN_POSTS):
                    continue

                lx, lz = spot
                group = road_style_group_at(spot, biome_lookup)
                if not prepare_deco_spot_surface(blocks, group, lx, lz, target_road_y, heights, ba, water_cells):
                    continue
                ly = target_road_y + 1
                clear_air_column(blocks, lx, lz, target_road_y, ba)
                add_lamp_post(blocks, group, lx, ly, lz, direction)
                used_deco_positions.add(spot)
                lamp_positions.add(spot)
                lamp_count += 1
                branch_lamps += 1
                break

            i += rng.randint(LAMP_MIN_SPACING, LAMP_MAX_SPACING)

        # If a long branch still has no lamp, place one near the middle, also respecting global spacing.
        if branch_lamps == 0 and len(path) >= 22:
            mid_i = len(path) // 2
            center = path[mid_i]
            direction = local_direction(path, mid_i)
            width = road_width_for_path(path, mid_i)
            if road_cell_is_bridge(center, road_cells):
                continue
            target_road_y = deco_road_top_y(center, road_cells, heights, height_overrides)
            left, right = side_vectors(direction)
            for side in [left, right]:
                spot = find_deco_spot(center, direction, side, width // 2 + DECORATION_SIDE_OFFSET, ba, heights, road_cell_set,
                                      used_deco_positions, blocked_building_cells, water_cells, target_road_y)
                if spot and far_from_positions(spot, lamp_positions, MIN_LAMP_DISTANCE_BETWEEN_POSTS):
                    lx, lz = spot
                    group = road_style_group_at(spot, biome_lookup)
                    if not prepare_deco_spot_surface(blocks, group, lx, lz, target_road_y, heights, ba, water_cells):
                        continue
                    ly = target_road_y + 1
                    clear_air_column(blocks, lx, lz, target_road_y, ba)
                    add_lamp_post(blocks, group, lx, ly, lz, direction)
                    used_deco_positions.add(spot)
                    lamp_positions.add(spot)
                    lamp_count += 1
                    break

    # 5) Side decorations using your biome-specific probability tables.
    for path_index, road_path in enumerate(paths):
        path = road_path.cells
        for i, center in enumerate(path):
            if i % DECORATION_STEP != 0:
                continue
            direction = local_direction(path, i)
            width = road_width_for_path(path, i)
            if road_cell_is_bridge(center, road_cells):
                continue
            target_road_y = deco_road_top_y(center, road_cells, heights, height_overrides)
            left, right = side_vectors(direction)
            offset = width // 2 + DECORATION_SIDE_OFFSET

            for side_salt, side in enumerate([left, right]):
                spot = find_deco_spot(
                    center, direction, side, offset, ba, heights, road_cell_set,
                    used_deco_positions, blocked_building_cells, water_cells, target_road_y
                )
                if spot is None:
                    continue
                x, z = spot
                group = road_style_group_at(spot, biome_lookup)
                style = STYLES.get(group, STYLES["plains"])
                rng = stable_rng(seed + path_index, x, z, 100 + side_salt)
                deco = weighted_choice(style.decorations, rng)

                # V7: random lamp rolls are allowed again, but still obey global spacing.
                if deco == "lamp_post":
                    if not far_from_positions(spot, lamp_positions, MIN_LAMP_DISTANCE_BETWEEN_POSTS):
                        continue
                    if not prepare_deco_spot_surface(blocks, group, x, z, target_road_y, heights, ba, water_cells):
                        continue
                    y = target_road_y + 1
                    clear_air_column(blocks, x, z, target_road_y, ba, height=8)
                    add_lamp_post(blocks, group, x, y, z, direction)
                    used_deco_positions.add(spot)
                    lamp_positions.add(spot)
                    lamp_count += 1
                    continue

                if deco in ("air", "nothing"):
                    continue

                if not prepare_deco_spot_surface(blocks, group, x, z, target_road_y, heights, ba, water_cells):
                    continue
                y = target_road_y + 1
                clear_air_column(blocks, x, z, target_road_y, ba, height=8)
                add_decoration(blocks, group, deco, x, y, z, direction, seed)
                used_deco_positions.add(spot)
                deco_count += 1

    print(f"Road network paths: {len(paths)}")
    print(f"Road surface cells: {len(road_cells)}")
    print(f"Bridge deck cells: {bridge_cell_count}")
    print(f"Lamp posts placed: {lamp_count}")
    print(f"Road decorations placed: {deco_count}")




# ------------------------------------------------------------
# Modular wall assets and generation
# ------------------------------------------------------------

@dataclass
class WallModuleAsset:
    name: str
    path: Path
    tribe: str
    module_type: str
    size_x: int
    size_y: int
    size_z: int
    pivot: Tuple[int, int, int]
    ground_y: int
    base_facing: str
    allowed_rotations: List[int]
    blocks: List[dict]
    connectors: List[dict]
    waypoints: List[dict]
    include_air: bool
    min_non_air_y: int
    footprint_columns: Dict[Tuple[int, int], int]


@dataclass
class WallPlacement:
    asset: WallModuleAsset
    side: str
    rotation: int
    world_pivot: Tuple[int, int, int]
    start_connector_name: Optional[str] = None
    end_connector_name: Optional[str] = None
    start_connector_world: Optional[Tuple[int, int, int]] = None
    end_connector_world: Optional[Tuple[int, int, int]] = None


@dataclass
class WallSide:
    name: str
    start: Pos2D
    end: Pos2D
    direction: Dir2D
    corner_start: str
    corner_end: str


def wall_module_asset_from_library_data(
    data: dict,
    library_path: Path,
    module_index: int,
) -> WallModuleAsset:
    module_type = str(data.get("module_type", "")).strip().lower()
    if module_type not in {
        "main_gate",
        "straight_wall",
        "oblique_wall",
        "tower_wall",
    }:
        raise ValueError(
            f"module #{module_index + 1}: unsupported module_type {module_type!r}"
        )

    size = data.get("size")
    pivot = data.get("pivot")
    blocks = list(data.get("blocks") or [])
    connectors = list(data.get("connectors") or [])

    if not isinstance(size, list) or len(size) != 3:
        raise ValueError(f"{module_type}: size must be [x, y, z]")
    if not isinstance(pivot, list) or len(pivot) != 3:
        raise ValueError(f"{module_type}: pivot must be [x, y, z]")
    if not blocks:
        raise ValueError(f"{module_type}: contains no blocks")
    if module_type != "tower_wall" and len(connectors) < 2:
        raise ValueError(
            f"{module_type}: at least two wall connectors are required"
        )

    non_air_entries = [
        entry
        for entry in blocks
        if str(entry.get("id", "minecraft:air")) not in AIR_IDS
    ]
    if not non_air_entries:
        raise ValueError(f"{module_type}: contains no non-air blocks")

    min_non_air_y = min(
        int(entry.get("pos", [0, 0, 0])[1])
        for entry in non_air_entries
    )
    ground_y = int(data.get("ground_y", min_non_air_y))

    footprint_columns: Dict[Tuple[int, int], int] = {}
    for entry in non_air_entries:
        pos = entry.get("pos", [0, 0, 0])
        lx, ly, lz = int(pos[0]), int(pos[1]), int(pos[2])
        key = (lx, lz)
        footprint_columns[key] = min(
            footprint_columns.get(key, ly),
            ly,
        )

    allowed = [
        int(value)
        for value in data.get("allowed_rotations", [0, 90, 180, 270])
        if int(value) % 90 == 0
    ]
    if not allowed:
        allowed = [0, 90, 180, 270]

    banner_count = sum(
        1
        for entry in blocks
        if is_banner_block_id(str(entry.get("id", "")))
    )
    banners_with_data = sum(
        1
        for entry in blocks
        if is_banner_block_id(str(entry.get("id", "")))
        and entry.get("data")
    )

    asset = WallModuleAsset(
        name=str(data.get("name") or f"{module_type}_{module_index + 1}"),
        path=library_path,
        tribe=str(data.get("tribe") or WALL_TRIBE),
        module_type=module_type,
        size_x=int(size[0]),
        size_y=int(size[1]),
        size_z=int(size[2]),
        pivot=(int(pivot[0]), int(pivot[1]), int(pivot[2])),
        ground_y=ground_y,
        base_facing=str(
            data.get("base_facing")
            or data.get("default_facing")
            or "north"
        ).lower(),
        allowed_rotations=sorted(set(value % 360 for value in allowed)),
        blocks=blocks,
        connectors=connectors,
        waypoints=list(data.get("waypoints") or []),
        include_air=bool(data.get("include_air", True)),
        min_non_air_y=min_non_air_y,
        footprint_columns=footprint_columns,
    )

    print(
        f"  {module_type}: {asset.name}, "
        f"size={asset.size_x}x{asset.size_y}x{asset.size_z}, "
        f"ground_y={asset.ground_y}, connectors={len(asset.connectors)}, "
        f"blocks={len(asset.blocks)}, banners={banner_count}, "
        f"banner_data={banners_with_data}"
    )
    if banner_count and banners_with_data < banner_count:
        print(
            f"    WARNING: {banner_count - banners_with_data} banner block(s) "
            "have no custom data and may appear as plain banners."
        )

    return asset


def load_wall_module_library() -> Dict[str, List[WallModuleAsset]]:
    if not GENERATE_WALLS:
        return {}

    if not WALL_LIBRARY_FILE.is_file():
        raise FileNotFoundError(
            f"Wall library does not exist: {WALL_LIBRARY_FILE}\n"
            "Run export_all_wall_modules_to_one_json.py first, or set "
            "GDMC_WALL_LIBRARY_FILE."
        )

    with WALL_LIBRARY_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("format") != "gdmc_wall_library_json":
        raise ValueError(
            f"{WALL_LIBRARY_FILE.name}: expected gdmc_wall_library_json"
        )

    library_tribe = str(data.get("tribe") or WALL_TRIBE).lower()
    if library_tribe != WALL_TRIBE.lower():
        raise ValueError(
            f"Wall library tribe is {library_tribe!r}, expected {WALL_TRIBE!r}"
        )

    raw_modules = data.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ValueError("Wall library contains no modules")

    print(f"Loaded single wall library: {WALL_LIBRARY_FILE}")
    library: Dict[str, List[WallModuleAsset]] = {}
    errors: List[str] = []

    for index, module_data in enumerate(raw_modules):
        if not isinstance(module_data, dict):
            errors.append(f"module #{index + 1}: not a JSON object")
            continue
        try:
            asset = wall_module_asset_from_library_data(
                module_data,
                WALL_LIBRARY_FILE,
                index,
            )
        except Exception as exc:
            errors.append(f"module #{index + 1}: {exc}")
            continue
        library.setdefault(asset.module_type, []).append(asset)

    required = {"main_gate", "straight_wall", "tower_wall"}
    missing = sorted(required - set(library))
    if missing:
        details = "\n".join(f"  - {item}" for item in missing)
        error_text = "\n".join(f"  - {item}" for item in errors)
        raise FileNotFoundError(
            "Missing required module types in the single wall library:\n"
            f"{details}"
            + (f"\nInvalid modules:\n{error_text}" if errors else "")
        )

    if "oblique_wall" not in library:
        print(
            "WARNING: No oblique_wall module was found. "
            "Wall chains will use straight modules only."
        )

    if errors:
        print("Ignored invalid wall modules:")
        for error in errors:
            print(f"  {error}")

    return library


def is_banner_block_id(block_id: str) -> bool:
    block_id = block_id.lower()
    return (
        block_id.endswith("_banner")
        or block_id.endswith("_wall_banner")
    )


def rotate_wall_offset(
    local_pos: Sequence[int],
    pivot: Tuple[int, int, int],
    rotation: int,
) -> Tuple[int, int, int]:
    """Rotate a local point clockwise around the module pivot."""
    x, y, z = int(local_pos[0]), int(local_pos[1]), int(local_pos[2])
    px, py, pz = pivot
    dx, dz = x - px, z - pz
    turns = (rotation // 90) % 4

    if turns == 0:
        rx, rz = dx, dz
    elif turns == 1:
        rx, rz = -dz, dx
    elif turns == 2:
        rx, rz = -dx, -dz
    else:
        rx, rz = dz, -dx

    return rx, y - py, rz


def wall_world_position(
    local_pos: Sequence[int],
    placement: WallPlacement,
) -> Tuple[int, int, int]:
    ox, oy, oz = rotate_wall_offset(
        local_pos,
        placement.asset.pivot,
        placement.rotation,
    )
    px, py, pz = placement.world_pivot
    return px + ox, py + oy, pz + oz


def wall_connector_options(
    asset: WallModuleAsset,
    desired_direction: Dir2D,
) -> List[Tuple[float, int, int, int, Tuple[int, int, int], Tuple[int, int, int]]]:
    """
    Return connector/rotation options ordered by alignment with desired direction.

    Tuple:
      score, rotation, start_index, end_index, start_offset, end_offset
    """
    dx, dz = desired_direction
    options: List[
        Tuple[
            float,
            int,
            int,
            int,
            Tuple[int, int, int],
            Tuple[int, int, int],
        ]
    ] = []

    for rotation in asset.allowed_rotations:
        offsets = [
            rotate_wall_offset(
                connector.get("pos", [0, 0, 0]),
                asset.pivot,
                rotation,
            )
            for connector in asset.connectors
        ]

        for start_index in range(len(offsets)):
            for end_index in range(len(offsets)):
                if start_index == end_index:
                    continue
                start_offset = offsets[start_index]
                end_offset = offsets[end_index]
                delta_x = end_offset[0] - start_offset[0]
                delta_z = end_offset[2] - start_offset[2]
                along = delta_x * dx + delta_z * dz
                perpendicular = abs(delta_x * (-dz) + delta_z * dx)

                if along < 2:
                    continue

                # Strongly prefer pieces that advance exactly along the side.
                score = perpendicular * 100.0 - along * 0.01
                options.append(
                    (
                        score,
                        rotation,
                        start_index,
                        end_index,
                        start_offset,
                        end_offset,
                    )
                )

    options.sort(key=lambda item: item[0])
    return options


def wall_module_world_columns(
    asset: WallModuleAsset,
    world_pivot: Tuple[int, int, int],
    rotation: int,
) -> Dict[Pos2D, int]:
    """Return each solid footprint column and its lowest world Y."""
    placement = WallPlacement(
        asset=asset,
        side="",
        rotation=rotation,
        world_pivot=world_pivot,
    )
    columns: Dict[Pos2D, int] = {}

    for (lx, lz), local_low_y in asset.footprint_columns.items():
        wx, wy, wz = wall_world_position(
            (lx, local_low_y, lz),
            placement,
        )
        key = (wx, wz)
        columns[key] = min(columns.get(key, wy), wy)

    return columns


def wall_module_solid_xz(
    asset: WallModuleAsset,
    world_pivot: Tuple[int, int, int],
    rotation: int,
) -> Set[Pos2D]:
    return set(
        wall_module_world_columns(
            asset,
            world_pivot,
            rotation,
        )
    )


def wall_pivot_y_for_ground(
    asset: WallModuleAsset,
    target_ground_y: int,
) -> int:
    """Align the module's exported local ground_y to a world terrain level."""
    return int(target_ground_y - (asset.ground_y - asset.pivot[1]))


def choose_wall_pivot_y(
    asset: WallModuleAsset,
    pivot_x: int,
    pivot_z: int,
    rotation: int,
    heights: Dict[Pos2D, int],
) -> Optional[int]:
    """Choose a terrain-aware pivot Y using the explicit exported ground_y."""
    provisional = (pivot_x, 0, pivot_z)
    placement = WallPlacement(
        asset=asset,
        side="",
        rotation=rotation,
        world_pivot=provisional,
    )
    terrain_tops: List[int] = []

    for lx, lz in asset.footprint_columns:
        wx, _wy, wz = wall_world_position(
            (lx, asset.ground_y, lz),
            placement,
        )
        if (wx, wz) in heights:
            terrain_tops.append(surface_top_y((wx, wz), heights))

    if not terrain_tops:
        return None

    # V23 no-excavation wall policy: put the module at or above the highest
    # terrain column in its solid footprint. Lower columns receive earthen
    # supports later; no hillside is carved away to force a median wall level.
    target_ground_y = max(terrain_tops)
    return wall_pivot_y_for_ground(asset, target_ground_y)


def wall_placement_terrain_error(
    asset: WallModuleAsset,
    world_pivot: Tuple[int, int, int],
    rotation: int,
    heights: Dict[Pos2D, int],
) -> Tuple[int, float]:
    solid_xz = wall_module_solid_xz(
        asset,
        world_pivot,
        rotation,
    )
    world_ground_y = (
        world_pivot[1]
        + asset.ground_y
        - asset.pivot[1]
    )
    cut_differences: List[int] = []
    fill_differences: List[int] = []

    for pos in solid_xz:
        if pos not in heights:
            return 10**6, 10**6
        terrain_top = surface_top_y(pos, heights)
        cut_differences.append(max(0, terrain_top - world_ground_y))
        fill_differences.append(max(0, world_ground_y - terrain_top))

    if not cut_differences:
        return 10**6, 10**6

    # Required digging is a hard error. Fill depth is permitted and receives
    # only a light score so stable/short supports remain preferred.
    max_cut = max(cut_differences)
    score = (
        sum(cut_differences) / len(cut_differences)
        + 0.10 * sum(fill_differences) / len(fill_differences)
    )
    return max_cut, score


def wall_placement_inside_build_area(
    asset: WallModuleAsset,
    world_pivot: Tuple[int, int, int],
    rotation: int,
    ba: dict,
) -> bool:
    placement = WallPlacement(
        asset=asset,
        side="",
        rotation=rotation,
        world_pivot=world_pivot,
    )

    # Check all non-air blocks. Air outside the area is ignored by the final
    # filter, but every solid wall block must remain inside.
    for entry in asset.blocks:
        if str(entry.get("id", "minecraft:air")) in AIR_IDS:
            continue
        wx, wy, wz = wall_world_position(
            entry.get("pos", [0, 0, 0]),
            placement,
        )
        if not in_build_area_xyz(ba, wx, wy, wz):
            return False
    return True


def wall_placement_is_valid(
    asset: WallModuleAsset,
    world_pivot: Tuple[int, int, int],
    rotation: int,
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    max_flatten: int,
) -> Tuple[bool, float, Set[Pos2D]]:
    solid_xz = wall_module_solid_xz(
        asset,
        world_pivot,
        rotation,
    )

    if not solid_xz:
        return False, 10**9, set()

    if any(pos in water_blocked for pos in solid_xz):
        return False, 10**9, solid_xz

    if not wall_placement_inside_build_area(
        asset,
        world_pivot,
        rotation,
        ba,
    ):
        return False, 10**9, solid_xz

    for x, z in solid_xz:
        for rect in building_rects:
            if rects_overlap(
                (x, z, x, z),
                rect,
                margin=WALL_BUILDING_CLEARANCE,
            ):
                return False, 10**9, solid_xz

    overlap = len(solid_xz & occupied_wall_xz)
    if overlap > WALL_ALLOWED_SEAM_OVERLAP_XZ:
        return False, 10**9, solid_xz

    max_error, mean_error = wall_placement_terrain_error(
        asset,
        world_pivot,
        rotation,
        heights,
    )
    if max_error > max_flatten:
        return False, 10**9, solid_xz

    return True, mean_error, solid_xz


def settlement_wall_perimeter(
    plots: Sequence[Plot],
    ba: dict,
    tower_assets: Sequence[WallModuleAsset],
) -> Tuple[Rect, int]:
    if not plots:
        raise ValueError("Cannot calculate walls without settlement plots")

    tower_radius = 3
    for tower in tower_assets:
        tower_radius = max(
            tower_radius,
            math.ceil(max(tower.size_x, tower.size_z) / 2),
        )

    edge_margin = tower_radius + 2

    settlement_x0 = min(plot.rect[0] for plot in plots)
    settlement_z0 = min(plot.rect[1] for plot in plots)
    settlement_x1 = max(plot.rect[2] for plot in plots)
    settlement_z1 = max(plot.rect[3] for plot in plots)

    x0 = max(
        ba["x1"] + edge_margin,
        settlement_x0 - WALL_PERIMETER_MARGIN,
    )
    z0 = max(
        ba["z1"] + edge_margin,
        settlement_z0 - WALL_PERIMETER_MARGIN,
    )
    x1 = min(
        ba["x2"] - edge_margin,
        settlement_x1 + WALL_PERIMETER_MARGIN,
    )
    z1 = min(
        ba["z2"] - edge_margin,
        settlement_z1 + WALL_PERIMETER_MARGIN,
    )

    if x0 >= settlement_x0 or z0 >= settlement_z0:
        raise RuntimeError(
            "The build area does not leave enough space for the north/west walls."
        )
    if x1 <= settlement_x1 or z1 <= settlement_z1:
        raise RuntimeError(
            "The build area does not leave enough space for the south/east walls."
        )

    return (x0, z0, x1, z1), tower_radius + 2


def make_wall_sides(perimeter: Rect) -> List[WallSide]:
    x0, z0, x1, z1 = perimeter
    return [
        WallSide(
            "north",
            (x0, z0),
            (x1, z0),
            (1, 0),
            "northwest",
            "northeast",
        ),
        WallSide(
            "east",
            (x1, z0),
            (x1, z1),
            (0, 1),
            "northeast",
            "southeast",
        ),
        WallSide(
            "south",
            (x1, z1),
            (x0, z1),
            (-1, 0),
            "southeast",
            "southwest",
        ),
        WallSide(
            "west",
            (x0, z1),
            (x0, z0),
            (0, -1),
            "southwest",
            "northwest",
        ),
    ]


def wall_side_length(side: WallSide) -> int:
    return abs(side.end[0] - side.start[0]) + abs(
        side.end[1] - side.start[1]
    )


def wall_side_point(side: WallSide, distance: int) -> Pos2D:
    return (
        side.start[0] + side.direction[0] * distance,
        side.start[1] + side.direction[1] * distance,
    )


def wall_side_ground_y(
    side: WallSide,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
) -> int:
    """Use one shared terrain level for an entire wall side."""
    samples: List[int] = []
    length = wall_side_length(side)

    for distance in range(length + 1):
        pos = wall_side_point(side, distance)
        if pos in water_blocked or pos not in heights:
            continue
        samples.append(surface_top_y(pos, heights))

    if not samples:
        return GLOBAL_MEDIAN_TOP_Y

    return int(round(statistics.median(samples)))


def wall_side_water_metrics(
    side: WallSide,
    water_cells: Set[Pos2D],
) -> Tuple[int, float, int]:
    """
    Return water-hit positions, ratio, and longest continuous water run.

    A position counts as wet when actual water is within the configured band
    around the planned side.
    """
    length = wall_side_length(side)
    dx, dz = side.direction
    perpendicular = (-dz, dx)
    wet_flags: List[bool] = []

    for distance in range(length + 1):
        x, z = wall_side_point(side, distance)
        wet = False

        for offset in range(
            -WALL_WATER_AVOID_DISTANCE,
            WALL_WATER_AVOID_DISTANCE + 1,
        ):
            test = (
                x + perpendicular[0] * offset,
                z + perpendicular[1] * offset,
            )
            if test in water_cells:
                wet = True
                break

        wet_flags.append(wet)

    wet_count = sum(wet_flags)
    longest = 0
    current = 0
    for wet in wet_flags:
        if wet:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    ratio = wet_count / max(1, len(wet_flags))
    return wet_count, ratio, longest


def side_should_be_skipped_for_water(
    side: WallSide,
    water_cells: Set[Pos2D],
) -> Tuple[bool, str]:
    wet_count, ratio, longest = wall_side_water_metrics(
        side,
        water_cells,
    )

    skip = (
        longest >= WALL_SIDE_MIN_WATER_RUN
        or ratio >= WALL_SIDE_WATER_RATIO_THRESHOLD
    )
    reason = (
        f"water hits={wet_count}, ratio={ratio:.1%}, "
        f"longest run={longest}"
    )
    return skip, reason


def connector_world_from_option(
    world_pivot: Tuple[int, int, int],
    offset: Tuple[int, int, int],
) -> Tuple[int, int, int]:
    return (
        world_pivot[0] + offset[0],
        world_pivot[1] + offset[1],
        world_pivot[2] + offset[2],
    )


def placement_from_connector_option(
    asset: WallModuleAsset,
    side_name: str,
    rotation: int,
    start_index: int,
    end_index: int,
    start_offset: Tuple[int, int, int],
    end_offset: Tuple[int, int, int],
    desired_start_world: Tuple[int, int, int],
    forced_ground_y: Optional[int] = None,
) -> WallPlacement:
    if forced_ground_y is None:
        pivot_y = desired_start_world[1] - start_offset[1]
    else:
        pivot_y = wall_pivot_y_for_ground(asset, forced_ground_y)

    world_pivot = (
        desired_start_world[0] - start_offset[0],
        pivot_y,
        desired_start_world[2] - start_offset[2],
    )
    actual_start_world = connector_world_from_option(
        world_pivot,
        start_offset,
    )
    actual_end_world = connector_world_from_option(
        world_pivot,
        end_offset,
    )

    return WallPlacement(
        asset=asset,
        side=side_name,
        rotation=rotation,
        world_pivot=world_pivot,
        start_connector_name=str(
            asset.connectors[start_index].get(
                "name",
                f"connector_{start_index}",
            )
        ),
        end_connector_name=str(
            asset.connectors[end_index].get(
                "name",
                f"connector_{end_index}",
            )
        ),
        start_connector_world=actual_start_world,
        end_connector_world=actual_end_world,
    )


def choose_gate_placement(
    side: WallSide,
    gate_assets: Sequence[WallModuleAsset],
    corner_clearance: int,
    side_ground_y: int,
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    seed: int,
) -> Optional[Tuple[WallPlacement, Set[Pos2D]]]:
    length = wall_side_length(side)
    usable_start = corner_clearance
    usable_end = length - corner_clearance

    if usable_end - usable_start < 6:
        return None

    rng = random.Random(seed + sum(ord(c) for c in side.name) * 997)
    distances = list(range(usable_start, usable_end + 1))
    rng.shuffle(distances)

    # Prefer the requested random range but keep fallback positions available.
    preferred_low = int(
        usable_start
        + (usable_end - usable_start) * WALL_GATE_MIN_FRACTION
    )
    preferred_high = int(
        usable_start
        + (usable_end - usable_start) * WALL_GATE_MAX_FRACTION
    )
    distances.sort(
        key=lambda value: (
            0 if preferred_low <= value <= preferred_high else 1,
            rng.random(),
        )
    )

    attempts = 0
    for target_distance in distances:
        if attempts >= WALL_GATE_POSITION_ATTEMPTS:
            break
        attempts += 1
        target_x, target_z = wall_side_point(side, target_distance)

        randomized_assets = list(gate_assets)
        rng.shuffle(randomized_assets)

        for asset in randomized_assets:
            options = wall_connector_options(
                asset,
                side.direction,
            )

            # Of the two connector-aligned orientations, prefer the one whose
            # saved road waypoint faces inward toward the settlement.
            inward_facing = {
                "north": "south",
                "east": "west",
                "south": "north",
                "west": "east",
            }[side.name]
            if asset.waypoints:
                original_gate_facing = str(
                    asset.waypoints[0].get("direction", "north")
                )
                options.sort(
                    key=lambda item: (
                        0
                        if rotate_direction(
                            original_gate_facing,
                            item[1],
                        )
                        == inward_facing
                        else 1,
                        item[0],
                    )
                )

            for option in options[:8]:
                (
                    _alignment_score,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                ) = option

                midpoint_x = (start_offset[0] + end_offset[0]) / 2.0
                midpoint_z = (start_offset[2] + end_offset[2]) / 2.0
                pivot_x = int(round(target_x - midpoint_x))
                pivot_z = int(round(target_z - midpoint_z))
                pivot_y = wall_pivot_y_for_ground(
                    asset,
                    side_ground_y,
                )

                world_pivot = (pivot_x, pivot_y, pivot_z)
                start_world = connector_world_from_option(
                    world_pivot,
                    start_offset,
                )
                placement = placement_from_connector_option(
                    asset,
                    side.name,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                    start_world,
                    forced_ground_y=side_ground_y,
                )

                valid, _terrain_error, solid_xz = wall_placement_is_valid(
                    asset,
                    placement.world_pivot,
                    rotation,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz,
                    WALL_MAX_FLATTEN,
                )
                if not valid:
                    valid, _terrain_error, solid_xz = wall_placement_is_valid(
                        asset,
                        placement.world_pivot,
                        rotation,
                        ba,
                        heights,
                        water_blocked,
                        building_rects,
                        occupied_wall_xz,
                        WALL_RELAXED_MAX_FLATTEN,
                    )
                if valid:
                    return placement, solid_xz

    return None


def chain_target_remaining(
    current: Tuple[int, int, int],
    target: Pos2D,
    direction: Dir2D,
) -> int:
    return (
        (target[0] - current[0]) * direction[0]
        + (target[1] - current[2]) * direction[1]
    )


def extend_wall_chain(
    side_name: str,
    current_connector: Tuple[int, int, int],
    target: Pos2D,
    desired_direction: Dir2D,
    side_ground_y: int,
    module_assets: Sequence[WallModuleAsset],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Set[Pos2D]]:
    placements: List[WallPlacement] = []
    newly_occupied: Set[Pos2D] = set()
    rng = random.Random(
        seed
        + sum(ord(c) for c in side_name) * 1777
        + current_connector[0] * 13
        + current_connector[2] * 17
    )

    current = current_connector
    iterations = 0

    while iterations < WALL_MAX_MODULES_PER_CHAIN:
        iterations += 1
        remaining = chain_target_remaining(
            current,
            target,
            desired_direction,
        )
        if remaining <= WALL_END_GAP_TOLERANCE:
            break

        candidates: List[
            Tuple[
                float,
                WallPlacement,
                Set[Pos2D],
            ]
        ] = []

        randomized_assets = list(module_assets)
        rng.shuffle(randomized_assets)

        for asset in randomized_assets:
            options = wall_connector_options(
                asset,
                desired_direction,
            )
            for option in options[:12]:
                (
                    alignment_score,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                ) = option

                placement = placement_from_connector_option(
                    asset,
                    side_name,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                    current,
                    forced_ground_y=side_ground_y,
                )
                assert placement.end_connector_world is not None
                end_world = placement.end_connector_world

                progress = (
                    (end_world[0] - current[0]) * desired_direction[0]
                    + (end_world[2] - current[2]) * desired_direction[1]
                )
                perpendicular = abs(
                    (end_world[0] - current[0]) * (-desired_direction[1])
                    + (end_world[2] - current[2]) * desired_direction[0]
                )

                if progress < 2:
                    continue
                if progress > remaining + WALL_END_GAP_TOLERANCE:
                    continue
                if perpendicular > WALL_MAX_PERPENDICULAR_DRIFT:
                    continue

                valid, terrain_error, solid_xz = wall_placement_is_valid(
                    asset,
                    placement.world_pivot,
                    rotation,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz | newly_occupied,
                    WALL_MAX_FLATTEN,
                )
                if not valid:
                    valid, terrain_error, solid_xz = wall_placement_is_valid(
                        asset,
                        placement.world_pivot,
                        rotation,
                        ba,
                        heights,
                        water_blocked,
                        building_rects,
                        occupied_wall_xz | newly_occupied,
                        WALL_RELAXED_MAX_FLATTEN,
                    )
                if not valid:
                    continue

                end_remaining = chain_target_remaining(
                    end_world,
                    target,
                    desired_direction,
                )
                type_penalty = (
                    WALL_OBLIQUE_PENALTY
                    if asset.module_type == "oblique_wall"
                    else 0.0
                )
                # Prefer alignment, terrain fit, and an endpoint close to the
                # target without forcing a tiny unusable final gap.
                score = (
                    alignment_score
                    + perpendicular * 35.0
                    + terrain_error * 8.0
                    + type_penalty
                    + max(0, WALL_END_GAP_TOLERANCE - end_remaining) * 3.0
                    + rng.random() * 0.25
                )
                candidates.append(
                    (score, placement, solid_xz)
                )

        if not candidates:
            print(
                f"  {side_name} wall chain stopped with "
                f"{remaining} blocks remaining before corner."
            )
            break

        candidates.sort(key=lambda item: item[0])
        _score, chosen, solid_xz = candidates[0]
        placements.append(chosen)
        newly_occupied.update(solid_xz)
        assert chosen.end_connector_world is not None
        current = chosen.end_connector_world

    return placements, newly_occupied


def gate_world_waypoints(
    placement: WallPlacement,
) -> List[dict]:
    results: List[dict] = []
    for waypoint in placement.asset.waypoints:
        wx, wy, wz = wall_world_position(
            waypoint.get("pos", [0, 0, 0]),
            placement,
        )
        direction = rotate_direction(
            str(waypoint.get("direction", "north")),
            placement.rotation,
        )
        results.append(
            {
                "name": waypoint.get("name", "gate_road"),
                "type": waypoint.get("type", "road"),
                "world_pos": (wx, wy, wz),
                "direction": direction,
                "side": placement.side,
            }
        )
    return results


def place_corner_towers(
    perimeter: Rect,
    successful_sides: Set[str],
    tower_assets: Sequence[WallModuleAsset],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Set[Pos2D]]:
    x0, z0, x1, z1 = perimeter
    settlement_center = ((x0 + x1) // 2, (z0 + z1) // 2)

    corners = {
        "northwest": ((x0, z0), {"north", "west"}),
        "northeast": ((x1, z0), {"north", "east"}),
        "southeast": ((x1, z1), {"south", "east"}),
        "southwest": ((x0, z1), {"south", "west"}),
    }

    placements: List[WallPlacement] = []
    newly_occupied: Set[Pos2D] = set()
    rng = random.Random(seed + 88001)

    for corner_name, (corner, adjacent_sides) in corners.items():
        if not (successful_sides & adjacent_sides):
            continue

        assets = list(tower_assets)
        rng.shuffle(assets)
        placed = False

        # Try the exact corner first, then move slightly inward if terrain or
        # water makes the exact point impossible.
        offsets: List[Tuple[int, int]] = [(0, 0)]
        toward_x = sign(settlement_center[0] - corner[0])
        toward_z = sign(settlement_center[1] - corner[1])
        for distance in range(1, WALL_TOWER_SEARCH_RADIUS + 1):
            offsets.extend(
                [
                    (toward_x * distance, 0),
                    (0, toward_z * distance),
                    (toward_x * distance, toward_z * distance),
                ]
            )

        for asset in assets:
            desired_facing = direction_to_facing(
                settlement_center[0] - corner[0],
                settlement_center[1] - corner[1],
            )
            rotation = rotation_to_face(
                asset.base_facing,
                desired_facing,
            )
            if rotation not in asset.allowed_rotations:
                rotation = asset.allowed_rotations[0]

            for offset_x, offset_z in offsets:
                pivot_x = corner[0] + offset_x
                pivot_z = corner[1] + offset_z
                pivot_y = choose_wall_pivot_y(
                    asset,
                    pivot_x,
                    pivot_z,
                    rotation,
                    heights,
                )
                if pivot_y is None:
                    continue
                world_pivot = (pivot_x, pivot_y, pivot_z)

                valid, _terrain_error, solid_xz = wall_placement_is_valid(
                    asset,
                    world_pivot,
                    rotation,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz | newly_occupied,
                    WALL_RELAXED_MAX_FLATTEN,
                )
                if not valid:
                    continue

                placements.append(
                    WallPlacement(
                        asset=asset,
                        side=corner_name,
                        rotation=rotation,
                        world_pivot=world_pivot,
                    )
                )
                newly_occupied.update(solid_xz)
                placed = True
                break
            if placed:
                break

        if not placed:
            print(
                f"WARNING: Could not place tower at {corner_name} corner."
            )

    return placements, newly_occupied


def plan_settlement_walls(
    plots: Sequence[Plot],
    wall_library: Dict[str, List[WallModuleAsset]],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    seed: int,
) -> Tuple[
    List[WallPlacement],
    Dict[str, str],
    List[dict],
    Optional[Rect],
]:
    if not GENERATE_WALLS:
        return [], {}, [], None

    perimeter, corner_clearance = settlement_wall_perimeter(
        plots,
        ba,
        wall_library["tower_wall"],
    )
    sides = make_wall_sides(perimeter)
    building_rects = [plot.rect for plot in plots]

    dry_sides: List[WallSide] = []
    side_status: Dict[str, str] = {}

    print(
        f"Planned wall perimeter: x {perimeter[0]}..{perimeter[2]}, "
        f"z {perimeter[1]}..{perimeter[3]}"
    )
    print("Checking each wall side for rivers/water...")

    for side in sides:
        skip, metrics = side_should_be_skipped_for_water(
            side,
            water_cells,
        )
        if skip:
            side_status[side.name] = f"SKIPPED WATER ({metrics})"
            print(f"  {side.name}: skipped — {metrics}")
        else:
            side_status[side.name] = f"DRY ({metrics})"
            dry_sides.append(side)
            print(f"  {side.name}: dry — {metrics}")

    placements: List[WallPlacement] = []
    occupied_wall_xz: Set[Pos2D] = set()
    gate_waypoints: List[dict] = []
    successful_sides: Set[str] = set()

    chain_assets = list(wall_library.get("straight_wall", []))
    chain_assets.extend(wall_library.get("oblique_wall", []))

    for side_index, side in enumerate(dry_sides):
        length = wall_side_length(side)
        side_ground_y = wall_side_ground_y(
            side,
            heights,
            water_blocked,
        )
        print(f"  {side.name}: shared wall ground Y={side_ground_y}")
        adjusted_start = wall_side_point(
            side,
            corner_clearance,
        )
        adjusted_end = wall_side_point(
            side,
            length - corner_clearance,
        )

        gate_result = choose_gate_placement(
            side,
            wall_library["main_gate"],
            corner_clearance,
            side_ground_y,
            ba,
            heights,
            water_blocked,
            building_rects,
            occupied_wall_xz,
            seed + side_index * 1009,
        )
        if gate_result is None:
            side_status[side.name] = "SKIPPED — no valid dry gate position"
            print(
                f"WARNING: {side.name} side was dry, but no valid gate "
                "position was found. The side will not be generated."
            )
            continue

        gate, gate_solid_xz = gate_result
        assert gate.start_connector_world is not None
        assert gate.end_connector_world is not None

        side_placements: List[WallPlacement] = [gate]
        side_occupied: Set[Pos2D] = set(gate_solid_xz)

        backward_direction = (
            -side.direction[0],
            -side.direction[1],
        )
        backward_chain, backward_occupied = extend_wall_chain(
            side.name,
            gate.start_connector_world,
            adjusted_start,
            backward_direction,
            side_ground_y,
            chain_assets,
            ba,
            heights,
            water_blocked,
            building_rects,
            occupied_wall_xz | side_occupied,
            seed + side_index * 2003 + 1,
        )
        side_placements.extend(backward_chain)
        side_occupied.update(backward_occupied)

        forward_chain, forward_occupied = extend_wall_chain(
            side.name,
            gate.end_connector_world,
            adjusted_end,
            side.direction,
            side_ground_y,
            chain_assets,
            ba,
            heights,
            water_blocked,
            building_rects,
            occupied_wall_xz | side_occupied,
            seed + side_index * 2003 + 2,
        )
        side_placements.extend(forward_chain)
        side_occupied.update(forward_occupied)

        placements.extend(side_placements)
        occupied_wall_xz.update(side_occupied)
        gate_waypoints.extend(gate_world_waypoints(gate))
        successful_sides.add(side.name)
        side_status[side.name] = (
            f"GENERATED — 1 gate, {len(side_placements) - 1} wall modules"
        )
        print(
            f"  {side.name}: generated with 1 gate and "
            f"{len(side_placements) - 1} straight/oblique modules."
        )

    towers, tower_occupied = place_corner_towers(
        perimeter,
        successful_sides,
        wall_library["tower_wall"],
        ba,
        heights,
        water_blocked,
        building_rects,
        occupied_wall_xz,
        seed,
    )
    placements.extend(towers)
    occupied_wall_xz.update(tower_occupied)

    return placements, side_status, gate_waypoints, perimeter


def prepare_wall_supports(
    blocks: List[dict],
    placements: Sequence[WallPlacement],
    heights: Dict[Pos2D, int],
    ba: dict,
    water_blocked: Set[Pos2D],
) -> int:
    """Prepare terrain using each module's explicit ground plane."""
    prepared_columns: Set[Tuple[int, int, int]] = set()

    for placement in placements:
        solid_xz = wall_module_solid_xz(
            placement.asset,
            placement.world_pivot,
            placement.rotation,
        )
        wall_ground_y = (
            placement.world_pivot[1]
            + placement.asset.ground_y
            - placement.asset.pivot[1]
        )

        for x, z in solid_xz:
            if (x, z) in water_blocked:
                continue
            if not in_build_area_xz(ba, x, z):
                continue

            key = (x, wall_ground_y, z)
            if key in prepared_columns:
                continue
            prepared_columns.add(key)

            existing_top = surface_top_y((x, z), heights)

            if existing_top < wall_ground_y:
                for y in range(existing_top + 1, wall_ground_y):
                    if in_build_area_xyz(ba, x, y, z):
                        blocks.append(b("dirt", x, y, z))
            elif existing_top > wall_ground_y:
                for y in range(
                    wall_ground_y,
                    min(ba["y2"], existing_top + WALL_TREE_CLEAR_HEIGHT) + 1,
                ):
                    blocks.append(b("air", x, y, z))

            for y in range(
                wall_ground_y + 1,
                min(
                    ba["y2"],
                    wall_ground_y + placement.asset.size_y + 3,
                ) + 1,
            ):
                blocks.append(b("air", x, y, z))

    return len(prepared_columns)


def place_wall_module_blocks(
    output: List[dict],
    placement: WallPlacement,
) -> int:
    entries = sorted(
        placement.asset.blocks,
        key=lambda entry: (
            int(entry.get("pos", [0, 0, 0])[1]),
            int(entry.get("pos", [0, 0, 0])[2]),
            int(entry.get("pos", [0, 0, 0])[0]),
        ),
    )
    count = 0

    for entry in entries:
        wx, wy, wz = wall_world_position(
            entry.get("pos", [0, 0, 0]),
            placement,
        )
        block_id = str(entry.get("id", "minecraft:air"))

        # Never replay exported air for modular walls. Adjacent modules overlap
        # slightly, and replaying air would erase logs, planks, banner supports,
        # torches, fences, and details from the neighboring module.
        if WALL_SKIP_JSON_AIR_BLOCKS and block_id in AIR_IDS:
            continue

        states = rotate_block_states(
            entry.get("states"),
            placement.rotation,
        )
        data = entry.get("data")
        output.append(
            b(
                block_id,
                wx,
                wy,
                wz,
                states,
                str(data) if data else None,
            )
        )
        count += 1

    return count


def build_wall_json_blocks(
    placements: Sequence[WallPlacement],
) -> Tuple[List[dict], List[dict], int, int, int]:
    all_wall_blocks: List[dict] = []
    total = 0

    for placement in placements:
        count = place_wall_module_blocks(
            all_wall_blocks,
            placement,
        )
        total += count

    banner_blocks = [
        block
        for block in all_wall_blocks
        if is_banner_block_id(str(block.get("id", "")))
    ]
    structural_blocks = [
        block
        for block in all_wall_blocks
        if not is_banner_block_id(str(block.get("id", "")))
    ]
    banners_with_data = sum(
        1
        for block in banner_blocks
        if block.get("data")
    )

    return (
        structural_blocks,
        banner_blocks,
        total,
        len(banner_blocks),
        banners_with_data,
    )


# ============================================================
# V16 overrides: balanced buildings + terrain-following contour walls
# ============================================================


def find_auto_building_plots(
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    altar: Plot,
    assets: Sequence[BuildingAsset],
    seed: int,
) -> List[Plot]:
    """Place discovered building types in balanced rounds.

    Each accepted round places at most one copy of every discovered normal
    building type. This keeps markets, watchtowers, houses, farms, barns, and
    blacksmiths within roughly one copy of each other without a hardcoded total.
    """
    if not assets:
        print("No repeatable normal-building assets were discovered.")
        return []

    rng = random.Random(seed + 45017)
    raw_candidates = generate_house_candidates(ba, altar.center, rng)

    seen: Set[Pos2D] = set()
    candidates: List[Pos2D] = []
    for point in raw_candidates:
        if point in seen:
            continue
        seen.add(point)
        candidates.append(point)

    candidates.sort(
        key=lambda point: (
            int(euclid(point, altar.center) // 7),
            stable_rng(seed, point[0], point[1], 991).random(),
        )
    )

    plots: List[Plot] = []
    occupied: List[Rect] = [altar.rect]
    usage_counts: Counter[str] = Counter()
    round_number = 0

    while candidates:
        round_number += 1
        staged_plots: List[Plot] = []
        staged_occupied = list(occupied)

        # Larger structures get first choice of terrain in every round.
        round_assets = sorted(
            assets,
            key=lambda asset: (
                -(asset.size_x * asset.size_z),
                stable_rng(
                    seed + round_number,
                    asset.size_x,
                    asset.size_z,
                    sum(ord(ch) for ch in asset.path.name),
                ).random(),
            ),
        )

        for asset_index, asset in enumerate(round_assets):
            best: Optional[Tuple[float, Pos2D, int, int, Rect]] = None
            scan_count = 0

            for candidate_index, candidate in enumerate(candidates):
                scan_count += 1
                if scan_count > AUTO_BUILDING_CANDIDATE_SCAN_LIMIT:
                    break

                waypoint = asset.waypoints[0]
                original_facing = waypoint.get("direction", "north")
                desired_facing = direction_to_facing(
                    altar.center[0] - candidate[0],
                    altar.center[1] - candidate[1],
                )
                rotation = rotation_to_face(original_facing, desired_facing)
                width, depth = rotated_dimensions(asset, rotation)
                min_distance = (
                    max(
                        altar.rotated_width or altar.size,
                        altar.rotated_depth or altar.size,
                    )
                    / 2
                    + max(width, depth) / 2
                    + BUILDING_SPACING
                    + 2
                )

                result = evaluate_rectangular_plot(
                    candidate,
                    width,
                    depth,
                    ba,
                    heights,
                    water_cells,
                    staged_occupied,
                    BUILDING_MAX_FLATTEN,
                    altar.center,
                    min_distance,
                    BUILDING_SPACING,
                    build_area_margin=AUTO_BUILDING_EDGE_RESERVE,
                )
                if result is None and RELAX_IF_NEEDED:
                    result = evaluate_rectangular_plot(
                        candidate,
                        width,
                        depth,
                        ba,
                        heights,
                        water_cells,
                        staged_occupied,
                        RELAXED_BUILDING_MAX_FLATTEN,
                        altar.center,
                        min_distance,
                        BUILDING_SPACING,
                        build_area_margin=AUTO_BUILDING_EDGE_RESERVE,
                    )
                if result is None:
                    continue

                terrain_score, target, rect = result
                randomness = stable_rng(
                    seed + round_number * 1009 + asset_index * 97,
                    candidate[0],
                    candidate[1],
                    candidate_index,
                ).random() * AUTO_BUILDING_RANDOMNESS
                score = terrain_score + randomness

                if best is None or score < best[0]:
                    best = (score, candidate, target, rotation, rect)

            if best is None:
                continue

            _score, center, target, rotation, rect = best
            plot = make_json_plot(
                asset,
                center,
                target,
                rect,
                rotation,
                kind="building",
            )
            staged_plots.append(plot)
            staged_occupied.append(rect)

        remaining_capacity = (
            AUTO_BUILDING_MAX_TOTAL - len(plots)
            if AUTO_BUILDING_MAX_TOTAL > 0
            else len(staged_plots)
        )
        if AUTO_BUILDING_MAX_TOTAL > 0:
            if remaining_capacity <= 0:
                print(
                    f"Reached per-settlement building cap: "
                    f"{AUTO_BUILDING_MAX_TOTAL}."
                )
                break
            staged_plots = staged_plots[:remaining_capacity]

        minimum_required = max(
            1,
            math.ceil(len(assets) * AUTO_BUILDING_MIN_ROUND_COVERAGE),
        )
        if AUTO_BUILDING_MAX_TOTAL > 0:
            minimum_required = min(minimum_required, remaining_capacity)

        if len(staged_plots) < minimum_required:
            print(
                f"Balanced building round {round_number} stopped: "
                f"only {len(staged_plots)}/{len(assets)} types still fit "
                f"(minimum accepted={minimum_required})."
            )
            break

        plots.extend(staged_plots)
        occupied.extend(plot.rect for plot in staged_plots)

        for plot in staged_plots:
            assert plot.asset is not None
            usage_counts[plot.asset.path.name] += 1
            print(
                f"Balanced building {len(plots):03d}: {plot.asset.name}, "
                f"round={round_number}, center={plot.center}, "
                f"size={plot.rotated_width}x{plot.rotated_depth}, "
                f"rotation={plot.rotation}°"
            )

        # Remove candidate centers close to any newly accepted footprint.
        new_rects = [plot.rect for plot in staged_plots]
        candidates = [
            point
            for point in candidates
            if not any(
                rects_overlap(
                    (point[0], point[1], point[0], point[1]),
                    rect,
                    margin=BUILDING_SPACING + 3,
                )
                for rect in new_rects
            )
        ]

    print(
        f"Balanced automatic fill placed {len(plots)} repeatable buildings "
        f"across {round_number - 1 if round_number else 0} accepted round(s)."
    )
    print("Balanced building type counts:")
    for asset in sorted(assets, key=lambda item: item.path.name):
        print(f"  {asset.path.name}: {usage_counts.get(asset.path.name, 0)}")

    if usage_counts:
        spread = max(usage_counts.values()) - min(
            usage_counts.get(asset.path.name, 0) for asset in assets
        )
        if spread > AUTO_BUILDING_FINAL_COUNT_SPREAD:
            print(
                f"WARNING: final building-count spread is {spread}; "
                "terrain prevented a perfectly even final round."
            )

    return plots


@dataclass
class WallPlacement:
    asset: WallModuleAsset
    side: str
    rotation: int
    world_pivot: Tuple[int, int, int]
    start_connector_name: Optional[str] = None
    end_connector_name: Optional[str] = None
    start_connector_world: Optional[Tuple[int, int, int]] = None
    end_connector_world: Optional[Tuple[int, int, int]] = None
    seam_previous_world: Optional[Tuple[int, int, int]] = None


@dataclass
class WallSide:
    name: str
    start: Pos2D
    end: Pos2D
    direction: Dir2D
    corner_start: str
    corner_end: str
    outward_facing: str = "north"
    macro_side: str = "north"
    outward_vector: Dir2D = (0, -1)


def wall_side_length(side: WallSide) -> int:
    """Length in 8-connected steps, supporting cardinal and diagonal sides."""
    return max(
        abs(side.end[0] - side.start[0]),
        abs(side.end[1] - side.start[1]),
    )


def wall_side_point(side: WallSide, distance: int) -> Pos2D:
    return (
        side.start[0] + side.direction[0] * distance,
        side.start[1] + side.direction[1] * distance,
    )


def _rotate_dir_vector(vector: Dir2D, rotation: int) -> Dir2D:
    x, z = vector
    turns = (rotation // 90) % 4
    for _ in range(turns):
        x, z = -z, x
    return sign(x), sign(z)


def _asset_visible_front_vector(
    asset: WallModuleAsset,
    rotation: int,
) -> Dir2D:
    """Infer the visible wall front from its first saved banner state."""
    for entry in asset.blocks:
        block_id = str(entry.get("id", ""))
        if not is_banner_block_id(block_id):
            continue
        states = entry.get("states") or {}
        if block_id.endswith("_wall_banner"):
            facing = str(states.get("facing", asset.base_facing))
            base_vector = facing_to_vec(facing)
            return _rotate_dir_vector(base_vector, rotation)
        if block_id.endswith("_banner"):
            try:
                banner_rotation = int(states.get("rotation", 0)) % 16
            except (TypeError, ValueError):
                banner_rotation = 0
            angle = math.radians(banner_rotation * 22.5)
            # Java standing-banner rotation: 0=south, 4=west,
            # 8=north, and 12=east.
            base_vector = (
                sign(int(round(-math.sin(angle) * 1000))),
                sign(int(round(math.cos(angle) * 1000))),
            )
            return _rotate_dir_vector(base_vector, rotation)

    return _rotate_dir_vector(
        facing_to_vec(asset.base_facing),
        rotation,
    )


def wall_connector_options(
    asset: WallModuleAsset,
    desired_direction: Dir2D,
    desired_outward_facing: Optional[Any] = None,
) -> List[Tuple[float, int, int, int, Tuple[int, int, int], Tuple[int, int, int]]]:
    """Return connector options aligned along a contour and facing outward."""
    dx, dz = desired_direction
    options: List[
        Tuple[
            float,
            int,
            int,
            int,
            Tuple[int, int, int],
            Tuple[int, int, int],
        ]
    ] = []

    for rotation in asset.allowed_rotations:
        offsets = [
            rotate_wall_offset(
                connector.get("pos", [0, 0, 0]),
                asset.pivot,
                rotation,
            )
            for connector in asset.connectors
        ]
        rotated_front_vector = _asset_visible_front_vector(asset, rotation)
        facing_penalty = 0.0
        if desired_outward_facing:
            if isinstance(desired_outward_facing, str):
                desired_vector = facing_to_vec(desired_outward_facing)
            else:
                desired_vector = (
                    int(desired_outward_facing[0]),
                    int(desired_outward_facing[1]),
                )
            dot = (
                rotated_front_vector[0] * desired_vector[0]
                + rotated_front_vector[1] * desired_vector[1]
            )
            if dot <= 0:
                facing_penalty = WALL_OUTWARD_FACING_PENALTY
            elif rotated_front_vector != desired_vector:
                facing_penalty = WALL_OUTWARD_FACING_PENALTY * 0.20

        for start_index in range(len(offsets)):
            for end_index in range(len(offsets)):
                if start_index == end_index:
                    continue
                start_offset = offsets[start_index]
                end_offset = offsets[end_index]
                delta_x = end_offset[0] - start_offset[0]
                delta_z = end_offset[2] - start_offset[2]
                along = delta_x * dx + delta_z * dz
                perpendicular = abs(
                    delta_x * (-dz) + delta_z * dx
                )
                if along < 2:
                    continue

                score = (
                    perpendicular * 100.0
                    - along * 0.01
                    + facing_penalty
                )
                options.append(
                    (
                        score,
                        rotation,
                        start_index,
                        end_index,
                        start_offset,
                        end_offset,
                    )
                )

    options.sort(key=lambda item: item[0])
    return options


def _octilinear_contour_vertices(
    plots: Sequence[Plot],
    ba: dict,
) -> List[Pos2D]:
    """Build an axis/diagonal convex envelope around all final buildings."""
    points: List[Pos2D] = []
    for plot in plots:
        x0, z0, x1, z1 = plot.rect
        points.extend([(x0, z0), (x1, z0), (x1, z1), (x0, z1)])

    if not points:
        raise ValueError("Cannot make a wall contour without buildings")

    margin = WALL_PERIMETER_MARGIN
    diagonal_margin = int(
        round(margin * WALL_CONTOUR_DIAGONAL_MARGIN_SCALE)
    )
    safe = 6

    xmin = max(ba["x1"] + safe, min(x for x, _ in points) - margin)
    xmax = min(ba["x2"] - safe, max(x for x, _ in points) + margin)
    zmin = max(ba["z1"] + safe, min(z for _, z in points) - margin)
    zmax = min(ba["z2"] - safe, max(z for _, z in points) + margin)

    smin = min(x + z for x, z in points) - diagonal_margin
    smax = max(x + z for x, z in points) + diagonal_margin
    dmin = min(x - z for x, z in points) - diagonal_margin
    dmax = max(x - z for x, z in points) + diagonal_margin

    # Boundary lines a*x + b*z = c.
    lines = [
        (1.0, 0.0, float(xmin)),
        (1.0, 0.0, float(xmax)),
        (0.0, 1.0, float(zmin)),
        (0.0, 1.0, float(zmax)),
        (1.0, 1.0, float(smin)),
        (1.0, 1.0, float(smax)),
        (1.0, -1.0, float(dmin)),
        (1.0, -1.0, float(dmax)),
    ]

    def inside(x: float, z: float, tolerance: float = 1.5) -> bool:
        return (
            xmin - tolerance <= x <= xmax + tolerance
            and zmin - tolerance <= z <= zmax + tolerance
            and smin - tolerance <= x + z <= smax + tolerance
            and dmin - tolerance <= x - z <= dmax + tolerance
        )

    vertices: Set[Pos2D] = set()
    for i, (a1, b1, c1) in enumerate(lines):
        for a2, b2, c2 in lines[i + 1:]:
            determinant = a1 * b2 - a2 * b1
            if abs(determinant) < 1e-9:
                continue
            x = (c1 * b2 - c2 * b1) / determinant
            z = (a1 * c2 - a2 * c1) / determinant
            if not inside(x, z):
                continue
            point = (int(round(x)), int(round(z)))
            if inside(point[0], point[1], tolerance=2.0):
                vertices.add(point)

    if len(vertices) < 4:
        return [(xmin, zmin), (xmax, zmin), (xmax, zmax), (xmin, zmax)]

    center_x = sum(x for x, _ in vertices) / len(vertices)
    center_z = sum(z for _, z in vertices) / len(vertices)
    ordered = sorted(
        vertices,
        key=lambda point: math.atan2(
            point[1] - center_z,
            point[0] - center_x,
        ),
    )

    # Remove collinear duplicate vertices.
    changed = True
    while changed and len(ordered) > 4:
        changed = False
        cleaned: List[Pos2D] = []
        count = len(ordered)
        for index, current in enumerate(ordered):
            previous = ordered[(index - 1) % count]
            following = ordered[(index + 1) % count]
            cross = (
                (current[0] - previous[0])
                * (following[1] - current[1])
                - (current[1] - previous[1])
                * (following[0] - current[0])
            )
            if cross == 0:
                changed = True
                continue
            cleaned.append(current)
        ordered = cleaned

    area2 = sum(
        ordered[i][0] * ordered[(i + 1) % len(ordered)][1]
        - ordered[(i + 1) % len(ordered)][0] * ordered[i][1]
        for i in range(len(ordered))
    )
    if area2 < 0:
        ordered.reverse()

    return ordered


def _contour_segments(
    vertices: Sequence[Pos2D],
    settlement_center: Pos2D,
) -> List[WallSide]:
    """Convert the polygon to cardinal/diagonal constant-direction runs."""
    raw_segments: List[WallSide] = []
    sequence_number = 0

    for edge_index in range(len(vertices)):
        start = vertices[edge_index]
        end = vertices[(edge_index + 1) % len(vertices)]
        path = line_2d(start, end)
        if len(path) < 2:
            continue

        run_start = path[0]
        previous_step = (
            sign(path[1][0] - path[0][0]),
            sign(path[1][1] - path[0][1]),
        )

        for index in range(2, len(path) + 1):
            at_end = index == len(path)
            step = None
            if not at_end:
                step = (
                    sign(path[index][0] - path[index - 1][0]),
                    sign(path[index][1] - path[index - 1][1]),
                )

            if at_end or step != previous_step:
                run_end = path[index - 1]
                if run_start != run_end:
                    midpoint = (
                        (run_start[0] + run_end[0]) // 2,
                        (run_start[1] + run_end[1]) // 2,
                    )
                    macro = direction_to_facing(
                        midpoint[0] - settlement_center[0],
                        midpoint[1] - settlement_center[1],
                    )
                    sequence_number += 1
                    raw_segments.append(
                        WallSide(
                            name=f"{macro}_{sequence_number}",
                            start=run_start,
                            end=run_end,
                            direction=previous_step,
                            corner_start=f"v{edge_index}",
                            corner_end=f"v{(edge_index + 1) % len(vertices)}",
                            outward_facing=direction_to_facing(
                                previous_step[1],
                                -previous_step[0],
                            ),
                            macro_side=macro,
                            outward_vector=(
                                previous_step[1],
                                -previous_step[0],
                            ),
                        )
                    )
                if not at_end:
                    run_start = path[index - 1]
                    previous_step = step  # type: ignore[assignment]

    # Merge adjacent runs with exactly the same direction and macro side.
    merged: List[WallSide] = []
    for segment in raw_segments:
        if (
            merged
            and merged[-1].end == segment.start
            and merged[-1].direction == segment.direction
            and merged[-1].macro_side == segment.macro_side
        ):
            merged[-1].end = segment.end
            merged[-1].corner_end = segment.corner_end
        else:
            merged.append(segment)

    return [
        segment
        for segment in merged
        if wall_side_length(segment) >= WALL_MIN_SEGMENT_LENGTH
    ]


def _macro_side_water_status(
    segments: Sequence[WallSide],
    water_cells: Set[Pos2D],
) -> Tuple[bool, str]:
    wet_count = 0
    point_count = 0
    longest = 0

    for segment in segments:
        segment_wet, segment_ratio, segment_longest = wall_side_water_metrics(
            segment,
            water_cells,
        )
        segment_points = wall_side_length(segment) + 1
        wet_count += segment_wet
        point_count += segment_points
        longest = max(longest, segment_longest)

    ratio = wet_count / max(1, point_count)
    skip = (
        longest >= WALL_SIDE_MIN_WATER_RUN
        or ratio >= WALL_SIDE_WATER_RATIO_THRESHOLD
    )
    return skip, (
        f"water hits={wet_count}, ratio={ratio:.1%}, longest run={longest}"
    )


def _terrain_following_placement(
    asset: WallModuleAsset,
    side_name: str,
    rotation: int,
    start_index: int,
    end_index: int,
    start_offset: Tuple[int, int, int],
    end_offset: Tuple[int, int, int],
    desired_start_world: Tuple[int, int, int],
    heights: Dict[Pos2D, int],
) -> Optional[WallPlacement]:
    pivot_x = desired_start_world[0] - start_offset[0]
    pivot_z = desired_start_world[2] - start_offset[2]
    ideal_pivot_y = choose_wall_pivot_y(
        asset,
        pivot_x,
        pivot_z,
        rotation,
        heights,
    )
    if ideal_pivot_y is None:
        return None

    ideal_start_y = ideal_pivot_y + start_offset[1]
    minimum_y = desired_start_world[1] - WALL_MAX_SEAM_STEP
    maximum_y = desired_start_world[1] + WALL_MAX_SEAM_STEP
    start_y = max(minimum_y, min(maximum_y, ideal_start_y))
    pivot_y = start_y - start_offset[1]

    world_pivot = (pivot_x, pivot_y, pivot_z)
    actual_start = connector_world_from_option(world_pivot, start_offset)
    actual_end = connector_world_from_option(world_pivot, end_offset)

    return WallPlacement(
        asset=asset,
        side=side_name,
        rotation=rotation,
        world_pivot=world_pivot,
        start_connector_name=str(
            asset.connectors[start_index].get("name", f"connector_{start_index}")
        ),
        end_connector_name=str(
            asset.connectors[end_index].get("name", f"connector_{end_index}")
        ),
        start_connector_world=actual_start,
        end_connector_world=actual_end,
        seam_previous_world=(
            desired_start_world
            if actual_start[1] != desired_start_world[1]
            else None
        ),
    )


def choose_gate_placement(
    side: WallSide,
    gate_assets: Sequence[WallModuleAsset],
    corner_clearance: int,
    side_ground_y: int,
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    seed: int,
    outward_facing: Optional[str] = None,
) -> Optional[Tuple[WallPlacement, Set[Pos2D]]]:
    del side_ground_y  # V16 chooses terrain Y independently at the gate.
    length = wall_side_length(side)
    usable_start = max(1, corner_clearance)
    usable_end = length - max(1, corner_clearance)
    if usable_end - usable_start < 5:
        return None

    rng = random.Random(seed + sum(ord(c) for c in side.name) * 997)
    distances = list(range(usable_start, usable_end + 1))
    rng.shuffle(distances)

    preferred_low = int(
        usable_start
        + (usable_end - usable_start) * WALL_GATE_MIN_FRACTION
    )
    preferred_high = int(
        usable_start
        + (usable_end - usable_start) * WALL_GATE_MAX_FRACTION
    )
    distances.sort(
        key=lambda value: (
            0 if preferred_low <= value <= preferred_high else 1,
            rng.random(),
        )
    )

    attempts = 0
    for target_distance in distances:
        if attempts >= WALL_GATE_POSITION_ATTEMPTS:
            break
        attempts += 1
        target_x, target_z = wall_side_point(side, target_distance)

        randomized_assets = list(gate_assets)
        rng.shuffle(randomized_assets)
        for asset in randomized_assets:
            options = wall_connector_options(
                asset,
                side.direction,
                outward_facing or side.outward_facing,
            )
            for option in options[:12]:
                (
                    _alignment_score,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                ) = option

                midpoint_x = (start_offset[0] + end_offset[0]) / 2.0
                midpoint_z = (start_offset[2] + end_offset[2]) / 2.0
                pivot_x = int(round(target_x - midpoint_x))
                pivot_z = int(round(target_z - midpoint_z))
                pivot_y = choose_wall_pivot_y(
                    asset,
                    pivot_x,
                    pivot_z,
                    rotation,
                    heights,
                )
                if pivot_y is None:
                    continue

                world_pivot = (pivot_x, pivot_y, pivot_z)
                start_world = connector_world_from_option(
                    world_pivot,
                    start_offset,
                )
                end_world = connector_world_from_option(
                    world_pivot,
                    end_offset,
                )
                placement = WallPlacement(
                    asset=asset,
                    side=side.name,
                    rotation=rotation,
                    world_pivot=world_pivot,
                    start_connector_name=str(
                        asset.connectors[start_index].get("name", "start")
                    ),
                    end_connector_name=str(
                        asset.connectors[end_index].get("name", "end")
                    ),
                    start_connector_world=start_world,
                    end_connector_world=end_world,
                )

                valid, _terrain_error, solid_xz = wall_placement_is_valid(
                    asset,
                    world_pivot,
                    rotation,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz,
                    WALL_MAX_FLATTEN,
                )
                if not valid:
                    valid, _terrain_error, solid_xz = wall_placement_is_valid(
                        asset,
                        world_pivot,
                        rotation,
                        ba,
                        heights,
                        water_blocked,
                        building_rects,
                        occupied_wall_xz,
                        WALL_RELAXED_MAX_FLATTEN,
                    )
                if valid:
                    return placement, solid_xz

    return None


def extend_wall_chain(
    side_name: str,
    current_connector: Tuple[int, int, int],
    target: Pos2D,
    desired_direction: Dir2D,
    side_ground_y: int,
    module_assets: Sequence[WallModuleAsset],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    seed: int,
    outward_facing: Optional[str] = None,
) -> Tuple[List[WallPlacement], Set[Pos2D]]:
    del side_ground_y  # V16 follows terrain module by module.
    placements: List[WallPlacement] = []
    newly_occupied: Set[Pos2D] = set()
    rng = random.Random(
        seed
        + sum(ord(c) for c in side_name) * 1777
        + current_connector[0] * 13
        + current_connector[2] * 17
    )

    current = current_connector
    iterations = 0
    while iterations < WALL_MAX_MODULES_PER_CHAIN:
        iterations += 1
        remaining = chain_target_remaining(current, target, desired_direction)
        if remaining <= WALL_END_GAP_TOLERANCE:
            break

        candidates: List[Tuple[float, WallPlacement, Set[Pos2D]]] = []
        randomized_assets = list(module_assets)
        rng.shuffle(randomized_assets)

        for asset in randomized_assets:
            options = wall_connector_options(
                asset,
                desired_direction,
                outward_facing,
            )
            for option in options[:16]:
                (
                    alignment_score,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                ) = option

                placement = _terrain_following_placement(
                    asset,
                    side_name,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                    current,
                    heights,
                )
                if placement is None or placement.end_connector_world is None:
                    continue

                end_world = placement.end_connector_world
                progress = (
                    (end_world[0] - current[0]) * desired_direction[0]
                    + (end_world[2] - current[2]) * desired_direction[1]
                )
                perpendicular = abs(
                    (end_world[0] - current[0]) * (-desired_direction[1])
                    + (end_world[2] - current[2]) * desired_direction[0]
                )

                if progress < 2:
                    continue
                if progress > remaining + WALL_END_GAP_TOLERANCE:
                    continue
                if perpendicular > WALL_MAX_PERPENDICULAR_DRIFT:
                    continue

                valid, terrain_error, solid_xz = wall_placement_is_valid(
                    asset,
                    placement.world_pivot,
                    rotation,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz | newly_occupied,
                    WALL_MAX_FLATTEN,
                )
                if not valid:
                    valid, terrain_error, solid_xz = wall_placement_is_valid(
                        asset,
                        placement.world_pivot,
                        rotation,
                        ba,
                        heights,
                        water_blocked,
                        building_rects,
                        occupied_wall_xz | newly_occupied,
                        WALL_RELAXED_MAX_FLATTEN,
                    )
                if not valid:
                    continue

                end_remaining = chain_target_remaining(
                    end_world,
                    target,
                    desired_direction,
                )
                type_penalty = (
                    WALL_OBLIQUE_PENALTY
                    if asset.module_type == "oblique_wall"
                    else 0.0
                )
                seam_step = abs(
                    placement.start_connector_world[1] - current[1]
                ) if placement.start_connector_world else 0

                score = (
                    alignment_score
                    + perpendicular * 35.0
                    + terrain_error * 8.0
                    + type_penalty
                    + seam_step * WALL_SEAM_STEP_PENALTY
                    + max(0, WALL_END_GAP_TOLERANCE - end_remaining) * 3.0
                    + rng.random() * 0.25
                )
                candidates.append((score, placement, solid_xz))

        if not candidates:
            print(
                f"  {side_name} chain stopped with {remaining} blocks "
                "remaining before its contour vertex."
            )
            break

        candidates.sort(key=lambda item: item[0])
        _score, chosen, solid_xz = candidates[0]
        placements.append(chosen)
        newly_occupied.update(solid_xz)
        assert chosen.end_connector_world is not None
        current = chosen.end_connector_world

    return placements, newly_occupied


def _place_contour_towers(
    vertices: Sequence[Pos2D],
    active_macro_sides: Set[str],
    tower_assets: Sequence[WallModuleAsset],
    settlement_center: Pos2D,
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    seed: int,
) -> List[WallPlacement]:
    placements: List[WallPlacement] = []
    if not tower_assets:
        return placements

    rng = random.Random(seed + 88001)
    candidate_vertices = list(vertices)[:WALL_MAX_CONTOUR_TOWERS]

    for index, vertex in enumerate(candidate_vertices):
        outward = direction_to_facing(
            vertex[0] - settlement_center[0],
            vertex[1] - settlement_center[1],
        )
        if outward not in active_macro_sides:
            # Keep endpoint towers only where a generated contour side exists.
            continue

        assets = list(tower_assets)
        rng.shuffle(assets)
        placed = False
        for asset in assets:
            rotation = rotation_to_face(asset.base_facing, outward)
            if rotation not in asset.allowed_rotations:
                rotation = asset.allowed_rotations[0]
            pivot_y = choose_wall_pivot_y(
                asset,
                vertex[0],
                vertex[1],
                rotation,
                heights,
            )
            if pivot_y is None:
                continue
            world_pivot = (vertex[0], pivot_y, vertex[1])
            valid, _terrain_error, _solid = wall_placement_is_valid(
                asset,
                world_pivot,
                rotation,
                ba,
                heights,
                water_blocked,
                building_rects,
                set(),  # towers may cover/hide wall-chain corner seams
                WALL_RELAXED_MAX_FLATTEN,
            )
            if not valid:
                continue
            placements.append(
                WallPlacement(
                    asset=asset,
                    side=f"contour_vertex_{index}",
                    rotation=rotation,
                    world_pivot=world_pivot,
                )
            )
            placed = True
            break

        if not placed:
            print(f"WARNING: no tower fit at contour vertex {vertex}.")

    return placements


def plan_settlement_walls(
    plots: Sequence[Plot],
    wall_library: Dict[str, List[WallModuleAsset]],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Dict[str, str], List[dict], Optional[Rect]]:
    if not GENERATE_WALLS:
        return [], {}, [], None

    vertices = _octilinear_contour_vertices(plots, ba)
    settlement_center = (
        int(round(sum(x for x, _ in vertices) / len(vertices))),
        int(round(sum(z for _, z in vertices) / len(vertices))),
    )
    segments = _contour_segments(vertices, settlement_center)
    building_rects = [plot.rect for plot in plots]

    print("Planned terrain-following octilinear wall contour:")
    print("  vertices: " + " -> ".join(str(vertex) for vertex in vertices))
    print(f"  contour segments: {len(segments)}")

    grouped: Dict[str, List[WallSide]] = {
        "north": [],
        "east": [],
        "south": [],
        "west": [],
    }
    for segment in segments:
        grouped[segment.macro_side].append(segment)

    side_status: Dict[str, str] = {}
    active_macro_sides: Set[str] = set()
    for macro, macro_segments in grouped.items():
        if not macro_segments:
            side_status[macro] = "SKIPPED — no contour segment"
            continue
        skip, reason = _macro_side_water_status(macro_segments, water_cells)
        if skip:
            side_status[macro] = f"SKIPPED WATER ({reason})"
            print(f"  {macro}: skipped — {reason}")
        else:
            side_status[macro] = f"DRY ({reason})"
            active_macro_sides.add(macro)
            print(f"  {macro}: dry — {reason}")

    chain_assets = list(wall_library.get("straight_wall", []))
    chain_assets.extend(wall_library.get("oblique_wall", []))
    placements: List[WallPlacement] = []
    occupied_wall_xz: Set[Pos2D] = set()
    gate_waypoints: List[dict] = []

    for macro_index, macro in enumerate(("north", "east", "south", "west")):
        if macro not in active_macro_sides:
            continue
        macro_segments = grouped[macro]
        cardinal_gate_candidates = [
            segment
            for segment in macro_segments
            if abs(segment.direction[0]) + abs(segment.direction[1]) == 1
            and wall_side_length(segment) >= 12
        ]
        gate_candidates = cardinal_gate_candidates or [
            segment
            for segment in macro_segments
            if wall_side_length(segment) >= 12
        ]
        if not gate_candidates:
            gate_candidates = list(macro_segments)
        gate_segment = max(
            gate_candidates,
            key=lambda segment: wall_side_length(segment),
        )
        ordered_macro_segments = [gate_segment] + [
            segment for segment in macro_segments if segment is not gate_segment
        ]

        macro_module_count = 0
        macro_gate_count = 0
        for segment_index, segment in enumerate(ordered_macro_segments):
            length = wall_side_length(segment)
            if length < WALL_MIN_SEGMENT_LENGTH:
                continue

            if segment is gate_segment:
                gate_result = choose_gate_placement(
                    segment,
                    wall_library["main_gate"],
                    corner_clearance=1,
                    side_ground_y=0,
                    ba=ba,
                    heights=heights,
                    water_blocked=water_blocked,
                    building_rects=building_rects,
                    occupied_wall_xz=occupied_wall_xz,
                    seed=seed + macro_index * 1009,
                    outward_facing=segment.outward_vector,
                )
                if gate_result is None:
                    print(
                        f"WARNING: {macro} contour was dry but no gate fit; "
                        "that macro side is skipped."
                    )
                    side_status[macro] = "SKIPPED — no valid gate position"
                    active_macro_sides.discard(macro)
                    break

                gate, gate_solid = gate_result
                placements.append(gate)
                occupied_wall_xz.update(gate_solid)
                gate_waypoints.extend(gate_world_waypoints(gate))
                macro_gate_count = 1

                assert gate.start_connector_world is not None
                assert gate.end_connector_world is not None

                back_chain, back_solid = extend_wall_chain(
                    segment.name,
                    gate.start_connector_world,
                    segment.start,
                    (-segment.direction[0], -segment.direction[1]),
                    0,
                    chain_assets,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz,
                    seed + macro_index * 2003 + segment_index * 31 + 1,
                    outward_facing=segment.outward_vector,
                )
                placements.extend(back_chain)
                occupied_wall_xz.update(back_solid)
                macro_module_count += len(back_chain)

                forward_chain, forward_solid = extend_wall_chain(
                    segment.name,
                    gate.end_connector_world,
                    segment.end,
                    segment.direction,
                    0,
                    chain_assets,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz,
                    seed + macro_index * 2003 + segment_index * 31 + 2,
                    outward_facing=segment.outward_vector,
                )
                placements.extend(forward_chain)
                occupied_wall_xz.update(forward_solid)
                macro_module_count += len(forward_chain)
            else:
                start_y = surface_top_y(segment.start, heights)
                start_connector = (
                    segment.start[0],
                    start_y,
                    segment.start[1],
                )
                chain, solid = extend_wall_chain(
                    segment.name,
                    start_connector,
                    segment.end,
                    segment.direction,
                    0,
                    chain_assets,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz,
                    seed + macro_index * 3001 + segment_index * 43,
                    outward_facing=segment.outward_vector,
                )
                placements.extend(chain)
                occupied_wall_xz.update(solid)
                macro_module_count += len(chain)

        if macro in active_macro_sides:
            side_status[macro] = (
                f"GENERATED — {macro_gate_count} gate, "
                f"{macro_module_count} terrain-following wall modules"
            )

    towers = _place_contour_towers(
        vertices,
        active_macro_sides,
        wall_library.get("tower_wall", []),
        settlement_center,
        ba,
        heights,
        water_blocked,
        building_rects,
        seed,
    )
    placements.extend(towers)

    bounding_rect: Rect = (
        min(x for x, _ in vertices),
        min(z for _, z in vertices),
        max(x for x, _ in vertices),
        max(z for _, z in vertices),
    )
    return placements, side_status, gate_waypoints, bounding_rect


def prepare_wall_supports(
    blocks: List[dict],
    placements: Sequence[WallPlacement],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
    water_cells: Set[Pos2D],
) -> int:
    """Support walls without excavation, including modules placed over water.

    Dry terrain is never dug down. A water footprint is packed from its ocean
    floor to one block below the module using sand in Desert and dirt elsewhere.
    Only vegetation/air above the supported wall elevation is cleared.
    """
    prepared_columns: Set[Tuple[int, int, int]] = set()
    fill_block = "minecraft:sand" if ACTIVE_TRIBE == "desert" else "minecraft:dirt"

    for placement in placements:
        solid_xz = wall_module_solid_xz(
            placement.asset,
            placement.world_pivot,
            placement.rotation,
        )
        wall_ground_y = (
            placement.world_pivot[1]
            + placement.asset.ground_y
            - placement.asset.pivot[1]
        )

        for x, z in solid_xz:
            if not in_build_area_xz(ba, x, z):
                continue
            key = (x, wall_ground_y, z)
            if key in prepared_columns:
                continue
            prepared_columns.add(key)

            support_top = wall_ground_y - 1
            if (x, z) in water_cells:
                existing_top = floor_heights.get((x, z), heights.get((x, z), support_top + 1)) - 1
                old_water_top = heights.get((x, z), existing_top + 1) - 1
                fill_top = max(support_top, old_water_top)
            else:
                existing_top = surface_top_y((x, z), heights)
                fill_top = support_top

            # Fill-first support. Water footprints are packed from the actual
            # ocean/river floor through the old liquid surface, never just a
            # shallow cap beneath the module.
            fill_start = min(existing_top + 1, fill_top)
            for y in range(fill_start, fill_top + 1):
                if in_build_area_xyz(ba, x, y, z):
                    blocks.append(b(fill_block, x, y, z))

            # Clear only above the natural/support surface. Never excavate terrain.
            clear_start = max(support_top + 2, wall_ground_y + 1)
            clear_end = min(
                ba["y2"],
                wall_ground_y + placement.asset.size_y + 2,
            )
            for y in range(clear_start, clear_end + 1):
                blocks.append(b("air", x, y, z))

        if (
            placement.seam_previous_world is not None
            and placement.start_connector_world is not None
        ):
            previous = placement.seam_previous_world
            current = placement.start_connector_world
            for x, z in line_2d(
                (previous[0], previous[2]),
                (current[0], current[2]),
            ):
                for y in range(
                    min(previous[1], current[1]),
                    max(previous[1], current[1]) + 1,
                ):
                    if in_build_area_xyz(ba, x, y, z):
                        blocks.append(b(WALL_SEAM_FILL_BLOCK, x, y, z))

    return len(prepared_columns)

# ============================================================
# V17 overrides
# - Load only the active tribe folder (builds/plains, builds/desert, ...)
# - Generate every dry wall run around the complete final settlement contour
# - Never place a solid wall footprint over water
# - Protect and clear the intended main-gate passage after neighboring walls
# ============================================================

RUN_MODE = (
    sys.argv[1] if len(sys.argv) > 1
    else os.environ.get("GDMC_ACTIVE_TRIBE", "plains")
).strip().lower()
WORLD_MODE_ALIASES = {"world", "auto", "all", "multi", "multitribe", "--world"}
WORLD_MODE = RUN_MODE in WORLD_MODE_ALIASES
SUPPORTED_TRIBES = ("plains", "desert", "savanna", "taiga")

if not WORLD_MODE and RUN_MODE not in SUPPORTED_TRIBES:
    raise SystemExit(
        "Usage: python main_multitribe_1000.py "
        "[world|plains|desert|savanna|taiga]"
    )

# World mode reconfigures these globals before each settlement. Plains is only
# the harmless initial value used while the module is loading.
ACTIVE_TRIBE = "plains" if WORLD_MODE else RUN_MODE
BUILDINGS_ROOT = Path(
    os.environ.get(
        "GDMC_BUILDINGS_ROOT",
        str(Path.home() / "Downloads" / "gdmc_main" / "builds"),
    )
)

TRIBE_LANDMARK_FILENAMES: Dict[str, str] = {
    "plains": "gathering_hall.json",
    "desert": "sacrificial_pit.json",
    "savanna": "holy_fountain.json",
    "taiga": "tree_of_life.json",
}

BUILDINGS_DIR = BUILDINGS_ROOT / ACTIVE_TRIBE
LANDMARK_FILENAME = TRIBE_LANDMARK_FILENAMES[ACTIVE_TRIBE]
WALL_TRIBE = ACTIVE_TRIBE
WALL_LIBRARY_FILE = (
    BUILDINGS_ROOT
    / "walls"
    / ACTIVE_TRIBE
    / f"{ACTIVE_TRIBE}_wall_library.json"
)
FORCE_ROAD_STYLE_GROUP = ACTIVE_TRIBE

# Optional per-settlement overrides used by world mode.
ACTIVE_BUILD_AREA_OVERRIDE: Optional[dict] = None
ACTIVE_LANDMARK_OVERRIDE: Optional[Pos2D] = None
ACTIVE_SETTLEMENT_LABEL = ""
ENFORCE_TRIBE_BIOME_BOUNDARY = os.environ.get(
    "GDMC_ENFORCE_TRIBE_BIOME_BOUNDARY",
    "1" if WORLD_MODE else "0",
).strip().lower() in {"1", "true", "yes"}

# Large-world planner settings. All can be changed through environment variables.
WORLD_BIOME_SAMPLE_STEP = max(4, int(os.environ.get("GDMC_WORLD_BIOME_STEP", "8")))
WORLD_BIOME_TILE_SIZE = max(32, int(os.environ.get("GDMC_WORLD_BIOME_TILE", "128")))
WORLD_BIOME_SCAN_Y = int(os.environ.get("GDMC_WORLD_BIOME_Y", "96"))
WORLD_MAX_SETTLEMENTS = max(1, int(os.environ.get("GDMC_WORLD_MAX_SETTLEMENTS", "4")))
WORLD_MAX_PER_TRIBE = max(1, int(os.environ.get("GDMC_WORLD_MAX_PER_TRIBE", "1")))
WORLD_MAX_PER_COMPONENT = max(1, int(os.environ.get("GDMC_WORLD_MAX_PER_COMPONENT", "1")))
WORLD_MIN_REGION_AREA = max(1000, int(os.environ.get("GDMC_WORLD_MIN_REGION_AREA", "12000")))
WORLD_SETTLEMENT_HALF_SIZE = max(60, int(os.environ.get("GDMC_WORLD_SETTLEMENT_HALF_SIZE", "105")))
WORLD_MIN_SETTLEMENT_HALF_SIZE = max(45, int(os.environ.get("GDMC_WORLD_MIN_HALF_SIZE", "72")))
WORLD_MIN_CENTER_DISTANCE = max(100, int(os.environ.get("GDMC_WORLD_MIN_CENTER_DISTANCE", "210")))
WORLD_MIN_BIOME_PURITY = min(1.0, max(0.50, float(os.environ.get("GDMC_WORLD_MIN_BIOME_PURITY", "0.82"))))
WORLD_BUILDING_CAP = max(1, int(os.environ.get("GDMC_WORLD_BUILDING_CAP", "24")))
WORLD_PLAN_ONLY = os.environ.get("GDMC_WORLD_PLAN_ONLY", "0").strip().lower() in {"1", "true", "yes"}

# A wet contour point is expanded by this many contour steps so a 4-7 block
# deep module cannot bridge across the edge of a river by accident.
WALL_WATER_RUN_PADDING = 3
# Check a compact corridor around each contour point. Final module validation
# still checks every solid footprint column against water_blocked.
WALL_WATER_CORRIDOR_RADIUS = 2
# Minimum dry run that is worth attempting with the exported modules.
WALL_MIN_DRY_RUN_LENGTH = max(WALL_MIN_SEGMENT_LENGTH, 5)

# V19 JSON + NBT building placement. A paired .nbt file is preferred over the
# legacy JSON block list because it also preserves item frames, paintings,
# armor stands, villagers, animals, and other saved entities.
PREFER_NBT_BUILDINGS = True
PLACE_NBT_ENTITIES = True
NBT_KEEP_LIQUIDS = True
NBT_DO_BLOCK_UPDATES = False
NBT_REQUEST_TIMEOUT = 180
_NBT_FILE_CACHE: Dict[Path, bytes] = {}

# Configured villagers are stored in each building JSON and spawned after all
# structures and walls are complete. A repeated building receives its own copy.
SPAWN_CONFIGURED_VILLAGERS = True
VILLAGER_REQUEST_TIMEOUT = 90
VILLAGER_SPAWN_BATCH_SIZE = 128


def load_plains_building_assets() -> List[BuildingAsset]:
    """Load only JSON buildings from builds/<ACTIVE_TRIBE>/.

    The historical function name is kept so the existing main pipeline does
    not need to change, but root-level JSON files and other tribe folders are
    intentionally ignored.
    """
    if not BUILDINGS_DIR.is_dir():
        raise FileNotFoundError(
            f"Active tribe building folder does not exist: {BUILDINGS_DIR}\n"
            f"Expected structure: {BUILDINGS_ROOT / 'plains'} and "
            f"{BUILDINGS_ROOT / 'desert'}"
        )

    assets: List[BuildingAsset] = []
    skipped: List[str] = []

    for path in sorted(BUILDINGS_DIR.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as file:
                header = json.load(file)
            if header.get("format") != "gdmc_building_json":
                skipped.append(path.name)
                continue

            declared_tribe = str(
                header.get("tribe")
                or header.get("biome")
                or ""
            ).strip().lower()
            if declared_tribe and declared_tribe != ACTIVE_TRIBE:
                print(
                    f"WARNING: ignoring {path.name}: declared tribe/biome "
                    f"is {declared_tribe!r}, active tribe is {ACTIVE_TRIBE!r}."
                )
                continue

            assets.append(load_building_asset(path))
        except Exception as exc:
            print(f"WARNING: skipping {path.name}: {exc}")

    if not assets:
        raise FileNotFoundError(
            f"No gdmc_building_json files were found in {BUILDINGS_DIR}."
        )

    if not any(asset.path.name == LANDMARK_FILENAME for asset in assets):
        raise FileNotFoundError(
            f"The unique {ACTIVE_TRIBE} landmark is missing: "
            f"{BUILDINGS_DIR / LANDMARK_FILENAME}"
        )

    print(
        f"Active tribe: {ACTIVE_TRIBE}; loading buildings only from "
        f"{BUILDINGS_DIR}"
    )
    print(f"Discovered {len(assets)} {ACTIVE_TRIBE} building assets")
    for asset in assets:
        waypoint = asset.waypoints[0]
        role = (
            "CENTRAL LANDMARK"
            if asset.path.name == LANDMARK_FILENAME
            else "repeatable"
        )
        if asset.nbt_path is not None and PREFER_NBT_BUILDINGS:
            placement_mode = (
                "NBT+entities"
                if asset.structure_entities and PLACE_NBT_ENTITIES
                else "NBT"
            )
        else:
            placement_mode = "legacy JSON blocks"
        print(
            f"  {asset.path.name}: {role}, "
            f"{asset.size_x}x{asset.size_y}x{asset.size_z}, "
            f"placement={placement_mode}, blocks={len(asset.blocks)}, "
            f"waypoint={waypoint.get('pos')}, "
            f"front={waypoint.get('direction', 'north')}, "
            f"configured_villagers={len(asset.villager_spawns)}"
        )

    if skipped:
        print(
            f"Ignored non-building JSON files in {BUILDINGS_DIR}: "
            + ", ".join(skipped)
        )

    return assets


def _contour_point_is_wet(
    point: Pos2D,
    water_cells: Set[Pos2D],
) -> bool:
    """Return True when water lies under/very near the wall footprint."""
    x, z = point
    radius = WALL_WATER_CORRIDOR_RADIUS
    for dx in range(-radius, radius + 1):
        for dz in range(-radius, radius + 1):
            if (x + dx, z + dz) in water_cells:
                return True
    return False


def _split_segment_into_dry_runs(
    segment: WallSide,
    water_cells: Set[Pos2D],
) -> Tuple[List[WallSide], int]:
    """Split one contour segment into dry wall runs separated by water.

    Water removes only the affected run instead of disabling the entire north,
    east, south, or west macro side. The river/lake becomes a natural boundary.
    """
    length = wall_side_length(segment)
    points = [wall_side_point(segment, distance) for distance in range(length + 1)]
    wet = [
        _contour_point_is_wet(point, water_cells)
        for point in points
    ]

    # Expand water gaps along the contour so a wide module cannot project over
    # the water even when its connector itself is still on dry land.
    expanded = list(wet)
    for index, is_wet in enumerate(wet):
        if not is_wet:
            continue
        for nearby in range(
            max(0, index - WALL_WATER_RUN_PADDING),
            min(len(expanded), index + WALL_WATER_RUN_PADDING + 1),
        ):
            expanded[nearby] = True

    runs: List[WallSide] = []
    run_start: Optional[int] = None
    run_number = 0

    for index in range(len(points) + 1):
        at_end = index == len(points)
        is_dry = not at_end and not expanded[index]

        if is_dry and run_start is None:
            run_start = index
            continue

        if (at_end or not is_dry) and run_start is not None:
            run_end = index - 1
            if run_end - run_start >= WALL_MIN_DRY_RUN_LENGTH:
                run_number += 1
                runs.append(
                    WallSide(
                        name=f"{segment.name}_dry_{run_number}",
                        start=points[run_start],
                        end=points[run_end],
                        direction=segment.direction,
                        corner_start=segment.corner_start,
                        corner_end=segment.corner_end,
                        outward_facing=segment.outward_facing,
                        macro_side=segment.macro_side,
                        outward_vector=segment.outward_vector,
                    )
                )
            run_start = None

    return runs, sum(1 for value in expanded if value)


def _gate_local_clear_entries(asset: WallModuleAsset) -> List[dict]:
    """Select only intentional air in the walk-through gate passage.

    Exported air is ignored for every other wall module. For a main gate we
    selectively replay central air above the ground and below the banner/canopy
    so an overlapping straight wall cannot plug the entrance.
    """
    if asset.module_type != "main_gate" or len(asset.connectors) < 2:
        return []

    first = asset.connectors[0].get("pos", [0, 0, 0])
    second = asset.connectors[1].get("pos", [0, 0, 0])
    x1, z1 = int(first[0]), int(first[2])
    x2, z2 = int(second[0]), int(second[2])
    axis_x = x2 - x1
    axis_z = z2 - z1
    axis_length = math.hypot(axis_x, axis_z)
    if axis_length < 2:
        return []

    banner_levels = [
        int(entry.get("pos", [0, 0, 0])[1])
        for entry in asset.blocks
        if is_banner_block_id(str(entry.get("id", "")))
    ]
    clear_top = (
        min(banner_levels) - 1
        if banner_levels
        else max(asset.ground_y + 1, asset.size_y // 2)
    )

    selected: List[dict] = []
    for entry in asset.blocks:
        if str(entry.get("id", "")) not in AIR_IDS:
            continue
        position = entry.get("pos", [0, 0, 0])
        lx, ly, lz = int(position[0]), int(position[1]), int(position[2])
        if ly <= asset.ground_y or ly > clear_top:
            continue

        # Distance along the connector span. Keep one block away from both
        # connector ends; side posts and seam details are restored afterward.
        along = (
            (lx - x1) * axis_x + (lz - z1) * axis_z
        ) / axis_length
        if along < 1.0 or along > axis_length - 1.0:
            continue
        selected.append(entry)

    return selected


def _gate_passage_world_xz(placement: WallPlacement) -> Set[Pos2D]:
    return {
        (wx, wz)
        for entry in _gate_local_clear_entries(placement.asset)
        for wx, _wy, wz in [
            wall_world_position(entry.get("pos", [0, 0, 0]), placement)
        ]
    }


def _place_wall_entry(
    entry: dict,
    placement: WallPlacement,
) -> dict:
    wx, wy, wz = wall_world_position(
        entry.get("pos", [0, 0, 0]),
        placement,
    )
    states = rotate_block_states(
        entry.get("states"),
        placement.rotation,
    )
    data = entry.get("data")
    return b(
        str(entry.get("id", "minecraft:air")),
        wx,
        wy,
        wz,
        states,
        str(data) if data else None,
    )


def build_wall_json_blocks(
    placements: Sequence[WallPlacement],
) -> Tuple[List[dict], List[dict], int, int, int]:
    """Build wall passes with main-gate priority.

    Order inside the structural pass:
      1. straight/oblique/tower structures
      2. intentional gate-passage air clear
      3. main-gate structure
    Customized banners remain in the dedicated final pass.
    """
    normal_structures: List[dict] = []
    gate_passage_clear: List[dict] = []
    gate_structures: List[dict] = []
    banners: List[dict] = []
    total_non_air = 0

    for placement in placements:
        entries = sorted(
            placement.asset.blocks,
            key=lambda entry: (
                int(entry.get("pos", [0, 0, 0])[1]),
                int(entry.get("pos", [0, 0, 0])[2]),
                int(entry.get("pos", [0, 0, 0])[0]),
            ),
        )

        if placement.asset.module_type == "main_gate":
            for entry in _gate_local_clear_entries(placement.asset):
                clear_block = _place_wall_entry(entry, placement)
                clear_block["id"] = "minecraft:air"
                gate_passage_clear.append(clear_block)

        for entry in entries:
            block_id = str(entry.get("id", "minecraft:air"))
            if block_id in AIR_IDS:
                continue

            block = _place_wall_entry(entry, placement)
            total_non_air += 1
            if is_banner_block_id(block_id):
                banners.append(block)
            elif placement.asset.module_type == "main_gate":
                gate_structures.append(block)
            else:
                normal_structures.append(block)

    structural = normal_structures + gate_passage_clear + gate_structures
    banners_with_data = sum(1 for block in banners if block.get("data"))

    if gate_passage_clear:
        print(
            f"Protected main-gate passage clear blocks: "
            f"{len(gate_passage_clear)}"
        )

    return (
        structural,
        banners,
        total_non_air + len(gate_passage_clear),
        len(banners),
        banners_with_data,
    )


def _extend_wall_chain_v17(
    side_name: str,
    current_connector: Tuple[int, int, int],
    target: Pos2D,
    desired_direction: Dir2D,
    module_assets: Sequence[WallModuleAsset],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    protected_gate_passage_xz: Set[Pos2D],
    seed: int,
    outward_facing: Optional[Any] = None,
) -> Tuple[List[WallPlacement], Set[Pos2D]]:
    """Terrain-following chain that may not enter a gate passage."""
    placements: List[WallPlacement] = []
    newly_occupied: Set[Pos2D] = set()
    rng = random.Random(
        seed
        + sum(ord(char) for char in side_name) * 1777
        + current_connector[0] * 13
        + current_connector[2] * 17
    )

    current = current_connector
    iterations = 0
    while iterations < WALL_MAX_MODULES_PER_CHAIN:
        iterations += 1
        remaining = chain_target_remaining(
            current,
            target,
            desired_direction,
        )
        if remaining <= WALL_END_GAP_TOLERANCE:
            break

        candidates: List[Tuple[float, WallPlacement, Set[Pos2D]]] = []
        randomized_assets = list(module_assets)
        rng.shuffle(randomized_assets)

        for asset in randomized_assets:
            options = wall_connector_options(
                asset,
                desired_direction,
                outward_facing,
            )
            for option in options[:16]:
                (
                    alignment_score,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                ) = option

                placement = _terrain_following_placement(
                    asset,
                    side_name,
                    rotation,
                    start_index,
                    end_index,
                    start_offset,
                    end_offset,
                    current,
                    heights,
                )
                if placement is None or placement.end_connector_world is None:
                    continue

                end_world = placement.end_connector_world
                progress = (
                    (end_world[0] - current[0]) * desired_direction[0]
                    + (end_world[2] - current[2]) * desired_direction[1]
                )
                perpendicular = abs(
                    (end_world[0] - current[0]) * (-desired_direction[1])
                    + (end_world[2] - current[2]) * desired_direction[0]
                )
                if progress < 2:
                    continue
                if progress > remaining + WALL_END_GAP_TOLERANCE:
                    continue
                if perpendicular > WALL_MAX_PERPENDICULAR_DRIFT:
                    continue

                valid, terrain_error, solid_xz = wall_placement_is_valid(
                    asset,
                    placement.world_pivot,
                    rotation,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_wall_xz | newly_occupied,
                    WALL_MAX_FLATTEN,
                )
                if not valid:
                    valid, terrain_error, solid_xz = wall_placement_is_valid(
                        asset,
                        placement.world_pivot,
                        rotation,
                        ba,
                        heights,
                        water_blocked,
                        building_rects,
                        occupied_wall_xz | newly_occupied,
                        WALL_RELAXED_MAX_FLATTEN,
                    )
                if not valid:
                    continue

                # This is stricter than the normal seam-overlap allowance.
                # No straight/oblique module may occupy the open gate passage.
                if solid_xz & protected_gate_passage_xz:
                    continue

                end_remaining = chain_target_remaining(
                    end_world,
                    target,
                    desired_direction,
                )
                type_penalty = (
                    WALL_OBLIQUE_PENALTY
                    if asset.module_type == "oblique_wall"
                    else 0.0
                )
                seam_step = (
                    abs(placement.start_connector_world[1] - current[1])
                    if placement.start_connector_world
                    else 0
                )
                score = (
                    alignment_score
                    + perpendicular * 35.0
                    + terrain_error * 8.0
                    + type_penalty
                    + seam_step * WALL_SEAM_STEP_PENALTY
                    + max(
                        0,
                        WALL_END_GAP_TOLERANCE - end_remaining,
                    )
                    * 3.0
                    + rng.random() * 0.25
                )
                candidates.append((score, placement, solid_xz))

        if not candidates:
            print(
                f"  {side_name} chain stopped with {remaining} blocks "
                "remaining before its dry-run endpoint."
            )
            break

        candidates.sort(key=lambda item: item[0])
        _score, chosen, solid_xz = candidates[0]
        placements.append(chosen)
        newly_occupied.update(solid_xz)
        assert chosen.end_connector_world is not None
        current = chosen.end_connector_world

    return placements, newly_occupied


def plan_settlement_walls(
    plots: Sequence[Plot],
    wall_library: Dict[str, List[WallModuleAsset]],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Dict[str, str], List[dict], Optional[Rect]]:
    """Wrap the complete settlement with one unbroken wall contour.

    V25 never removes a wall run because of water. Modules may stand on a
    reclaimed water foundation, and the final fallback base closes any module
    chain gap while preserving intentional gate openings.
    """
    if not GENERATE_WALLS:
        return [], {}, [], None

    vertices = _octilinear_contour_vertices(plots, ba)
    settlement_center = (
        int(round(sum(x for x, _ in vertices) / len(vertices))),
        int(round(sum(z for _, z in vertices) / len(vertices))),
    )
    contour_segments = _contour_segments(vertices, settlement_center)
    building_rects = [plot.rect for plot in plots]

    print("Planned complete settlement contour after all buildings:")
    print("  vertices: " + " -> ".join(str(vertex) for vertex in vertices))
    print(f"  raw contour segments: {len(contour_segments)}")

    grouped_runs: Dict[str, List[WallSide]] = {
        "north": [],
        "east": [],
        "south": [],
        "west": [],
    }
    water_points_by_macro: Counter = Counter()

    for segment in contour_segments:
        grouped_runs[segment.macro_side].append(segment)
        water_points_by_macro[segment.macro_side] += sum(
            1
            for distance in range(wall_side_length(segment) + 1)
            if wall_side_point(segment, distance) in water_cells
        )

    side_status: Dict[str, str] = {}
    for macro in ("north", "east", "south", "west"):
        runs = grouped_runs[macro]
        run_length = sum(wall_side_length(run) for run in runs)
        side_status[macro] = (
            f"FULL RUNS={len(runs)}, contour length={run_length}, "
            f"water points reclaimed={water_points_by_macro[macro]}"
        )
        print(f"  {macro}: {side_status[macro]}")

    chain_assets = list(wall_library.get("straight_wall", []))
    chain_assets.extend(wall_library.get("oblique_wall", []))
    placements: List[WallPlacement] = []
    occupied_wall_xz: Set[Pos2D] = set()
    protected_gate_passages: Set[Pos2D] = set()
    gate_waypoints: List[dict] = []
    active_macro_sides: Set[str] = set()

    for macro_index, macro in enumerate(("north", "east", "south", "west")):
        runs = sorted(
            grouped_runs[macro],
            key=wall_side_length,
            reverse=True,
        )
        if not runs:
            continue

        # Exactly one gate for this macro side. Water is allowed because V25
        # reclaims and supports the wall footprint before module placement.
        gate_order = sorted(
            runs,
            key=lambda run: (
                0
                if abs(run.direction[0]) + abs(run.direction[1]) == 1
                else 1,
                -wall_side_length(run),
            ),
        )
        gate_result: Optional[Tuple[WallPlacement, Set[Pos2D]]] = None
        gate_run: Optional[WallSide] = None
        for candidate_index, candidate in enumerate(gate_order):
            gate_result = choose_gate_placement(
                candidate,
                wall_library["main_gate"],
                corner_clearance=1,
                side_ground_y=0,
                ba=ba,
                heights=heights,
                water_blocked=water_blocked,
                building_rects=building_rects,
                occupied_wall_xz=occupied_wall_xz,
                seed=seed + macro_index * 1009 + candidate_index * 71,
                outward_facing=candidate.outward_vector,
            )
            if gate_result is not None:
                gate_run = candidate
                break

        if gate_result is None or gate_run is None:
            side_status[macro] = (
                "CONNECTED BY FALLBACK — no valid modular main-gate position"
            )
            print(f"WARNING: {macro}: {side_status[macro]}")
            continue

        gate, gate_solid = gate_result
        placements.append(gate)
        occupied_wall_xz.update(gate_solid)
        gate_passage = _gate_passage_world_xz(gate)
        protected_gate_passages.update(gate_passage)
        gate_waypoints.extend(gate_world_waypoints(gate))
        active_macro_sides.add(macro)

        assert gate.start_connector_world is not None
        assert gate.end_connector_world is not None

        module_count = 0
        backward_chain, backward_solid = _extend_wall_chain_v17(
            gate_run.name,
            gate.start_connector_world,
            gate_run.start,
            (-gate_run.direction[0], -gate_run.direction[1]),
            chain_assets,
            ba,
            heights,
            water_blocked,
            building_rects,
            occupied_wall_xz,
            protected_gate_passages,
            seed + macro_index * 2003 + 1,
            outward_facing=gate_run.outward_vector,
        )
        placements.extend(backward_chain)
        occupied_wall_xz.update(backward_solid)
        module_count += len(backward_chain)

        forward_chain, forward_solid = _extend_wall_chain_v17(
            gate_run.name,
            gate.end_connector_world,
            gate_run.end,
            gate_run.direction,
            chain_assets,
            ba,
            heights,
            water_blocked,
            building_rects,
            occupied_wall_xz,
            protected_gate_passages,
            seed + macro_index * 2003 + 2,
            outward_facing=gate_run.outward_vector,
        )
        placements.extend(forward_chain)
        occupied_wall_xz.update(forward_solid)
        module_count += len(forward_chain)

        # Generate every other complete run on the same side. Any leftover
        # module-chain gap is closed by the continuous fallback base.
        for run_index, run in enumerate(runs):
            if run is gate_run:
                continue
            start_connector = (
                run.start[0],
                surface_top_y(run.start, heights),
                run.start[1],
            )
            chain, solid = _extend_wall_chain_v17(
                run.name,
                start_connector,
                run.end,
                run.direction,
                chain_assets,
                ba,
                heights,
                water_blocked,
                building_rects,
                occupied_wall_xz,
                protected_gate_passages,
                seed + macro_index * 3001 + run_index * 43,
                outward_facing=run.outward_vector,
            )
            placements.extend(chain)
            occupied_wall_xz.update(solid)
            module_count += len(chain)

        side_status[macro] = (
            f"GENERATED — 1 gate, {len(runs)} complete run(s), "
            f"{module_count} terrain-following wall modules, "
            f"water points reclaimed={water_points_by_macro[macro]}"
        )
        print(f"  {macro}: {side_status[macro]}")

    # Corner towers are attempted after the complete wall runs. Water is
    # supported and reclaimed during the final wall-foundation pass.
    towers = _place_contour_towers(
        vertices,
        active_macro_sides,
        wall_library.get("tower_wall", []),
        settlement_center,
        ba,
        heights,
        water_blocked,
        building_rects,
        seed,
    )
    placements.extend(towers)

    bounding_rect: Rect = (
        min(x for x, _ in vertices),
        min(z for _, z in vertices),
        max(x for x, _ in vertices),
        max(z for _, z in vertices),
    )
    return placements, side_status, gate_waypoints, bounding_rect


# ============================================================
# V25 overrides: continuous wall base + enclosed-water reclamation
# ============================================================

def _wall_connection_block() -> str:
    return {
        "desert": "minecraft:sandstone",
        "savanna": "minecraft:red_sandstone",
        "taiga": "minecraft:cobblestone",
        "plains": "minecraft:stone_bricks",
    }.get(ACTIVE_TRIBE, "minecraft:stone_bricks")


def _wall_ground_fill_block() -> str:
    return "minecraft:sand" if ACTIVE_TRIBE == "desert" else "minecraft:dirt"


def _point_in_polygon(point: Tuple[float, float], vertices: Sequence[Pos2D]) -> bool:
    """Even/odd polygon test for the octilinear settlement contour."""
    px, pz = point
    inside = False
    count = len(vertices)
    for index in range(count):
        x1, z1 = vertices[index]
        x2, z2 = vertices[(index + 1) % count]
        if (z1 > pz) == (z2 > pz):
            continue
        crossing_x = x1 + (pz - z1) * (x2 - x1) / (z2 - z1)
        if px < crossing_x:
            inside = not inside
    return inside


def _ordered_contour_points(
    vertices: Sequence[Pos2D],
    settlement_center: Pos2D,
) -> List[Pos2D]:
    del settlement_center  # The fallback follows every polygon edge directly.
    points: List[Pos2D] = []
    for index, start in enumerate(vertices):
        end = vertices[(index + 1) % len(vertices)]
        for point in line_2d(start, end):
            if not points or points[-1] != point:
                points.append(point)
    # The final polygon edge already ends on the first vertex. Keep every
    # contour column exactly once so support/fallback statistics stay accurate.
    if len(points) > 1 and points[-1] == points[0]:
        points.pop()
    return points


def build_continuous_wall_foundation_and_drain(
    plots: Sequence[Plot],
    placements: Sequence[WallPlacement],
    ba: dict,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
) -> Tuple[List[dict], List[dict], Dict[str, int]]:
    """Close accidental wall gaps and reclaim all water enclosed by the wall.

    The fallback is intentionally a low base rather than a replacement design:
    exported modules overwrite it during the later wall pass. Only contour cells
    not occupied by a module receive the visible biome-matched connector wall.
    """
    if not plots:
        return [], [], {
            "contour_points": 0,
            "gap_columns": 0,
            "attachment_columns": 0,
            "drained_columns": 0,
            "wall_water_columns_filled": 0,
        }

    vertices = _octilinear_contour_vertices(plots, ba)
    center = (
        int(round(sum(x for x, _ in vertices) / len(vertices))),
        int(round(sum(z for _, z in vertices) / len(vertices))),
    )
    contour_points = _ordered_contour_points(vertices, center)
    module_solid: Set[Pos2D] = set()
    gate_passage: Set[Pos2D] = set()
    for placement in placements:
        module_solid.update(
            wall_module_solid_xz(
                placement.asset,
                placement.world_pivot,
                placement.rotation,
            )
        )
        if placement.asset.module_type == "main_gate":
            raw_passage = _gate_passage_world_xz(placement)
            gate_passage.update(raw_passage)
            for px, pz in raw_passage:
                for ox in (-1, 0, 1):
                    for oz in (-1, 0, 1):
                        gate_passage.add((px + ox, pz + oz))
            for waypoint in gate_world_waypoints(placement):
                wx, _wy, wz = waypoint["world_pos"]
                for ox in range(-2, 3):
                    for oz in range(-2, 3):
                        gate_passage.add((wx + ox, wz + oz))

    module_coverage: Set[Pos2D] = set(module_solid)
    cover_radius = WALL_FALLBACK_MODULE_COVER_RADIUS
    for mx, mz in module_solid:
        for ox in range(-cover_radius, cover_radius + 1):
            for oz in range(-cover_radius, cover_radius + 1):
                if max(abs(ox), abs(oz)) <= cover_radius:
                    module_coverage.add((mx + ox, mz + oz))

    drain_output: List[dict] = []
    foundation_output: List[dict] = []
    ground_block = _wall_ground_fill_block()
    connection_block = _wall_connection_block()
    drained_columns = 0

    if WALL_DRAIN_ENCLOSED_WATER:
        min_x = max(ba["x1"], min(x for x, _ in vertices))
        max_x = min(ba["x2"], max(x for x, _ in vertices))
        min_z = max(ba["z1"], min(z for _, z in vertices))
        max_z = min(ba["z2"], max(z for _, z in vertices))
        for x, z in water_cells:
            if not (min_x <= x <= max_x and min_z <= z <= max_z):
                continue
            if not _point_in_polygon((x + 0.5, z + 0.5), vertices):
                continue
            floor_top = floor_heights.get((x, z), heights.get((x, z), 65)) - 1
            water_top = heights.get((x, z), floor_top + 1) - 1
            if water_top < floor_top + 1:
                continue
            for y in range(max(ba["y1"], floor_top + 1), min(ba["y2"], water_top) + 1):
                drain_output.append(b(ground_block, x, y, z))
            drained_columns += 1

    gap_columns = 0
    gap_points: Set[Pos2D] = set()
    previous_y: Optional[int] = None
    wall_water_columns_filled = 0
    for x, z in contour_points:
        if not in_build_area_xz(ba, x, z):
            continue
        top_y = surface_top_y((x, z), heights)

        if (x, z) in water_cells:
            floor_top = floor_heights.get((x, z), heights.get((x, z), top_y + 1)) - 1
            water_top = heights.get((x, z), floor_top + 1) - 1
            top_y = max(top_y, water_top)
            for y in range(max(ba["y1"], floor_top + 1), min(ba["y2"], top_y) + 1):
                foundation_output.append(b(ground_block, x, y, z))
            wall_water_columns_filled += 1
        else:
            # Compact solid footing beneath every dry contour point, even above caves.
            for y in range(
                max(ba["y1"], top_y - WALL_FOUNDATION_DEPTH),
                top_y,
            ):
                foundation_output.append(b(ground_block, x, y, z))

        if (x, z) in gate_passage:
            previous_y = top_y
            continue

        # Do not draw a low fallback line beside exported modules. A module is
        # considered to cover nearby contour points because its visible body can
        # be offset from the connector centerline by several blocks.
        covered_by_module = (x, z) in module_coverage
        if covered_by_module:
            previous_y = top_y
            continue

        bottom_y = top_y
        if previous_y is not None:
            bottom_y = min(bottom_y, previous_y)
        for y in range(
            max(ba["y1"], bottom_y),
            min(ba["y2"], top_y + WALL_CONNECTION_FILL_HEIGHT - 1) + 1,
        ):
            foundation_output.append(b(connection_block, x, y, z))
        gap_columns += 1
        gap_points.add((x, z))
        previous_y = top_y

    # Attach every fallback run to the nearest real module body. This preserves
    # guaranteed continuity without drawing a complete second parallel wall.
    attachment_columns: Set[Pos2D] = set()
    if gap_points and module_solid:
        boundary_points = [
            point
            for point in gap_points
            if any(
                (point[0] + dx, point[1] + dz) in module_coverage
                for dx in (-1, 0, 1)
                for dz in (-1, 0, 1)
                if not (dx == 0 and dz == 0)
            )
        ]
        for point in boundary_points:
            nearby = [
                module_point
                for module_point in module_solid
                if max(
                    abs(module_point[0] - point[0]),
                    abs(module_point[1] - point[1]),
                ) <= WALL_FALLBACK_ATTACHMENT_RADIUS
            ]
            if not nearby:
                continue
            nearest = min(
                nearby,
                key=lambda module_point: (
                    abs(module_point[0] - point[0])
                    + abs(module_point[1] - point[1])
                ),
            )
            for ax, az in line_2d(point, nearest):
                if (ax, az) in gate_passage or (ax, az) in module_solid:
                    continue
                if not in_build_area_xz(ba, ax, az):
                    continue
                attachment_columns.add((ax, az))

        for ax, az in sorted(attachment_columns):
            top_y = surface_top_y((ax, az), heights)
            if (ax, az) in water_cells:
                floor_top = floor_heights.get(
                    (ax, az), heights.get((ax, az), top_y + 1)
                ) - 1
                for y in range(
                    max(ba["y1"], floor_top + 1),
                    min(ba["y2"], top_y) + 1,
                ):
                    foundation_output.append(b(ground_block, ax, y, az))
            else:
                for y in range(
                    max(ba["y1"], top_y - WALL_FOUNDATION_DEPTH),
                    top_y,
                ):
                    foundation_output.append(b(ground_block, ax, y, az))
            for y in range(
                top_y,
                min(ba["y2"], top_y + WALL_CONNECTION_FILL_HEIGHT - 1) + 1,
            ):
                foundation_output.append(b(connection_block, ax, y, az))

    return drain_output, foundation_output, {
        "contour_points": len(set(contour_points)),
        "gap_columns": gap_columns,
        "attachment_columns": len(attachment_columns),
        "drained_columns": drained_columns,
        "wall_water_columns_filled": wall_water_columns_filled,
    }

# ------------------------------------------------------------
# V19 paired JSON + NBT building placement
# ------------------------------------------------------------

def building_uses_nbt(plot: Plot) -> bool:
    return bool(
        PREFER_NBT_BUILDINGS
        and plot.asset is not None
        and plot.asset.nbt_path is not None
    )


def _read_nbt_file(path: Path) -> bytes:
    cached = _NBT_FILE_CACHE.get(path)
    if cached is not None:
        return cached
    data = path.read_bytes()
    if not data:
        raise ValueError(f"NBT file is empty: {path}")
    _NBT_FILE_CACHE[path] = data
    return data


def _nbt_post_origin(plot: Plot) -> Tuple[int, int, int]:
    """Translate POST /structure so its rotated bounds match plot.rect.

    GDMC-HTTP rotates clockwise around local pivot (0, 0). The translations
    below reproduce rotate_local_xz(), which keeps every rotated coordinate
    non-negative inside the selected plot rectangle.
    """
    if plot.asset is None or plot.origin is None:
        raise ValueError("NBT placement requires a building asset and origin")

    x0, y0, z0 = plot.origin
    turns = (plot.rotation // 90) % 4
    if turns == 0:
        return x0, y0, z0
    if turns == 1:
        return x0 + plot.asset.size_z - 1, y0, z0
    if turns == 2:
        return (
            x0 + plot.asset.size_x - 1,
            y0,
            z0 + plot.asset.size_z - 1,
        )
    return x0, y0, z0 + plot.asset.size_x - 1


def place_nbt_building(plot: Plot) -> None:
    """Place one paired NBT structure through GDMC-HTTP."""
    if plot.asset is None or plot.asset.nbt_path is None:
        raise ValueError("This building has no paired NBT file")

    asset = plot.asset
    nbt_data = _read_nbt_file(asset.nbt_path)
    post_x, post_y, post_z = _nbt_post_origin(plot)
    turns = (plot.rotation // 90) % 4
    include_entities = bool(
        PLACE_NBT_ENTITIES and asset.structure_entities
    )

    params = {
        "x": post_x,
        "y": post_y,
        "z": post_z,
        "rotate": turns,
        "pivotX": 0,
        "pivotZ": 0,
        "entities": str(include_entities).lower(),
        "keepLiquids": str(NBT_KEEP_LIQUIDS).lower(),
        "doBlockUpdates": str(NBT_DO_BLOCK_UPDATES).lower(),
        "spawnDrops": "false",
        "withinBuildArea": str(WITHIN_BUILD_AREA).lower(),
        "dimension": DIMENSION,
    }
    headers = {"Content-Type": "application/octet-stream"}
    # GET /structure normally returns a gzip-compressed NBT file. Preserve and
    # declare that compression when posting it back. Uncompressed NBT is also
    # supported, so omit the header when the gzip magic number is absent.
    if nbt_data.startswith(b"\x1f\x8b"):
        headers["Content-Encoding"] = "gzip"

    response = requests.post(
        f"{HOST}/structure",
        params=params,
        data=nbt_data,
        headers=headers,
        timeout=NBT_REQUEST_TIMEOUT,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        print(
            f"GDMC returned an error while placing NBT building "
            f"{asset.nbt_path.name}:"
        )
        print(response.text)
        raise

    try:
        result = response.json()
    except ValueError:
        result = None
    if isinstance(result, dict) and int(result.get("status", 1)) == 0:
        raise RuntimeError(
            f"GDMC reported status=0 while placing {asset.nbt_path.name}"
        )

    print(
        f"  placed NBT {asset.nbt_path.name}: origin=({post_x}, {post_y}, "
        f"{post_z}), rotation={plot.rotation}°, entities={include_entities}"
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------



def villager_type_for_tribe(tribe: str) -> str:
    """Choose the villager skin/type automatically from the building tribe."""
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
    """Minecraft yaw: south=0, west=90, north=180, east=-90."""
    return {
        "south": 0.0,
        "west": 90.0,
        "north": 180.0,
        "east": -90.0,
    }.get(str(facing).lower(), 0.0)


def configured_villager_world_spawn(
    plot: Plot,
    villager: dict,
) -> Tuple[float, float, float, str]:
    """Rotate a saved local villager position and facing with its building."""
    if plot.asset is None or plot.origin is None:
        raise ValueError("Configured villager requires a building asset and origin")

    local = villager.get("pos", [0, 0, 0])
    lx, ly, lz = int(local[0]), int(local[1]), int(local[2])
    rx, rz = rotate_local_xz(
        lx,
        lz,
        plot.asset.size_x,
        plot.asset.size_z,
        plot.rotation,
    )
    origin_x, origin_y, origin_z = plot.origin
    facing = rotate_direction(
        str(villager.get("facing", "south")),
        plot.rotation,
    )

    # X/Z are centered in the selected block. Y is the saved feet level.
    return (
        origin_x + rx + 0.5,
        origin_y + ly,
        origin_z + rz + 0.5,
        facing,
    )


def configured_villager_snbt(asset: BuildingAsset, villager: dict, facing: str) -> str:
    profession = str(villager.get("profession", "minecraft:none")).strip().lower()
    if not profession.startswith("minecraft:"):
        profession = "minecraft:" + profession

    requested_type = str(villager.get("type", "auto")).strip().lower()
    if requested_type in {"", "auto", "automatic", "tribe"}:
        villager_type = villager_type_for_tribe(asset.tribe)
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

    # Minecraft Java 1.21.5+ stores text components directly as SNBT.
    # Do not wrap the component in a JSON string, or Minecraft will display
    # the literal component text (for example: {text:"Aldrin"}).
    custom_name = str(villager.get("custom_name") or "").strip()
    if custom_name:
        name_value = json.dumps(custom_name, ensure_ascii=False)
        fields.append(f"CustomName:{{text:{name_value}}}")
        if bool(villager.get("custom_name_visible", True)):
            fields.append("CustomNameVisible:1b")

    # Level 2+ villagers keep their chosen profession even without a workstation.
    if level >= 2:
        fields.append("Xp:10")
    if bool(villager.get("persistent", True)):
        fields.append("PersistenceRequired:1b")
    if bool(villager.get("stationary", True)):
        fields.extend(["NoAI:1b", "Motion:[0.0d,0.0d,0.0d]"])

    return "{" + ",".join(fields) + "}"


def build_configured_villager_instructions(
    plots: Sequence[Plot],
    ba: dict,
) -> List[dict]:
    instructions: List[dict] = []
    for plot in plots:
        asset = plot.asset
        if asset is None:
            continue
        for villager in asset.villager_spawns:
            world_x, world_y, world_z, facing = configured_villager_world_spawn(
                plot,
                villager,
            )
            block_x = math.floor(world_x)
            block_y = math.floor(world_y)
            block_z = math.floor(world_z)
            if not in_build_area_xyz(ba, block_x, block_y, block_z):
                print(
                    f"WARNING: skipping configured villager for {asset.name}: "
                    f"spawn ({world_x}, {world_y}, {world_z}) is outside /buildarea."
                )
                continue

            instructions.append(
                {
                    "id": "minecraft:villager",
                    "x": world_x,
                    "y": world_y,
                    "z": world_z,
                    "data": configured_villager_snbt(asset, villager, facing),
                    "_description": (
                        f"{asset.name}/{villager.get('name', 'villager')} "
                        f"custom_name={villager.get('custom_name') or '(unnamed)'!r} "
                        f"facing={facing} profession={villager.get('profession')} "
                        f"type={villager_type_for_tribe(asset.tribe)}"
                    ),
                }
            )
    return instructions


def spawn_configured_villagers(instructions: Sequence[dict]) -> int:
    """Spawn configured villagers through GDMC-HTTP PUT /entities."""
    if not instructions:
        return 0

    placed = 0
    params = {
        "x": 0,
        "y": 0,
        "z": 0,
        "dimension": DIMENSION,
    }

    for start in range(0, len(instructions), VILLAGER_SPAWN_BATCH_SIZE):
        batch = instructions[start:start + VILLAGER_SPAWN_BATCH_SIZE]
        payload = [
            {key: value for key, value in entry.items() if not key.startswith("_")}
            for entry in batch
        ]
        response = requests.put(
            f"{HOST}/entities",
            params=params,
            json=payload,
            timeout=VILLAGER_REQUEST_TIMEOUT,
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
                    print(
                        f"WARNING: configured villager may not have spawned: "
                        f"{description}; result={result}"
                    )
                else:
                    placed += 1
                    print(f"  spawned {description}")
        else:
            # A successful HTTP response without the expected result list is
            # still counted, but reported for easier version debugging.
            placed += len(batch)
            print(
                f"  spawned villager batch of {len(batch)} "
                f"(response format was {type(results).__name__})"
            )

    return placed



def _terrain_first_rect(ba: dict, center: Pos2D) -> Rect:
    """Return the full area that must be formed before settlement generation."""
    inset = TERRAIN_FIRST_EDGE_INSET
    available_half_x = max(1, (ba["x2"] - ba["x1"] + 1) // 2 - inset)
    available_half_z = max(1, (ba["z2"] - ba["z1"] + 1) // 2 - inset)

    if ACTIVE_BUILD_AREA_OVERRIDE is not None:
        half = min(available_half_x, available_half_z)
    else:
        requested = (
            int(math.ceil(SETTLEMENT_BUILDING_RADIUS))
            + AUTO_BUILDING_EDGE_RESERVE
            + WALL_PERIMETER_MARGIN
            + SETTLEMENT_TERRAIN_MARGIN
            if SETTLEMENT_BUILDING_RADIUS is not None
            else TERRAIN_FIRST_MAX_HALF_SIZE
        )
        half = min(available_half_x, available_half_z, requested)

    cx, cz = center
    return _clipped_rect(
        (cx - half, cz - half, cx + half, cz + half),
        ba,
    )


def _terrain_first_fill_block() -> str:
    return "sand" if ACTIVE_TRIBE == "desert" else "dirt"


def _terrain_first_surface_block() -> str:
    return "sand" if ACTIVE_TRIBE == "desert" else "grass_block"


def _terrain_first_grade(
    terrain_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    biome_forbidden: Set[Pos2D],
    tree_protected: Set[Pos2D],
) -> int:
    """Choose a lower-middle grade, ignoring water, ravine bottoms, and trees."""
    x0, z0, x1, z1 = terrain_rect
    samples: List[int] = []
    for x in range(x0, x1 + 1, 2):
        for z in range(z0, z1 + 1, 2):
            pos = (x, z)
            if (
                pos not in heights
                or pos in water_cells
                or pos in biome_forbidden
                or pos in tree_protected
            ):
                continue
            samples.append(_terrain_ground_top(pos, heights, floor_heights))

    if not samples:
        return GLOBAL_MEDIAN_TOP_Y

    # 42% avoids raising everything to a hilltop while staying above most holes.
    return _percentile_int(samples, 0.42)


def _terrain_first_tree_cells(
    terrain_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    biome_forbidden: Set[Pos2D],
) -> Set[Pos2D]:
    return _tree_and_ridge_protected_cells(
        terrain_rect,
        heights,
        floor_heights,
        biome_forbidden,
        set(),
    )


def _is_tree_log_block(block_id: str) -> bool:
    name = str(block_id).lower()
    return name.endswith(("_log", "_wood", "_stem", "_hyphae"))


def _is_tree_leaf_block(block_id: str) -> bool:
    name = str(block_id).lower()
    return name.endswith("_leaves")


def _connected_xz_components(cells: Set[Pos2D]) -> List[Set[Pos2D]]:
    remaining = set(cells)
    components: List[Set[Pos2D]] = []
    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            x, z = stack.pop()
            for dx in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == 0 and dz == 0:
                        continue
                    neighbor = (x + dx, z + dz)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        component.add(neighbor)
                        stack.append(neighbor)
        components.append(component)
    return components


def _read_tree_blocks_in_box(
    box: Tuple[int, int, int, int, int, int],
) -> Tuple[Set[Tuple[int, int, int]], Set[Tuple[int, int, int]]]:
    """Read only log/leaf positions from a bounded world box."""
    min_x, min_y, min_z, max_x, max_y, max_z = box
    logs: Set[Tuple[int, int, int]] = set()
    leaves: Set[Tuple[int, int, int]] = set()
    tile = TERRAIN_DAMAGED_TREE_BLOCK_TILE

    for x0 in range(min_x, max_x + 1, tile):
        x1 = min(max_x, x0 + tile - 1)
        for z0 in range(min_z, max_z + 1, tile):
            z1 = min(max_z, z0 + tile - 1)
            for y0 in range(min_y, max_y + 1, tile):
                y1 = min(max_y, y0 + tile - 1)
                data = http_get(
                    "/blocks",
                    params={
                        "x": x0,
                        "y": y0,
                        "z": z0,
                        "dx": x1 - x0 + 1,
                        "dy": y1 - y0 + 1,
                        "dz": z1 - z0 + 1,
                        "dimension": DIMENSION,
                        "withinBuildArea": str(WITHIN_BUILD_AREA_READS).lower(),
                    },
                )
                entries = data.get("blocks", []) if isinstance(data, dict) else data
                for entry in entries:
                    block_id = str(entry.get("id", ""))
                    pos = (int(entry["x"]), int(entry["y"]), int(entry["z"]))
                    if _is_tree_log_block(block_id):
                        logs.add(pos)
                    elif _is_tree_leaf_block(block_id):
                        leaves.add(pos)
    return logs, leaves


def find_damaged_tree_blocks(
    damaged_seed_cells: Set[Pos2D],
    terrain_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
) -> Set[Tuple[int, int, int]]:
    """Find complete natural trees touched by the terrain cut.

    Heightmaps identify likely damaged tree footprints. Actual blocks are then
    read from Minecraft. Connected logs select the tree trunk/branches, and all
    nearby leaves belonging to that crown are removed with them.
    """
    if not TERRAIN_FIRST_REMOVE_DAMAGED_TREES or not damaged_seed_cells:
        return set()

    # Do not clip the scan to terrain_rect: a damaged trunk can stand inside the
    # formed area while its branches/crown extend outside it.
    _tx0, _tz0, _tx1, _tz1 = terrain_rect
    removals: Set[Tuple[int, int, int]] = set()
    for component in _connected_xz_components(damaged_seed_cells):
        min_x = max(ba["x1"], min(x for x, _ in component) - TERRAIN_DAMAGED_TREE_SCAN_RADIUS)
        max_x = min(ba["x2"], max(x for x, _ in component) + TERRAIN_DAMAGED_TREE_SCAN_RADIUS)
        min_z = max(ba["z1"], min(z for _, z in component) - TERRAIN_DAMAGED_TREE_SCAN_RADIUS)
        max_z = min(ba["z2"], max(z for _, z in component) + TERRAIN_DAMAGED_TREE_SCAN_RADIUS)

        footprint = [
            (x, z)
            for x in range(min_x, max_x + 1)
            for z in range(min_z, max_z + 1)
            if (x, z) in heights
        ]
        if not footprint:
            continue
        ground_values = [
            _terrain_ground_top(pos, heights, floor_heights)
            for pos in footprint
        ]
        visible_values = [heights[pos] - 1 for pos in footprint]
        min_y = max(ba["y1"], min(ground_values) - 2)
        max_y = min(
            ba["y2"],
            max(visible_values) + TERRAIN_DAMAGED_TREE_EXTRA_HEIGHT,
        )

        try:
            logs, leaves = _read_tree_blocks_in_box(
                (min_x, min_y, min_z, max_x, max_y, max_z)
            )
        except Exception as exc:
            print(f"WARNING: damaged-tree block scan failed: {exc}")
            continue
        if not logs and not leaves:
            continue

        seed_radius = SETTLEMENT_TREE_PROTECTION_RADIUS + 2
        starting_logs = {
            log
            for log in logs
            if any(
                max(abs(log[0] - sx), abs(log[2] - sz)) <= seed_radius
                for sx, sz in component
            )
        }
        if not starting_logs:
            # A cut may touch only the crown edge. Select the closest log column
            # inside the local scan so the whole damaged tree still disappears.
            nearest = sorted(
                logs,
                key=lambda log: min(
                    max(abs(log[0] - sx), abs(log[2] - sz))
                    for sx, sz in component
                ),
            )
            if nearest:
                best_distance = min(
                    max(abs(nearest[0][0] - sx), abs(nearest[0][2] - sz))
                    for sx, sz in component
                )
                starting_logs = {
                    log for log in nearest
                    if min(
                        max(abs(log[0] - sx), abs(log[2] - sz))
                        for sx, sz in component
                    ) == best_distance
                }

        if not starting_logs:
            # A previous terrain/structure pass may already have removed the
            # trunk while leaving a floating leaf crown. Remove those orphaned
            # leaves when they are close to the damaged-tree seed component.
            orphan_radius = TERRAIN_POST_ORPHAN_LEAF_RADIUS
            orphan_leaves = {
                leaf
                for leaf in leaves
                if any(
                    max(abs(leaf[0] - sx), abs(leaf[2] - sz)) <= orphan_radius
                    for sx, sz in component
                )
            }
            removals.update(orphan_leaves)
            continue

        selected_logs = set(starting_logs)
        stack = list(starting_logs)
        while stack:
            x, y, z = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == dy == dz == 0:
                            continue
                        neighbor = (x + dx, y + dy, z + dz)
                        if neighbor in logs and neighbor not in selected_logs:
                            selected_logs.add(neighbor)
                            stack.append(neighbor)

        selected_leaves: Set[Tuple[int, int, int]] = set()
        radius = TERRAIN_DAMAGED_TREE_LEAF_RADIUS
        for x, y, z in selected_logs:
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        leaf = (x + dx, y + dy, z + dz)
                        if leaf in leaves:
                            selected_leaves.add(leaf)

        removals.update(selected_logs)
        removals.update(selected_leaves)

    return removals


def find_building_intersecting_tree_blocks(
    plots: Sequence[Plot],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
) -> Set[Tuple[int, int, int]]:
    """Remove complete trees intersecting buildings and their clear margins."""
    if not TERRAIN_FIRST_REMOVE_DAMAGED_TREES or not plots:
        return set()

    seed_cells: Set[Pos2D] = set()
    scan_rects: List[Rect] = []
    for plot in plots:
        margin = (
            LANDMARK_TREE_CLEAR_MARGIN
            if plot.kind == "landmark"
            else BUILDING_TREE_CLEAR_MARGIN
        )
        seed_rect = _clipped_rect(rect_with_margin(plot.rect, margin), ba)
        seed_cells.update(rect_cells(seed_rect))
        scan_rects.append(
            _clipped_rect(
                rect_with_margin(seed_rect, TERRAIN_DAMAGED_TREE_SCAN_RADIUS),
                ba,
            )
        )

    if not seed_cells:
        return set()

    terrain_rect = (
        min(rect[0] for rect in scan_rects),
        min(rect[1] for rect in scan_rects),
        max(rect[2] for rect in scan_rects),
        max(rect[3] for rect in scan_rects),
    )
    return find_damaged_tree_blocks(
        seed_cells,
        terrain_rect,
        heights,
        floor_heights,
        ba,
    )


def plan_terrain_first_surface(
    ba: dict,
    center: Pos2D,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    biome_forbidden: Set[Pos2D],
) -> Tuple[
    Dict[Pos2D, int],
    Set[Pos2D],
    Set[Pos2D],
    Set[Pos2D],
    Rect,
    int,
]:
    """Plan a sealed broad surface without leaving protected land pillars.

    V31 never omits a terrain column merely because a tree is present. Every
    valid interior column receives a target. A tree is preserved only when its
    ground remains exactly unchanged; otherwise the whole damaged tree is
    removed before the terrain is written. This removes the isolated dirt/stone
    chunks that earlier versions left beneath protected trunks and crowns.
    """
    terrain_rect = _terrain_first_rect(ba, center)
    x0, z0, x1, z1 = terrain_rect
    original_tree_cells = _terrain_first_tree_cells(
        terrain_rect, heights, floor_heights, biome_forbidden
    )
    original_tree_cells -= water_cells

    grade = _terrain_first_grade(
        terrain_rect,
        heights,
        floor_heights,
        water_cells,
        biome_forbidden,
        original_tree_cells,
    )

    ground: Dict[Pos2D, int] = {}
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            pos = (x, z)
            if pos in biome_forbidden or pos not in heights:
                continue
            ground[pos] = _terrain_ground_top(pos, heights, floor_heights)

    mountain_cells: Set[Pos2D] = set()
    radius = TERRAIN_FIRST_SMOOTH_RADIUS
    for (x, z), existing in ground.items():
        local: List[int] = []
        for ox in range(-radius, radius + 1, 2):
            for oz in range(-radius, radius + 1, 2):
                sample = (x + ox, z + oz)
                if sample in ground and sample not in water_cells:
                    local.append(ground[sample])
        local_low = _percentile_int(local, 0.25) if local else existing
        if (
            existing >= grade + MOUNTAIN_ABOVE_GRADE_TRIGGER
            or existing - local_low >= MOUNTAIN_LOCAL_RELIEF_TRIGGER
        ):
            mountain_cells.add((x, z))

    targets: Dict[Pos2D, int] = {}
    for (x, z), existing in ground.items():
        pos = (x, z)
        local: List[int] = []
        for ox in range(-radius, radius + 1, 2):
            for oz in range(-radius, radius + 1, 2):
                sample = (x + ox, z + oz)
                if sample in ground and sample not in water_cells:
                    local.append(ground[sample])
        local_median = int(round(statistics.median(local))) if local else grade

        terrace = 0
        if TERRAIN_FIRST_TERRACE_VARIATION:
            terrace = stable_rng(
                SEED, x // 14, z // 14, 26001
            ).randint(0, TERRAIN_FIRST_TERRACE_VARIATION)

        broad_grade = grade + terrace
        desired = int(round(broad_grade * 0.78 + local_median * 0.22))

        if pos in water_cells or existing <= grade - TERRAIN_FIRST_RAVINE_TRIGGER:
            desired = max(desired, grade)
        if TERRAIN_FIRST_RECLAIM_WATER and pos in water_cells:
            desired = max(desired, surface_top_y(pos, heights))
        if pos in mountain_cells:
            desired = min(desired, broad_grade)

        edge_distance = min(x - x0, x1 - x, z - z0, z1 - z)
        blend = min(1.0, max(0.0, edge_distance / TERRAIN_FIRST_BLEND_WIDTH))
        target = int(round(existing * (1.0 - blend) + desired * blend))
        target = max(existing - TERRAIN_FIRST_MAX_CUT, target)
        target = min(existing + TERRAIN_FIRST_MAX_FILL, target)

        if pos in water_cells:
            if TERRAIN_FIRST_RECLAIM_WATER:
                target = max(target, surface_top_y(pos, heights))
            else:
                target = max(target, min(grade, SEA_SURFACE_BLOCK_Y + 2))
        targets[pos] = target

    # Smooth the complete field. No tree columns are skipped, so smoothing
    # cannot leave a tall protected island inside the formed settlement.
    for _ in range(4):
        updated = dict(targets)
        for (x, z), value in targets.items():
            neighbors = [
                targets[p]
                for p in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1))
                if p in targets
            ]
            if not neighbors:
                continue
            low = min(neighbors) - 1
            high = max(neighbors) + 1
            updated[(x, z)] = max(low, min(high, value))
        targets = updated

    if TERRAIN_FIRST_RECLAIM_WATER:
        for pos in water_cells:
            if pos in targets and pos in heights:
                targets[pos] = max(targets[pos], surface_top_y(pos, heights))

    protected: Set[Pos2D] = {
        pos
        for pos in original_tree_cells
        if pos in targets and targets[pos] == ground.get(pos)
    }
    damaged_tree_seed_cells: Set[Pos2D] = {
        pos
        for pos in original_tree_cells
        if pos in targets and targets[pos] != ground.get(pos)
    }

    # Catch crowns/roots touching a changed neighboring column even when the
    # tree's own ground column happens to remain at the same Y.
    changed_cells = {
        pos for pos, target in targets.items()
        if target != ground.get(pos, target) or pos in water_cells
    }
    if changed_cells and original_tree_cells:
        radius = TERRAIN_DAMAGED_TREE_IMPACT_RADIUS
        for x, z in changed_cells:
            for ox in range(-radius, radius + 1):
                for oz in range(-radius, radius + 1):
                    candidate = (x + ox, z + oz)
                    if candidate in original_tree_cells:
                        damaged_tree_seed_cells.add(candidate)
                        protected.discard(candidate)

    return (
        targets,
        protected,
        mountain_cells,
        damaged_tree_seed_cells,
        terrain_rect,
        grade,
    )

def build_terrain_first_blocks(
    targets: Dict[Pos2D, int],
    protected: Set[Pos2D],
    mountain_cells: Set[Pos2D],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    ba: dict,
) -> Tuple[List[dict], dict]:
    """Build the first physical placement pass for terrain formation."""
    del protected  # protected cells are omitted from targets already.
    fill_block = _terrain_first_fill_block()
    surface_block = _terrain_first_surface_block()
    output: List[dict] = []
    stats = {
        "columns": 0,
        "filled": 0,
        "cut": 0,
        "ravine_fills": 0,
        "mountain_cuts": 0,
        "water_columns_reclaimed": 0,
        "subgrade_blocks": 0,
    }

    for (x, z), target in sorted(targets.items()):
        existing = _terrain_ground_top((x, z), heights, floor_heights)
        visible_top = heights.get((x, z), existing + 1) - 1
        delta = target - existing
        stats["columns"] += 1
        if (x, z) in water_cells and TERRAIN_FIRST_RECLAIM_WATER:
            stats["water_columns_reclaimed"] += 1

        if delta > 0:
            stats["filled"] += 1
            if delta >= TERRAIN_FIRST_RAVINE_TRIGGER:
                stats["ravine_fills"] += 1
            for y in range(existing + 1, target):
                if in_build_area_xyz(ba, x, y, z):
                    output.append(b(fill_block, x, y, z))
        elif delta < 0:
            stats["cut"] += 1
            if (x, z) in mountain_cells:
                stats["mountain_cuts"] += 1
            clear_end = (
                ba["y2"]
                if TERRAIN_CLEAR_CUT_COLUMNS_TO_SKY
                else min(ba["y2"], max(existing, visible_top) + 2)
            )
            for y in range(target + 1, clear_end + 1):
                output.append(b("air", x, y, z))

        # Seal the complete shallow subgrade, even when the original heightmap
        # hid a cave entrance below an apparently normal surface.
        subgrade_start = max(ba["y1"], target - TERRAIN_FIRST_SOLID_DEPTH)
        for y in range(subgrade_start, target):
            output.append(b(fill_block, x, y, z))
            stats["subgrade_blocks"] += 1

        output.append(b(surface_block, x, target, z))

    return output, stats



def _refresh_post_terrain_state(
    ba: dict,
    biome_lookup: Dict[Pos2D, str],
) -> Tuple[
    Dict[Pos2D, int],
    Dict[Pos2D, int],
    Set[Pos2D],
    Set[Pos2D],
]:
    """Re-read terrain and water after a physical correction pass."""
    refreshed_heights = get_height_lookup(
        ba["x1"], ba["x2"], ba["z1"], ba["z2"], HEIGHTMAP_TYPE
    )
    refreshed_floor = get_height_lookup(
        ba["x1"], ba["x2"], ba["z1"], ba["z2"], "OCEAN_FLOOR_NO_PLANTS"
    )
    refreshed_water, refreshed_blocked = build_water_sets(
        refreshed_heights,
        refreshed_floor,
        ba,
        WATER_BUFFER,
        biome_lookup,
    )
    return (
        refreshed_heights,
        refreshed_floor,
        refreshed_water,
        refreshed_blocked,
    )


def build_post_terrain_audit_blocks(
    targets: Dict[Pos2D, int],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    ba: dict,
    seal_all_columns: bool,
) -> Tuple[List[dict], dict]:
    """Repair terrain defects found after the first terrain-forming pass.

    The original target field is the source of truth. Columns below it are
    filled, columns above it are cleared, all repaired surfaces are restored to
    biome-matched ground, and the subgrade is packed so caves cannot remain
    visible immediately below roads, buildings, or walls.
    """
    fill_block = _terrain_first_fill_block()
    surface_block = _terrain_first_surface_block()
    output: List[dict] = []
    stats = {
        "checked_columns": 0,
        "hole_columns": 0,
        "large_hole_columns": 0,
        "leftover_chunk_columns": 0,
        "water_columns": 0,
        "sealed_columns": 0,
        "blocks": 0,
    }

    for (x, z), target in sorted(targets.items()):
        if not in_build_area_xz(ba, x, z):
            continue
        stats["checked_columns"] += 1

        actual_ground = _terrain_ground_top(
            (x, z), heights, floor_heights
        )
        visible_top = heights.get((x, z), actual_ground + 1) - 1
        is_water = (x, z) in water_cells

        hole_depth = max(0, target - actual_ground)
        leftover_height = max(
            0,
            actual_ground - target,
            visible_top - target - TERRAIN_POST_CHUNK_TOLERANCE,
        )
        defective = hole_depth > 0 or leftover_height > 0 or is_water

        if hole_depth > 0:
            stats["hole_columns"] += 1
            if hole_depth >= TERRAIN_FIRST_RAVINE_TRIGGER:
                stats["large_hole_columns"] += 1
        if leftover_height > 0:
            stats["leftover_chunk_columns"] += 1
        if is_water:
            stats["water_columns"] += 1

        if not defective and not seal_all_columns:
            continue

        stats["sealed_columns"] += 1

        # Remove every leftover dirt/stone/log/leaf block above the planned
        # surface. Sky clearing ensures floating chunks cannot survive.
        if leftover_height > 0:
            clear_end = (
                ba["y2"]
                if TERRAIN_CLEAR_CUT_COLUMNS_TO_SKY
                else min(ba["y2"], max(actual_ground, visible_top) + 3)
            )
            for y in range(target + 1, clear_end + 1):
                output.append(b("air", x, y, z))

        # Fill the complete detected depression. Even when the surface already
        # matches, reinforce a deeper subgrade during the first audit pass.
        fill_start = max(
            ba["y1"],
            min(actual_ground + 1, target - TERRAIN_POST_SOLID_DEPTH),
        )
        for y in range(fill_start, target):
            output.append(b(fill_block, x, y, z))

        # Reassert the biome surface after all fill/cut operations.
        output.append(b(surface_block, x, target, z))

    stats["blocks"] = len(output)
    return output, stats


def _post_terrain_tree_seed_cells(
    targets: Dict[Pos2D, int],
    changed_cells: Set[Pos2D],
    terrain_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    ba: dict,
) -> Tuple[Set[Pos2D], Rect]:
    """Find tree remnants damaged by terrain changes, including outside walls."""
    expanded_rect = _clipped_rect(
        rect_with_margin(terrain_rect, TERRAIN_POST_TREE_SCAN_MARGIN),
        ba,
    )
    post_tree_cells = _terrain_first_tree_cells(
        expanded_rect,
        heights,
        floor_heights,
        set(),
    )
    post_tree_cells -= water_cells

    suspicious: Set[Pos2D] = set()
    radius = TERRAIN_POST_TREE_TOUCH_RADIUS

    for x, z in post_tree_cells:
        pos = (x, z)

        # Any tree material still standing directly over a formed column is a
        # leftover remnant, even when its trunk is just outside the settlement.
        if pos in targets:
            target = targets[pos]
            visible_top = heights.get(pos, target + 1) - 1
            if visible_top > target:
                suspicious.add(pos)
                continue

        # Trees outside the settlement are also removed when their trunk/crown
        # touches terrain that was physically cut, filled, or water-reclaimed.
        touched = False
        for ox in range(-radius, radius + 1):
            if touched:
                break
            for oz in range(-radius, radius + 1):
                if (x + ox, z + oz) in changed_cells:
                    touched = True
                    break
        if touched:
            suspicious.add(pos)

    return suspicious, expanded_rect


def run_post_terrain_audit(
    targets: Dict[Pos2D, int],
    terrain_rect: Rect,
    changed_cells: Set[Pos2D],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    biome_lookup: Dict[Pos2D, str],
    ba: dict,
) -> Tuple[
    Dict[Pos2D, int],
    Dict[Pos2D, int],
    Set[Pos2D],
    Set[Pos2D],
    dict,
]:
    """Perform the required second scan and physical cleanup."""
    total_stats = {
        "passes": 0,
        "hole_columns": 0,
        "large_hole_columns": 0,
        "leftover_chunk_columns": 0,
        "water_columns": 0,
        "terrain_blocks": 0,
        "tree_seed_cells": 0,
        "tree_blocks_removed": 0,
        "final_defects": 0,
    }

    current_heights = heights
    current_floor = floor_heights
    current_water = water_cells
    current_blocked = water_blocked

    for pass_index in range(TERRAIN_POST_AUDIT_PASSES):
        audit_blocks, stats = build_post_terrain_audit_blocks(
            targets,
            current_heights,
            current_floor,
            current_water,
            ba,
            seal_all_columns=(pass_index == 0),
        )
        defects = (
            stats["hole_columns"]
            + stats["leftover_chunk_columns"]
            + stats["water_columns"]
        )
        total_stats["passes"] += 1
        total_stats["hole_columns"] += stats["hole_columns"]
        total_stats["large_hole_columns"] += stats["large_hole_columns"]
        total_stats["leftover_chunk_columns"] += stats["leftover_chunk_columns"]
        total_stats["water_columns"] += stats["water_columns"]
        total_stats["terrain_blocks"] += len(audit_blocks)

        print(
            f"POST-TERRAIN AUDIT {pass_index + 1}: "
            f"holes={stats['hole_columns']} "
            f"(large={stats['large_hole_columns']}), "
            f"leftover chunks={stats['leftover_chunk_columns']}, "
            f"water={stats['water_columns']}, "
            f"sealed columns={stats['sealed_columns']}"
        )

        if audit_blocks:
            put_blocks(audit_blocks, do_block_updates=False)
            (
                current_heights,
                current_floor,
                current_water,
                current_blocked,
            ) = _refresh_post_terrain_state(ba, biome_lookup)

        if pass_index > 0 and defects == 0:
            break

    # Re-scan actual Minecraft tree blocks after the terrain has physically
    # changed. The scan extends outside the settlement so damaged trunks and
    # crowns across the boundary are removed as one complete tree.
    tree_seeds, expanded_tree_rect = _post_terrain_tree_seed_cells(
        targets,
        changed_cells,
        terrain_rect,
        current_heights,
        current_floor,
        current_water,
        ba,
    )
    total_stats["tree_seed_cells"] = len(tree_seeds)

    leftover_tree_positions = find_damaged_tree_blocks(
        tree_seeds,
        expanded_tree_rect,
        current_heights,
        current_floor,
        ba,
    )
    if leftover_tree_positions:
        tree_blocks = [
            b("air", x, y, z)
            for x, y, z in sorted(
                leftover_tree_positions,
                key=lambda p: (-p[1], p[0], p[2]),
            )
        ]
        put_blocks(tree_blocks, do_block_updates=False)
        total_stats["tree_blocks_removed"] = len(tree_blocks)
        (
            current_heights,
            current_floor,
            current_water,
            current_blocked,
        ) = _refresh_post_terrain_state(ba, biome_lookup)

    # Final verification after tree cleanup. This catches a ground chunk or
    # depression that was previously hidden by logs/leaves in the heightmap.
    verification_blocks, verification = build_post_terrain_audit_blocks(
        targets,
        current_heights,
        current_floor,
        current_water,
        ba,
        seal_all_columns=False,
    )
    final_defects = (
        verification["hole_columns"]
        + verification["leftover_chunk_columns"]
        + verification["water_columns"]
    )
    total_stats["final_defects"] = final_defects
    if verification_blocks:
        print(
            "POST-TERRAIN FINAL REPAIR: "
            f"holes={verification['hole_columns']}, "
            f"leftover chunks={verification['leftover_chunk_columns']}, "
            f"water={verification['water_columns']}"
        )
        put_blocks(verification_blocks, do_block_updates=False)
        total_stats["terrain_blocks"] += len(verification_blocks)
        (
            current_heights,
            current_floor,
            current_water,
            current_blocked,
        ) = _refresh_post_terrain_state(ba, biome_lookup)
        total_stats["final_defects"] = 0

    return (
        current_heights,
        current_floor,
        current_water,
        current_blocked,
        total_stats,
    )

def form_settlement_terrain_first(
    ba: dict,
    center: Pos2D,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    biome_lookup: Dict[Pos2D, str],
    water_cells: Set[Pos2D],
    biome_forbidden: Set[Pos2D],
) -> Tuple[
    Dict[Pos2D, int],
    Dict[Pos2D, int],
    Set[Pos2D],
    Set[Pos2D],
    Dict[Pos2D, str],
    dict,
]:
    """Form terrain, re-scan it, repair defects, then refresh everything."""
    (
        targets,
        protected,
        mountain_cells,
        damaged_tree_seed_cells,
        terrain_rect,
        grade,
    ) = plan_terrain_first_surface(
        ba,
        center,
        heights,
        floor_heights,
        water_cells,
        biome_forbidden,
    )

    original_ground = {
        pos: _terrain_ground_top(pos, heights, floor_heights)
        for pos in targets
    }
    changed_cells = {
        pos
        for pos, target in targets.items()
        if target != original_ground.get(pos, target) or pos in water_cells
    }

    damaged_tree_positions = find_damaged_tree_blocks(
        damaged_tree_seed_cells,
        terrain_rect,
        heights,
        floor_heights,
        ba,
    )
    damaged_tree_blocks = [
        b("air", x, y, z)
        for x, y, z in sorted(
            damaged_tree_positions,
            key=lambda p: (-p[1], p[0], p[2]),
        )
    ]
    terrain_blocks, stats = build_terrain_first_blocks(
        targets,
        protected,
        mountain_cells,
        heights,
        floor_heights,
        water_cells,
        ba,
    )
    stats.update({
        "rect": terrain_rect,
        "grade": grade,
        "protected_trees": len(protected),
        "changed_columns": len(changed_cells),
        "damaged_tree_seed_cells": len(damaged_tree_seed_cells),
        "damaged_tree_blocks_removed": len(damaged_tree_blocks),
        "explicit_blocks": len(damaged_tree_blocks) + len(terrain_blocks),
    })

    print(
        "TERRAIN-FIRST PASS: forming the full settlement ground before "
        "landmarks, buildings, roads, or walls..."
    )
    print(
        f"  area x={terrain_rect[0]}..{terrain_rect[2]}, "
        f"z={terrain_rect[1]}..{terrain_rect[3]}, shared grade≈Y{grade}"
    )
    print(
        f"  columns={stats['columns']}, changed={stats['changed_columns']}, "
        f"ravine fills={stats['ravine_fills']}, "
        f"mountain cuts={stats['mountain_cuts']}, "
        f"water reclaimed={stats['water_columns_reclaimed']}, "
        f"preserved tree cells={stats['protected_trees']}, "
        f"damaged tree blocks removed={stats['damaged_tree_blocks_removed']}"
    )

    put_blocks(damaged_tree_blocks + terrain_blocks, do_block_updates=False)

    print("Refreshing heightmaps after initial terrain formation...")
    (
        new_heights,
        new_floor_heights,
        new_water,
        new_water_blocked,
    ) = _refresh_post_terrain_state(ba, biome_lookup)

    if TERRAIN_POST_AUDIT_ENABLED:
        print(
            "Running the post-terrain scan for holes, leftover land chunks, "
            "water, logs, and leaves..."
        )
        (
            new_heights,
            new_floor_heights,
            new_water,
            new_water_blocked,
            audit_stats,
        ) = run_post_terrain_audit(
            targets,
            terrain_rect,
            changed_cells,
            new_heights,
            new_floor_heights,
            new_water,
            new_water_blocked,
            biome_lookup,
            ba,
        )
        stats["post_terrain_audit"] = audit_stats
        stats["explicit_blocks"] += (
            audit_stats["terrain_blocks"]
            + audit_stats["tree_blocks_removed"]
        )
        print(
            "POST-TERRAIN CLEANUP COMPLETE: "
            f"holes repaired={audit_stats['hole_columns']}, "
            f"large holes={audit_stats['large_hole_columns']}, "
            f"land chunks removed={audit_stats['leftover_chunk_columns']}, "
            f"outside/leftover tree blocks removed="
            f"{audit_stats['tree_blocks_removed']}"
        )

    return (
        new_heights,
        new_floor_heights,
        new_water,
        new_water_blocked,
        biome_lookup,
        stats,
    )


def _xz_distance_to_rect(pos: Pos2D, rect: Rect) -> int:
    """Chebyshev distance from one X/Z cell to an inclusive rectangle."""
    x, z = pos
    x0, z0, x1, z1 = rect
    dx = 0 if x0 <= x <= x1 else min(abs(x - x0), abs(x - x1))
    dz = 0 if z0 <= z <= z1 else min(abs(z - z0), abs(z - z1))
    return max(dx, dz)


def plan_final_structure_terrain(
    plots: Sequence[Plot],
    ba: dict,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    biome_forbidden: Set[Pos2D],
    settlement_grade: int,
) -> Tuple[Dict[Pos2D, int], Rect, Rect, Set[Pos2D]]:
    """Create the final terrain field from actual building footprints/Y levels.

    The wall-safe core is completely covered, rather than being a collection of
    disconnected building pads. Building margins are locked to their exact plot
    Y, preventing the surrounding terrain from burying walls or lower floors.
    Only the outer transition ring blends back into untouched terrain.
    """
    if not plots:
        empty = (ba["x1"], ba["z1"], ba["x1"], ba["z1"])
        return {}, empty, empty, set()

    building_bounds = (
        min(plot.rect[0] for plot in plots),
        min(plot.rect[1] for plot in plots),
        max(plot.rect[2] for plot in plots),
        max(plot.rect[3] for plot in plots),
    )
    wall_safe_margin = max(
        FINAL_TERRAIN_WALL_SAFE_MARGIN,
        WALL_PERIMETER_MARGIN + 2,
    )
    core_rect = _clipped_rect(
        rect_with_margin(building_bounds, wall_safe_margin),
        ba,
    )
    full_rect = _clipped_rect(
        rect_with_margin(core_rect, FINAL_TERRAIN_EDGE_BLEND),
        ba,
    )

    targets: Dict[Pos2D, int] = {}
    exact_pad_cells: Set[Pos2D] = set()
    x0, z0, x1, z1 = full_rect

    # Exact building-pad ownership. When margins overlap, the nearest footprint
    # wins; plot levels already differ by at most one block.
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            pos = (x, z)
            if pos in biome_forbidden or pos not in heights:
                continue

            nearest_plot = min(
                plots,
                key=lambda plot: (
                    _xz_distance_to_rect(pos, plot.rect),
                    euclid(pos, plot.center),
                ),
            )
            distance_to_plot = _xz_distance_to_rect(pos, nearest_plot.rect)
            natural = _terrain_ground_top(pos, heights, floor_heights)

            if distance_to_plot <= FINAL_TERRAIN_BUILDING_PAD_MARGIN:
                target = nearest_plot.target_top_y
                exact_pad_cells.add(pos)
            elif (
                core_rect[0] <= x <= core_rect[2]
                and core_rect[1] <= z <= core_rect[3]
            ):
                # A single broad wall-safe terrace removes land chunks between
                # buildings. A nearest building at +1 is approached gradually.
                target = settlement_grade
                if nearest_plot.target_top_y > settlement_grade and distance_to_plot <= 7:
                    target = settlement_grade + 1
            else:
                edge_distance = min(
                    x - full_rect[0], full_rect[2] - x,
                    z - full_rect[1], full_rect[3] - z,
                )
                blend = min(
                    1.0,
                    max(0.0, edge_distance / max(1, FINAL_TERRAIN_EDGE_BLEND)),
                )
                target = int(round(natural * (1.0 - blend) + settlement_grade * blend))

            targets[pos] = target

    # Ensure a maximum one-block grade change except across the outermost blend.
    for _ in range(4):
        updated = dict(targets)
        for pos, value in targets.items():
            if pos in exact_pad_cells:
                continue
            x, z = pos
            neighbors = [
                targets[p]
                for p in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1))
                if p in targets
            ]
            if not neighbors:
                continue
            updated[pos] = max(min(neighbors) - 1, min(max(neighbors) + 1, value))
        targets = updated

    # Re-lock pads after smoothing.
    for pos in exact_pad_cells:
        nearest_plot = min(
            plots,
            key=lambda plot: (
                _xz_distance_to_rect(pos, plot.rect),
                euclid(pos, plot.center),
            ),
        )
        targets[pos] = nearest_plot.target_top_y

    return targets, core_rect, full_rect, exact_pad_cells


def build_final_structure_terrain_blocks(
    targets: Dict[Pos2D, int],
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    ba: dict,
    only_defects: bool = False,
) -> Tuple[List[dict], dict, Set[Pos2D]]:
    """Physically force the world to the final structure-aware target field."""
    fill_block = _terrain_first_fill_block()
    surface_block = _terrain_first_surface_block()
    output: List[dict] = []
    changed: Set[Pos2D] = set()
    stats = {
        "columns": 0,
        "cut_columns": 0,
        "fill_columns": 0,
        "water_columns": 0,
        "verified_columns": 0,
        "blocks": 0,
    }

    for (x, z), target in sorted(targets.items()):
        if not in_build_area_xz(ba, x, z):
            continue
        stats["columns"] += 1
        ground = _terrain_ground_top((x, z), heights, floor_heights)
        visible = heights.get((x, z), ground + 1) - 1
        water = (x, z) in water_cells
        defect = ground != target or visible > target or water
        if only_defects and not defect:
            continue
        if not defect and not only_defects:
            # Still write a solid subgrade in the wall/building core.
            pass
        else:
            changed.add((x, z))

        if ground > target or visible > target:
            stats["cut_columns"] += 1
            clear_end = ba["y2"] if TERRAIN_CLEAR_CUT_COLUMNS_TO_SKY else min(
                ba["y2"], max(ground, visible) + 3
            )
            for y in range(target + 1, clear_end + 1):
                output.append(b("air", x, y, z))

        if ground < target:
            stats["fill_columns"] += 1
        if water:
            stats["water_columns"] += 1

        # Fill from the detected floor for true holes/ravines, and at least the
        # configured solid depth for hidden cave mouths below normal-looking land.
        fill_start = max(
            ba["y1"],
            min(ground + 1, target - FINAL_TERRAIN_SOLID_DEPTH),
        )
        for y in range(fill_start, target):
            output.append(b(fill_block, x, y, z))
        output.append(b(surface_block, x, target, z))
        stats["verified_columns"] += 1

    stats["blocks"] = len(output)
    return output, stats, changed


def run_final_structure_terrain_conform(
    plots: Sequence[Plot],
    settlement_grade: int,
    ba: dict,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    biome_lookup: Dict[Pos2D, str],
    biome_forbidden: Set[Pos2D],
) -> Tuple[
    Dict[Pos2D, int],
    Dict[Pos2D, int],
    Set[Pos2D],
    Set[Pos2D],
    dict,
]:
    """Lock final building and wall terrain before planning roads/walls."""
    targets, core_rect, full_rect, exact_pad_cells = plan_final_structure_terrain(
        plots,
        ba,
        heights,
        floor_heights,
        biome_forbidden,
        settlement_grade,
    )
    if not targets:
        return heights, floor_heights, water_cells, water_blocked, {}

    original_ground = {
        pos: _terrain_ground_top(pos, heights, floor_heights)
        for pos in targets
    }
    changed_seed_cells = {
        pos for pos, target in targets.items()
        if target != original_ground.get(pos, target) or pos in water_cells
    }

    # Detect every tree touched by this final terrain field, including crowns
    # rooted just outside the formed rectangle.
    expanded_tree_rect = _clipped_rect(
        rect_with_margin(full_rect, TERRAIN_POST_TREE_SCAN_MARGIN), ba
    )
    tree_cells = _terrain_first_tree_cells(
        expanded_tree_rect, heights, floor_heights, biome_forbidden
    ) - water_cells
    damaged_tree_seeds: Set[Pos2D] = set()
    radius = FINAL_TERRAIN_TREE_TOUCH_RADIUS
    for tx, tz in tree_cells:
        touched = False
        for ox in range(-radius, radius + 1):
            if touched:
                break
            for oz in range(-radius, radius + 1):
                if (tx + ox, tz + oz) in changed_seed_cells:
                    touched = True
                    break
        if touched:
            damaged_tree_seeds.add((tx, tz))

    tree_positions = find_all_settlement_tree_blocks(
        set(targets),
        expanded_tree_rect,
        heights,
        floor_heights,
        ba,
    )
    if tree_positions:
        put_blocks(
            [b("air", x, y, z) for x, y, z in sorted(
                tree_positions, key=lambda p: (-p[1], p[0], p[2])
            )],
            do_block_updates=False,
        )
        heights, floor_heights, water_cells, water_blocked = (
            _refresh_post_terrain_state(ba, biome_lookup)
        )

    terrain_blocks, first_stats, changed = build_final_structure_terrain_blocks(
        targets,
        heights,
        floor_heights,
        water_cells,
        ba,
        only_defects=False,
    )
    print(
        "FINAL STRUCTURE TERRAIN PASS: "
        f"core x={core_rect[0]}..{core_rect[2]}, "
        f"z={core_rect[1]}..{core_rect[3]}, "
        f"exact building-pad cells={len(exact_pad_cells)}, "
        f"tree blocks removed={len(tree_positions)}"
    )
    put_blocks(terrain_blocks, do_block_updates=False)
    heights, floor_heights, water_cells, water_blocked = (
        _refresh_post_terrain_state(ba, biome_lookup)
    )

    verify_stats: List[dict] = []
    for verify_index in range(FINAL_TERRAIN_VERIFY_PASSES):
        repair_blocks, stats, _repair_changed = build_final_structure_terrain_blocks(
            targets,
            heights,
            floor_heights,
            water_cells,
            ba,
            only_defects=True,
        )
        verify_stats.append(stats)
        print(
            f"FINAL TERRAIN VERIFY {verify_index + 1}: "
            f"repairs={stats['verified_columns']}, "
            f"cuts={stats['cut_columns']}, fills={stats['fill_columns']}, "
            f"water={stats['water_columns']}"
        )
        if not repair_blocks:
            break
        put_blocks(repair_blocks, do_block_updates=False)
        heights, floor_heights, water_cells, water_blocked = (
            _refresh_post_terrain_state(ba, biome_lookup)
        )

    # Last exact pad assertion: no structure may be planned below surrounding
    # ground. Repair any column hidden by a stale heightmap/tree remnant.
    pad_repairs: List[dict] = []
    fill_block = _terrain_first_fill_block()
    surface_block = _terrain_first_surface_block()
    for pos in exact_pad_cells:
        target = targets[pos]
        ground = _terrain_ground_top(pos, heights, floor_heights)
        visible = heights.get(pos, ground + 1) - 1
        if ground == target and visible <= target and pos not in water_cells:
            continue
        x, z = pos
        for y in range(target + 1, ba["y2"] + 1):
            pad_repairs.append(b("air", x, y, z))
        fill_start = max(ba["y1"], min(ground + 1, target - FINAL_TERRAIN_SOLID_DEPTH))
        for y in range(fill_start, target):
            pad_repairs.append(b(fill_block, x, y, z))
        pad_repairs.append(b(surface_block, x, target, z))
    if pad_repairs:
        print(f"FINAL BUILDING-PAD REPAIR: {len(pad_repairs)} blocks")
        put_blocks(pad_repairs, do_block_updates=False)
        heights, floor_heights, water_cells, water_blocked = (
            _refresh_post_terrain_state(ba, biome_lookup)
        )

    return (
        heights,
        floor_heights,
        water_cells,
        water_blocked,
        {
            "targets": len(targets),
            "core_rect": core_rect,
            "full_rect": full_rect,
            "tree_blocks_removed": len(tree_positions),
            "first_pass": first_stats,
            "verify": verify_stats,
            "pad_repair_blocks": len(pad_repairs),
        },
    )

def run_single_settlement() -> dict:
    global GLOBAL_MEDIAN_TOP_Y

    random.seed(SEED)
    ba = (
        dict(ACTIVE_BUILD_AREA_OVERRIDE)
        if ACTIVE_BUILD_AREA_OVERRIDE is not None
        else get_build_area()
    )
    if ACTIVE_SETTLEMENT_LABEL:
        print(f"\n===== {ACTIVE_SETTLEMENT_LABEL} =====")
    if ACTIVE_LANDMARK_OVERRIDE is not None:
        requested_landmark = ACTIVE_LANDMARK_OVERRIDE
        print(f"Using planned biome-interior landmark center: {requested_landmark}")
    elif AUTO_CENTER_LANDMARK:
        requested_landmark = (
            (ba["x1"] + ba["x2"]) // 2,
            (ba["z1"] + ba["z2"]) // 2,
        )
        print(
            f"Using the active settlement-area middle as the landmark: "
            f"{requested_landmark}"
        )
    else:
        requested_landmark = prompt_landmark_center(ba)
    assets = load_plains_building_assets()
    wall_library = load_wall_module_library() if GENERATE_WALLS else {}
    assets_by_filename = {asset.path.name: asset for asset in assets}

    landmark_asset = assets_by_filename.get(LANDMARK_FILENAME)
    if landmark_asset is None:
        raise FileNotFoundError(f"Landmark asset was not loaded: {LANDMARK_FILENAME}")

    normal_assets = [
        asset
        for asset in assets
        if asset.path.name != LANDMARK_FILENAME
    ]
    print(f"Unique central landmark: {LANDMARK_FILENAME}: 1")
    print(
        f"Automatically repeatable building types discovered: "
        f"{len(normal_assets)}"
    )
    for asset in normal_assets:
        print(f"  {asset.path.name}")

    print("Reading heightmaps...")
    heights = get_height_lookup(
        ba["x1"], ba["x2"], ba["z1"], ba["z2"], HEIGHTMAP_TYPE
    )
    floor_heights = get_height_lookup(
        ba["x1"], ba["x2"], ba["z1"], ba["z2"], "OCEAN_FLOOR_NO_PLANTS"
    )
    tops = [height - 1 for height in heights.values()]
    GLOBAL_MEDIAN_TOP_Y = int(round(statistics.median(tops))) if tops else 64

    print("Reading biomes for water detection...")
    biome_lookup = get_biome_lookup(
        ba["x1"], ba["x2"], ba["z1"], ba["z2"], SEA_SURFACE_BLOCK_Y
    )
    biome_groups = Counter(
        biome_to_group(biome_lookup.get(pos, "minecraft:plains"))
        for pos in biome_lookup
    )

    water_cells, water_blocked = build_water_sets(
        heights, floor_heights, ba, WATER_BUFFER, biome_lookup
    )
    print(f"Median terrain top Y: {GLOBAL_MEDIAN_TOP_Y}")
    print(
        f"Water cells: {len(water_cells)}; "
        f"water-buffer blocked cells: {len(water_blocked)}"
    )

    biome_forbidden: Set[Pos2D] = set()
    if ENFORCE_TRIBE_BIOME_BOUNDARY:
        biome_forbidden = {
            pos
            for pos in heights
            if biome_to_group(
                biome_lookup.get(pos, "minecraft:plains")
            ) != ACTIVE_TRIBE
        }
        print(
            f"Biome-boundary blocked cells for {ACTIVE_TRIBE}: "
            f"{len(biome_forbidden)}"
        )
    settlement_blocked = set(water_blocked) | biome_forbidden

    terrain_first_stats: dict = {}
    if TERRAIN_FORM_FIRST:
        terrain_center = (
            requested_landmark
            if requested_landmark is not None
            else ((ba["x1"] + ba["x2"]) // 2, (ba["z1"] + ba["z2"]) // 2)
        )
        (
            heights,
            floor_heights,
            water_cells,
            water_blocked,
            biome_lookup,
            terrain_first_stats,
        ) = form_settlement_terrain_first(
            ba,
            terrain_center,
            heights,
            floor_heights,
            biome_lookup,
            water_cells,
            biome_forbidden,
        )
        tops = [height - 1 for height in heights.values()]
        GLOBAL_MEDIAN_TOP_Y = (
            int(round(statistics.median(tops))) if tops else GLOBAL_MEDIAN_TOP_Y
        )
        settlement_blocked = set(water_blocked) | biome_forbidden
        print(
            f"Terrain-first refresh complete: median top Y={GLOBAL_MEDIAN_TOP_Y}, "
            f"remaining water cells={len(water_cells)}"
        )

    print("Finding the unique landmark plot on the already formed terrain...")
    landmark = find_landmark_plot(
        ba, heights, settlement_blocked, landmark_asset,
        requested_landmark, SEED,
    )

    landmark_biome = biome_lookup.get(landmark.center, "minecraft:plains")
    landmark_group = biome_to_group(landmark_biome)
    if landmark_group != ACTIVE_TRIBE:
        message = (
            f"Landmark biome is {landmark_biome} ({landmark_group}), "
            f"but the active building tribe is {ACTIVE_TRIBE}."
        )
        if STRICT_PLAINS_BIOME:
            raise RuntimeError(message)
        print("WARNING: " + message + f" Continuing with {ACTIVE_TRIBE} buildings/style.")

    print(
        "Automatically filling valid terrain with repeatable normal buildings..."
    )
    normal_buildings = find_auto_building_plots(
        ba,
        heights,
        settlement_blocked,
        landmark,
        normal_assets,
        SEED,
    )

    all_buildings = [landmark] + normal_buildings

    settlement_grade = normalize_plot_levels_for_mountain_flatten(
        all_buildings,
        heights,
        floor_heights,
        ba,
    )
    print(
        f"Shared mountain-flatten settlement grade: Y={settlement_grade}; "
        f"building levels kept within {MOUNTAIN_PLOT_LEVEL_SPREAD} block(s)."
    )

    final_terrain_stats: dict = {}
    if FINAL_TERRAIN_CONFORM_ENABLED:
        print(
            "Reforming terrain again from the actual selected building "
            "footprints before roads, walls, or structures..."
        )
        (
            heights,
            floor_heights,
            water_cells,
            water_blocked,
            final_terrain_stats,
        ) = run_final_structure_terrain_conform(
            all_buildings,
            settlement_grade,
            ba,
            heights,
            floor_heights,
            water_cells,
            water_blocked,
            biome_lookup,
            biome_forbidden,
        )
        settlement_blocked = set(water_blocked) | biome_forbidden
        tops = [height - 1 for height in heights.values()]
        GLOBAL_MEDIAN_TOP_Y = (
            int(round(statistics.median(tops))) if tops else GLOBAL_MEDIAN_TOP_Y
        )
        print(
            f"Final structure-aware terrain refresh complete: "
            f"median top Y={GLOBAL_MEDIAN_TOP_Y}, "
            f"remaining water={len(water_cells)}"
        )

    configured_villager_instructions = (
        build_configured_villager_instructions(all_buildings, ba)
        if SPAWN_CONFIGURED_VILLAGERS
        else []
    )
    print(
        f"Configured villagers queued from building metadata: "
        f"{len(configured_villager_instructions)}"
    )

    wall_placements: List[WallPlacement] = []
    wall_side_status: Dict[str, str] = {}
    gate_waypoints: List[dict] = []
    wall_perimeter: Optional[Rect] = None

    blocks: List[dict] = []
    height_overrides: Dict[Pos2D, int] = {}

    terrain_targets: Dict[Pos2D, int] = {}
    protected_terrain_cells: Set[Pos2D] = set()
    mountain_terrain_cells: Set[Pos2D] = set()
    if GENTLE_SETTLEMENT_TERRAIN and not TERRAIN_FORM_FIRST:
        print(
            "Planning whole-settlement terrain: flattening mountain mass into "
            "broad grass terraces while preserving non-mountain trees..."
        )
        (
            terrain_targets,
            protected_terrain_cells,
            mountain_terrain_cells,
            terrain_rect,
            settlement_grade,
        ) = plan_gentle_settlement_terrain(
            all_buildings,
            ba,
            heights,
            floor_heights,
            settlement_blocked,
            None,
            settlement_grade,
        )
        (
            cut_columns,
            mountain_cut_columns,
            filled_columns,
            hole_columns,
        ) = apply_gentle_settlement_terrain(
            blocks,
            terrain_targets,
            mountain_terrain_cells,
            heights,
            floor_heights,
            ba,
            height_overrides,
        )
        print(
            f"Settlement terrain area: x={terrain_rect[0]}..{terrain_rect[2]}, "
            f"z={terrain_rect[1]}..{terrain_rect[3]}, grade Y={settlement_grade}"
        )
        print(
            f"Terrain columns: changed={len(terrain_targets)}, "
            f"mountain-cut={mountain_cut_columns}, other-cut={cut_columns - mountain_cut_columns}, "
            f"filled={filled_columns}, hole/cave fills={hole_columns}; "
            f"preserved tree cells={len(protected_terrain_cells)}"
        )

    # Wall selection must see the post-flatten terrain rather than the original
    # mountain. Heightmap values are first-free Y, therefore target + 1.
    effective_heights = dict(heights)
    for pos, target_top_y in terrain_targets.items():
        effective_heights[pos] = target_top_y + 1
    for plot in all_buildings:
        for pos in rect_cells(plot.rect):
            effective_heights[pos] = plot.target_top_y + 1

    if GENERATE_WALLS:
        print("Planning V36 decorative wall-library modules around the outer structures...")
        (
            wall_placements,
            wall_side_status,
            gate_waypoints,
            wall_perimeter,
        ) = plan_settlement_walls(
            all_buildings,
            wall_library,
            ba,
            effective_heights,
            water_cells,
            set(biome_forbidden) - set(water_cells),
            SEED,
        )

    wall_connection_blocks: List[dict] = []
    wall_connection_stats = {
        "contour_points": 0,
        "gap_columns": 0,
        "attachment_columns": 0,
        "drained_columns": 0,
    }
    if GENERATE_WALLS and wall_perimeter is not None and WALL_FORCE_CONTINUOUS:
        print(
            "Planning the continuous wall foundation and reclaiming "
            "enclosed water before roads are placed..."
        )
        drain_blocks, wall_connection_blocks, wall_connection_stats = (
            build_continuous_wall_foundation_and_drain(
                all_buildings,
                wall_placements,
                ba,
                effective_heights,
                floor_heights,
                water_cells,
            )
        )
        # Water reclamation belongs in the early terrain pass. Roads placed later
        # remain visible and cannot be overwritten by the wall-support pass.
        blocks.extend(drain_blocks)
        print(
            f"Continuous contour points={wall_connection_stats['contour_points']}, "
            f"fallback connector columns={wall_connection_stats['gap_columns']}, "
            f"module attachment columns={wall_connection_stats.get('attachment_columns', 0)}, "
            f"drained water columns={wall_connection_stats['drained_columns']}, "
            f"wall-over-water columns filled={wall_connection_stats.get('wall_water_columns_filled', 0)}"
        )

    print("Scanning complete trees intersecting buildings and their margins...")
    building_tree_positions = find_building_intersecting_tree_blocks(
        all_buildings,
        heights,
        floor_heights,
        ba,
    )
    if building_tree_positions:
        building_tree_blocks = [
            b("air", x, y, z)
            for x, y, z in sorted(
                building_tree_positions,
                key=lambda p: (-p[1], p[0], p[2]),
            )
        ]
        blocks.extend(building_tree_blocks)
        print(
            f"Complete building-intersecting tree blocks removed: "
            f"{len(building_tree_blocks)}"
        )
    else:
        print("No complete trees intersected the building clearance areas.")

    print("Clearing trees only where structures or mountain cuts require space...")
    if CLEAR_TREES_IN_SETTLEMENT_BOUNDS:
        cleared_cells = clear_trees_in_settlement_bounds(
            blocks, all_buildings, heights, floor_heights,
            ba, settlement_blocked,
        )
        print(f"Settlement bounding-box tree-clearing cells: {cleared_cells}")
    else:
        clear_trees_for_plot(
            blocks, landmark, ba, water_cells=settlement_blocked,
            margin=LANDMARK_TREE_CLEAR_MARGIN,
        )
        for building in normal_buildings:
            clear_trees_for_plot(
                blocks, building, ba, water_cells=settlement_blocked,
                margin=BUILDING_TREE_CLEAR_MARGIN,
            )
        print(
            f"Local clearing: landmark margin={LANDMARK_TREE_CLEAR_MARGIN}, "
            f"building margin={BUILDING_TREE_CLEAR_MARGIN}"
        )

    print("Preparing fill-first landmark and building pads...")
    for building in all_buildings:
        prepare_json_building_plot(
            blocks, building, heights, ba, height_overrides
        )

    paths: List[RoadPath] = []
    if not DISABLE_ROADS and normal_buildings:
        print("Generating roads from the landmark waypoint to building waypoints...")
        paths = build_road_network(
            landmark, normal_buildings, ba, heights, floor_heights,
            height_overrides, SEED, water_cells,
            extra_blocked=biome_forbidden,
        )
        building_cells: Set[Pos2D] = set(biome_forbidden)
        for plot in all_buildings:
            building_cells.update(rect_cells(plot.rect))
        place_roads(
            blocks, paths, ba, heights, floor_heights, biome_lookup,
            height_overrides, building_cells, water_cells, SEED,
        )

    # V16: walls are genuinely the final construction stage. Their terrain
    # supports are queued separately and placed only after all buildings/roads.
    wall_support_blocks: List[dict] = list(wall_connection_blocks)
    if GENERATE_WALLS and wall_perimeter is not None:
        print("Preparing fill-first terrain supports for the final wall stage...")
        wall_support_columns = prepare_wall_supports(
            wall_support_blocks,
            wall_placements,
            effective_heights,
            floor_heights,
            ba,
            water_cells,
        )
        print(f"Wall module support/clearing columns: {wall_support_columns}")
    else:
        wall_support_columns = 0

    print("Preparing complete buildings for the final placement pass...")
    json_blocks: List[dict] = []
    json_block_count = 0
    nbt_buildings: List[Plot] = []
    for building in all_buildings:
        if building_uses_nbt(building):
            nbt_buildings.append(building)
            assert building.asset is not None
            assert building.asset.nbt_path is not None
            print(
                f"  queued NBT structure {building.asset.nbt_path.name} for "
                f"{building.asset.name}"
            )
            continue

        count = place_json_building(json_blocks, building)
        json_block_count += count
        print(
            f"  queued {count} legacy JSON blocks for "
            f"{building.asset.name if building.asset else 'unknown'}"
        )

    (
        wall_json_blocks,
        wall_banner_blocks,
        wall_json_block_count,
        wall_banner_count,
        wall_banners_with_data,
    ) = build_wall_json_blocks(wall_placements)
    if wall_placements:
        print(
            f"Queued {wall_json_block_count} JSON wall blocks for "
            f"{len(wall_placements)} modules; "
            f"banners={wall_banner_count}, "
            f"banner_data={wall_banners_with_data}."
        )

    # Filter accidental out-of-build-area placements in all passes.
    before = len(blocks)
    blocks = [
        block for block in blocks
        if in_build_area_xyz(
            ba, int(block["x"]), int(block["y"]), int(block["z"])
        )
    ]
    skipped = before - len(blocks)

    json_before = len(json_blocks)
    json_blocks = [
        block for block in json_blocks
        if in_build_area_xyz(
            ba, int(block["x"]), int(block["y"]), int(block["z"])
        )
    ]
    skipped_json = json_before - len(json_blocks)

    wall_before = len(wall_json_blocks)
    wall_json_blocks = [
        block for block in wall_json_blocks
        if in_build_area_xyz(
            ba, int(block["x"]), int(block["y"]), int(block["z"])
        )
    ]
    skipped_wall_json = wall_before - len(wall_json_blocks)

    wall_banner_before = len(wall_banner_blocks)
    wall_banner_blocks = [
        block for block in wall_banner_blocks
        if in_build_area_xyz(
            ba, int(block["x"]), int(block["y"]), int(block["z"])
        )
    ]
    skipped_wall_banners = wall_banner_before - len(wall_banner_blocks)

    wall_support_before = len(wall_support_blocks)
    wall_support_blocks = [
        block for block in wall_support_blocks
        if in_build_area_xyz(
            ba, int(block["x"]), int(block["y"]), int(block["z"])
        )
    ]
    skipped_wall_supports = wall_support_before - len(wall_support_blocks)

    if wall_placements and WALL_WARN_IF_NO_BANNERS and not wall_banner_blocks:
        print(
            "WARNING: Wall modules were planned, but no banner blocks remain. "
            "Check the wall library, module selection, and /buildarea Y limits."
        )

    if WALL_PRINT_BANNER_COORDINATES and wall_banner_blocks:
        print("Verified customized banner placements:")
        for index, block in enumerate(wall_banner_blocks, 1):
            print(
                f"  banner {index:03d}: "
                f"{block.get('id')} at "
                f"({block.get('x')}, {block.get('y')}, {block.get('z')}), "
                f"state={block.get('state', {})}, "
                f"custom_data={'yes' if block.get('data') else 'NO'}"
            )

    actual_counts = Counter(
        plot.asset.path.name
        for plot in normal_buildings
        if plot.asset is not None
    )

    print(f"\n========== {ACTIVE_TRIBE.upper()} SETTLEMENT OUTPUT ==========")
    print(
        "Landmark placement request: "
        + (str(requested_landmark) if requested_landmark is not None else "random")
    )
    print(
        f"Unique landmark: {landmark.asset.name if landmark.asset else 'unknown'} "
        f"at {landmark.center}, top Y={landmark.target_top_y}, "
        f"rotation={landmark.rotation}°, road hub={landmark.door_front}"
    )
    print(
        f"Landmark TP: /tp @s {landmark.center[0]} "
        f"{landmark.target_top_y + 3} {landmark.center[1]}"
    )
    print(
        f"Automatically placed repeatable buildings: "
        f"{len(normal_buildings)}"
    )
    print("Placed building counts discovered from the folder:")
    for asset in sorted(normal_assets, key=lambda item: item.path.name):
        print(
            f"  {asset.path.name}: "
            f"placed={actual_counts.get(asset.path.name, 0)}"
        )

    for index, plot in enumerate(all_buildings, 1):
        asset_name = plot.asset.name if plot.asset else "unknown"
        label = "LANDMARK" if plot.kind == "landmark" else f"BUILDING {index - 1:02d}"
        print(
            f"{label}. {asset_name}: center={plot.center}, "
            f"footprint={plot.rotated_width}x{plot.rotated_depth}, "
            f"rotation={plot.rotation}°, origin={plot.origin}, "
            f"saved entrance={plot.entrance_world}, "
            f"road connection={plot.door_front}, facing={plot.door_facing}"
        )

    print(f"Queued legacy JSON building blocks: {json_block_count}")
    print(f"Queued paired NBT building structures: {len(nbt_buildings)}")
    print(f"Wall generation enabled: {GENERATE_WALLS}")
    if wall_perimeter is not None:
        print(
            f"Wall perimeter: x {wall_perimeter[0]}..{wall_perimeter[2]}, "
            f"z {wall_perimeter[1]}..{wall_perimeter[3]}"
        )
    if wall_side_status:
        print("Wall side status:")
        for side_name in ("north", "east", "south", "west"):
            if side_name in wall_side_status:
                print(f"  {side_name}: {wall_side_status[side_name]}")
    print(f"Wall modules queued: {len(wall_placements)}")
    if GENERATE_WALLS:
        print(
            f"Continuous wall fallback columns: "
            f"{wall_connection_stats.get('gap_columns', 0)}; "
            f"enclosed water columns drained: "
            f"{wall_connection_stats.get('drained_columns', 0)}"
        )
    print(f"Gate road waypoints: {len(gate_waypoints)}")
    for waypoint in gate_waypoints:
        print(
            f"  gate {waypoint['side']}: {waypoint['world_pos']}, "
            f"facing={waypoint['direction']}"
        )
    print(f"Queued JSON wall blocks: {wall_json_block_count}")
    print(
        f"Customized banner blocks: {wall_banner_count}; "
        f"with saved pattern data: {wall_banners_with_data}"
    )
    print(f"Detected biome groups in build area: {dict(biome_groups)}")
    print(f"Forced road/building style: {FORCE_ROAD_STYLE_GROUP or 'automatic'}")
    if skipped:
        print(f"Skipped terrain/road placements outside /buildarea: {skipped}")
    if skipped_json:
        print(f"Skipped JSON building placements outside /buildarea: {skipped_json}")
    if skipped_wall_json:
        print(f"Skipped JSON wall placements outside /buildarea: {skipped_wall_json}")
    if skipped_wall_banners:
        print(f"Skipped banner placements outside /buildarea: {skipped_wall_banners}")
    if skipped_wall_supports:
        print(f"Skipped wall-support placements outside /buildarea: {skipped_wall_supports}")
    if terrain_first_stats:
        print(
            f"Terrain-first pass: {terrain_first_stats.get('columns', 0)} columns, "
            f"{terrain_first_stats.get('ravine_fills', 0)} ravine fills, "
            f"{terrain_first_stats.get('mountain_cuts', 0)} mountain cuts, "
            f"{terrain_first_stats.get('explicit_blocks', 0)} blocks placed before generation"
        )
    if final_terrain_stats:
        print(
            f"Final structure terrain: {final_terrain_stats.get('targets', 0)} target columns, "
            f"tree blocks removed={final_terrain_stats.get('tree_blocks_removed', 0)}, "
            f"building-pad repair blocks={final_terrain_stats.get('pad_repair_blocks', 0)}"
        )
    print(f"Terrain/road placements: {len(blocks)}")
    print(f"Final-stage wall support placements: {len(wall_support_blocks)}")
    print(f"Final legacy JSON building block placements: {len(json_blocks)}")
    print(f"Final paired NBT structure placements: {len(nbt_buildings)}")
    print(f"Final JSON wall placements: {len(wall_json_blocks)}")
    print(f"Final wall banner placements: {len(wall_banner_blocks)}")
    print(
        f"Configured villager entity placements: "
        f"{len(configured_villager_instructions)}"
    )
    print(
        f"Total explicit block placements: "
        f"{len(blocks) + len(json_blocks) + len(wall_support_blocks) + len(wall_json_blocks) + len(wall_banner_blocks)}"
    )
    print(
        f"Additional complete NBT structure placements: {len(nbt_buildings)}"
    )
    print("==============================================\n")

    total_passes = 1
    total_passes += int(bool(json_blocks))
    total_passes += int(bool(nbt_buildings))
    total_passes += int(bool(wall_support_blocks))
    total_passes += int(bool(wall_json_blocks))
    total_passes += int(bool(wall_banner_blocks))
    total_passes += int(bool(configured_villager_instructions))

    pass_number = 1
    print(
        f"Placement pass {pass_number}/{total_passes}: terrain, roads, lamps, "
        "and decorations..."
    )
    put_blocks(blocks, do_block_updates=DO_BLOCK_UPDATES)
    pass_number += 1

    if not json_blocks and not nbt_buildings:
        raise RuntimeError(
            "No building assets remain for placement. Check the paired NBT "
            "filenames, JSON block lists, and /buildarea limits."
        )

    if json_blocks:
        print(
            f"Placement pass {pass_number}/{total_passes}: legacy JSON "
            "buildings (block updates disabled)..."
        )
        put_blocks(json_blocks, do_block_updates=False)
        pass_number += 1

    if nbt_buildings:
        print(
            f"Placement pass {pass_number}/{total_passes}: paired NBT "
            "buildings, inventories, command data, and saved entities..."
        )
        for index, building in enumerate(nbt_buildings, 1):
            assert building.asset is not None
            print(
                f"Placing NBT building {index}/{len(nbt_buildings)}: "
                f"{building.asset.name}"
            )
            place_nbt_building(building)
        pass_number += 1

    if wall_support_blocks:
        print(
            f"Placement pass {pass_number}/{total_passes}: local terrain "
            "reformation for the final wall contour..."
        )
        put_blocks(wall_support_blocks, do_block_updates=DO_BLOCK_UPDATES)
        pass_number += 1

    if wall_json_blocks:
        print(
            f"Placement pass {pass_number}/{total_passes}: outward-facing "
            "terrain-following walls and gates..."
        )
        put_blocks(wall_json_blocks, do_block_updates=False)
        pass_number += 1

    if wall_banner_blocks:
        print(
            f"Placement pass {pass_number}/{total_passes}: customized wall "
            "banners after their support blocks..."
        )
        put_blocks(
            wall_banner_blocks,
            do_block_updates=WALL_BANNER_DO_BLOCK_UPDATES,
        )
        pass_number += 1

    spawned_villagers = 0
    if configured_villager_instructions:
        print(
            f"Placement pass {pass_number}/{total_passes}: configured "
            "villagers after buildings and walls..."
        )
        spawned_villagers = spawn_configured_villagers(
            configured_villager_instructions
        )
        print(
            f"Configured villagers successfully reported as spawned: "
            f"{spawned_villagers}/{len(configured_villager_instructions)}"
        )

    planted_trees = 0
    grown_trees = 0
    remaining_saplings = 0
    if V34_REFOREST_AFTER_SETTLEMENT:
        print(
            "Post-settlement reforestation: scanning actual open spaces "
            "inside the finished wall contour..."
        )
        try:
            reforest_stats = reforest_finished_settlement(
                plots=all_buildings,
                paths=paths,
                ba=ba,
                wall_perimeter=wall_perimeter,
                biome_lookup=biome_lookup,
                biome_forbidden=biome_forbidden,
                seed=SEED,
            )
            planted_trees = int(reforest_stats.get("planted", 0))
            grown_trees = int(reforest_stats.get("grown", 0))
            remaining_saplings = int(
                reforest_stats.get("remaining_saplings", 0)
            )
        except Exception as exc:
            print(f"WARNING: post-settlement reforestation failed: {exc}")

    generated_sides = sum(
        1
        for status in wall_side_status.values()
        if status.startswith("GENERATED")
    )
    print(
        f"Done! Placed 1 central landmark, {len(normal_buildings)} "
        f"automatically generated buildings using JSON/NBT assets, walls on "
        f"{generated_sides} side(s), {spawned_villagers} configured "
        f"villager(s), and {grown_trees} immediately grown tree(s) "
        f"with {remaining_saplings} sapling(s) left to grow naturally."
    )

    return {
        "tribe": ACTIVE_TRIBE,
        "landmark": landmark.center,
        "buildings": len(normal_buildings),
        "wall_modules": len(wall_placements),
        "wall_sides": generated_sides,
        "villagers": spawned_villagers,
        "trees_planted": planted_trees,
        "trees_grown": grown_trees,
        "saplings_remaining": remaining_saplings,
        "area": dict(ba),
    }


def configure_active_tribe(tribe: str, *, allow_wall_env_override: bool = False) -> None:
    """Switch all legacy globals to one tribe before a settlement run."""
    global ACTIVE_TRIBE, BUILDINGS_DIR, LANDMARK_FILENAME
    global WALL_TRIBE, WALL_LIBRARY_FILE, FORCE_ROAD_STYLE_GROUP

    tribe = tribe.strip().lower()
    if tribe not in SUPPORTED_TRIBES:
        raise ValueError(f"Unsupported tribe: {tribe}")

    ACTIVE_TRIBE = tribe
    BUILDINGS_DIR = BUILDINGS_ROOT / tribe
    LANDMARK_FILENAME = TRIBE_LANDMARK_FILENAMES[tribe]
    WALL_TRIBE = tribe
    default_wall = (
        BUILDINGS_ROOT / "walls" / tribe / f"{tribe}_wall_library.json"
    )
    if allow_wall_env_override and os.environ.get("GDMC_WALL_LIBRARY_FILE"):
        WALL_LIBRARY_FILE = Path(os.environ["GDMC_WALL_LIBRARY_FILE"])
    else:
        WALL_LIBRARY_FILE = default_wall
    FORCE_ROAD_STYLE_GROUP = tribe


def _available_world_tribes() -> List[str]:
    available: List[str] = []
    for tribe in SUPPORTED_TRIBES:
        building_dir = BUILDINGS_ROOT / tribe
        landmark = building_dir / TRIBE_LANDMARK_FILENAMES[tribe]
        wall_library = (
            BUILDINGS_ROOT / "walls" / tribe / f"{tribe}_wall_library.json"
        )
        if not building_dir.is_dir():
            print(f"World planner: skipping {tribe}; folder missing: {building_dir}")
            continue
        if not landmark.is_file():
            print(f"World planner: skipping {tribe}; landmark missing: {landmark}")
            continue
        if GENERATE_WALLS and not wall_library.is_file():
            print(f"World planner: skipping {tribe}; wall library missing: {wall_library}")
            continue
        available.append(tribe)
    return available


def scan_coarse_biome_groups(ba: dict, tribes: Set[str]) -> Dict[Pos2D, str]:
    """Scan a large build area in tiles, retaining only a coarse biome grid."""
    step = WORLD_BIOME_SAMPLE_STEP
    tile = WORLD_BIOME_TILE_SIZE
    grid: Dict[Pos2D, str] = {}

    tile_count_x = math.ceil((ba["x2"] - ba["x1"] + 1) / tile)
    tile_count_z = math.ceil((ba["z2"] - ba["z1"] + 1) / tile)
    total_tiles = tile_count_x * tile_count_z
    tile_index = 0

    print(
        f"Scanning biome map: area={ba['x2'] - ba['x1'] + 1}x"
        f"{ba['z2'] - ba['z1'] + 1}, step={step}, tiles={total_tiles}"
    )

    for x0 in range(ba["x1"], ba["x2"] + 1, tile):
        x1 = min(ba["x2"], x0 + tile - 1)
        for z0 in range(ba["z1"], ba["z2"] + 1, tile):
            z1 = min(ba["z2"], z0 + tile - 1)
            tile_index += 1
            params = {
                "x": x0,
                "y": WORLD_BIOME_SCAN_Y,
                "z": z0,
                "dx": x1 - x0 + 1,
                "dy": 1,
                "dz": z1 - z0 + 1,
                "dimension": DIMENSION,
                "withinBuildArea": str(WITHIN_BUILD_AREA_READS).lower(),
            }
            data = http_get("/biomes", params=params)
            for entry in data:
                x = int(entry["x"])
                z = int(entry["z"])
                if (x - ba["x1"]) % step or (z - ba["z1"]) % step:
                    continue
                biome_id = str(entry.get("id", "minecraft:plains"))
                if is_water_biome(biome_id):
                    continue
                group = biome_to_group(biome_id)
                if group in tribes:
                    grid[(x, z)] = group
            print(
                f"  biome tile {tile_index}/{total_tiles}: "
                f"x={x0}..{x1}, z={z0}..{z1}"
            )

    counts = Counter(grid.values())
    print(f"Coarse supported-biome samples: {dict(counts)}")
    return grid


def _coarse_components(grid: Dict[Pos2D, str]) -> List[Tuple[str, Set[Pos2D]]]:
    step = WORLD_BIOME_SAMPLE_STEP
    unseen = set(grid)
    components: List[Tuple[str, Set[Pos2D]]] = []

    while unseen:
        seed_point = unseen.pop()
        tribe = grid[seed_point]
        component = {seed_point}
        queue = [seed_point]
        head = 0
        while head < len(queue):
            x, z = queue[head]
            head += 1
            for neighbor in (
                (x + step, z),
                (x - step, z),
                (x, z + step),
                (x, z - step),
            ):
                if neighbor in unseen and grid.get(neighbor) == tribe:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append((tribe, component))

    return components


def _component_inward_distances(component: Set[Pos2D]) -> Dict[Pos2D, int]:
    step = WORLD_BIOME_SAMPLE_STEP
    boundary: List[Pos2D] = []
    for x, z in component:
        if any(
            neighbor not in component
            for neighbor in (
                (x + step, z),
                (x - step, z),
                (x, z + step),
                (x, z - step),
            )
        ):
            boundary.append((x, z))

    distances = {point: 0 for point in boundary}
    queue = list(boundary)
    head = 0
    while head < len(queue):
        x, z = queue[head]
        head += 1
        next_distance = distances[(x, z)] + 1
        for neighbor in (
            (x + step, z),
            (x - step, z),
            (x, z + step),
            (x, z - step),
        ):
            if neighbor in component and neighbor not in distances:
                distances[neighbor] = next_distance
                queue.append(neighbor)
    return distances


def _component_square_purity(
    center: Pos2D,
    half_size: int,
    component: Set[Pos2D],
) -> float:
    step = WORLD_BIOME_SAMPLE_STEP
    cx, cz = center
    total = 0
    matching = 0
    radius_steps = max(1, half_size // step)
    for dx in range(-radius_steps, radius_steps + 1):
        for dz in range(-radius_steps, radius_steps + 1):
            x = cx + dx * step
            z = cz + dz * step
            total += 1
            if (x, z) in component:
                matching += 1
    return matching / max(1, total)


def choose_world_settlement_sites(
    ba: dict,
    grid: Dict[Pos2D, str],
) -> List[dict]:
    """Choose separated, biome-interior settlement areas across the map."""
    step = WORLD_BIOME_SAMPLE_STEP
    raw_candidates: List[dict] = []

    for component_index, (tribe, component) in enumerate(_coarse_components(grid), 1):
        area = len(component) * step * step
        if area < WORLD_MIN_REGION_AREA:
            continue

        distances = _component_inward_distances(component)
        ordered = sorted(
            component,
            key=lambda point: (distances.get(point, 0), point[0], point[1]),
            reverse=True,
        )
        chosen_in_component: List[Pos2D] = []

        for point in ordered:
            inward_blocks = (distances.get(point, 0) + 1) * step
            if inward_blocks < WORLD_MIN_SETTLEMENT_HALF_SIZE:
                break
            half_size = min(
                WORLD_SETTLEMENT_HALF_SIZE,
                max(WORLD_MIN_SETTLEMENT_HALF_SIZE, inward_blocks - step),
            )
            if not in_build_area_xz(ba, point[0], point[1], margin=half_size + 3):
                continue
            if any(
                euclid(point, previous) < WORLD_MIN_CENTER_DISTANCE
                for previous in chosen_in_component
            ):
                continue

            purity = _component_square_purity(point, half_size, component)
            if purity < WORLD_MIN_BIOME_PURITY:
                continue

            raw_candidates.append(
                {
                    "tribe": tribe,
                    "center": point,
                    "half_size": half_size,
                    "component_area": area,
                    "purity": purity,
                    "inward_blocks": inward_blocks,
                    "component": component_index,
                    "score": inward_blocks * 4 + purity * 100 + math.sqrt(area),
                }
            )
            chosen_in_component.append(point)
            if len(chosen_in_component) >= WORLD_MAX_PER_COMPONENT:
                break

    by_tribe: Dict[str, List[dict]] = {tribe: [] for tribe in SUPPORTED_TRIBES}
    for candidate in raw_candidates:
        by_tribe[candidate["tribe"]].append(candidate)
    for candidates in by_tribe.values():
        candidates.sort(key=lambda item: item["score"], reverse=True)

    selected: List[dict] = []
    tribe_counts: Counter[str] = Counter()

    # First pass gives every available biome tribe a chance.
    for tribe in SUPPORTED_TRIBES:
        if by_tribe[tribe]:
            candidate = by_tribe[tribe].pop(0)
            if all(
                euclid(candidate["center"], existing["center"])
                >= WORLD_MIN_CENTER_DISTANCE
                for existing in selected
            ):
                selected.append(candidate)
                tribe_counts[tribe] += 1

    # Fill remaining slots by site quality while respecting per-tribe limits.
    remaining = [item for values in by_tribe.values() for item in values]
    remaining.sort(key=lambda item: item["score"], reverse=True)
    for candidate in remaining:
        if len(selected) >= WORLD_MAX_SETTLEMENTS:
            break
        tribe = candidate["tribe"]
        if tribe_counts[tribe] >= WORLD_MAX_PER_TRIBE:
            continue
        if any(
            euclid(candidate["center"], existing["center"])
            < WORLD_MIN_CENTER_DISTANCE
            for existing in selected
        ):
            continue
        selected.append(candidate)
        tribe_counts[tribe] += 1

    selected = selected[:WORLD_MAX_SETTLEMENTS]
    selected.sort(key=lambda item: (item["center"][0], item["center"][1]))
    return selected


def _local_settlement_area(full_ba: dict, center: Pos2D, half_size: int) -> dict:
    return {
        "x1": max(full_ba["x1"], center[0] - half_size),
        "x2": min(full_ba["x2"], center[0] + half_size),
        "y1": full_ba["y1"],
        "y2": full_ba["y2"],
        "z1": max(full_ba["z1"], center[1] - half_size),
        "z2": min(full_ba["z2"], center[1] + half_size),
    }


def run_world_generation() -> None:
    """Generate several isolated biome-matched tribal settlements."""
    global ACTIVE_BUILD_AREA_OVERRIDE, ACTIVE_LANDMARK_OVERRIDE
    global ACTIVE_SETTLEMENT_LABEL, SEED, AUTO_BUILDING_MAX_TOTAL
    global SETTLEMENT_BUILDING_RADIUS, LANDMARK_SEARCH_RADIUS_FROM_REQUEST

    full_ba = get_build_area()
    width = full_ba["x2"] - full_ba["x1"] + 1
    depth = full_ba["z2"] - full_ba["z1"] + 1
    print(f"Large-world mode: build area is {width}x{depth} blocks.")
    if width < 400 or depth < 400:
        print(
            "WARNING: world mode is designed for large areas such as "
            "1000x1000; continuing anyway."
        )

    available = _available_world_tribes()
    if not available:
        raise RuntimeError("No complete tribe asset folders are available.")
    print(f"World planner available tribes: {', '.join(available)}")

    coarse_grid = scan_coarse_biome_groups(full_ba, set(available))
    sites = [
        site for site in choose_world_settlement_sites(full_ba, coarse_grid)
        if site["tribe"] in available
    ]
    if not sites:
        raise RuntimeError(
            "No biome region was large/interior enough for a settlement. "
            "Lower GDMC_WORLD_MIN_REGION_AREA or GDMC_WORLD_MIN_BIOME_PURITY."
        )

    print("\nPlanned tribal settlements:")
    for index, site in enumerate(sites, 1):
        print(
            f"  {index}. {site['tribe']}: center={site['center']}, "
            f"area radius={site['half_size']}, biome purity={site['purity']:.1%}, "
            f"component≈{site['component_area']} blocks"
        )

    if WORLD_PLAN_ONLY:
        print("GDMC_WORLD_PLAN_ONLY is enabled; no blocks were placed.")
        return

    base_seed = SEED
    previous_cap = AUTO_BUILDING_MAX_TOTAL
    previous_radius = SETTLEMENT_BUILDING_RADIUS
    previous_search_radius = LANDMARK_SEARCH_RADIUS_FROM_REQUEST
    results: List[dict] = []

    try:
        for index, site in enumerate(sites, 1):
            tribe = site["tribe"]
            configure_active_tribe(tribe)
            ACTIVE_BUILD_AREA_OVERRIDE = _local_settlement_area(
                full_ba, site["center"], site["half_size"]
            )
            ACTIVE_LANDMARK_OVERRIDE = site["center"]
            ACTIVE_SETTLEMENT_LABEL = (
                f"WORLD SETTLEMENT {index}/{len(sites)} — {tribe.upper()}"
            )
            SEED = (
                base_seed
                + index * 100003
                + sum(ord(character) for character in tribe) * 997
            )
            AUTO_BUILDING_MAX_TOTAL = WORLD_BUILDING_CAP
            SETTLEMENT_BUILDING_RADIUS = max(
                35.0, site["half_size"] - AUTO_BUILDING_EDGE_RESERVE - 8
            )
            LANDMARK_SEARCH_RADIUS_FROM_REQUEST = max(
                previous_search_radius, min(64, site["half_size"] // 2)
            )

            print(
                f"\nStarting {tribe} settlement {index}/{len(sites)} "
                f"inside x={ACTIVE_BUILD_AREA_OVERRIDE['x1']}.."
                f"{ACTIVE_BUILD_AREA_OVERRIDE['x2']}, "
                f"z={ACTIVE_BUILD_AREA_OVERRIDE['z1']}.."
                f"{ACTIVE_BUILD_AREA_OVERRIDE['z2']}"
            )
            try:
                result = run_single_settlement()
                result["site_purity"] = site["purity"]
                results.append(result)
            except Exception as exc:
                print(
                    f"ERROR: {tribe} settlement at {site['center']} failed: "
                    f"{exc}"
                )
                print("Continuing with the remaining planned settlements.")
    finally:
        ACTIVE_BUILD_AREA_OVERRIDE = None
        ACTIVE_LANDMARK_OVERRIDE = None
        ACTIVE_SETTLEMENT_LABEL = ""
        SEED = base_seed
        AUTO_BUILDING_MAX_TOTAL = previous_cap
        SETTLEMENT_BUILDING_RADIUS = previous_radius
        LANDMARK_SEARCH_RADIUS_FROM_REQUEST = previous_search_radius

    print("\n================ WORLD GENERATION SUMMARY ================")
    print(f"Planned settlements: {len(sites)}")
    print(f"Successfully generated: {len(results)}")
    for index, result in enumerate(results, 1):
        print(
            f"  {index}. {result['tribe']}: landmark={result['landmark']}, "
            f"buildings={result['buildings']}, wall_modules={result['wall_modules']}, "
            f"villagers={result['villagers']}, trees={result.get('trees_grown', 0)}, "
            f"saplings={result.get('saplings_remaining', 0)}"
        )
    print("==========================================================")


def main() -> None:
    if WORLD_MODE:
        run_world_generation()
        return

    configure_active_tribe(ACTIVE_TRIBE, allow_wall_env_override=True)
    run_single_settlement()



# ============================================================
# V32 test-mode overrides
# - one repeatable building per tribe
# - no early square terrain pass
# - organic structure-aware terrain footprint
# - all trees intersecting that footprint are removed completely
# - campfires are capped
# - wall libraries are bypassed in favor of one connected stone-brick contour
# ============================================================

V32_SIMPLE_STONE_WALLS = os.environ.get(
    "GDMC_SIMPLE_STONE_WALLS", "1"
).strip().lower() in {"1", "true", "yes"}
V32_REMOVE_ALL_SETTLEMENT_TREES = os.environ.get(
    "GDMC_REMOVE_ALL_SETTLEMENT_TREES", "1"
).strip().lower() in {"1", "true", "yes"}
V32_TREE_CLEAR_MARGIN = max(
    6, int(os.environ.get("GDMC_ALL_TREE_CLEAR_MARGIN", "10"))
)
V32_TREE_CROWN_RADIUS = max(
    6, int(os.environ.get("GDMC_ALL_TREE_CROWN_RADIUS", "10"))
)
V32_ORGANIC_BLEND_WIDTH = max(
    8, int(os.environ.get("GDMC_ORGANIC_TERRAIN_BLEND", "12"))
)
V32_WATER_RECLAIM_MIN_WEIGHT = min(
    0.85,
    max(0.20, float(os.environ.get("GDMC_WATER_RECLAIM_MIN_WEIGHT", "0.42"))),
)
V32_ROAD_CAMPFIRE_MAX = max(
    0, int(os.environ.get("GDMC_ROAD_CAMPFIRE_MAX", "1"))
)
_V32_ROAD_CAMPFIRES_PLACED = 0

# The earlier broad pass was responsible for the square 200x200 plateaus and
# abrupt ocean slicing. Buildings are still only planned first; no structure is
# physically placed until the organic terrain pass finishes.
TERRAIN_FORM_FIRST = False
TERRAIN_POST_AUDIT_ENABLED = False
GENTLE_SETTLEMENT_TERRAIN = False
FINAL_TERRAIN_CONFORM_ENABLED = True

# Fast test configuration: one normal building plus the tribe landmark.
WORLD_BUILDING_CAP = max(
    1, int(os.environ.get("GDMC_WORLD_BUILDING_CAP", "1"))
)
AUTO_BUILDING_MAX_TOTAL = max(
    1, int(os.environ.get("GDMC_MAX_BUILDINGS_PER_SETTLEMENT", "1"))
)

# Tight wall and organic terrain settings.
WALL_PERIMETER_MARGIN = max(
    5, min(8, int(os.environ.get("GDMC_WALL_MARGIN", "6")))
)
WALL_MIN_BUILDING_GAP = WALL_PERIMETER_MARGIN
WALL_BUILDING_CLEARANCE = max(2, WALL_PERIMETER_MARGIN - 2)
WALL_CONNECTION_FILL_HEIGHT = max(
    3, int(os.environ.get("GDMC_SIMPLE_WALL_HEIGHT", "4"))
)
WALL_FORCE_CONTINUOUS = True
WALL_DRAIN_ENCLOSED_WATER = True
FINAL_TERRAIN_EDGE_BLEND = V32_ORGANIC_BLEND_WIDTH
FINAL_TERRAIN_BUILDING_PAD_MARGIN = max(
    3, int(os.environ.get("GDMC_FINAL_BUILDING_PAD_MARGIN", "4"))
)

# Fewer roadside decoration attempts during quick tests.
DECORATION_STEP = max(3, int(os.environ.get("GDMC_DECORATION_STEP", "4")))

# Lower campfire probability before applying the hard per-settlement cap.
for _v32_group, _v32_style in STYLES.items():
    _v32_adjusted: List[Tuple[str, float]] = []
    _v32_removed_weight = 0.0
    for _v32_name, _v32_weight in _v32_style.decorations:
        if _v32_name in {"campfire", "soul_campfire"}:
            _v32_adjusted.append((_v32_name, min(_v32_weight, 0.025)))
            _v32_removed_weight += max(0.0, _v32_weight - 0.025)
        else:
            _v32_adjusted.append((_v32_name, _v32_weight))
    if _v32_removed_weight:
        for _v32_index, (_v32_name, _v32_weight) in enumerate(_v32_adjusted):
            if _v32_name == "air":
                _v32_adjusted[_v32_index] = (
                    _v32_name,
                    _v32_weight + _v32_removed_weight,
                )
                break
    _v32_style.decorations = _v32_adjusted


def _v32_distance_to_segment(
    point: Tuple[float, float],
    start: Pos2D,
    end: Pos2D,
) -> float:
    px, pz = point
    ax, az = start
    bx, bz = end
    dx = bx - ax
    dz = bz - az
    length_sq = dx * dx + dz * dz
    if length_sq <= 0:
        return math.hypot(px - ax, pz - az)
    t = ((px - ax) * dx + (pz - az) * dz) / length_sq
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qz = az + t * dz
    return math.hypot(px - qx, pz - qz)


def _v32_polygon_edge_distance(
    point: Tuple[float, float],
    vertices: Sequence[Pos2D],
) -> float:
    return min(
        _v32_distance_to_segment(
            point,
            vertices[index],
            vertices[(index + 1) % len(vertices)],
        )
        for index in range(len(vertices))
    )


def _v32_organic_edge_noise(x: int, z: int) -> float:
    """Continuous low-frequency noise; never per-block random static."""
    phase = (SEED % 10007) * 0.0017
    return (
        2.2 * math.sin(x * 0.105 + z * 0.031 + phase)
        + 1.6 * math.sin(x * -0.047 + z * 0.091 + phase * 1.7)
        + 0.9 * math.sin((x + z) * 0.061 + phase * 0.6)
    )


def _v32_cell_is_water_like(
    pos: Pos2D,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
) -> bool:
    if pos not in heights or pos not in floor_heights:
        return False
    return heights[pos] - floor_heights[pos] >= WATER_HEIGHT_DIFF_THRESHOLD


def plan_final_structure_terrain(
    plots: Sequence[Plot],
    ba: dict,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    biome_forbidden: Set[Pos2D],
    settlement_grade: int,
) -> Tuple[Dict[Pos2D, int], Rect, Rect, Set[Pos2D]]:
    """Create an organic terrain island around the actual final structures.

    The stone wall contour is the fully formed core. Outside that contour, a
    wavy transition ring blends back into natural land or the existing water
    surface. This avoids the old rectangular plateau and vertical ocean slice.
    """
    if not plots:
        empty = (ba["x1"], ba["z1"], ba["x1"], ba["z1"])
        return {}, empty, empty, set()

    vertices = _octilinear_contour_vertices(plots, ba)
    core_rect: Rect = (
        min(x for x, _ in vertices),
        min(z for _, z in vertices),
        max(x for x, _ in vertices),
        max(z for _, z in vertices),
    )
    maximum_noise = 6
    full_rect = _clipped_rect(
        rect_with_margin(
            core_rect,
            V32_ORGANIC_BLEND_WIDTH + maximum_noise + 2,
        ),
        ba,
    )

    targets: Dict[Pos2D, int] = {}
    exact_pad_cells: Set[Pos2D] = set()
    x0, z0, x1, z1 = full_rect

    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            pos = (x, z)
            if pos in biome_forbidden or pos not in heights:
                continue

            nearest_plot = min(
                plots,
                key=lambda plot: (
                    _xz_distance_to_rect(pos, plot.rect),
                    euclid(pos, plot.center),
                ),
            )
            plot_distance = _xz_distance_to_rect(pos, nearest_plot.rect)
            point = (x + 0.5, z + 0.5)
            edge_distance = _v32_polygon_edge_distance(point, vertices)
            inside = (
                _point_in_polygon(point, vertices)
                or edge_distance <= 0.80
            )

            natural_ground = _terrain_ground_top(
                pos, heights, floor_heights
            )
            visible_surface = heights.get(pos, natural_ground + 1) - 1
            water_like = _v32_cell_is_water_like(
                pos, heights, floor_heights
            )

            if plot_distance <= FINAL_TERRAIN_BUILDING_PAD_MARGIN:
                target = nearest_plot.target_top_y
                exact_pad_cells.add(pos)
            elif inside:
                # Keep the wall line level. The deeper interior may retain a
                # subtle one-block terrace so the settlement is not a flat slab.
                if edge_distance <= 1.75:
                    target = settlement_grade
                else:
                    terrace_noise = _v32_organic_edge_noise(x // 2, z // 2)
                    target = settlement_grade + (
                        1 if terrace_noise > 2.65 else 0
                    )
            else:
                local_blend_width = max(
                    6.0,
                    V32_ORGANIC_BLEND_WIDTH
                    + _v32_organic_edge_noise(x, z),
                )
                if edge_distance > local_blend_width:
                    continue

                weight = 1.0 - edge_distance / local_blend_width
                weight = max(0.0, min(1.0, weight))
                # Smoothstep gives a gradual shoreline instead of a hard shelf.
                weight = weight * weight * (3.0 - 2.0 * weight)

                # Leave the outer water untouched. Only the stronger inner part
                # of the organic transition becomes reclaimed settlement land.
                if water_like and weight < V32_WATER_RECLAIM_MIN_WEIGHT:
                    continue

                natural_reference = (
                    visible_surface if water_like else natural_ground
                )
                target = int(round(
                    natural_reference * (1.0 - weight)
                    + settlement_grade * weight
                ))
                if water_like:
                    target = max(visible_surface, target)

                # Skip cells where the organic transition would make no actual
                # terrain change. This keeps the visible edge irregular.
                if target == natural_ground and not water_like:
                    continue

            targets[pos] = int(target)

    # Smooth only within the organic target mask. Missing neighbors are untouched
    # natural terrain, so the target map never expands back into a rectangle.
    for _ in range(4):
        updated = dict(targets)
        for pos, value in targets.items():
            if pos in exact_pad_cells:
                continue
            x, z = pos
            neighbors = [
                targets[p]
                for p in (
                    (x + 1, z),
                    (x - 1, z),
                    (x, z + 1),
                    (x, z - 1),
                )
                if p in targets
            ]
            if not neighbors:
                continue
            updated[pos] = max(
                min(neighbors) - 1,
                min(max(neighbors) + 1, value),
            )
        targets = updated

    # Building pads always win after smoothing.
    for pos in exact_pad_cells:
        nearest_plot = min(
            plots,
            key=lambda plot: (
                _xz_distance_to_rect(pos, plot.rect),
                euclid(pos, plot.center),
            ),
        )
        targets[pos] = nearest_plot.target_top_y

    return targets, core_rect, full_rect, exact_pad_cells


def find_all_settlement_tree_blocks(
    target_cells: Set[Pos2D],
    scan_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
) -> Set[Tuple[int, int, int]]:
    """Remove complete trees intersecting the organic settlement footprint.

    This intentionally ignores the older damaged-tree heuristic. All trunks,
    branches, and leaves touching the formed area are removed for the current
    test version, including crowns rooted just outside the wall.
    """
    if not V32_REMOVE_ALL_SETTLEMENT_TREES or not target_cells:
        return set()

    min_x = max(ba["x1"], scan_rect[0])
    max_x = min(ba["x2"], scan_rect[2])
    min_z = max(ba["z1"], scan_rect[1])
    max_z = min(ba["z2"], scan_rect[3])
    footprint = [
        (x, z)
        for x in range(min_x, max_x + 1)
        for z in range(min_z, max_z + 1)
        if (x, z) in heights
    ]
    if not footprint:
        return set()

    ground_values = [
        _terrain_ground_top(pos, heights, floor_heights)
        for pos in footprint
    ]
    visible_values = [
        heights[pos] - 1
        for pos in footprint
    ]
    min_y = max(ba["y1"], min(ground_values) - 12)
    max_y = min(
        ba["y2"],
        max(visible_values) + TERRAIN_DAMAGED_TREE_EXTRA_HEIGHT + 16,
    )

    try:
        logs, leaves = _read_tree_blocks_in_box(
            (min_x, min_y, min_z, max_x, max_y, max_z)
        )
    except Exception as exc:
        print(f"WARNING: complete settlement-tree scan failed: {exc}")
        return set()

    if not logs and not leaves:
        return set()

    # Select trunks within a generous distance of any organic target cell.
    # Bucketing avoids comparing every tree block with every terrain cell.
    bucket_size = max(4, V32_TREE_CLEAR_MARGIN)
    target_buckets: Dict[Tuple[int, int], List[Pos2D]] = {}
    for tx, tz in target_cells:
        target_buckets.setdefault(
            (tx // bucket_size, tz // bucket_size), []
        ).append((tx, tz))

    def near_target(x: int, z: int, radius: int) -> bool:
        bx = x // bucket_size
        bz = z // bucket_size
        reach = math.ceil(radius / bucket_size) + 1
        for obx in range(-reach, reach + 1):
            for obz in range(-reach, reach + 1):
                for tx, tz in target_buckets.get(
                    (bx + obx, bz + obz), []
                ):
                    if max(abs(x - tx), abs(z - tz)) <= radius:
                        return True
        return False

    starting_logs = {
        log
        for log in logs
        if near_target(log[0], log[2], V32_TREE_CLEAR_MARGIN)
    }

    # Grow through every connected trunk/branch so no chopped logs remain.
    selected_logs = set(starting_logs)
    stack = list(starting_logs)
    while stack:
        x, y, z = stack.pop()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == dy == dz == 0:
                        continue
                    neighbor = (x + dx, y + dy, z + dz)
                    if neighbor in logs and neighbor not in selected_logs:
                        selected_logs.add(neighbor)
                        stack.append(neighbor)

    selected_leaves: Set[Tuple[int, int, int]] = {
        leaf
        for leaf in leaves
        if near_target(
            leaf[0],
            leaf[2],
            V32_TREE_CLEAR_MARGIN,
        )
    }
    # Include the complete crowns of every selected trunk.
    for lx, ly, lz in selected_logs:
        for dx in range(-V32_TREE_CROWN_RADIUS, V32_TREE_CROWN_RADIUS + 1):
            for dy in range(-V32_TREE_CROWN_RADIUS, V32_TREE_CROWN_RADIUS + 1):
                for dz in range(-V32_TREE_CROWN_RADIUS, V32_TREE_CROWN_RADIUS + 1):
                    leaf = (lx + dx, ly + dy, lz + dz)
                    if leaf in leaves:
                        selected_leaves.add(leaf)

    removals = selected_logs | selected_leaves
    print(
        f"V32 complete tree clearing: logs={len(selected_logs)}, "
        f"leaves={len(selected_leaves)}, total={len(removals)}"
    )
    return removals


# Bypass modular wall JSON completely during this test cycle.
def load_wall_module_library() -> Dict[str, List[WallModuleAsset]]:
    if V32_SIMPLE_STONE_WALLS:
        print(
            "V32 wall mode: wall-library loading is disabled; "
            "using one continuous stone-brick contour."
        )
        return {}
    raise RuntimeError(
        "V32_SIMPLE_STONE_WALLS was disabled, but the V31 modular loader "
        "has been intentionally bypassed in this test build."
    )


def plan_settlement_walls(
    plots: Sequence[Plot],
    wall_library: Dict[str, List[WallModuleAsset]],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Dict[str, str], List[dict], Optional[Rect]]:
    del wall_library, heights, water_cells, water_blocked, seed
    if not GENERATE_WALLS or not plots:
        return [], {}, [], None

    vertices = _octilinear_contour_vertices(plots, ba)
    center = (
        int(round(sum(x for x, _ in vertices) / len(vertices))),
        int(round(sum(z for _, z in vertices) / len(vertices))),
    )
    segments = _contour_segments(vertices, center)
    counts = Counter(segment.macro_side for segment in segments)
    lengths = Counter()
    for segment in segments:
        lengths[segment.macro_side] += wall_side_length(segment)

    status = {
        side: (
            f"GENERATED SIMPLE STONE BRICKS — "
            f"{counts.get(side, 0)} run(s), length={lengths.get(side, 0)}"
        )
        for side in ("north", "east", "south", "west")
    }
    print(
        "V32 simple wall contour: "
        + " -> ".join(str(vertex) for vertex in vertices)
    )
    perimeter: Rect = (
        min(x for x, _ in vertices),
        min(z for _, z in vertices),
        max(x for x, _ in vertices),
        max(z for _, z in vertices),
    )
    return [], status, [], perimeter


def _wall_connection_block() -> str:
    return "minecraft:stone_bricks"


def _available_world_tribes() -> List[str]:
    """Wall libraries are not required in the temporary stone-brick mode."""
    available: List[str] = []
    for tribe in SUPPORTED_TRIBES:
        building_dir = BUILDINGS_ROOT / tribe
        landmark = building_dir / TRIBE_LANDMARK_FILENAMES[tribe]
        if not building_dir.is_dir():
            print(
                f"World planner: skipping {tribe}; "
                f"folder missing: {building_dir}"
            )
            continue
        if not landmark.is_file():
            print(
                f"World planner: skipping {tribe}; "
                f"landmark missing: {landmark}"
            )
            continue
        available.append(tribe)
    return available


_v31_add_decoration = add_decoration


def add_decoration(
    blocks: List[dict],
    group: str,
    deco: str,
    x: int,
    y: int,
    z: int,
    road_dir: Dir2D,
    seed: int,
) -> None:
    global _V32_ROAD_CAMPFIRES_PLACED
    if deco in {"campfire", "soul_campfire"}:
        if _V32_ROAD_CAMPFIRES_PLACED >= V32_ROAD_CAMPFIRE_MAX:
            return
        _V32_ROAD_CAMPFIRES_PLACED += 1
    _v31_add_decoration(
        blocks, group, deco, x, y, z, road_dir, seed
    )


_v31_run_single_settlement = run_single_settlement


def run_single_settlement() -> dict:
    global _V32_ROAD_CAMPFIRES_PLACED
    _V32_ROAD_CAMPFIRES_PLACED = 0
    return _v31_run_single_settlement()



# ============================================================
# V33 overrides
# - exactly one normal building for each discovered JSON building type
# - tree deletion is component-based: select a trunk, then delete only leaves
#   owned by that trunk component
# - old column-by-column tree-clearing helpers are disabled
# ============================================================

V33_ONE_PER_BUILDING_TYPE = os.environ.get(
    "GDMC_ONE_PER_BUILDING_TYPE", "1"
).strip().lower() in {"1", "true", "yes"}
V33_TREE_ROOT_TARGET_MARGIN = max(
    0, min(2, int(os.environ.get("GDMC_TREE_ROOT_TARGET_MARGIN", "0")))
)
V33_TREE_LEAF_ASSIGN_RADIUS = max(
    4, min(10, int(os.environ.get("GDMC_TREE_LEAF_ASSIGN_RADIUS", "7")))
)
V33_TREE_LOG_BUCKET_SIZE = max(
    2, int(os.environ.get("GDMC_TREE_LOG_BUCKET_SIZE", "4"))
)


def _v33_near_target(
    x: int,
    z: int,
    target_cells: Set[Pos2D],
    margin: int,
) -> bool:
    if (x, z) in target_cells:
        return True
    if margin <= 0:
        return False
    for ox in range(-margin, margin + 1):
        for oz in range(-margin, margin + 1):
            if max(abs(ox), abs(oz)) <= margin and (x + ox, z + oz) in target_cells:
                return True
    return False


def _v33_log_components(
    logs: Set[Tuple[int, int, int]],
) -> Tuple[List[Set[Tuple[int, int, int]]], Dict[Tuple[int, int, int], int]]:
    """Split natural logs into individual connected tree components."""
    remaining = set(logs)
    components: List[Set[Tuple[int, int, int]]] = []
    owner: Dict[Tuple[int, int, int], int] = {}

    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            x, y, z = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == dy == dz == 0:
                            continue
                        neighbor = (x + dx, y + dy, z + dz)
                        if neighbor in remaining:
                            remaining.remove(neighbor)
                            component.add(neighbor)
                            stack.append(neighbor)
        component_id = len(components)
        components.append(component)
        for block in component:
            owner[block] = component_id

    return components, owner


def _v33_assign_leaves_to_log_components(
    leaves: Set[Tuple[int, int, int]],
    log_owner: Dict[Tuple[int, int, int], int],
    selected_component_ids: Set[int],
) -> Set[Tuple[int, int, int]]:
    """Assign each leaf to its nearest trunk component.

    A leaf is deleted only when its nearest trunk belongs to a selected tree.
    When selected and unselected trees are equally close, the leaf is preserved.
    This prevents touching crowns from stealing leaves from neighboring trees.
    """
    if not leaves or not log_owner or not selected_component_ids:
        return set()

    bucket_size = V33_TREE_LOG_BUCKET_SIZE
    radius = V33_TREE_LEAF_ASSIGN_RADIUS
    radius_sq = radius * radius
    reach = math.ceil(radius / bucket_size)
    buckets: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
    for log in log_owner:
        x, y, z = log
        buckets.setdefault(
            (x // bucket_size, y // bucket_size, z // bucket_size), []
        ).append(log)

    selected_leaves: Set[Tuple[int, int, int]] = set()
    for leaf in leaves:
        lx, ly, lz = leaf
        bx, by, bz = lx // bucket_size, ly // bucket_size, lz // bucket_size
        best_distance: Optional[int] = None
        nearest_components: Set[int] = set()

        for obx in range(-reach, reach + 1):
            for oby in range(-reach, reach + 1):
                for obz in range(-reach, reach + 1):
                    for log in buckets.get((bx + obx, by + oby, bz + obz), []):
                        dx = lx - log[0]
                        dy = ly - log[1]
                        dz = lz - log[2]
                        distance = dx * dx + dy * dy + dz * dz
                        if distance > radius_sq:
                            continue
                        component_id = log_owner[log]
                        if best_distance is None or distance < best_distance:
                            best_distance = distance
                            nearest_components = {component_id}
                        elif distance == best_distance:
                            nearest_components.add(component_id)

        if best_distance is None:
            continue

        # Delete only when every equally-near owner is a selected tree. A tie
        # involving an outside/unselected tree is preserved conservatively.
        if nearest_components and nearest_components <= selected_component_ids:
            selected_leaves.add(leaf)

    return selected_leaves


def find_all_settlement_tree_blocks(
    target_cells: Set[Pos2D],
    scan_rect: Rect,
    heights: Dict[Pos2D, int],
    floor_heights: Dict[Pos2D, int],
    ba: dict,
) -> Set[Tuple[int, int, int]]:
    """Delete trees one tree at a time, never by broad leaf proximity."""
    if not V32_REMOVE_ALL_SETTLEMENT_TREES or not target_cells:
        return set()

    min_x = max(ba["x1"], scan_rect[0])
    max_x = min(ba["x2"], scan_rect[2])
    min_z = max(ba["z1"], scan_rect[1])
    max_z = min(ba["z2"], scan_rect[3])
    footprint = [
        (x, z)
        for x in range(min_x, max_x + 1)
        for z in range(min_z, max_z + 1)
        if (x, z) in heights
    ]
    if not footprint:
        return set()

    ground_values = [_terrain_ground_top(pos, heights, floor_heights) for pos in footprint]
    visible_values = [heights[pos] - 1 for pos in footprint]
    min_y = max(ba["y1"], min(ground_values) - 12)
    max_y = min(
        ba["y2"],
        max(visible_values) + TERRAIN_DAMAGED_TREE_EXTRA_HEIGHT + 16,
    )

    try:
        logs, leaves = _read_tree_blocks_in_box(
            (min_x, min_y, min_z, max_x, max_y, max_z)
        )
    except Exception as exc:
        print(f"WARNING: V33 tree-component scan failed: {exc}")
        return set()

    if not logs:
        return set()

    components, log_owner = _v33_log_components(logs)
    selected_component_ids: Set[int] = set()

    for component_id, component in enumerate(components):
        minimum_y = min(y for _x, y, _z in component)
        root_logs = {
            (x, y, z)
            for x, y, z in component
            if y <= minimum_y + 2
        }

        # A tree belongs to the settlement only when its trunk/root intersects
        # the organic terrain mask. Canopy overlap alone does not select it.
        root_intersects = any(
            _v33_near_target(x, z, target_cells, V33_TREE_ROOT_TARGET_MARGIN)
            for x, _y, z in root_logs
        )
        trunk_intersects = any((x, z) in target_cells for x, _y, z in component)
        if root_intersects or trunk_intersects:
            selected_component_ids.add(component_id)

    selected_logs = {
        log
        for log, component_id in log_owner.items()
        if component_id in selected_component_ids
    }
    selected_leaves = _v33_assign_leaves_to_log_components(
        leaves,
        log_owner,
        selected_component_ids,
    )
    removals = selected_logs | selected_leaves

    print(
        "V33 tree-by-tree clearing: "
        f"selected trees={len(selected_component_ids)}/{len(components)}, "
        f"logs={len(selected_logs)}, leaves={len(selected_leaves)}, "
        f"total={len(removals)}"
    )
    return removals


def find_auto_building_plots(
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    altar: Plot,
    assets: Sequence[BuildingAsset],
    seed: int,
) -> List[Plot]:
    """Place exactly one copy of each discovered non-landmark building type."""
    if not assets:
        print("No repeatable normal-building assets were discovered.")
        return []
    if not V33_ONE_PER_BUILDING_TYPE:
        return []

    rng = random.Random(seed + 45017)
    raw_candidates = generate_house_candidates(ba, altar.center, rng)
    seen: Set[Pos2D] = set()
    candidates: List[Pos2D] = []
    for point in raw_candidates:
        if point not in seen:
            seen.add(point)
            candidates.append(point)
    candidates.sort(
        key=lambda point: (
            int(euclid(point, altar.center) // 7),
            stable_rng(seed, point[0], point[1], 991).random(),
        )
    )

    plots: List[Plot] = []
    occupied: List[Rect] = [altar.rect]
    # Larger assets place first, but every type is attempted exactly once.
    ordered_assets = sorted(
        assets,
        key=lambda asset: (
            -(asset.size_x * asset.size_z),
            asset.path.name,
        ),
    )

    for asset_index, asset in enumerate(ordered_assets):
        best: Optional[Tuple[float, Pos2D, int, int, Rect]] = None
        waypoint = asset.waypoints[0]
        original_facing = waypoint.get("direction", "north")

        # First use the normal edge reserve; if that fails, retry with a smaller
        # reserve while still keeping enough room for the simple wall.
        reserve_attempts = [
            AUTO_BUILDING_EDGE_RESERVE,
            max(WALL_PERIMETER_MARGIN + 4, 12),
        ]
        flatten_attempts = [
            BUILDING_MAX_FLATTEN,
            RELAXED_BUILDING_MAX_FLATTEN,
            RELAXED_BUILDING_MAX_FLATTEN + 2,
        ]

        for reserve in reserve_attempts:
            if best is not None:
                break
            for max_flatten in flatten_attempts:
                scan_count = 0
                for candidate_index, candidate in enumerate(candidates):
                    scan_count += 1
                    if scan_count > AUTO_BUILDING_CANDIDATE_SCAN_LIMIT:
                        break

                    desired_facing = direction_to_facing(
                        altar.center[0] - candidate[0],
                        altar.center[1] - candidate[1],
                    )
                    rotation = rotation_to_face(original_facing, desired_facing)
                    width, depth = rotated_dimensions(asset, rotation)
                    min_distance = (
                        max(
                            altar.rotated_width or altar.size,
                            altar.rotated_depth or altar.size,
                        ) / 2
                        + max(width, depth) / 2
                        + BUILDING_SPACING
                        + 2
                    )

                    result = evaluate_rectangular_plot(
                        candidate,
                        width,
                        depth,
                        ba,
                        heights,
                        water_cells,
                        occupied,
                        max_flatten,
                        altar.center,
                        min_distance,
                        BUILDING_SPACING,
                        build_area_margin=reserve,
                    )
                    if result is None:
                        continue

                    terrain_score, target, rect = result
                    randomness = stable_rng(
                        seed + asset_index * 1009,
                        candidate[0],
                        candidate[1],
                        candidate_index,
                    ).random() * AUTO_BUILDING_RANDOMNESS
                    score = terrain_score + randomness
                    if best is None or score < best[0]:
                        best = (score, candidate, target, rotation, rect)

                if best is not None:
                    break

        if best is None:
            print(
                f"WARNING: one-per-type mode could not place {asset.name}; "
                "no valid non-overlapping plot was found."
            )
            continue

        _score, center, target, rotation, rect = best
        plot = make_json_plot(asset, center, target, rect, rotation, kind="building")
        plots.append(plot)
        occupied.append(rect)
        print(
            f"One-per-type building {len(plots):03d}/{len(ordered_assets)}: "
            f"{asset.name}, center={center}, "
            f"size={plot.rotated_width}x{plot.rotated_depth}, "
            f"rotation={rotation}°"
        )

        candidates = [
            point
            for point in candidates
            if not rects_overlap(
                (point[0], point[1], point[0], point[1]),
                rect,
                margin=BUILDING_SPACING + 3,
            )
        ]

    placed_names = {plot.asset.path.name for plot in plots if plot.asset is not None}
    print(
        f"One-per-type generation placed {len(plots)}/{len(ordered_assets)} "
        "repeatable building types."
    )
    for asset in sorted(ordered_assets, key=lambda item: item.path.name):
        print(f"  {asset.path.name}: {'1' if asset.path.name in placed_names else '0'}")
    return plots


# The organic terrain pass already performs the tree-component deletion before
# structures and roads are queued. Disable all older column-by-column tree
# clearing, which could shave leaves from an unrelated neighboring tree.
def find_building_intersecting_tree_blocks(*args: Any, **kwargs: Any) -> Set[Tuple[int, int, int]]:
    return set()


def clear_trees_for_plot(*args: Any, **kwargs: Any) -> None:
    return None


def clear_trees_in_settlement_bounds(*args: Any, **kwargs: Any) -> int:
    return 0


def clear_trees_around_road_cells(*args: Any, **kwargs: Any) -> int:
    return 0


# ============================================================
# V34 post-settlement reforestation
# - preserves V33 one-building-per-type placement
# - scans the completed settlement rather than the pre-build terrain
# - plants only on verified open natural ground
# - keeps clear of buildings, roads, and the wall contour
# - places stage-1 biome saplings, then uses /place feature to grow them
# - failed growth attempts leave valid saplings to grow naturally
# ============================================================

V34_REFOREST_AFTER_SETTLEMENT = os.environ.get(
    "GDMC_REFOREST_AFTER_SETTLEMENT", "1"
).strip().lower() in {"1", "true", "yes"}
V34_TREE_SAMPLE_STRIDE = max(
    1, int(os.environ.get("GDMC_REFOREST_SAMPLE_STRIDE", "2"))
)
V34_TREE_DENSITY = max(
    0.0002, float(os.environ.get("GDMC_REFOREST_DENSITY", "0.0024"))
)
V34_TREE_MIN_COUNT = max(
    0, int(os.environ.get("GDMC_REFOREST_MIN_TREES", "8"))
)
V34_TREE_MAX_COUNT = max(
    V34_TREE_MIN_COUNT,
    int(os.environ.get("GDMC_REFOREST_MAX_TREES", "56")),
)
V34_TREE_MIN_SPACING = max(
    5, int(os.environ.get("GDMC_REFOREST_MIN_SPACING", "8"))
)
V34_TREE_BUILDING_CLEARANCE = max(
    4, int(os.environ.get("GDMC_REFOREST_BUILDING_CLEARANCE", "6"))
)
V34_TREE_ROAD_CLEARANCE = max(
    3, int(os.environ.get("GDMC_REFOREST_ROAD_CLEARANCE", "5"))
)
V34_TREE_WALL_CLEARANCE = max(
    3, int(os.environ.get("GDMC_REFOREST_WALL_CLEARANCE", "5"))
)
V34_TREE_MAX_LOCAL_RELIEF = max(
    0, int(os.environ.get("GDMC_REFOREST_MAX_RELIEF", "1"))
)
V34_SURFACE_READ_TILE = max(
    16, int(os.environ.get("GDMC_REFOREST_READ_TILE", "48"))
)
V34_COMMAND_BATCH_SIZE = max(
    1, int(os.environ.get("GDMC_REFOREST_COMMAND_BATCH", "48"))
)
V34_GROW_IMMEDIATELY = os.environ.get(
    "GDMC_REFOREST_GROW_IMMEDIATELY", "1"
).strip().lower() in {"1", "true", "yes"}
V34_DESERT_DENSITY_MULTIPLIER = max(
    0.0, float(os.environ.get("GDMC_DESERT_TREE_DENSITY_MULTIPLIER", "0.35"))
)

V34_TREE_PALETTES: Dict[str, List[Tuple[str, str, float]]] = {
    "plains": [
        ("minecraft:oak_sapling", "minecraft:oak", 0.62),
        ("minecraft:birch_sapling", "minecraft:birch", 0.38),
    ],
    "savanna": [
        ("minecraft:acacia_sapling", "minecraft:acacia", 1.0),
    ],
    "taiga": [
        ("minecraft:spruce_sapling", "minecraft:spruce", 1.0),
    ],
    # A desert has no native vanilla tree. Use sparse acacia oasis trees and
    # replace only the single support block with coarse dirt.
    "desert": [
        ("minecraft:acacia_sapling", "minecraft:acacia", 1.0),
    ],
}

V34_DENSITY_MULTIPLIERS: Dict[str, float] = {
    "plains": 1.0,
    "savanna": 0.85,
    "taiga": 1.15,
    "desert": V34_DESERT_DENSITY_MULTIPLIER,
}

V34_NATURAL_GROUND: Dict[str, Set[str]] = {
    "plains": {
        "minecraft:grass_block", "minecraft:dirt", "minecraft:coarse_dirt",
        "minecraft:podzol", "minecraft:rooted_dirt", "minecraft:moss_block",
    },
    "savanna": {
        "minecraft:grass_block", "minecraft:dirt", "minecraft:coarse_dirt",
        "minecraft:packed_mud", "minecraft:mud",
    },
    "taiga": {
        "minecraft:grass_block", "minecraft:dirt", "minecraft:coarse_dirt",
        "minecraft:podzol", "minecraft:rooted_dirt", "minecraft:moss_block",
    },
    "desert": {
        "minecraft:sand", "minecraft:red_sand", "minecraft:dirt",
        "minecraft:coarse_dirt", "minecraft:grass_block",
    },
}

V34_REPLACEABLE_ABOVE = {
    "minecraft:air", "minecraft:cave_air", "minecraft:void_air",
    "minecraft:short_grass", "minecraft:tall_grass", "minecraft:fern",
    "minecraft:large_fern", "minecraft:dead_bush", "minecraft:snow",
    "minecraft:snow_layer", "minecraft:vine", "minecraft:glow_lichen",
    "minecraft:dandelion", "minecraft:poppy", "minecraft:blue_orchid",
    "minecraft:allium", "minecraft:azure_bluet", "minecraft:red_tulip",
    "minecraft:orange_tulip", "minecraft:white_tulip", "minecraft:pink_tulip",
    "minecraft:oxeye_daisy", "minecraft:cornflower", "minecraft:lily_of_the_valley",
    "minecraft:torchflower", "minecraft:closed_eyeblossom", "minecraft:open_eyeblossom",
}


def post_minecraft_commands(
    commands: Sequence[str],
    *,
    source: Tuple[int, int, int] = (0, 0, 0),
) -> List[dict]:
    """Run console commands through GDMC-HTTP's POST /commands endpoint."""
    if not commands:
        return []
    params = {
        "x": int(source[0]),
        "y": int(source[1]),
        "z": int(source[2]),
        "dimension": DIMENSION,
    }
    response = requests.post(
        f"{HOST}/commands",
        params=params,
        data="\n".join(command.lstrip("/") for command in commands),
        headers={"Content-Type": "text/plain; charset=UTF-8"},
        timeout=max(90, len(commands) * 3),
    )
    try:
        response.raise_for_status()
    except requests.HTTPError:
        print("GDMC returned an error while running tree-growth commands:")
        print(response.text)
        raise
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected /commands response; expected a JSON list")
    return payload


def _v34_is_replaceable_above(block_id: str) -> bool:
    block_id = str(block_id or "minecraft:air")
    if block_id in V34_REPLACEABLE_ABOVE:
        return True
    return (
        block_id.endswith("_flower")
        or block_id.endswith("_sapling")
        or block_id.endswith("_mushroom")
    )


def _v34_cells_near_paths(
    paths: Sequence[RoadPath],
    clearance: int,
) -> Set[Pos2D]:
    blocked: Set[Pos2D] = set()
    for road_path in paths:
        for x, z in road_path.cells:
            for ox in range(-clearance, clearance + 1):
                for oz in range(-clearance, clearance + 1):
                    if max(abs(ox), abs(oz)) <= clearance:
                        blocked.add((x + ox, z + oz))
    return blocked


def _v34_local_relief(
    pos: Pos2D,
    heights: Dict[Pos2D, int],
) -> int:
    x, z = pos
    values = [
        heights[(x + ox, z + oz)] - 1
        for ox in range(-2, 3)
        for oz in range(-2, 3)
        if (x + ox, z + oz) in heights
    ]
    return max(values) - min(values) if values else 99


def _v34_weighted_tree_choice(
    group: str,
    rng: random.Random,
) -> Tuple[str, str]:
    palette = V34_TREE_PALETTES.get(group, V34_TREE_PALETTES["plains"])
    total = sum(max(0.0, weight) for _sapling, _feature, weight in palette)
    pick = rng.random() * max(total, 1.0)
    running = 0.0
    for sapling, feature, weight in palette:
        running += max(0.0, weight)
        if pick <= running:
            return sapling, feature
    return palette[-1][0], palette[-1][1]


def _v34_read_surface_blocks(
    positions: Sequence[Tuple[int, int, int]],
    ba: dict,
) -> Dict[Tuple[int, int, int], str]:
    """Read ground and one block above candidate positions in bounded tiles."""
    if not positions:
        return {}
    grouped: Dict[Tuple[int, int, int], List[Tuple[int, int, int]]] = {}
    tile = V34_SURFACE_READ_TILE
    for x, y, z in positions:
        tile_x = (x - ba["x1"]) // tile
        tile_z = (z - ba["z1"]) // tile
        grouped.setdefault((tile_x, tile_z, y), []).append((x, y, z))

    result: Dict[Tuple[int, int, int], str] = {}
    for (_tile_x, _tile_z, y), group in grouped.items():
        x0 = min(x for x, _y, _z in group)
        x1 = max(x for x, _y, _z in group)
        z0 = min(z for _x, _y, z in group)
        z1 = max(z for _x, _y, z in group)
        params = {
            "x": x0,
            "y": y,
            "z": z0,
            "dx": x1 - x0 + 1,
            "dy": 2,
            "dz": z1 - z0 + 1,
            "dimension": DIMENSION,
            "withinBuildArea": str(WITHIN_BUILD_AREA_READS).lower(),
        }
        data = http_get("/blocks", params=params)
        for entry in data:
            result[(
                int(entry["x"]),
                int(entry["y"]),
                int(entry["z"]),
            )] = str(entry.get("id", "minecraft:air"))
    return result


def _v34_tree_cluster_score(x: int, z: int, seed: int) -> float:
    """Low-frequency score creates loose groves instead of a rigid grid."""
    phase = (seed % 8191) * 0.0031
    noise = (
        0.65 * math.sin(x * 0.082 + z * 0.027 + phase)
        + 0.45 * math.sin(x * -0.041 + z * 0.071 + phase * 1.9)
        + 0.25 * math.sin((x + z) * 0.039 + phase * 0.7)
    )
    jitter = stable_rng(seed, x, z, 3401).random() * 1.25
    return noise + jitter


def _v34_select_open_tree_sites(
    plots: Sequence[Plot],
    paths: Sequence[RoadPath],
    ba: dict,
    biome_lookup: Dict[Pos2D, str],
    biome_forbidden: Set[Pos2D],
    seed: int,
) -> Tuple[List[Tuple[int, int, int, str]], Dict[Pos2D, int]]:
    vertices = _octilinear_contour_vertices(plots, ba)
    rect = _clipped_rect((
        min(x for x, _z in vertices),
        min(z for _x, z in vertices),
        max(x for x, _z in vertices),
        max(z for _x, z in vertices),
    ), ba)

    heights = get_height_lookup(
        rect[0], rect[2], rect[1], rect[3], HEIGHTMAP_TYPE
    )
    floor_heights = get_height_lookup(
        rect[0], rect[2], rect[1], rect[3], "OCEAN_FLOOR_NO_PLANTS"
    )
    # Surface-block verification below is the final water guard. Use the two
    # refreshed heightmaps here instead of repeating the expensive exact
    # sea-level block scan after every settlement.
    water_cells = {
        pos
        for pos in heights
        if is_water_cell(
            pos, heights, floor_heights,
            WATER_HEIGHT_DIFF_THRESHOLD, biome_lookup,
        )
    }

    road_blocked = _v34_cells_near_paths(paths, V34_TREE_ROAD_CLEARANCE)
    candidates: List[Tuple[int, int, int, str]] = []
    stride = V34_TREE_SAMPLE_STRIDE
    offset_rng = random.Random(seed + 34001)
    offset_x = offset_rng.randrange(stride)
    offset_z = offset_rng.randrange(stride)

    for x in range(rect[0] + offset_x, rect[2] + 1, stride):
        for z in range(rect[1] + offset_z, rect[3] + 1, stride):
            pos = (x, z)
            point = (x + 0.5, z + 0.5)
            if pos in biome_forbidden or pos in water_cells or pos in road_blocked:
                continue
            if not _point_in_polygon(point, vertices):
                continue
            if _v32_polygon_edge_distance(point, vertices) < V34_TREE_WALL_CLEARANCE:
                continue
            if any(
                _xz_distance_to_rect(pos, plot.rect)
                <= V34_TREE_BUILDING_CLEARANCE
                for plot in plots
            ):
                continue
            if pos not in heights or pos not in floor_heights:
                continue
            if _v34_local_relief(pos, heights) > V34_TREE_MAX_LOCAL_RELIEF:
                continue
            y = heights[pos] - 1
            if y < ba["y1"] or y + 14 > ba["y2"]:
                continue
            group = biome_to_group(
                biome_lookup.get(pos, f"minecraft:{ACTIVE_TRIBE}")
            )
            if group not in V34_TREE_PALETTES:
                continue
            candidates.append((x, y, z, group))

    block_map = _v34_read_surface_blocks(candidates, ba)
    verified: List[Tuple[int, int, int, str]] = []
    for x, y, z, group in candidates:
        ground_id = block_map.get((x, y, z))
        above_id = block_map.get((x, y + 1, z), "minecraft:air")
        if ground_id not in V34_NATURAL_GROUND.get(group, set()):
            continue
        if not _v34_is_replaceable_above(above_id):
            continue
        verified.append((x, y, z, group))

    # Approximate actual open area from the sample grid, then apply biome density.
    density_multiplier = V34_DENSITY_MULTIPLIERS.get(ACTIVE_TRIBE, 1.0)
    estimated_open_area = len(verified) * stride * stride
    requested = int(round(estimated_open_area * V34_TREE_DENSITY * density_multiplier))
    if verified and density_multiplier > 0.0:
        requested = max(V34_TREE_MIN_COUNT, requested)
    requested = min(V34_TREE_MAX_COUNT, requested, len(verified))

    ordered = sorted(
        verified,
        key=lambda item: _v34_tree_cluster_score(item[0], item[2], seed),
        reverse=True,
    )
    selected: List[Tuple[int, int, int, str]] = []
    spacing_sq = V34_TREE_MIN_SPACING * V34_TREE_MIN_SPACING
    for candidate in ordered:
        x, _y, z, _group = candidate
        if all(
            (x - sx) * (x - sx) + (z - sz) * (z - sz) >= spacing_sq
            for sx, _sy, sz, _sgroup in selected
        ):
            selected.append(candidate)
            if len(selected) >= requested:
                break

    print(
        "V34 open-space tree planning: "
        f"sampled={len(candidates)}, verified={len(verified)}, "
        f"estimated open area={estimated_open_area}, selected={len(selected)}"
    )
    return selected, heights


def reforest_finished_settlement(
    *,
    plots: Sequence[Plot],
    paths: Sequence[RoadPath],
    ba: dict,
    wall_perimeter: Optional[Rect],
    biome_lookup: Dict[Pos2D, str],
    biome_forbidden: Set[Pos2D],
    seed: int,
) -> dict:
    """Plant biome saplings after all settlement construction and grow them."""
    del wall_perimeter  # The actual octilinear contour is recomputed from plots.
    if not plots:
        return {"planted": 0, "grown": 0, "remaining_saplings": 0}

    sites, _heights = _v34_select_open_tree_sites(
        plots,
        paths,
        ba,
        biome_lookup,
        biome_forbidden,
        seed,
    )
    if not sites:
        print("V34 reforestation: no verified open tree sites were found.")
        return {"planted": 0, "grown": 0, "remaining_saplings": 0}

    sapling_blocks: List[dict] = []
    growth_commands: List[str] = []
    planned: List[Tuple[int, int, int, str, str, str]] = []
    rng = random.Random(seed + 34991)

    for index, (x, ground_y, z, group) in enumerate(sites):
        sapling_id, feature_id = _v34_weighted_tree_choice(group, rng)
        if group == "desert":
            sapling_blocks.append(b("coarse_dirt", x, ground_y, z))
        sapling_blocks.append(
            b(sapling_id, x, ground_y + 1, z, {"stage": "1"})
        )
        growth_commands.append(
            f"place feature {feature_id} {x} {ground_y + 1} {z}"
        )
        planned.append((x, ground_y + 1, z, group, sapling_id, feature_id))

    print(
        f"V34 reforestation: planting {len(planned)} stage-1 biome saplings..."
    )
    put_blocks(sapling_blocks, do_block_updates=True)

    grown = 0
    if V34_GROW_IMMEDIATELY:
        for start in range(0, len(growth_commands), V34_COMMAND_BATCH_SIZE):
            batch = growth_commands[start:start + V34_COMMAND_BATCH_SIZE]
            try:
                results = post_minecraft_commands(batch)
            except Exception as exc:
                print(
                    "WARNING: immediate tree growth command batch failed; "
                    f"the planted saplings remain in the world: {exc}"
                )
                continue
            grown += sum(
                1 for result in results
                if isinstance(result, dict) and int(result.get("status", 0)) == 1
            )

    remaining = len(planned) - grown
    per_group = Counter(group for _x, _y, _z, group, _sapling, _feature in planned)
    print(
        "V34 reforestation complete: "
        f"planted={len(planned)}, immediately grown={grown}, "
        f"remaining stage-1 saplings={remaining}, by biome={dict(per_group)}"
    )
    return {
        "planted": len(planned),
        "grown": grown,
        "remaining_saplings": remaining,
        "by_biome": dict(per_group),
    }



# ============================================================
# V36 decorative wall-library runtime
# - restores tribe wall libraries after the temporary V32 stone-wall mode
# - consumes V35 straight-wall pattern and residual-filler metadata
# - keeps every exported module one block above terrain through ground_y=-1
# - uses banner -> light -> light decorative sequencing
# - reserves 1/2/3-block illuminated fillers for final cardinal residual gaps
# - disables diagonal emergency attachment lines
# ============================================================

V36_USE_DECORATIVE_WALL_LIBRARIES = os.environ.get(
    "GDMC_USE_DECORATIVE_WALL_LIBRARIES", "1"
).strip().lower() in {"1", "true", "yes"}
V36_WALLS_ROOT = Path(
    os.environ.get(
        "GDMC_WALLS_ROOT",
        str(BUILDINGS_ROOT.parent / "walls"),
    )
)
V36_WALL_PATTERN_NAMES: List[str] = []
V36_FILLER_MODULE_NAMES: Dict[int, str] = {}
V36_WALL_MODULES_BY_NAME: Dict[str, WallModuleAsset] = {}
V36_WALL_LIBRARY_METADATA: Dict[str, Any] = {}

# The temporary stone-only mode is no longer the runtime wall system.
V32_SIMPLE_STONE_WALLS = False
# The user paused the sapling/reforestation experiment while walls are fixed.
V34_REFOREST_AFTER_SETTLEMENT = os.environ.get(
    "GDMC_REFOREST_AFTER_SETTLEMENT", "0"
).strip().lower() in {"1", "true", "yes"}

# Keep the fallback on the actual contour only. The old attachment search could
# draw a diagonal staircase from the contour to an offset module body.
WALL_FALLBACK_ATTACHMENT_RADIUS = 0
WALL_FALLBACK_MODULE_COVER_RADIUS = max(
    2, int(os.environ.get("GDMC_WALL_FALLBACK_COVER_RADIUS", "3"))
)
WALL_ALLOWED_SEAM_OVERLAP_XZ = max(
    WALL_ALLOWED_SEAM_OVERLAP_XZ,
    int(os.environ.get("GDMC_WALL_ALLOWED_SEAM_OVERLAP", "12")),
)
# The fallback is now only a low emergency spine; V35 fillers provide the full
# decorated closure for normal 1/2/3-block cardinal residuals.
WALL_CONNECTION_FILL_HEIGHT = max(
    1, int(os.environ.get("GDMC_WALL_EMERGENCY_SPINE_HEIGHT", "2"))
)


def _v36_preferred_wall_library_path(tribe: str) -> Path:
    return V36_WALLS_ROOT / tribe / f"{tribe}_wall_library.json"


def _v36_resolve_wall_library_path(tribe: str) -> Path:
    explicit = os.environ.get("GDMC_WALL_LIBRARY_FILE")
    if explicit and tribe == ACTIVE_TRIBE:
        return Path(explicit)

    preferred = _v36_preferred_wall_library_path(tribe)
    legacy = BUILDINGS_ROOT / "walls" / tribe / f"{tribe}_wall_library.json"
    if preferred.is_file():
        return preferred
    if legacy.is_file():
        return legacy
    return preferred


_v36_base_configure_active_tribe = configure_active_tribe


def configure_active_tribe(
    tribe: str,
    *,
    allow_wall_env_override: bool = False,
) -> None:
    global WALL_LIBRARY_FILE
    _v36_base_configure_active_tribe(
        tribe,
        allow_wall_env_override=allow_wall_env_override,
    )
    if allow_wall_env_override and os.environ.get("GDMC_WALL_LIBRARY_FILE"):
        WALL_LIBRARY_FILE = Path(os.environ["GDMC_WALL_LIBRARY_FILE"])
    else:
        WALL_LIBRARY_FILE = _v36_resolve_wall_library_path(tribe)


def _available_world_tribes() -> List[str]:
    available: List[str] = []
    for tribe in SUPPORTED_TRIBES:
        building_dir = BUILDINGS_ROOT / tribe
        landmark = building_dir / TRIBE_LANDMARK_FILENAMES[tribe]
        wall_library = _v36_resolve_wall_library_path(tribe)
        if not building_dir.is_dir():
            print(
                f"World planner: skipping {tribe}; "
                f"folder missing: {building_dir}"
            )
            continue
        if not landmark.is_file():
            print(
                f"World planner: skipping {tribe}; "
                f"landmark missing: {landmark}"
            )
            continue
        if GENERATE_WALLS and not wall_library.is_file():
            print(
                f"World planner: skipping {tribe}; "
                f"V35 wall library missing: {wall_library}"
            )
            continue
        available.append(tribe)
    return available


def load_wall_module_library() -> Dict[str, List[WallModuleAsset]]:
    """Load the active V35 library and retain sequencing/filler metadata."""
    global WALL_LIBRARY_FILE
    global V36_WALL_PATTERN_NAMES, V36_FILLER_MODULE_NAMES
    global V36_WALL_MODULES_BY_NAME, V36_WALL_LIBRARY_METADATA

    if not GENERATE_WALLS:
        return {}
    if not V36_USE_DECORATIVE_WALL_LIBRARIES:
        raise RuntimeError(
            "Decorative wall libraries are disabled. Set "
            "GDMC_USE_DECORATIVE_WALL_LIBRARIES=1."
        )

    WALL_LIBRARY_FILE = _v36_resolve_wall_library_path(ACTIVE_TRIBE)
    if not WALL_LIBRARY_FILE.is_file():
        raise FileNotFoundError(
            f"Wall library does not exist: {WALL_LIBRARY_FILE}\n"
            "Copy the V35 library to "
            f"{_v36_preferred_wall_library_path(ACTIVE_TRIBE)}"
        )

    with WALL_LIBRARY_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if data.get("format") != "gdmc_wall_library_json":
        raise ValueError(
            f"{WALL_LIBRARY_FILE.name}: expected gdmc_wall_library_json"
        )
    library_tribe = str(data.get("tribe") or ACTIVE_TRIBE).strip().lower()
    if library_tribe != ACTIVE_TRIBE:
        raise ValueError(
            f"Wall library tribe is {library_tribe!r}, "
            f"but the active tribe is {ACTIVE_TRIBE!r}."
        )

    raw_modules = data.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        raise ValueError("Wall library contains no modules")

    library: Dict[str, List[WallModuleAsset]] = {}
    by_name: Dict[str, WallModuleAsset] = {}
    errors: List[str] = []
    requested_offset = int(data.get("vertical_offset_above_terrain", 1))

    print(f"Loaded V35 decorative wall library: {WALL_LIBRARY_FILE}")
    for index, module_data in enumerate(raw_modules):
        if not isinstance(module_data, dict):
            errors.append(f"module #{index + 1}: not a JSON object")
            continue
        try:
            asset = wall_module_asset_from_library_data(
                module_data,
                WALL_LIBRARY_FILE,
                index,
            )
        except Exception as exc:
            errors.append(f"module #{index + 1}: {exc}")
            continue

        # Dataclasses are not slotted, so V35 runtime metadata can be attached
        # without breaking the older loader or placement functions.
        setattr(asset, "role", str(module_data.get("role") or ""))
        setattr(
            asset,
            "runtime_policy",
            str(module_data.get("runtime_policy") or ""),
        )
        setattr(asset, "library_order", index)

        # A straight module must advance on one exact centerline. The updated
        # Plains straight export still carried a one-block Z drift in its end
        # connector; normalizing connector metadata here prevents every repeated
        # module from walking diagonally away from the contour. Block data is not
        # moved or redesigned.
        if asset.module_type == "straight_wall" and len(asset.connectors) >= 2:
            start_pos = list(asset.connectors[0].get("pos", [0, 0, 0]))
            end_pos = list(asset.connectors[1].get("pos", [0, 0, 0]))
            delta_x = int(end_pos[0]) - int(start_pos[0])
            delta_z = int(end_pos[2]) - int(start_pos[2])
            if abs(delta_x) >= abs(delta_z) and delta_z != 0:
                print(
                    f"  normalizing {asset.name} straight connector Z "
                    f"{end_pos[2]} -> {start_pos[2]}"
                )
                end_pos[2] = start_pos[2]
            elif abs(delta_z) > abs(delta_x) and delta_x != 0:
                print(
                    f"  normalizing {asset.name} straight connector X "
                    f"{end_pos[0]} -> {start_pos[0]}"
                )
                end_pos[0] = start_pos[0]
            asset.connectors[0]["pos"] = [int(v) for v in start_pos]
            asset.connectors[1]["pos"] = [int(v) for v in end_pos]

        # V35 uses local Y=0 for the lowest exported wall block and ground_y=-1,
        # which means the lowest wall block lands at terrain Y+1. Normalize an
        # accidentally older export to the same rule.
        expected_ground_y = asset.min_non_air_y - requested_offset
        if requested_offset == 1 and asset.ground_y != expected_ground_y:
            print(
                f"  normalizing {asset.name} ground_y "
                f"{asset.ground_y} -> {expected_ground_y}"
            )
            asset.ground_y = expected_ground_y

        library.setdefault(asset.module_type, []).append(asset)
        by_name[asset.name] = asset

    required = {"main_gate", "straight_wall", "tower_wall"}
    missing = sorted(required - set(library))
    if missing:
        raise FileNotFoundError(
            "Missing required wall module types: " + ", ".join(missing)
        )
    if errors:
        print("Ignored invalid wall modules:")
        for error in errors:
            print(f"  {error}")

    pattern_meta = data.get("straight_wall_pattern") or {}
    pattern_names = [
        str(name)
        for name in pattern_meta.get("cycle", [])
        if str(name) in by_name
        and getattr(by_name[str(name)], "role", "") == "decorative_straight"
    ]
    if not pattern_names:
        pattern_names = [
            asset.name
            for asset in library.get("straight_wall", [])
            if getattr(asset, "role", "") == "decorative_straight"
        ]
    if not pattern_names:
        pattern_names = [
            asset.name
            for asset in library.get("straight_wall", [])
            if getattr(asset, "role", "") != "gap_filler"
        ]

    filler_meta = data.get("filler_policy") or {}
    filler_names: Dict[int, str] = {}
    for raw_length, raw_name in (
        filler_meta.get("length_to_module") or {}
    ).items():
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            continue
        name = str(raw_name)
        asset = by_name.get(name)
        if (
            length >= 1
            and asset is not None
            and getattr(asset, "role", "") == "gap_filler"
        ):
            filler_names[length] = name

    V36_WALL_PATTERN_NAMES = pattern_names
    V36_FILLER_MODULE_NAMES = filler_names
    V36_WALL_MODULES_BY_NAME = by_name
    V36_WALL_LIBRARY_METADATA = dict(data)

    print(
        "V36 straight-wall cycle: "
        + (" -> ".join(pattern_names) if pattern_names else "none")
    )
    print(
        "V36 residual fillers: "
        + (
            ", ".join(
                f"{length}={name}"
                for length, name in sorted(filler_names.items())
            )
            if filler_names
            else "none"
        )
    )
    print(
        f"V36 vertical placement: lowest exported wall block is "
        f"{requested_offset} block(s) above terrain."
    )
    return library


def _wall_connection_block() -> str:
    """Emergency contour-spine material, used only where no module covers."""
    return {
        "desert": "minecraft:sandstone",
        "savanna": "minecraft:red_sandstone",
        "taiga": "minecraft:cobblestone",
        "plains": "minecraft:stone_bricks",
    }.get(ACTIVE_TRIBE, "minecraft:stone_bricks")


def _v36_connector_options(
    asset: WallModuleAsset,
    desired_direction: Dir2D,
    desired_outward_facing: Optional[Any] = None,
    minimum_progress: int = 1,
) -> List[
    Tuple[
        float,
        int,
        int,
        int,
        Tuple[int, int, int],
        Tuple[int, int, int],
    ]
]:
    """Connector options that also allow the new one-block filler."""
    dx, dz = desired_direction
    options: List[
        Tuple[
            float,
            int,
            int,
            int,
            Tuple[int, int, int],
            Tuple[int, int, int],
        ]
    ] = []

    for rotation in asset.allowed_rotations:
        offsets = [
            rotate_wall_offset(
                connector.get("pos", [0, 0, 0]),
                asset.pivot,
                rotation,
            )
            for connector in asset.connectors
        ]
        rotated_front = _asset_visible_front_vector(asset, rotation)
        facing_penalty = 0.0
        if desired_outward_facing:
            if isinstance(desired_outward_facing, str):
                desired_vector = facing_to_vec(desired_outward_facing)
            else:
                desired_vector = (
                    int(desired_outward_facing[0]),
                    int(desired_outward_facing[1]),
                )
            dot = (
                rotated_front[0] * desired_vector[0]
                + rotated_front[1] * desired_vector[1]
            )
            if dot <= 0:
                facing_penalty = WALL_OUTWARD_FACING_PENALTY
            elif rotated_front != desired_vector:
                facing_penalty = WALL_OUTWARD_FACING_PENALTY * 0.20

        for start_index in range(len(offsets)):
            for end_index in range(len(offsets)):
                if start_index == end_index:
                    continue
                start_offset = offsets[start_index]
                end_offset = offsets[end_index]
                delta_x = end_offset[0] - start_offset[0]
                delta_z = end_offset[2] - start_offset[2]
                along = delta_x * dx + delta_z * dz
                perpendicular = abs(
                    delta_x * (-dz) + delta_z * dx
                )
                if along < minimum_progress:
                    continue
                options.append(
                    (
                        perpendicular * 100.0 - along * 0.01 + facing_penalty,
                        rotation,
                        start_index,
                        end_index,
                        start_offset,
                        end_offset,
                    )
                )

    options.sort(key=lambda item: item[0])
    return options


def _v36_asset_progresses(
    asset: WallModuleAsset,
    desired_direction: Dir2D,
    outward_facing: Optional[Any],
) -> Set[int]:
    values: Set[int] = set()
    for option in _v36_connector_options(
        asset,
        desired_direction,
        outward_facing,
        minimum_progress=1,
    ):
        start_offset = option[4]
        end_offset = option[5]
        values.add(
            (end_offset[0] - start_offset[0]) * desired_direction[0]
            + (end_offset[2] - start_offset[2]) * desired_direction[1]
        )
    return {value for value in values if value > 0}


def _v36_best_asset_placement(
    asset: WallModuleAsset,
    side_name: str,
    current: Tuple[int, int, int],
    target: Pos2D,
    desired_direction: Dir2D,
    remaining: int,
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    protected_gate_passage_xz: Set[Pos2D],
    outward_facing: Optional[Any],
    exact_progress: Optional[int] = None,
) -> Optional[Tuple[float, WallPlacement, Set[Pos2D], int]]:
    candidates: List[Tuple[float, WallPlacement, Set[Pos2D], int]] = []
    for option in _v36_connector_options(
        asset,
        desired_direction,
        outward_facing,
        minimum_progress=1,
    )[:24]:
        (
            alignment_score,
            rotation,
            start_index,
            end_index,
            start_offset,
            end_offset,
        ) = option
        placement = _terrain_following_placement(
            asset,
            side_name,
            rotation,
            start_index,
            end_index,
            start_offset,
            end_offset,
            current,
            heights,
        )
        if placement is None or placement.end_connector_world is None:
            continue

        end_world = placement.end_connector_world
        progress = (
            (end_world[0] - current[0]) * desired_direction[0]
            + (end_world[2] - current[2]) * desired_direction[1]
        )
        perpendicular = abs(
            (end_world[0] - current[0]) * (-desired_direction[1])
            + (end_world[2] - current[2]) * desired_direction[0]
        )
        if progress < 1 or progress > remaining:
            continue
        if exact_progress is not None and progress != exact_progress:
            continue
        if perpendicular > WALL_MAX_PERPENDICULAR_DRIFT:
            continue

        valid, terrain_error, solid_xz = wall_placement_is_valid(
            asset,
            placement.world_pivot,
            rotation,
            ba,
            heights,
            water_blocked,
            building_rects,
            occupied_wall_xz,
            WALL_MAX_FLATTEN,
        )
        if not valid:
            valid, terrain_error, solid_xz = wall_placement_is_valid(
                asset,
                placement.world_pivot,
                rotation,
                ba,
                heights,
                water_blocked,
                building_rects,
                occupied_wall_xz,
                WALL_RELAXED_MAX_FLATTEN,
            )
        if not valid or solid_xz & protected_gate_passage_xz:
            continue

        end_remaining = chain_target_remaining(
            end_world,
            target,
            desired_direction,
        )
        seam_step = (
            abs(placement.start_connector_world[1] - current[1])
            if placement.start_connector_world
            else 0
        )
        score = (
            alignment_score
            + perpendicular * 35.0
            + terrain_error * 8.0
            + seam_step * WALL_SEAM_STEP_PENALTY
            + max(0, end_remaining) * 0.01
        )
        candidates.append((score, placement, solid_xz, progress))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0]


def _extend_wall_chain_v36(
    side_name: str,
    current_connector: Tuple[int, int, int],
    target: Pos2D,
    desired_direction: Dir2D,
    decorative_straights: Sequence[WallModuleAsset],
    oblique_assets: Sequence[WallModuleAsset],
    filler_assets: Dict[int, WallModuleAsset],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    protected_gate_passage_xz: Set[Pos2D],
    seed: int,
    outward_facing: Optional[Any] = None,
    pattern_start_index: int = 0,
) -> Tuple[List[WallPlacement], Set[Pos2D], int, int]:
    """Build one run using decorative modules, then one exact residual filler."""
    del seed  # Ordering is intentionally deterministic in V36.
    placements: List[WallPlacement] = []
    newly_occupied: Set[Pos2D] = set()
    current = current_connector
    pattern_index = pattern_start_index
    filler_count = 0
    iterations = 0
    cardinal = desired_direction[0] == 0 or desired_direction[1] == 0

    pattern_assets = [
        V36_WALL_MODULES_BY_NAME[name]
        for name in V36_WALL_PATTERN_NAMES
        if name in V36_WALL_MODULES_BY_NAME
    ]
    if not pattern_assets:
        pattern_assets = list(decorative_straights)

    while iterations < WALL_MAX_MODULES_PER_CHAIN:
        iterations += 1
        remaining = chain_target_remaining(
            current,
            target,
            desired_direction,
        )
        if remaining <= 0:
            break

        occupied_now = occupied_wall_xz | newly_occupied
        chosen: Optional[
            Tuple[float, WallPlacement, Set[Pos2D], int]
        ] = None
        chosen_is_decorative = False

        if cardinal and pattern_assets:
            expected = pattern_assets[pattern_index % len(pattern_assets)]
            ordered = [expected] + [
                asset
                for asset in decorative_straights
                if asset.name != expected.name
            ]

            minimum_normal_progress = min(
                (
                    min(_v36_asset_progresses(asset, desired_direction, outward_facing))
                    for asset in decorative_straights
                    if _v36_asset_progresses(asset, desired_direction, outward_facing)
                ),
                default=10**6,
            )

            for asset_index, asset in enumerate(ordered):
                candidate = _v36_best_asset_placement(
                    asset,
                    side_name,
                    current,
                    target,
                    desired_direction,
                    remaining,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_now,
                    protected_gate_passage_xz,
                    outward_facing,
                )
                if candidate is None:
                    continue
                residual = remaining - candidate[3]
                residual_is_representable = (
                    residual == 0
                    or residual in filler_assets
                    or residual >= minimum_normal_progress
                )
                if not residual_is_representable:
                    continue
                adjusted_score = candidate[0] + asset_index * 1000.0
                chosen = (
                    adjusted_score,
                    candidate[1],
                    candidate[2],
                    candidate[3],
                )
                chosen_is_decorative = True
                break

            # Only after no full decorative segment can fit do we consume the
            # exact 1/2/3-block residual filler. Fillers therefore never appear
            # in the middle of an otherwise normal run.
            if chosen is None:
                filler = filler_assets.get(remaining)
                if filler is not None:
                    chosen = _v36_best_asset_placement(
                        filler,
                        side_name,
                        current,
                        target,
                        desired_direction,
                        remaining,
                        ba,
                        heights,
                        water_blocked,
                        building_rects,
                        occupied_now,
                        protected_gate_passage_xz,
                        outward_facing,
                        exact_progress=remaining,
                    )
                    if chosen is not None:
                        filler_count += 1
        else:
            # Oblique modules are reserved for actual diagonal contour runs.
            for asset in oblique_assets:
                candidate = _v36_best_asset_placement(
                    asset,
                    side_name,
                    current,
                    target,
                    desired_direction,
                    remaining,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_now,
                    protected_gate_passage_xz,
                    outward_facing,
                )
                if candidate is None:
                    continue
                if chosen is None or candidate[0] < chosen[0]:
                    chosen = candidate

        if chosen is None:
            print(
                f"  {side_name} V36 chain stopped with {remaining} "
                "contour unit(s) remaining; the low emergency spine will "
                "cover only that unresolved section."
            )
            break

        _score, placement, solid_xz, _progress = chosen
        placements.append(placement)
        newly_occupied.update(solid_xz)
        assert placement.end_connector_world is not None
        current = placement.end_connector_world
        if chosen_is_decorative:
            pattern_index += 1

    return placements, newly_occupied, pattern_index, filler_count


def plan_settlement_walls(
    plots: Sequence[Plot],
    wall_library: Dict[str, List[WallModuleAsset]],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Dict[str, str], List[dict], Optional[Rect]]:
    """V36 version of the current octilinear modular-wall algorithm."""
    if not GENERATE_WALLS:
        return [], {}, [], None
    if not wall_library:
        raise RuntimeError("V36 requires a loaded decorative wall library")

    vertices = _octilinear_contour_vertices(plots, ba)
    settlement_center = (
        int(round(sum(x for x, _ in vertices) / len(vertices))),
        int(round(sum(z for _, z in vertices) / len(vertices))),
    )
    contour_segments = _contour_segments(vertices, settlement_center)
    building_rects = [plot.rect for plot in plots]

    print("V36 decorative wall contour after all buildings:")
    print("  vertices: " + " -> ".join(str(vertex) for vertex in vertices))
    print(f"  contour segments: {len(contour_segments)}")

    grouped_runs: Dict[str, List[WallSide]] = {
        "north": [],
        "east": [],
        "south": [],
        "west": [],
    }
    water_points_by_macro: Counter = Counter()
    for segment in contour_segments:
        grouped_runs[segment.macro_side].append(segment)
        water_points_by_macro[segment.macro_side] += sum(
            1
            for distance in range(wall_side_length(segment) + 1)
            if wall_side_point(segment, distance) in water_cells
        )

    decorative_straights = [
        asset
        for asset in wall_library.get("straight_wall", [])
        if getattr(asset, "role", "") == "decorative_straight"
    ]
    if not decorative_straights:
        decorative_straights = [
            asset
            for asset in wall_library.get("straight_wall", [])
            if getattr(asset, "role", "") != "gap_filler"
        ]
    filler_assets = {
        length: V36_WALL_MODULES_BY_NAME[name]
        for length, name in V36_FILLER_MODULE_NAMES.items()
        if name in V36_WALL_MODULES_BY_NAME
    }
    oblique_assets = list(wall_library.get("oblique_wall", []))

    if not decorative_straights:
        raise RuntimeError("V36 wall library contains no decorative straight modules")

    side_status: Dict[str, str] = {}
    placements: List[WallPlacement] = []
    occupied_wall_xz: Set[Pos2D] = set()
    protected_gate_passages: Set[Pos2D] = set()
    gate_waypoints: List[dict] = []
    active_macro_sides: Set[str] = set()

    for macro_index, macro in enumerate(("north", "east", "south", "west")):
        runs = sorted(
            grouped_runs[macro],
            key=wall_side_length,
            reverse=True,
        )
        if not runs:
            continue

        gate_order = sorted(
            runs,
            key=lambda run: (
                0 if abs(run.direction[0]) + abs(run.direction[1]) == 1 else 1,
                -wall_side_length(run),
            ),
        )
        gate_result: Optional[Tuple[WallPlacement, Set[Pos2D]]] = None
        gate_run: Optional[WallSide] = None
        for candidate_index, candidate in enumerate(gate_order):
            gate_result = choose_gate_placement(
                candidate,
                wall_library["main_gate"],
                corner_clearance=1,
                side_ground_y=0,
                ba=ba,
                heights=heights,
                water_blocked=water_blocked,
                building_rects=building_rects,
                occupied_wall_xz=occupied_wall_xz,
                seed=seed + macro_index * 1009 + candidate_index * 71,
                outward_facing=candidate.outward_vector,
            )
            if gate_result is not None:
                gate_run = candidate
                break

        if gate_result is None or gate_run is None:
            side_status[macro] = (
                "CONNECTED BY LOW EMERGENCY SPINE — no valid modular gate"
            )
            print(f"WARNING: {macro}: {side_status[macro]}")
            continue

        gate, gate_solid = gate_result
        placements.append(gate)
        # The gate is intentionally placed after normal wall structures, so the
        # first wall modules may overlap its decorative side wings. Only the
        # actual walk-through passage remains protected from wall blocks.
        occupied_before_gate = set(occupied_wall_xz)
        gate_passage = _gate_passage_world_xz(gate)
        protected_gate_passages.update(gate_passage)
        gate_waypoints.extend(gate_world_waypoints(gate))
        active_macro_sides.add(macro)

        assert gate.start_connector_world is not None
        assert gate.end_connector_world is not None

        module_count = 0
        filler_count = 0
        # Gate modules already carry prominent banners, so the first two wall
        # segments beside each gate are light-only before the next banner.
        backward_chain, backward_solid, _pattern, back_fillers = (
            _extend_wall_chain_v36(
                gate_run.name,
                gate.start_connector_world,
                gate_run.start,
                (-gate_run.direction[0], -gate_run.direction[1]),
                decorative_straights,
                oblique_assets,
                filler_assets,
                ba,
                heights,
                water_blocked,
                building_rects,
                occupied_before_gate,
                protected_gate_passages,
                seed + macro_index * 2003 + 1,
                outward_facing=gate_run.outward_vector,
                pattern_start_index=1,
            )
        )
        placements.extend(backward_chain)
        module_count += len(backward_chain)
        filler_count += back_fillers

        forward_chain, forward_solid, _pattern, forward_fillers = (
            _extend_wall_chain_v36(
                gate_run.name,
                gate.end_connector_world,
                gate_run.end,
                gate_run.direction,
                decorative_straights,
                oblique_assets,
                filler_assets,
                ba,
                heights,
                water_blocked,
                building_rects,
                occupied_before_gate | backward_solid,
                protected_gate_passages,
                seed + macro_index * 2003 + 2,
                outward_facing=gate_run.outward_vector,
                pattern_start_index=1,
            )
        )
        placements.extend(forward_chain)
        occupied_wall_xz.update(gate_solid)
        occupied_wall_xz.update(backward_solid)
        occupied_wall_xz.update(forward_solid)
        module_count += len(forward_chain)
        filler_count += forward_fillers

        for run_index, run in enumerate(runs):
            if run is gate_run:
                continue
            start_connector = (
                run.start[0],
                surface_top_y(run.start, heights),
                run.start[1],
            )
            chain, solid, _pattern, run_fillers = _extend_wall_chain_v36(
                run.name,
                start_connector,
                run.end,
                run.direction,
                decorative_straights,
                oblique_assets,
                filler_assets,
                ba,
                heights,
                water_blocked,
                building_rects,
                occupied_wall_xz,
                protected_gate_passages,
                seed + macro_index * 3001 + run_index * 43,
                outward_facing=run.outward_vector,
                pattern_start_index=0,
            )
            placements.extend(chain)
            occupied_wall_xz.update(solid)
            module_count += len(chain)
            filler_count += run_fillers

        side_status[macro] = (
            f"GENERATED V36 — 1 gate, {len(runs)} run(s), "
            f"{module_count} wall modules, {filler_count} final filler(s), "
            f"water points reclaimed={water_points_by_macro[macro]}"
        )
        print(f"  {macro}: {side_status[macro]}")

    towers = _place_contour_towers(
        vertices,
        active_macro_sides,
        wall_library.get("tower_wall", []),
        settlement_center,
        ba,
        heights,
        water_blocked,
        building_rects,
        seed,
    )
    placements.extend(towers)

    role_counts = Counter(
        getattr(placement.asset, "role", "") or placement.asset.module_type
        for placement in placements
    )
    name_counts = Counter(placement.asset.name for placement in placements)
    print(f"V36 wall role counts: {dict(role_counts)}")
    print(f"V36 wall module counts: {dict(name_counts)}")

    bounding_rect: Rect = (
        min(x for x, _ in vertices),
        min(z for _, z in vertices),
        max(x for x, _ in vertices),
        max(z for _, z in vertices),
    )
    return placements, side_status, gate_waypoints, bounding_rect



# ============================================================
# V37 compact settlements, editable building ratios, and repaired wall runs
# ============================================================

V37_OBLIQUE_PATTERN_NAMES: List[str] = []
V37_OBLIQUE_FILLER_NAMES: Dict[int, str] = {}


def _v37_active_settings(tribe: Optional[str] = None) -> Dict[str, Any]:
    selected = str(tribe or ACTIVE_TRIBE).strip().lower()
    base = TRIBE_GENERATION_SETTINGS.get(selected)
    if base is None:
        base = TRIBE_GENERATION_SETTINGS["plains"]
    return base


def _v37_normalize_asset_key(value: Any) -> str:
    text = str(value).strip().lower()
    if text.endswith(".json"):
        text = text[:-5]
    return "".join(character for character in text if character.isalnum())


def _v37_asset_ratio(asset: BuildingAsset, ratios: Dict[str, Any]) -> float:
    wildcard = float(ratios.get("*", ratios.get("default", 1)))
    identifiers = {
        _v37_normalize_asset_key(asset.name),
        _v37_normalize_asset_key(asset.path.name),
        _v37_normalize_asset_key(asset.path.stem),
    }
    exact: List[Tuple[int, float]] = []
    partial: List[Tuple[int, float]] = []
    for raw_key, raw_value in ratios.items():
        if str(raw_key).strip().lower() in {"*", "default"}:
            continue
        key = _v37_normalize_asset_key(raw_key)
        if not key:
            continue
        try:
            value = max(0.0, float(raw_value))
        except (TypeError, ValueError):
            continue
        if key in identifiers:
            exact.append((len(key), value))
        elif any(key in identifier for identifier in identifiers):
            partial.append((len(key), value))
    if exact:
        return max(exact, key=lambda item: item[0])[1]
    if partial:
        return max(partial, key=lambda item: item[0])[1]
    return max(0.0, wildcard)


def _v37_allocate_building_counts(
    assets: Sequence[BuildingAsset],
    settings: Dict[str, Any],
) -> Dict[str, int]:
    ratios = dict(settings.get("building_ratios") or {"*": 1})
    weights = {
        asset.path.name: _v37_asset_ratio(asset, ratios)
        for asset in assets
    }
    positive = [asset for asset in assets if weights[asset.path.name] > 0]
    requested_total = settings.get("building_total")
    environment_total = os.environ.get("GDMC_BUILDING_TOTAL")
    if environment_total is not None:
        requested_total = int(environment_total)

    cap = max(0, int(settings.get("world_safety_cap", 0)))
    if requested_total is None:
        counts = {
            asset.path.name: max(0, int(round(weights[asset.path.name])))
            for asset in assets
        }
        if cap and sum(counts.values()) > cap:
            requested_total = cap
        else:
            return counts

    total = max(0, int(requested_total))
    if cap:
        total = min(total, cap)
    counts = {asset.path.name: 0 for asset in assets}
    if total <= 0 or not positive:
        return counts

    ensure_each = bool(settings.get("ensure_each_type", True))
    remaining_total = total
    if ensure_each and total >= len(positive):
        for asset in positive:
            counts[asset.path.name] = 1
        remaining_total -= len(positive)

    if remaining_total <= 0:
        if total < len(positive):
            ordered = sorted(
                positive,
                key=lambda asset: (-weights[asset.path.name], asset.path.name),
            )
            for asset in ordered[:total]:
                counts[asset.path.name] = 1
        return counts

    weight_sum = sum(weights[asset.path.name] for asset in positive)
    raw_shares = {
        asset.path.name: remaining_total * weights[asset.path.name] / weight_sum
        for asset in positive
    }
    assigned = 0
    for asset in positive:
        addition = int(math.floor(raw_shares[asset.path.name]))
        counts[asset.path.name] += addition
        assigned += addition
    leftovers = remaining_total - assigned
    remainder_order = sorted(
        positive,
        key=lambda asset: (
            -(raw_shares[asset.path.name] - math.floor(raw_shares[asset.path.name])),
            -weights[asset.path.name],
            asset.path.name,
        ),
    )
    for asset in remainder_order[:leftovers]:
        counts[asset.path.name] += 1
    return counts


def _v37_rect_edge_gap(first: Rect, second: Rect) -> float:
    dx = max(second[0] - first[2] - 1, first[0] - second[2] - 1, 0)
    dz = max(second[1] - first[3] - 1, first[1] - second[3] - 1, 0)
    return math.hypot(dx, dz)


def _v37_rect_bounds(rectangles: Sequence[Rect]) -> Rect:
    return (
        min(rect[0] for rect in rectangles),
        min(rect[1] for rect in rectangles),
        max(rect[2] for rect in rectangles),
        max(rect[3] for rect in rectangles),
    )


def _v37_rect_area(rect: Rect) -> int:
    return max(0, rect[2] - rect[0] + 1) * max(0, rect[3] - rect[1] + 1)


def find_auto_building_plots(
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    altar: Plot,
    assets: Sequence[BuildingAsset],
    seed: int,
) -> List[Plot]:
    """Pack the requested building mixture into one compact settlement cluster."""
    if not assets:
        print("No repeatable normal-building assets were discovered.")
        return []

    settings = _v37_active_settings()
    spacing = max(1, int(settings.get("building_spacing", 4)))
    counts = _v37_allocate_building_counts(assets, settings)
    total_requested = sum(counts.values())
    print(
        f"V37 building settings for {ACTIVE_TRIBE}: total={total_requested}, "
        f"spacing={spacing}, compact radius={settings.get('compact_radius')}.."
        f"{settings.get('maximum_radius')}"
    )
    print("V37 requested building counts:")
    for asset in sorted(assets, key=lambda item: item.path.name):
        print(f"  {asset.path.name}: {counts.get(asset.path.name, 0)}")
    if total_requested <= 0:
        return []

    by_name = {asset.path.name: asset for asset in assets}
    remaining = dict(counts)
    schedule: List[BuildingAsset] = []
    round_number = 0
    while any(value > 0 for value in remaining.values()):
        round_number += 1
        round_assets = [
            by_name[name]
            for name, value in remaining.items()
            if value > 0
        ]
        round_assets.sort(
            key=lambda asset: (
                -(asset.size_x * asset.size_z),
                stable_rng(seed, round_number, len(asset.path.name), 3701).random(),
                asset.path.name,
            )
        )
        for asset in round_assets:
            schedule.append(asset)
            remaining[asset.path.name] -= 1

    rng = random.Random(seed + 37037)
    raw_candidates = generate_house_candidates(ba, altar.center, rng)
    candidates = list(dict.fromkeys(raw_candidates))
    candidates.sort(
        key=lambda point: (
            euclid(point, altar.center),
            stable_rng(seed, point[0], point[1], 3703).random(),
        )
    )

    compact_radius = max(20, int(settings.get("compact_radius", 48)))
    maximum_radius = max(compact_radius, int(settings.get("maximum_radius", 72)))
    radius_step = max(4, int(settings.get("radius_step", 8)))
    if SETTLEMENT_BUILDING_RADIUS is not None:
        maximum_radius = min(maximum_radius, int(SETTLEMENT_BUILDING_RADIUS))
    radius_attempts = list(range(compact_radius, maximum_radius + 1, radius_step))
    if not radius_attempts or radius_attempts[-1] != maximum_radius:
        radius_attempts.append(maximum_radius)

    plots: List[Plot] = []
    occupied: List[Rect] = [altar.rect]
    placed_by_name: Counter = Counter()

    for schedule_index, asset in enumerate(schedule):
        best: Optional[Tuple[float, Pos2D, int, int, Rect]] = None
        waypoint = asset.waypoints[0]
        original_facing = waypoint.get("direction", "north")

        for expansion_index, radius in enumerate(radius_attempts):
            if best is not None:
                break
            cluster_limit = float(settings.get("cluster_link_distance", 22)) + expansion_index * 5
            reserve_attempts = [
                AUTO_BUILDING_EDGE_RESERVE,
                max(WALL_PERIMETER_MARGIN + 4, 12),
            ]
            flatten_attempts = [
                BUILDING_MAX_FLATTEN,
                RELAXED_BUILDING_MAX_FLATTEN,
                RELAXED_BUILDING_MAX_FLATTEN + 2,
            ]
            for reserve in reserve_attempts:
                if best is not None:
                    break
                for max_flatten in flatten_attempts:
                    scan_count = 0
                    current_bounds = _v37_rect_bounds(occupied)
                    current_area = _v37_rect_area(current_bounds)
                    for candidate_index, candidate in enumerate(candidates):
                        if euclid(candidate, altar.center) > radius:
                            break
                        scan_count += 1
                        if scan_count > AUTO_BUILDING_CANDIDATE_SCAN_LIMIT:
                            break

                        desired_facing = direction_to_facing(
                            altar.center[0] - candidate[0],
                            altar.center[1] - candidate[1],
                        )
                        rotation = rotation_to_face(original_facing, desired_facing)
                        width, depth = rotated_dimensions(asset, rotation)
                        min_distance = (
                            max(
                                altar.rotated_width or altar.size,
                                altar.rotated_depth or altar.size,
                            ) / 2
                            + max(width, depth) / 2
                            + spacing
                            + 1
                        )

                        result = evaluate_rectangular_plot(
                            candidate,
                            width,
                            depth,
                            ba,
                            heights,
                            water_cells,
                            occupied,
                            max_flatten,
                            altar.center,
                            min_distance,
                            spacing,
                            build_area_margin=reserve,
                        )
                        if result is None:
                            continue
                        terrain_score, target, rect = result
                        nearest_gap = min(
                            _v37_rect_edge_gap(rect, existing)
                            for existing in occupied
                        )
                        if plots and nearest_gap > cluster_limit:
                            continue

                        expanded_bounds = (
                            min(current_bounds[0], rect[0]),
                            min(current_bounds[1], rect[1]),
                            max(current_bounds[2], rect[2]),
                            max(current_bounds[3], rect[3]),
                        )
                        bounds_growth = _v37_rect_area(expanded_bounds) - current_area
                        radial = euclid(candidate, altar.center)
                        randomness = stable_rng(
                            seed + schedule_index * 1009,
                            candidate[0],
                            candidate[1],
                            candidate_index,
                        ).random() * max(1.0, AUTO_BUILDING_RANDOMNESS * 0.20)
                        score = (
                            terrain_score * float(settings.get("terrain_score_weight", 0.35))
                            + nearest_gap * float(settings.get("nearest_building_weight", 11.0))
                            + bounds_growth * float(settings.get("bounds_growth_weight", 0.20))
                            + radial * float(settings.get("landmark_distance_weight", 0.55))
                            + randomness
                        )
                        if best is None or score < best[0]:
                            best = (score, candidate, target, rotation, rect)
                    if best is not None:
                        break

        if best is None:
            print(
                f"WARNING: V37 could not place requested copy of {asset.name}; "
                "the compact and expanded search radii contained no valid plot."
            )
            continue

        _score, center, target, rotation, rect = best
        plot = make_json_plot(asset, center, target, rect, rotation, kind="building")
        plots.append(plot)
        occupied.append(rect)
        placed_by_name[asset.path.name] += 1
        nearest_gap = min(
            _v37_rect_edge_gap(rect, existing)
            for existing in occupied[:-1]
        )
        print(
            f"V37 compact building {len(plots):03d}/{total_requested}: "
            f"{asset.name} copy={placed_by_name[asset.path.name]}/"
            f"{counts[asset.path.name]}, center={center}, "
            f"size={plot.rotated_width}x{plot.rotated_depth}, "
            f"nearest edge gap={nearest_gap:.1f}, rotation={rotation}°"
        )
        candidates = [
            point
            for point in candidates
            if not rects_overlap(
                (point[0], point[1], point[0], point[1]),
                rect,
                margin=spacing + 1,
            )
        ]

    print(
        f"V37 compact generation placed {len(plots)}/{total_requested} "
        "requested normal buildings."
    )
    for asset in sorted(assets, key=lambda item: item.path.name):
        print(
            f"  {asset.path.name}: {placed_by_name[asset.path.name]}/"
            f"{counts[asset.path.name]}"
        )
    return plots


_v37_previous_configure_active_tribe = configure_active_tribe


def configure_active_tribe(
    tribe: str,
    *,
    allow_wall_env_override: bool = False,
) -> None:
    global BUILDING_SPACING, WALL_BUILDING_CLEARANCE
    _v37_previous_configure_active_tribe(
        tribe,
        allow_wall_env_override=allow_wall_env_override,
    )
    settings = _v37_active_settings(tribe)
    BUILDING_SPACING = max(1, int(settings.get("building_spacing", 4)))
    WALL_BUILDING_CLEARANCE = max(
        0,
        int(settings.get("wall_building_clearance", 1)),
    )


_v37_previous_load_wall_module_library = load_wall_module_library


def _v37_variant_cycle(
    role: str,
    tokens: Sequence[Any],
) -> List[str]:
    candidates = [
        asset
        for asset in V36_WALL_MODULES_BY_NAME.values()
        if getattr(asset, "role", "") == role
    ]
    if not candidates:
        return []
    by_variant: Dict[str, WallModuleAsset] = {}
    for asset in candidates:
        variant = str(getattr(asset, "decoration_variant", "") or "").lower()
        if not variant:
            variant = "banner" if "banner" in asset.name else "light"
        by_variant.setdefault(variant, asset)
    fallback = by_variant.get("light") or candidates[0]
    result: List[str] = []
    for raw_token in tokens:
        token = str(raw_token).strip().lower()
        exact = V36_WALL_MODULES_BY_NAME.get(str(raw_token))
        if exact is not None and getattr(exact, "role", "") == role:
            result.append(exact.name)
            continue
        result.append((by_variant.get(token) or fallback).name)
    return result


def load_wall_module_library() -> Dict[str, List[WallModuleAsset]]:
    global V36_WALL_PATTERN_NAMES
    global V37_OBLIQUE_PATTERN_NAMES, V37_OBLIQUE_FILLER_NAMES
    library = _v37_previous_load_wall_module_library()
    raw_modules = {
        str(module.get("name")): module
        for module in V36_WALL_LIBRARY_METADATA.get("modules", [])
        if isinstance(module, dict)
    }
    for name, asset in V36_WALL_MODULES_BY_NAME.items():
        raw = raw_modules.get(name, {})
        setattr(
            asset,
            "decoration_variant",
            str(raw.get("decoration_variant") or ("banner" if "banner" in name else "light")),
        )

    settings = _v37_active_settings()
    straight_cycle = _v37_variant_cycle(
        "decorative_straight",
        settings.get("straight_wall_pattern", ["banner", "light", "light"]),
    )
    if straight_cycle:
        V36_WALL_PATTERN_NAMES = straight_cycle

    oblique_cycle = _v37_variant_cycle(
        "decorative_oblique",
        settings.get("oblique_wall_pattern", ["light", "light", "light", "banner"]),
    )
    if not oblique_cycle:
        metadata_cycle = (
            V36_WALL_LIBRARY_METADATA.get("oblique_wall_pattern", {})
            .get("cycle", [])
        )
        oblique_cycle = [
            str(name)
            for name in metadata_cycle
            if str(name) in V36_WALL_MODULES_BY_NAME
        ]
    V37_OBLIQUE_PATTERN_NAMES = oblique_cycle

    V37_OBLIQUE_FILLER_NAMES = {}
    filler_metadata = V36_WALL_LIBRARY_METADATA.get("oblique_filler_policy", {})
    for raw_remaining, raw_name in (
        filler_metadata.get("remaining_contour_units_to_module", {}) or {}
    ).items():
        try:
            remaining = int(raw_remaining)
        except (TypeError, ValueError):
            continue
        name = str(raw_name)
        asset = V36_WALL_MODULES_BY_NAME.get(name)
        if asset is not None and getattr(asset, "role", "") == "oblique_gap_filler":
            V37_OBLIQUE_FILLER_NAMES[remaining] = name

    print("V37 straight pattern: " + " -> ".join(V36_WALL_PATTERN_NAMES))
    print(
        "V37 oblique pattern: "
        + (" -> ".join(V37_OBLIQUE_PATTERN_NAMES) if V37_OBLIQUE_PATTERN_NAMES else "none")
    )
    print(
        "V37 oblique residual fillers: "
        + (
            ", ".join(
                f"{remaining}={name}"
                for remaining, name in sorted(V37_OBLIQUE_FILLER_NAMES.items())
            )
            if V37_OBLIQUE_FILLER_NAMES
            else "none"
        )
    )
    print(f"V37 wall/building clearance: {WALL_BUILDING_CLEARANCE} block(s)")
    return library


def _v37_minimum_progress(
    assets: Sequence[WallModuleAsset],
    desired_direction: Dir2D,
    outward_facing: Optional[Any],
) -> int:
    values: List[int] = []
    for asset in assets:
        progresses = _v36_asset_progresses(
            asset,
            desired_direction,
            outward_facing,
        )
        if progresses:
            values.append(min(progresses))
    return min(values) if values else 10**6


def _extend_wall_chain_v36(
    side_name: str,
    current_connector: Tuple[int, int, int],
    target: Pos2D,
    desired_direction: Dir2D,
    decorative_straights: Sequence[WallModuleAsset],
    oblique_assets: Sequence[WallModuleAsset],
    filler_assets: Dict[int, WallModuleAsset],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_blocked: Set[Pos2D],
    building_rects: Sequence[Rect],
    occupied_wall_xz: Set[Pos2D],
    protected_gate_passage_xz: Set[Pos2D],
    seed: int,
    outward_facing: Optional[Any] = None,
    pattern_start_index: int = 0,
) -> Tuple[List[WallPlacement], Set[Pos2D], int, int]:
    """V37 wall chain with separate straight/oblique patterns and fillers."""
    del seed
    placements: List[WallPlacement] = []
    newly_occupied: Set[Pos2D] = set()
    current = current_connector
    pattern_index = pattern_start_index
    filler_count = 0
    iterations = 0
    cardinal = desired_direction[0] == 0 or desired_direction[1] == 0

    if cardinal:
        normal_assets = list(decorative_straights)
        pattern_assets = [
            V36_WALL_MODULES_BY_NAME[name]
            for name in V36_WALL_PATTERN_NAMES
            if name in V36_WALL_MODULES_BY_NAME
        ] or normal_assets
        residual_fillers = dict(filler_assets)
    else:
        normal_assets = [
            asset
            for asset in oblique_assets
            if getattr(asset, "role", "") == "decorative_oblique"
        ]
        if not normal_assets:
            normal_assets = [
                asset
                for asset in oblique_assets
                if getattr(asset, "role", "") != "oblique_gap_filler"
            ]
        pattern_assets = [
            V36_WALL_MODULES_BY_NAME[name]
            for name in V37_OBLIQUE_PATTERN_NAMES
            if name in V36_WALL_MODULES_BY_NAME
        ] or normal_assets
        residual_fillers = {
            remaining: V36_WALL_MODULES_BY_NAME[name]
            for remaining, name in V37_OBLIQUE_FILLER_NAMES.items()
            if name in V36_WALL_MODULES_BY_NAME
        }

    minimum_normal_progress = _v37_minimum_progress(
        normal_assets,
        desired_direction,
        outward_facing,
    )

    while iterations < WALL_MAX_MODULES_PER_CHAIN:
        iterations += 1
        remaining = chain_target_remaining(current, target, desired_direction)
        if remaining <= 0:
            break
        occupied_now = occupied_wall_xz | newly_occupied
        chosen: Optional[Tuple[float, WallPlacement, Set[Pos2D], int]] = None
        chosen_is_decorative = False

        if pattern_assets:
            expected = pattern_assets[pattern_index % len(pattern_assets)]
            ordered = [expected] + [
                asset for asset in normal_assets if asset.name != expected.name
            ]
            for asset_index, asset in enumerate(ordered):
                candidate = _v36_best_asset_placement(
                    asset,
                    side_name,
                    current,
                    target,
                    desired_direction,
                    remaining,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_now,
                    protected_gate_passage_xz,
                    outward_facing,
                )
                if candidate is None:
                    continue
                residual = remaining - candidate[3]
                if not (
                    residual == 0
                    or residual in residual_fillers
                    or residual >= minimum_normal_progress
                ):
                    continue
                chosen = (
                    candidate[0] + asset_index * 1000.0,
                    candidate[1],
                    candidate[2],
                    candidate[3],
                )
                chosen_is_decorative = True
                break

        if chosen is None:
            filler = residual_fillers.get(remaining)
            if filler is not None:
                chosen = _v36_best_asset_placement(
                    filler,
                    side_name,
                    current,
                    target,
                    desired_direction,
                    remaining,
                    ba,
                    heights,
                    water_blocked,
                    building_rects,
                    occupied_now,
                    protected_gate_passage_xz,
                    outward_facing,
                    exact_progress=remaining,
                )
                if chosen is not None:
                    filler_count += 1

        if chosen is None:
            print(
                f"  {side_name} V37 chain stopped with {remaining} "
                "contour unit(s) remaining; only that unresolved portion "
                "will use the emergency spine."
            )
            break

        _score, placement, solid_xz, _progress = chosen
        placements.append(placement)
        newly_occupied.update(solid_xz)
        assert placement.end_connector_world is not None
        current = placement.end_connector_world
        if chosen_is_decorative:
            pattern_index += 1

    return placements, newly_occupied, pattern_index, filler_count


_v37_previous_plan_settlement_walls = plan_settlement_walls


def plan_settlement_walls(
    plots: Sequence[Plot],
    wall_library: Dict[str, List[WallModuleAsset]],
    ba: dict,
    heights: Dict[Pos2D, int],
    water_cells: Set[Pos2D],
    water_blocked: Set[Pos2D],
    seed: int,
) -> Tuple[List[WallPlacement], Dict[str, str], List[dict], Optional[Rect]]:
    global WALL_BUILDING_CLEARANCE
    WALL_BUILDING_CLEARANCE = max(
        0,
        int(_v37_active_settings().get("wall_building_clearance", 1)),
    )
    result = _v37_previous_plan_settlement_walls(
        plots,
        wall_library,
        ba,
        heights,
        water_cells,
        water_blocked,
        seed,
    )
    placements = result[0]
    unresolved = sum(
        1
        for status in result[1].values()
        if "EMERGENCY" in status.upper()
    )
    print(
        f"V37 wall planning complete: modules={len(placements)}, "
        f"macro sides without a gate={unresolved}."
    )
    return result

if __name__ == "__main__":
    main()

# V34: post-settlement biome saplings, verified open-space planting, and immediate feature growth.
# V33: one copy per building type and trunk-component-owned tree clearing.
# V32: organic terrain mask, complete settlement-tree removal, one-building test mode, and simple connected stone-brick walls.
# V31: structure-aware final terrain lock removes land islands and prevents buried buildings.
# V30: post-terrain rescan repairs holes/chunks and removes damaged trees beyond the settlement.
# V28: complete building-intersecting tree removal and exact waypoint-Y road anchors.
# V27: full water reclamation during terrain formation, solid wall-over-water foundations, and complete damaged-tree removal.
# V26: full terrain-first formation, deep ravine filling, shallow cave sealing, and refreshed heightmaps before generation.

# V25: unbroken 10-block-offset walls, reclaimed enclosed water, and solid biome road subgrades.

# V24: mountain flattening before generation, grass terraces, unified plot grade, and walls planned on regraded terrain.

# V23: gentle whole-settlement terrain, shallow cuts, cave filling, preserved trees, and no-dig walls.

# V22: 1000x1000 multi-biome world planning with isolated tribe settlements.

# V21: custom villager names, automatic tribe skins, rotation-safe spawning.
