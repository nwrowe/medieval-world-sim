import assert from "node:assert/strict";
import { createWildernessViews } from "../src/medieval_world_sim/web/static/wilderness-views.mjs";

const world = {
  started:true,
  player:{destination:null,stamina:17},
  wilderness:{
    x:4,y:5,biome:"forest",geology:"metamorphic",
    elevation_m:410,river:false,stamina:17,
    gather_cost:{"1":3,"2":5},
    resources:[{item:"timber",potential:90,available:5},
      {item:"herbs",potential:75,available:0}],
    sites:[{id:"site-007",name:"Forgotten Shrine",kind:"forest_shrine",
      danger:3,clue:"old growth trees",resolved:null,
      choices:[{id:"survey",label:"Survey from safety",stamina:2,chance:80,available:true},
        {id:"scavenge",label:"Search for supplies",stamina:4,chance:65,available:true},
        {id:"delve",label:"Explore the depths",stamina:7,chance:55,available:true}]}],
  },
};
const fired=[];
let renders=0;
const ctx={
  getState:()=>world,
  action:(name,params)=>fired.push({name,params}),
  render:()=>{renders++;},
  isBusy:()=>false,
  pretty:x=>String(x).replaceAll("_"," "),
  esc:x=>String(x??"").replaceAll("&","&amp;").replaceAll("<","&lt;")
    .replaceAll('"',"&quot;"),
  disabled:x=>x?" disabled":"",
  button:(title,attrs)=>'<button '+attrs+'>'+title+'</button>',
  panel:(name,desc,content)=>'<section><h2>'+name+'</h2><p>'+desc+
    '</p>'+content+'</section>',
};
const views=createWildernessViews(ctx);
assert.match(views.renderWilderness(),/forest/i);
assert.match(views.renderWilderness(),/Local potential: 90/);
assert.match(views.renderWilderness(),/Gather 1 · 3 stamina/);
assert.match(views.renderWilderness(),/Forgotten Shrine/);
assert.match(views.renderWilderness(),/Go around · free/);
assert.match(views.renderWilderness(),/Survey from safety/);
assert.match(views.renderWilderness(),/data-wilderness="investigate"/);
views.handleWildernessClick({dataset:{wilderness:"gather",item:"timber",quantity:"2"}});
assert.deepEqual(fired.pop(),{name:"wilderness_gather",params:{item:"timber",quantity:2}});
views.handleWildernessClick({dataset:{wilderness:"investigate",
  siteId:"site-007",approach:"delve"}});
assert.deepEqual(fired.pop(),{name:"investigate_site",
  params:{site_id:"site-007",approach:"delve"}});
views.handleWildernessClick({dataset:{wilderness:"bypass",siteId:"site-007"}});
assert.equal(renders,1);
assert.match(views.renderWilderness(),/passed by without spending stamina/);
assert.doesNotMatch(views.renderWilderness(),/data-wilderness="investigate"/);
views.handleWildernessClick({dataset:{wilderness:"reconsider",siteId:"site-007"}});
assert.equal(renders,2);
assert.match(views.renderWilderness(),/Explore the depths/);
world.wilderness.sites[0].resolved={
  approach:"scavenge",success:true,item:"herbs",quantity:2,damage:0};
assert.match(views.renderWilderness(),/Already investigated/);
assert.doesNotMatch(views.renderWilderness(),/data-wilderness="investigate"/);
world.player.destination="crownreach";
assert.equal(views.renderWilderness(),"");
console.log("Wilderness optional-site view and action routing passed");
