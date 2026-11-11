"""Offline, self-contained historical atlas with an era scrubber.

This overlays the same actual terrain/river SVG as the geographical atlas;
historical towns, roads and ruin markers are temporal layers. It never exposes
these synthetic histories as a live, authoritative multiplayer world state.
"""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json

from .hexgrid import center
from .render import MARGIN, TILE_PX, TOP, render_svg

_COLORS = ("#edb977", "#84b4b0", "#b59dc6", "#d18d86", "#9fb67d",
           "#d5bb80", "#82a2d6", "#caa59b", "#a3b9ad", "#d49db1")


def render_history_html(world, svg: str | None = None) -> str:
    """Make a locally openable historical survey with six inspectable eras."""
    if world.history is None:
        raise ValueError("Generate a world history before rendering its atlas")
    if svg is None:
        svg = render_svg(world)
    route_svg = []
    for i, route in enumerate(world.roads):
        pts = " ".join(f"{center(x, y, TILE_PX)[0]:.1f},"
                       f"{center(x, y, TILE_PX)[1]:.1f}" for x, y in route.path)
        route_svg.append(
            f'<polyline id="historic-route-{i}" data-a="{escape(route.a)}" '
            f'data-b="{escape(route.b)}" points="{pts}" fill="none" '
            'stroke-linecap="round" stroke-linejoin="round" opacity=".85" '
            'stroke="#aa7d4b" stroke-width="2.5" visibility="hidden"/>')
    cities = []
    for town in world.settlements:
        x, y = center(town.x, town.y, TILE_PX)
        cities.append(
            f'<g class="historic-town" data-id="{escape(town.id)}" '
            'visibility="hidden" tabindex="0" role="button" '
            f'aria-label="{escape(town.name)}">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" '
            'stroke="#473a2a" stroke-width="1.5" fill="#edb977"/>'
            f'<text x="{x+9:.1f}" y="{y-8:.1f}" font-size="12" '
            'font-family="Georgia,serif" font-weight="bold" fill="#2c302a" '
            'paint-order="stroke" stroke="#f0e6cf" stroke-width="3.2">'
            f'{escape(town.name)}</text></g>')
    ruins = []
    for ruin in world.history.ruins:
        x, y = center(ruin.x, ruin.y, TILE_PX)
        ruins.append(
            f'<path class="historic-ruin" data-id="{escape(ruin.id)}" '
            f'd="M{x:.1f},{y-5:.1f}L{x+5:.1f},{y:.1f}L{x:.1f},{y+5:.1f}'
            f'L{x-5:.1f},{y:.1f}Z" visibility="hidden" '
            'fill="#704c69" stroke="#f9e2c2" stroke-width="1.2" '
            'tabindex="0" role="button">'
            f'<title>{escape(ruin.name)}: {escape(ruin.cause)}</title></path>')
    layers = (f'<g id="historical-overlays" transform="translate({MARGIN},{TOP})">'
              '<g id="historic-road-layer" pointer-events="none">'
              + "".join(route_svg) + '</g>'
              '<g id="historic-ruin-layer">' + "".join(ruins) + '</g>'
              '<g id="historic-town-layer">' + "".join(cities) + '</g></g>')
    if not svg.rstrip().endswith("</svg>"):
        raise ValueError("The historical atlas needs a complete SVG map")
    svg = svg.rstrip()[:-6] + layers + "</svg>"
    history = asdict(world.history)
    data = {
        "eras": history["eras"], "ruins": history["ruins"],
        "colors": _COLORS, "seed": world.seed,
    }
    encoded = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e")
    html = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Oathmere · Historical Survey · Seed __SEED__</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Segoe UI,sans-serif}
