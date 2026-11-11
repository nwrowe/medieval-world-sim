"""Standalone interactive hex inspector for reviewing a generated world.

The HTML contains its SVG and survey records inline, so designers can open it
locally with no server, package, JavaScript framework or network connection.
This is NOT the player's fog-of-war map; it deliberately exposes all atlas data.
"""
from __future__ import annotations

from html import escape
from dataclasses import asdict
import json

from .hexgrid import vertices
from .render import MARGIN, TILE_PX, TOP, render_svg
from .access import minutes_per_hex


def render_inspector_html(world, svg: str | None = None) -> str:
    """Return a self-contained clickable survey atlas (no live-game side effects)."""
    if svg is None:
        svg = render_svg(world)
    polygons = []
    for index, tile in enumerate(world.tiles):
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in
                          vertices(tile.x, tile.y, TILE_PX))
        polygons.append(f'<polygon data-index="{index}" points="{points}"/>')
    hit_layer = (
        f'<g id="atlas-inspector-hit" transform="translate({MARGIN},{TOP})" '
        'fill="transparent" stroke="none" pointer-events="all">'
        + "".join(polygons) + '</g>')
    if not svg.rstrip().endswith("</svg>"):
        raise ValueError("Atlas SVG is missing closing root element")
    svg = svg.rstrip()[:-6] + hit_layer + "</svg>"

    settlements = {(s.x, s.y): s.name for s in world.settlements}
    by_id = {p.settlement_id: asdict(p) for p in world.resource_profiles}
    town_profiles = {(s.x, s.y): by_id.get(s.id)
                     for s in world.settlements}
    sites = {}
    for site in world.sites:
        sites.setdefault((site.x, site.y), []).append(site.name)
    landmarks = {}
    for mark in world.landmarks:
        landmarks.setdefault((mark.x, mark.y), []).append(mark.name)
    roads = {(x, y) for road in world.roads for x, y in road.path}
    events = {}
    for event in world.event_locations:
        events.setdefault((event.x, event.y), []).append(
            f"{event.name} ({event.starts_at} to {event.ends_at})")
    record = [
        {"x": t.x, "y": t.y, "biome": t.biome,
         "height": t.elevation_m, "temp": t.temperature_c,
         "rain": t.rainfall_mm, "geology": t.geology, "soil": t.soil,
         "water": t.waterbody, "watercraft": t.navigable,
         "seabed_depth": t.seabed_depth_m,
         "natural_difficulty": t.natural_difficulty,
         "travel_difficulty": t.travel_difficulty,
         "road_surface": t.road_surface,
         "foot_minutes": (round(minutes_per_hex(t.travel_difficulty, world.cell_km), 1)
                          if t.travel_difficulty is not None else None),
         "flow": t.flow if t.river else 0,
         "resources": t.resources, "town": settlements.get((t.x, t.y), ""),
         "town_profile": town_profiles.get((t.x, t.y)),
         "sites": sites.get((t.x, t.y), []),
         "landmarks": landmarks.get((t.x, t.y), []),
         "events": events.get((t.x, t.y), []),
         "road": (t.x, t.y) in roads}
        for t in world.tiles
    ]
    # JSON inside script tags must never accidentally close the containing tag.
    payload = json.dumps(record, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    title = f"Oathmere Atlas · Seed {world.seed}"
    page = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>__TITLE__</title>
<style>
:root {color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#161e22;color:#e9e5d9}
main{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:14px;padding:16px;max-width:1900px;margin:auto}
#map-view{overflow:auto;height:calc(100vh - 32px);background:#293b39;border:1px solid #52635c;border-radius:9px;cursor:crosshair}
#map-view svg{display:block;width:100%;height:auto;min-width:650px}
#atlas-inspector-hit polygon{cursor:crosshair}
#atlas-inspector-hit polygon:hover{fill:rgba(245,202,107,.17);stroke:#fff0bd;stroke-width:1.7;stroke-dasharray:none}
#atlas-inspector-hit polygon.is-selected{fill:rgba(255,213,112,.20);stroke:#ffe1a0;stroke-width:2.8}
aside{background:#202a2b;border:1px solid #43554f;border-radius:9px;padding:17px;overflow:auto;max-height:calc(100vh - 32px)}
h1{font-family:Georgia,serif;font-size:22px;font-weight:normal;margin:0 0 6px}
p{font-size:13px;color:#c6cec6;line-height:1.6;margin:6px 0 14px}
h2{font-size:15px;color:#f4d99f;margin:22px 0 8px}
.info{display:grid;grid-template-columns:1fr 1fr;gap:8px 12px;font-size:13px}
.info strong{display:block;color:#eddbb0;font-size:12px;margin-bottom:2px}
.info span{color:#eef0e9}
.tag{display:inline-block;background:#344644;padding:5px 8px;border-radius:5px;font-size:12px;margin:3px 3px 3px 0}
button{background:#394d4a;border:1px solid #728579;color:#fff2db;border-radius:5px;padding:7px 12px;cursor:pointer}
.toolbar{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin:10px 0 14px}
#selected{color:#f6ddab}
select{background:#394d4a;border:1px solid #728579;color:#fff2db;
padding:7px;border-radius:5px;max-width:100%;width:100%}
.resource-note{border-top:1px solid #41564e;padding-top:7px;margin-top:8px}
.resource-note b{color:#eecb96;font-size:13px}
.resource-note p{font-size:12px;margin:4px 0 8px}
#economy-block h3{font-size:13px;color:#e9c992;margin:12px 0 5px}
small{color:#abb6ae}
@media(max-width:860px){main{grid-template-columns:1fr}#map-view{height:56vh}aside{max-height:none}}
</style></head>
<body><main>
<div id="map-view">__SVG__</div>
<aside aria-live="polite">
<h1>The Royal Survey</h1><p>Seed __SEED__ · Click any hex for elevation, terrain difficulty, estimated walking time, climate, resources and authored locations.</p>
<div class="toolbar"><button id="zoom-in" type="button">Zoom +</button>
<button id="zoom-out" type="button">Zoom −</button>
<button id="reset" type="button">Reset</button>
<small id="zoom-label">100%</small></div>
<label for="town-list">Jump to a settlement</label>
<select id="town-list"><option value="">Choose a town...</option></select>
<h2 id="selected">Select a hex</h2>
<div class="info" id="facts"></div>
<h2>Local natural resources</h2><div id="resources"><p>Select a tile to inspect its potential.</p></div>
<h2>Places and infrastructure</h2><div id="places"><p>Roads, settlements, and landmarks appear here.</p></div>
<h2>Town resource economy</h2>
<p><small>For a town-by-town regional comparison, open <a href="town-resources.md">the resource report</a> in the same folder.</small></p>
<div id="economy-block"><p>Select a town hex to see its primary and secondary resources, geographic justification, local shortages and potential trading partners.</p></div>
<p><small>This is a designer's survey. Land difficulty is 1 (easy) to 100 (very hard); sea and lake hexes have no foot route. Watercraft suitability is a separate, provisional survey. Road times are estimates, not yet connected to live travel. Potential resources are not player inventories.</small></p>
</aside></main>
<script id="atlas-data" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
var records=JSON.parse(document.getElementById("atlas-data").textContent);
var map=document.getElementById("map-view");
var svg=map.querySelector("svg");
var selected=null;
var scale=1;
function info(label,value){var node=document.createElement("div"),a=document.createElement("strong"),b=document.createElement("span");a.textContent=label;b.textContent=String(value);node.append(a,b);return node}
function tags(id,values){var target=document.getElementById(id);target.replaceChildren();if(!values.length){var p=document.createElement("p");p.textContent="None mapped";target.append(p);return}values.forEach(function(value){var span=document.createElement("span");span.className="tag";span.textContent=value;target.append(span)})}
function heading(target,label){
 var h=document.createElement("h3");h.textContent=label;target.append(h);
}
function resourceList(target,label,resources){
 heading(target,label);
 if(!resources.length){var no=document.createElement("p");no.textContent="None";target.append(no);return}
 resources.forEach(function(r){
  var card=document.createElement("div");card.className="resource-note";
  var title=document.createElement("b");
  title.textContent=r.resource.replace(/_/g," ")+" · "+r.estimated_units_per_hour+"/hour potential";
  var note=document.createElement("p");note.textContent=r.explanation;
  card.append(title,note);target.append(card);
 });
}
function townEconomy(profile){
 var target=document.getElementById("economy-block");target.replaceChildren();
 if(!profile){var msg=document.createElement("p");msg.textContent="Select a town hex to inspect local production and import needs.";target.append(msg);return}
 var name=document.createElement("p");name.textContent=profile.settlement_name+
  " · five-hex geographic production catchment";target.append(name);
 resourceList(target,"Primary natural resources",profile.primary);
 resourceList(target,"Secondary natural resources",profile.secondary);
 resourceList(target,"Lacking locally",profile.lacking);
 heading(target,"Local industry dependencies");
 var ready=profile.industries.filter(function(i){return i.classification!=="no_local_inputs"});
 ready.forEach(function(i){
  var row=document.createElement("p");var missing=i.imports_needed.length?
   "Import "+i.imports_needed.join(", ").replace(/_/g," "):"All raw inputs available locally";
  row.textContent=i.recipe+": "+missing;target.append(row);
 });
 if(!ready.length){var empty=document.createElement("p");empty.textContent="No recipe uses locally produced raw inputs.";target.append(empty)}
 heading(target,"Potential suppliers by road");
 profile.supplier_candidates.forEach(function(s){
  var p=document.createElement("p");p.textContent=s.resource.replace(/_/g," ")+
   " from "+s.source_name+" · "+s.route_minutes+" min overland";target.append(p);
 });
 var caution=document.createElement("p");caution.textContent=
  "Production rates are modeled capacity, not goods in stock or guaranteed exports.";
 target.append(caution);
}
function choose(index){
 var t=records[index];if(!t)return;
 if(selected)selected.classList.remove("is-selected");
 selected=svg.querySelector('#atlas-inspector-hit polygon[data-index="'+index+'"]');
 if(selected)selected.classList.add("is-selected");
 document.getElementById("selected").textContent="Hex "+t.x+", "+t.y+" · "+t.biome;
 var facts=document.getElementById("facts");facts.replaceChildren();
 [["Elevation",t.height+" m"],["Temperature",t.temp+" °C"],
 ["Annual rainfall",t.rain+" mm"],["Soil fertility",t.soil+" / 100"],
 ["Geology",t.geology],["Water",t.water],
 ["Seabed depth",t.water==="sea"?t.seabed_depth+" m":"—"],
 ["Natural land difficulty",t.natural_difficulty===null?"No land passage":t.natural_difficulty+" / 100"],
 ["Road-adjusted difficulty",t.travel_difficulty===null?"No land passage":t.travel_difficulty+" / 100"],
 ["Estimated foot time / hex",t.foot_minutes===null?"No land passage":t.foot_minutes+" minutes"],
 ["Road",t.road_surface||"No constructed road"],
 ["Watercraft suitability",t.watercraft?"Potential water route":"Not assessed as navigable water"],
 ["River flow",t.flow||"—"]].forEach(function(k){facts.append(info(k[0],k[1]))});
 tags("resources",Object.keys(t.resources).sort().map(function(k){return k.replace(/_/g," ")+" · "+t.resources[k]+"/100"}));
 var places=[];if(t.road)places.push("Road");if(t.town)places.push("Settlement: "+t.town);
 t.sites.forEach(function(s){places.push("Exploration: "+s)});
 t.landmarks.forEach(function(s){places.push("Landmark: "+s)});
 t.events.forEach(function(s){places.push("Scheduled event: "+s)});
 tags("places",places);
 townEconomy(t.town_profile);
}
var picker=document.getElementById("town-list");
records.forEach(function(rec,index){
 if(!rec.town_profile)return;
 var option=document.createElement("option");option.value=String(index);
 option.textContent=rec.town;
 picker.append(option);
});
picker.onchange=function(){
 if(picker.value==="")return;
 choose(Number(picker.value));
 // Reveal the selected hex in the scrollable map, not just its details.
 if(selected){
  var frame=map.getBoundingClientRect(),tile=selected.getBoundingClientRect();
  map.scrollLeft+=tile.left+tile.width/2-(frame.left+frame.width/2);
  map.scrollTop+=tile.top+tile.height/2-(frame.top+frame.height/2);
 }
};
svg.addEventListener("click",function(e){var p=e.target.closest("polygon[data-index]");if(p&&svg.contains(p))choose(Number(p.dataset.index))});
function zoom(next){scale=Math.max(1,Math.min(3.5,next));svg.style.width=Math.round(scale*100)+"%";document.getElementById("zoom-label").textContent=Math.round(scale*100)+"%"}
document.getElementById("zoom-in").onclick=function(){zoom(scale*1.3)};
document.getElementById("zoom-out").onclick=function(){zoom(scale/1.3)};
document.getElementById("reset").onclick=function(){zoom(1);map.scrollTop=0;map.scrollLeft=0};
map.addEventListener("wheel",function(e){if(e.ctrlKey){e.preventDefault();zoom(scale * (e.deltaY > 0 ? 0.9 : 1.1))}},{passive:false});
})();
</script></body></html>"""
    return (page.replace("__TITLE__", escape(title))
            .replace("__SEED__", str(world.seed))
            .replace("__SVG__", svg)
            .replace("__DATA__", payload))
