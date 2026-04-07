"""
Generate an earthquake-damaged candidate CityJSON for PDM demo scenarios.

The output file is a new artifact and the original source file is untouched.
The generated file explicitly removes CRS metadata (metadata.referenceSystem).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from pathlib import Path


DEFAULT_SOURCE = Path(
    "/data/home/sagerdev/demo_app_3dSAGER/data/RawCitiesData/The Hague/Source A/"
    "TheHague3D_Batch_07_Loosduinen_2022-08-08.json"
)
DEFAULT_ANCHORS = [
    "0518100000327112",
    "0518100000213258",
    "0518100000285840",
]


def _normalize_id(value: str) -> str:
    match = re.search(r"(\d{10,})", str(value))
    return match.group(1) if match else str(value)


def _iter_indices(node):
    if isinstance(node, int):
        yield node
        return
    if isinstance(node, list):
        for child in node:
            yield from _iter_indices(child)


def _collect_building_vertices(city_obj: dict) -> set[int]:
    indices = set()
    for geom in city_obj.get("geometry", []) or []:
        for idx in _iter_indices(geom.get("boundaries", [])):
            if isinstance(idx, int):
                indices.add(idx)
    return indices


def _get_footprint_ring_indices(city_obj: dict) -> list[int]:
    geoms = city_obj.get("geometry", []) or []
    if not geoms:
        return []
    geom = geoms[0]
    boundaries = geom.get("boundaries", [])
    if geom.get("type") == "Solid":
        # First shell, first face, first ring
        if boundaries and boundaries[0] and boundaries[0][0] and boundaries[0][0][0]:
            return list(boundaries[0][0][0])
    elif geom.get("type") in ("MultiSurface", "CompositeSurface"):
        if boundaries and boundaries[0] and boundaries[0][0]:
            return list(boundaries[0][0])
    return []


def _damage_factor(rng: random.Random) -> float:
    roll = rng.random()
    if roll < 0.35:
        return rng.uniform(0.08, 0.28)  # severe collapse
    if roll < 0.75:
        return rng.uniform(0.30, 0.55)  # moderate collapse
    return rng.uniform(0.60, 0.85)      # light damage


def _choose_damage_mode(rng: random.Random) -> str:
    # Mild/medium default (outside severe clusters)
    roll = rng.random()
    if roll < 0.60:
        return "tilt"
    if roll < 0.85:
        return "side_collapse"
    return "core_hole"


def _choose_damage_mode_severe(rng: random.Random) -> str:
    # Severe cluster mode (inside collapse hotspots)
    roll = rng.random()
    if roll < 0.70:
        return "core_hole"
    return "side_collapse"


def _choose_damage_mode_demo(rng: random.Random) -> str:
    # Very visible destruction for demo hotspots (still local, not smeared)
    roll = rng.random()
    if roll < 0.45:
        return "core_hole"
    if roll < 0.85:
        return "side_collapse"
    return "tilt"


def generate_damaged_file(
    source_path: Path,
    output_path: Path,
    anchors: list[str],
    seed: int = 20260330,
    affect_ratio: float = 0.88,
) -> dict:
    rng = random.Random(seed)
    with source_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "CityJSON" or "CityObjects" not in data or "vertices" not in data:
        raise ValueError("Input file is not a valid CityJSON building dataset")

    city_objects = data.get("CityObjects", {})
    vertices = data.get("vertices", [])

    normalized_anchor_ids = {_normalize_id(a) for a in anchors}
    building_to_vertices: dict[str, set[int]] = {}
    building_to_footprint: dict[str, list[int]] = {}
    building_centers: dict[str, tuple[float, float]] = {}
    anchor_buildings = set()
    anchor_vertices = set()

    for obj_id, city_obj in city_objects.items():
        if city_obj.get("type") != "Building":
            continue
        vset = _collect_building_vertices(city_obj)
        if not vset:
            continue
        building_to_vertices[obj_id] = vset
        fp = _get_footprint_ring_indices(city_obj)
        if fp:
            building_to_footprint[obj_id] = fp
        cx = sum(float(vertices[i][0]) for i in vset) / len(vset)
        cy = sum(float(vertices[i][1]) for i in vset) / len(vset)
        building_centers[obj_id] = (cx, cy)
        if _normalize_id(obj_id) in normalized_anchor_ids:
            anchor_buildings.add(obj_id)
            anchor_vertices.update(vset)

    if len(anchor_buildings) < 3:
        raise ValueError(
            f"Expected at least 3 anchor buildings, found {len(anchor_buildings)} in source file"
        )

    candidate_buildings = [bid for bid in building_to_vertices.keys() if bid not in anchor_buildings]
    rng.shuffle(candidate_buildings)

    target_affected = int(len(candidate_buildings) * affect_ratio)
    affected_buildings = set(candidate_buildings[:target_affected])

    # Realistic clustered damage: only some zones have severe collapse.
    # This avoids "everything looks equally destroyed".
    hotspot_count = min(6, max(3, len(affected_buildings) // 2000))
    hotspot_ids = rng.sample(list(affected_buildings), hotspot_count) if affected_buildings else []
    hotspot_centers = [building_centers[bid] for bid in hotspot_ids if bid in building_centers]
    hotspot_radius = 120.0  # local effect radius (RD-New units are meters)

    # Additional "demo destruction zone": deterministic near dataset center
    # so it is visible immediately, not hidden in a random neighborhood.
    demo_hotspot_centers = []
    demo_hotspot_radius = 165.0
    if building_centers:
        xs = [c[0] for c in building_centers.values()]
        ys = [c[1] for c in building_centers.values()]
        data_cx = sum(xs) / len(xs)
        data_cy = sum(ys) / len(ys)
        nearest = sorted(
            ((math.hypot(cx - data_cx, cy - data_cy), bid) for bid, (cx, cy) in building_centers.items()),
            key=lambda t: t[0]
        )
        # use 2 center-near hotspots to make one clearly damaged district
        for _, bid in nearest[:2]:
            demo_hotspot_centers.append(building_centers[bid])
    forced_remove_buildings = set()
    if demo_hotspot_centers:
        # Force a visible number of missing buildings near demo hotspots.
        ranked = []
        for bid in affected_buildings:
            if bid not in building_centers:
                continue
            bx, by = building_centers[bid]
            dmin = min(math.hypot(bx - hx, by - hy) for hx, hy in demo_hotspot_centers)
            ranked.append((dmin, bid))
        ranked.sort(key=lambda t: t[0])
        target_remove = min(420, max(180, len(affected_buildings) // 28))
        for _, bid in ranked:
            if len(forced_remove_buildings) >= target_remove:
                break
            forced_remove_buildings.add(bid)

    proposed_vertex_updates: dict[int, tuple[float, float, float]] = {}
    touched_vertices = 0
    mode_counts = {"tilt": 0, "side_collapse": 0, "core_hole": 0}
    removed_buildings = set()

    for building_id in affected_buildings:
        idx_set = building_to_vertices[building_id]
        mutable_indices = [idx for idx in idx_set if idx not in anchor_vertices and 0 <= idx < len(vertices)]
        if len(mutable_indices) < 4:
            continue

        z_values = [float(vertices[idx][2]) for idx in mutable_indices]
        min_z = min(z_values)
        max_z = max(z_values)
        if max_z <= min_z:
            continue

        center_x_b, center_y_b = building_centers.get(building_id, (0.0, 0.0))
        severity = 0.0
        for hx, hy in hotspot_centers:
            dx = center_x_b - hx
            dy = center_y_b - hy
            d = math.hypot(dx, dy)
            local = math.exp(-(d * d) / (2.0 * hotspot_radius * hotspot_radius))
            if local > severity:
                severity = local

        demo_severity = 0.0
        for hx, hy in demo_hotspot_centers:
            dx = center_x_b - hx
            dy = center_y_b - hy
            d = math.hypot(dx, dy)
            local = math.exp(-(d * d) / (2.0 * demo_hotspot_radius * demo_hotspot_radius))
            if local > demo_severity:
                demo_severity = local

        # Most buildings are mild/moderate; hotspots produce severe collapses.
        if demo_severity > 0.32:
            mode = _choose_damage_mode_demo(rng)
            severe_building = True
            demo_building = True
        elif severity > 0.52 or (severity > 0.28 and rng.random() < 0.55):
            mode = _choose_damage_mode_severe(rng)
            severe_building = True
            demo_building = False
        else:
            mode = _choose_damage_mode(rng)
            severe_building = False
            demo_building = False
        mode_counts[mode] += 1
        factor = _damage_factor(rng)
        if severe_building:
            factor *= rng.uniform(0.45, 0.75)  # more vertical loss in hotspots
        else:
            factor *= rng.uniform(0.78, 0.96)
        height = max_z - min_z
        noise_span = height * 0.05

        # Force-remove a subset around demo hotspots for clearly visible missing structures.
        if building_id in forced_remove_buildings:
            removed_buildings.add(building_id)
            continue

        # In severe/demo hotspots remove some buildings completely (total collapse).
        if severe_building and rng.random() < (0.18 if demo_building else 0.08):
            removed_buildings.add(building_id)
            continue

        center_x = sum(float(vertices[i][0]) for i in mutable_indices) / len(mutable_indices)
        center_y = sum(float(vertices[i][1]) for i in mutable_indices) / len(mutable_indices)
        min_x = min(float(vertices[i][0]) for i in mutable_indices)
        max_x = max(float(vertices[i][0]) for i in mutable_indices)
        min_y = min(float(vertices[i][1]) for i in mutable_indices)
        max_y = max(float(vertices[i][1]) for i in mutable_indices)
        footprint_span = max(max_x - min_x, max_y - min_y, 2.0)
        footprint_indices = [i for i in building_to_footprint.get(building_id, []) if i in mutable_indices]
        fp_set = set(footprint_indices)

        # Keep horizontal displacement limited so buildings look broken/collapsed,
        # not smeared across long distances.
        base_shift = min(2.0, max(0.35, footprint_span * 0.12))
        if demo_building:
            max_xy_shift = base_shift * 1.35
        elif severe_building:
            max_xy_shift = base_shift * 1.2
        else:
            max_xy_shift = base_shift

        ang = rng.uniform(0.0, 2.0 * math.pi)
        dir_x = math.cos(ang)
        dir_y = math.sin(ang)
        side_threshold = rng.uniform(-0.08, 0.08) * footprint_span
        hole_radius = max(0.7, footprint_span * rng.uniform(0.18, 0.30))
        top_damage_cut = rng.uniform(0.30, 0.55)
        collapse_sector_angle = rng.uniform(-math.pi, math.pi)
        collapse_sector_half_width = rng.uniform(0.45, 0.95)

        # Building-level tilt: small translation increasing with height.
        tilt_x = dir_x * rng.uniform(0.35, 1.0) * max_xy_shift
        tilt_y = dir_y * rng.uniform(0.35, 1.0) * max_xy_shift

        for idx in mutable_indices:
            old_x = float(vertices[idx][0])
            old_y = float(vertices[idx][1])
            old_z = float(vertices[idx][2])
            rel_h = (old_z - min_z) / max(height, 1e-9)  # 0=ground, 1=roof
            rel_h = max(0.0, min(1.0, rel_h))

            new_z = min_z + (old_z - min_z) * factor

            roof_weight = rel_h ** 1.6
            side_weight = ((old_x - center_x) * dir_x + (old_y - center_y) * dir_y)
            radial_x = old_x - center_x
            radial_y = old_y - center_y
            radial_norm = math.hypot(radial_x, radial_y) + 1e-9
            radial_ux = radial_x / radial_norm
            radial_uy = radial_y / radial_norm

            # Base tilt (present in all modes), strongest near roof.
            new_x = old_x + tilt_x * roof_weight
            new_y = old_y + tilt_y * roof_weight

            if mode == "tilt":
                # Stronger collapse on one side, limited horizontal drift.
                if side_weight > side_threshold:
                    new_z -= roof_weight * height * rng.uniform(0.20, 0.55)
                    new_x += dir_x * max_xy_shift * rng.uniform(0.08, 0.28) * roof_weight
                    new_y += dir_y * max_xy_shift * rng.uniform(0.08, 0.28) * roof_weight
            elif mode == "side_collapse":
                # A wedge/corner drops: looks like part of building is missing.
                if side_weight > side_threshold and rel_h > top_damage_cut:
                    new_z = min_z + rng.uniform(0.0, max(0.42, height * 0.09))
                    # Pull inward so collapsed chunk appears gone rather than stretched.
                    new_x -= radial_ux * max_xy_shift * rng.uniform(0.12, 0.35)
                    new_y -= radial_uy * max_xy_shift * rng.uniform(0.12, 0.35)
            else:  # core_hole
                # Center collapses down creating an inner "hole".
                hole_mul = 1.35 if demo_building else 1.0
                if radial_norm < hole_radius * hole_mul and rel_h > 0.22:
                    new_z = min_z + rng.uniform(0.0, max(0.38, height * 0.12))
                    # slight inward pull for crater effect
                    new_x -= radial_ux * max_xy_shift * rng.uniform(0.04, 0.18)
                    new_y -= radial_uy * max_xy_shift * rng.uniform(0.04, 0.18)

            # Extra footprint "bite" so extrusion visibly loses chunks (important for this viewer).
            # We only move footprint vertices inward, never far away.
            if idx in fp_set:
                ang_v = math.atan2(old_y - center_y, old_x - center_x)
                d_ang = abs((ang_v - collapse_sector_angle + math.pi) % (2 * math.pi) - math.pi)
                in_collapse_sector = d_ang < collapse_sector_half_width
                if mode in ("side_collapse", "core_hole") and in_collapse_sector:
                    inward = max_xy_shift * (0.55 if demo_building else 0.35) * (1.0 - d_ang / collapse_sector_half_width)
                    new_x -= radial_ux * inward
                    new_y -= radial_uy * inward
                    # Slightly reduce local top in collapsed footprint edge
                    if rel_h > 0.4:
                        new_z -= height * (0.10 if demo_building else 0.06)

            # Small jaggedness so edges are irregular.
            new_z += rng.uniform(-noise_span, noise_span) * (0.2 + roof_weight)

            # Additional random missing chunks (upper vertices only).
            drop_prob = 0.33 if demo_building else (0.12 if severe_building else 0.04)
            if rel_h > 0.50 and rng.random() < drop_prob:
                new_z = min_z + rng.uniform(0.0, max(0.34, height * 0.07))

            if new_z < min_z:
                new_z = min_z

            # Clamp horizontal movement to avoid long-distance smearing.
            dx = new_x - old_x
            dy = new_y - old_y
            dxy = math.hypot(dx, dy)
            if dxy > max_xy_shift:
                scale = max_xy_shift / max(dxy, 1e-9)
                new_x = old_x + dx * scale
                new_y = old_y + dy * scale

            proposed = (new_x, new_y, new_z)
            if idx in proposed_vertex_updates:
                old_p = proposed_vertex_updates[idx]
                # Keep the more collapsed Z, and blend XY to avoid sudden jumps.
                z_keep = min(old_p[2], proposed[2])
                x_blend = (old_p[0] + proposed[0]) / 2.0
                y_blend = (old_p[1] + proposed[1]) / 2.0
                proposed_vertex_updates[idx] = (x_blend, y_blend, z_keep)
            else:
                proposed_vertex_updates[idx] = proposed

    for idx, (new_x, new_y, new_z) in proposed_vertex_updates.items():
        vertices[idx][0] = round(float(new_x), 6)
        vertices[idx][1] = round(float(new_y), 6)
        vertices[idx][2] = round(float(new_z), 6)
        touched_vertices += 1

    # Remove fully collapsed buildings from CityObjects (they become "missing").
    if removed_buildings:
        for bid in removed_buildings:
            city_objects.pop(bid, None)

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        metadata.pop("referenceSystem", None)
        metadata["pdmDamageScenario"] = {
            "kind": "earthquake",
            "profile": "clustered_breakage_with_demo_hotspots_v8",
            "seed": seed,
            "anchors_preserved": sorted(anchor_buildings),
            "affected_building_ratio": affect_ratio,
            "hotspot_count": len(hotspot_centers),
            "hotspot_radius_m": hotspot_radius,
            "demo_hotspot_count": len(demo_hotspot_centers),
            "demo_hotspot_radius_m": demo_hotspot_radius,
            "demo_hotspot_centers_xy": [[round(c[0], 3), round(c[1], 3)] for c in demo_hotspot_centers],
            "removed_buildings_count": len(removed_buildings),
            "damage_mode_counts": mode_counts,
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    return {
        "output_file": str(output_path),
        "anchors_preserved_count": len(anchor_buildings),
        "affected_buildings_count": len(affected_buildings),
        "updated_vertices_count": touched_vertices,
        "removed_buildings_count": len(removed_buildings),
        "damage_mode_counts": mode_counts,
        "crs_removed": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate PDM damaged CityJSON with no CRS metadata")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Input CityJSON file")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CityJSON path (default: <source_stem>_pdm_eq_damaged_no_crs.json)",
    )
    parser.add_argument("--seed", type=int, default=20260330, help="Random seed for deterministic output")
    parser.add_argument(
        "--anchors",
        nargs="+",
        default=DEFAULT_ANCHORS,
        help="Anchor building IDs to keep unchanged (minimum 3)",
    )
    parser.add_argument(
        "--affect-ratio",
        type=float,
        default=0.88,
        help="Fraction of non-anchor buildings to damage",
    )
    args = parser.parse_args()

    output = args.output
    if output is None:
        output = args.source.with_name(f"{args.source.stem}_pdm_eq_damaged_no_crs_v8.json")

    result = generate_damaged_file(
        source_path=args.source,
        output_path=output,
        anchors=args.anchors,
        seed=args.seed,
        affect_ratio=args.affect_ratio,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
