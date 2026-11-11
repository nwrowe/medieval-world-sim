"""Readable companion report for atlas-derived regional-resource economics."""
from __future__ import annotations

import json

from ..content.catalog import RAW_RESOURCES, RECIPES

RESOURCE_SURVEY_SCHEMA = 1


def render_resource_json(world) -> str:
    """Stable, small JSON contract for a future (explicit) economy adapter."""
    from dataclasses import asdict
    data = {
        "schema_version": RESOURCE_SURVEY_SCHEMA,
        "world_seed": world.seed,
        "generator_version": world.version,
        "units": {
            "potential": "mean per-tile resource potential, 0..100",
            "estimated_units_per_hour": "proposed production capacity, not stocks",
            "route_minutes": "estimated land-road travel, not shipping time",
            "raw_inputs_per_craft": "recipe inputs expanded to raw resource counts",
        },
        "raw_resource_ids": list(RAW_RESOURCES),
        "recipe_ids": sorted(RECIPES),
        "towns": [asdict(p) for p in world.resource_profiles],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _show(goods) -> str:
    return ", ".join(a.resource.replace("_", " ").title() for a in goods) or "None"


def render_resource_markdown(world) -> str:
    """Human-facing regional production and import-dependency comparison."""
    lines = [
        f"# Oathmere — Regional Resource Survey (Seed {world.seed})",
        "",
        "**Designer production model, not live market inventory.** The categories",
        "below reflect the resources naturally supported within five hexes of",
        "each town. 'Lacking' means there is **no modeled local production at",
        "this resolution**; it does not mean the material cannot exist nearby,",
        "be stored in a warehouse, or be imported by a merchant.",
        "",
        "## Town comparison",
        "",
        "| Town | Primary natural resources | Secondary natural resources | No local production |",
        "| --- | --- | --- | --- |",
    ]
    for profile in world.resource_profiles:
        lines.append(
            f"| {profile.settlement_name} | {_show(profile.primary)} | "
            f"{_show(profile.secondary)} | {_show(profile.lacking)} |")
    for profile in world.resource_profiles:
        lines.extend([
            "",
            f"## {profile.settlement_name}",
            "",
            f"Stable settlement ID: `{profile.settlement_id}`.",
            "",
            f"**Primary:** {_show(profile.primary)}.",
            "",
            f"**Secondary:** {_show(profile.secondary)}.",
            "",
            f"**Lacking local production:** {_show(profile.lacking)}.",
            "",
            "### Geographic evidence",
            "",
        ])
        for grade, evidence in (("Primary", profile.primary),
                                ("Secondary", profile.secondary),
                                ("Lacking", profile.lacking)):
            for assessment in evidence:
                lines.append(
                    f"- **{assessment.resource.replace('_', ' ').title()} "
                    f"({grade.lower()})** — {assessment.explanation} "
                    f"Indicative capacity: {assessment.estimated_units_per_hour}/hour.")
        lines.extend(["", "### Industry supply chains", ""])
        opportunities = [i for i in profile.industries
                         if i.classification != "no_local_inputs"]
        for industry in opportunities:
            raw = ", ".join(
                f"{good.replace('_', ' ')} ×{count}"
                for good, count in industry.raw_inputs_per_craft.items())
            missing = ", ".join(x.replace("_", " ") for x in industry.imports_needed)
            supply = ("Can source all modeled raw inputs locally" if not missing
                      else f"Requires imports of: {missing}")
            lines.append(f"- **{industry.recipe}** → {', '.join(industry.outputs)}: "
                         f"{raw}. {supply}.")
        if not opportunities:
            lines.append("- No modeled processing recipe currently uses a locally "
                         "produced raw input.")
        lines.extend(["", "### Candidate overland suppliers", ""])
        if not profile.supplier_candidates:
            lines.append("- No neighboring supplier is identified for the currently "
                         "lacking raw resources.")
        for candidate in profile.supplier_candidates:
            lines.append(
                f"- **{candidate.resource.replace('_', ' ').title()}**: "
                f"{candidate.source_name} ({candidate.source_id}), "
                f"approximately {candidate.route_minutes} minutes along the "
                "generated road network; source's potential production "
                f"{candidate.estimated_source_units_per_hour}/hour.")
    lines.extend([
        "",
        "## Important economic boundaries",
        "",
        "- A town's extraction estimate is **not** guaranteed exportable surplus.",
        "  Real exports require labor, operating businesses, stock, local demand,",
        "  storage and transport, all governed by the future authoritative economy.",
        "- A missing input in a recipe is an **industrial import dependency**;",
        "  it is not a claim that a company or buyer already exists in that town.",
        "- Existing recipes are reused by ID and expanded through intermediate",
        "  materials (for example, steel requires iron ore plus coal).",
        "- Overland supplier suggestions use actual generated road travel times",
        "  and potential source output. They do not teleport goods or create trades.",
        "- The playable five-city system and stored accounts are unchanged.",
        "",
    ])
    return "\n".join(lines)
