"""Readable, reproducible world-history narrative from causal event records."""
from __future__ import annotations


def render_chronicle(world) -> str:
    """Export a markdown chronicle: same events as the interactive atlas and JSON."""
    history = world.history
    if history is None:
        raise ValueError("World has no historical chronicle")
    lines = [
        f"# The Chronicle of Oathmere — Seed {world.seed}",
        "",
        "> **Designer survey, not official canon.** The settlements, roads, political",
        "> allegiances, populations and events below are geography-driven historical",
        "> projections, not live NPC population records or player-facing discoveries.",
        "",
        f"Survey span: **Year {history.start_year} to Year {history.present_year}**.",
        "",
    ]
    for era in history.eras:
        total = sum(t.population for t in era.towns)
        lines.extend([
            f"## {era.name} (Year {era.year})",
            "",
            f"At this point, {len(era.towns)} founded settlements support an estimated",
            f"{total:,} inhabitants. {len(era.roads)} geographic trade corridors",
            f"are active under {len(era.polities)} local political centers.",
            "",
        ])
        if era.polities:
            lines.append("**Political centers:** " + "; ".join(
                f"{p.name} (seat: {next(t.name for t in era.towns if t.id == p.seat_id)}, "
                f"{len(p.member_ids)} settlements)"
                for p in era.polities
            ) + ".")
            lines.append("")
        for event in era.events:
            lines.append(f"- **{event.title}.** {event.account}")
        if not era.events:
            lines.append("- The survey records no distinct turning points this era.")
        lines.append("")
    lines.extend([
        "## Abandoned places and surviving ruins",
        "",
        "These records explain how geographically plausible sites became abandoned.",
        "A historical ruin does not automatically add a playable dungeon interior.",
        "",
    ])
    for ruin in history.ruins:
        lines.extend([
            f"### {ruin.name}",
            "",
            f"- **Location:** hex ({ruin.x}, {ruin.y})",
            f"- **Former function:** {ruin.former_use}",
            f"- **Occupied:** Year {ruin.founded_year} to {ruin.abandoned_year}",
            f"- **Abandonment:** {ruin.cause}",
            f"- **Related present-day site:** {ruin.linked_site_id or 'Uncatalogued hamlet'}",
            "",
        ])
    lines.extend([
        "## Historical assumptions",
        "",
        "Founding suitability uses water, rainfall, soil, terrain difficulty and",
        "accessible resources. Trade proxies use complementary settlement production,",
        "population, road surface and real route time; market strength and road",
        "travel costs influence political allegiance. Environmental risks follow",
        "climate and flood exposure. The model is deterministic for this seed and",
        "its accompanying authored world-content manifest.",
        "",
        "These are proposals for worldbuilding, not evidence of real simulated",
        "commodity stock, actual warfare, official noble lineages or time-dependent",
        "multiplayer territory. See docs/HISTORICAL_DEVELOPMENT.md.",
        "",
    ])
    return "\n".join(lines)