*{box-sizing:border-box}body{background:#161e22;color:#ede8d9;margin:0}
main{display:grid;grid-template-columns:minmax(0,1fr) 365px;gap:12px;
padding:14px;max-width:1900px;margin:0 auto}
#historical-map{overflow:auto;max-height:calc(100vh - 28px);
border-radius:9px;border:1px solid #51645c;background:#345047}
#historical-map svg{width:100%;height:auto;min-width:650px;display:block}
#historical-map #road-network,#historical-map #settlements,
#historical-map #exploration-sites{display:none}
#historical-map .historic-town,#historical-map .historic-ruin{cursor:pointer}
#historical-map .historic-town:hover circle,#historical-map .historic-ruin:hover{
stroke:#fff5a3;stroke-width:3}
aside{background:#212b2b;border:1px solid #4f5c51;border-radius:9px;
padding:15px 18px;max-height:calc(100vh - 28px);overflow:auto}
h1{font:normal 24px Georgia,serif;margin:0 0 6px;color:#f5ddb4}
h2{font:normal 21px Georgia,serif;margin:14px 0 8px;color:#f0c98f}
h3{font-size:14px;margin:17px 0 8px;color:#f3d8aa}
p{font-size:13px;color:#c5cfc6;line-height:1.5}
label{font-size:12px;color:#c5d1c7}
select,button{background:#364c49;color:#f6ead6;border:1px solid #71887d;
border-radius:5px;padding:9px 12px;font:inherit;cursor:pointer}
button{min-width:45px}
.controls{display:flex;gap:7px;align-items:center;margin:14px 0}
.controls select{flex:1;min-width:0}
.statline{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;
margin:12px 0}
.stat{border:1px solid #4b6059;border-radius:5px;padding:9px 6px}
.stat b{display:block;font-size:18px;color:#fae3b9}
.stat small{font-size:10px;color:#bfcdc3}
#polities{display:flex;flex-wrap:wrap;gap:5px}
.pill{border-radius:6px;padding:5px 8px;background:#31403e;font-size:11px}
.pill i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
.event{border-top:1px solid #435750;padding:10px 0}
.event b{color:#f1d49c;font-size:13px}
.event span{font-size:10px;color:#b1c2b6;margin-left:6px;text-transform:uppercase}
.event p{margin:5px 0 0}
#detail{padding:10px;margin-top:8px;background:#34423d;border-radius:5px;
font-size:12px;line-height:1.55}
#detail strong{color:#eac68f}
a{color:#c6d9ce}
.note{font-size:11px;line-height:1.5;color:#aebbb1}
@media(max-width:890px){
main{grid-template-columns:1fr}#historical-map{height:55vh}aside{max-height:none}}
</style></head><body>
<main><div id="historical-map">__SVG__</div><aside>
<h1>The Chronicle of Oathmere</h1>
<p>Seed __SEED__ · Settlements and cultures emerge from climate, fertile valleys,
resources, trade corridors, mountain passes and political influence.</p>
<label for="era">Historical era</label>
<div class="controls">
<button id="prior-era" title="Previous era" type="button">‹</button>
<select id="era"></select>
<button id="next-era" title="Next era" type="button">›</button></div>
<h2 id="era-heading"></h2>
<p id="era-description"></p>
<div class="statline">
<div class="stat"><b id="pop-stat">—</b><small>Estimated people</small></div>
<div class="stat"><b id="town-stat">—</b><small>Settled towns</small></div>
<div class="stat"><b id="route-stat">—</b><small>Trade corridors</small></div></div>
<h3>Political centers</h3><div id="polities"></div>
<h3>Selected place</h3><div id="detail">Click a historic town or abandoned site on the atlas.</div>
<h3>Events of this era</h3><div id="events"></div>
<p class="note">All historical populations, political boundaries and trade indices
are reproducible design estimates, not the live world's saved citizens, gold,
kingdoms or physical roads. Earlier roads follow geographically feasible
corridors, not excavated archaeological evidence.</p>
<p><a href="atlas.html">Open the geographic hex inspector</a></p>
</aside></main>
<script id="chronicle-json" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
var data=JSON.parse(document.getElementById("chronicle-json").textContent);
var sel=document.getElementById("era");
var root=document.querySelector("#historical-map svg");
var towns=Array.from(root.querySelectorAll(".historic-town"));
var roads=Array.from(root.querySelectorAll("#historic-road-layer polyline"));
var ruins=Array.from(root.querySelectorAll(".historic-ruin"));
var current=data.eras.length-1;
var colors=data.colors;
data.eras.forEach(function(era,i){
 var opt=document.createElement("option");
 opt.value=String(i);opt.textContent="Year "+era.year+" · "+era.name;sel.append(opt);
});
function make(tag,klass,content){
 var el=document.createElement(tag);if(klass)el.className=klass;
 if(content!==undefined)el.textContent=content;return el;
}
function showDetail(title,detail){
 var div=document.getElementById("detail");div.replaceChildren();
 div.append(make("strong",null,title),document.createElement("p"));
 div.lastChild.textContent=detail;
}
function update(index){
 current=Math.max(0,Math.min(data.eras.length-1,index));
 sel.value=String(current);
 var era=data.eras[current];
 document.getElementById("era-heading").textContent=era.name+" · "+era.year;
 document.getElementById("era-description").textContent=
  "Review the people, routes and political centers present by this year.";
 document.getElementById("pop-stat").textContent=
  era.towns.reduce(function(n,t){return n+t.population},0).toLocaleString();
 document.getElementById("town-stat").textContent=String(era.towns.length);
 document.getElementById("route-stat").textContent=String(era.roads.length);
 var lookup={};era.towns.forEach(function(t){lookup[t.id]=t});
 var members={};era.polities.forEach(function(p,i){members[p.id]=colors[i%colors.length]});
 towns.forEach(function(g){
  var town=lookup[g.dataset.id];g.setAttribute("visibility",town?"visible":"hidden");
  if(!town)return;
  g.querySelector("circle").setAttribute("r",
    String(Math.min(11,4+Math.sqrt(town.population)/8)));
  g.querySelector("circle").setAttribute("fill",members[town.polity_id]||colors[0]);
  g.dataset.description=town.population.toLocaleString()+" people · "+
   town.status+" · Food security "+town.food_security+
   "/100 · Trade "+town.trade_volume+" · "+
   (era.polities.find(function(p){return p.id===town.polity_id})||{name:"Independent"}).name;
 });
 var active={};
 era.roads.forEach(function(r){active[[r.a,r.b].sort().join("|")]=r});
 roads.forEach(function(line){
  var key=[line.dataset.a,line.dataset.b].sort().join("|");
  var road=active[key];line.setAttribute("visibility",road?"visible":"hidden");
  if(!road)return;
  line.setAttribute("stroke",road.surface==="cobblestone"?"#f4e0bf":
    road.surface==="dirt"?"#d6a46a":"#977c60");
  line.setAttribute("stroke-dasharray",road.surface==="trail"?"3 5":"none");
  line.setAttribute("stroke-width",String(Math.min(5,2+road.trade_volume/22)));
 });
 var older=data.ruins.filter(function(r){return r.abandoned_year<=era.year});
 var vanished={};older.forEach(function(r){vanished[r.id]=r});
 ruins.forEach(function(path){
  var r=vanished[path.dataset.id];
  path.setAttribute("visibility",r?"visible":"hidden");
 });
 var political=document.getElementById("polities");political.replaceChildren();
 era.polities.forEach(function(p,i){
  var pill=make("div","pill"),dot=make("i"),title=make("span",null,p.name);
  dot.style.background=colors[i%colors.length];
  pill.append(dot,title);political.append(pill);
 });
 var events=document.getElementById("events");events.replaceChildren();
 era.events.forEach(function(e){
  var block=make("div","event"),title=make("b",null,e.title);
  var category=make("span",null,e.kind),description=make("p",null,e.account);
  block.append(title,category,description);events.append(block);
 });
 if(!era.events.length)events.append(make("p",null,"No recorded turning points in this era."));
 document.getElementById("detail").textContent=
  "Select a colored historic town or purple abandoned site to inspect its past.";
}
function clickMarker(event){
 var town=event.target.closest(".historic-town");
 if(town){
  var t=data.eras[current].towns.find(function(x){return x.id===town.dataset.id});
  if(t)showDetail(t.name,town.dataset.description);
  return;
 }
 var marker=event.target.closest(".historic-ruin");
 if(marker){
  var ruin=data.ruins.find(function(x){return x.id===marker.dataset.id});
  if(ruin&&ruin.abandoned_year<=data.eras[current].year){
   showDetail(ruin.name,"Former "+ruin.former_use+" · abandoned in year "+
    ruin.abandoned_year+". "+ruin.cause);
  }
 }
}
root.addEventListener("click",clickMarker);
root.addEventListener("keydown",function(e){
 if(e.key==="Enter"||e.key===" "){clickMarker(e);e.preventDefault()}
});
document.getElementById("prior-era").onclick=function(){update(current-1)};
document.getElementById("next-era").onclick=function(){update(current+1)};
sel.onchange=function(){update(Number(sel.value))};
update(current);
})();
</script></body></html>"""
    return (html.replace("__SEED__", str(world.seed))
            .replace("__SVG__", svg).replace("__DATA__", encoded))
