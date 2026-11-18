import assert from "node:assert/strict";
import { createEconomyViews } from "../src/medieval_world_sim/web/static/economy-views.mjs";
import { createEconomyActions } from "../src/medieval_world_sim/web/static/economy-actions.mjs";

const actor = "hero";
const state = {
  actor_id: actor, player: { city: "crownreach",
    work: { manual: 12, intelligence: 14, endurance: 10, shifts: 2 } },
  gear: [{id: 7, kind: "sword", quality: 77}],
  economy: {
    industries: [{id:"bakery",inputs:{grain:2},outputs:{bread:3}}],
    goods: ["bread", "grain"],
    owned: [{
      id:"river_bakery",city:"crownreach",industry:"bakery",gold:120,
      inventory:{bread:3},equipment:[],employees:[],job_offers:[],
      facility_level:1,shifts_completed:1,perks:[],
      quality:{effectiveness:45,stars:3},daily_revenue:10,daily_units_sold:2,
      can_manage:true,
    }],
    candidates:[{id:"hero",name:"Hero"}],
    jobs:[{company_id:"river_bakery",industry:"bakery",city:"crownreach",
      wage:{gold:3,item:null,quantity:0},can_shift:true,ready_minutes:0}],
    job_offers:[],
    listings:[{id:5,seller_id:"other",seller:"Other player",
      company:false,item:"bread",quantity:2,unit_price:7,
      gear_id:null,can_cancel:false}],
    market_sources:[{id:"hero",name:"My inventory"},
      {id:"river_bakery",name:"river_bakery (company)"}],
  },
};

const enc = x => String(x ?? "").replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;").replaceAll('"', "&quot;");
const ctx = {
  getState: () => state, esc:enc,
  pretty: x => String(x).replaceAll("_", " "),
  money:x=>String(x)+" g",
  button:(title, attrs)=>'<button '+attrs+'>'+enc(title)+'</button>',
  disabled:flag=>flag?" disabled":"",
  isBusy:()=>false,
  heading:(_,title)=>'<h2>'+title+'</h2>',
  panel:(title,_,body)=>'<section><h3>'+title+'</h3>'+body+'</section>',
};
const views = createEconomyViews(ctx);
assert.match(views.renderCompanies(), /river_bakery/);
assert.match(views.renderCompanies(), /company-stock/);
assert.match(views.renderCompanies(), /job-offer/);
assert.match(views.renderEmployment(), /Work shift/);
assert.match(views.renderEmployment(), /<div class="stack">/);
assert.match(views.renderStalls(), /Player market/);
assert.match(views.renderStalls(), /Other player/);
assert.match(views.renderStalls(), /listing-buy/);

// A pure input dispatcher receives no credentials and only submits a vetted
// command shape to the existing authenticated action() helper.
const sent=[];
const actions=createEconomyActions({
  getState:()=>state,
  getRoot:()=>({querySelector:()=>null}),
  action:(name,params)=>sent.push({name,params}),
  notify:()=>{throw Error("Unexpected notification");},
});
const target=(econ,company)=>({
  dataset:{econ,company},closest:()=>null,
});
assert.equal(actions.handleEconomyClick(target("job-shift","river_bakery")),true);
assert.deepEqual(sent.pop(),{name:"shift",params:{company_id:"river_bakery"}});
assert.equal(actions.handleEconomyClick(target("job-accept","river_bakery")),true);
assert.deepEqual(sent.pop(),{name:"accept_job",params:{company_id:"river_bakery"}});
assert.equal(actions.handleEconomyClick(target("unhandled","river_bakery")),false);
console.log("Economy views and delegated action handling passed");
