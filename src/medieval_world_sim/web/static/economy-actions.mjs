/* Browser command adapter for the civilian economy.
 * The only authority is the authenticated server command. This module
 * validates input shape for UX and never computes wealth or ownership.
 */
export function createEconomyActions(ctx) {
  const find = (scope, field) =>
    scope && scope.querySelector('[data-econ-field="' + field + '"]');
  const value = (scope, field) => {
    const el = find(scope, field);
    return el ? String(el.value) : "";
  };
  const whole = (scope, field, min = 0, max = 1000000000) => {
    const raw = value(scope, field);
    if (!/^(0|[1-9]\d*)$/.test(raw)) throw Error("Enter a nonnegative whole number");
    const num = Number(raw);
    if (!Number.isSafeInteger(num) || num < min || num > max) {
      throw Error("Amount is outside the allowed range");
    }
    return num;
  };
  const fire = (name, params, message) => {
    ctx.action(name, params, message);
  };

  function handleEconomyClick(element) {
    const name = element && element.dataset.econ;
    if (!name) return false;
    try {
      const root = ctx.getRoot();
      const company = element.closest("[data-econ-company]");
      const companyId = element.dataset.company ||
        (company && company.dataset.econCompany);
      const listingForm = root.querySelector('[data-econ-listing="true"]');
      const stalls = root.querySelector(".economy-buyer");
      const actorId = ctx.getState().actor_id || "hero";
      switch (name) {
        case "company-found": {
          const slug = root.querySelector("#economy-new-id")?.value.trim();
          const form = root.querySelector("#economy-new-id")?.closest(".economy-controls");
          if (!/^[a-z][a-z0-9_-]{2,31}$/.test(slug || "")) {
            throw Error("Use 3–32 lowercase letters, numbers, _ or - for the company ID");
          }
          fire("found_company", {
            company_id: slug, industry: value(form, "industry"),
            investment: whole(form, "investment", 1),
          }, "Company founded");
          break;
        }
        case "company-fund":
        case "company-withdraw":
          fire(name === "company-fund" ? "company_deposit_gold" :
            "company_withdraw_gold", {
            company_id: companyId, amount: whole(company, "gold-amount", 1),
          }, "Company treasury updated");
          break;
        case "company-stock":
        case "company-unstock":
          fire(name === "company-stock" ? "company_deposit_goods" :
            "company_withdraw_goods", {
            company_id: companyId, item: value(company, "goods-item"),
            quantity: whole(company, "goods-quantity", 1, 10000),
          }, "Company inventory updated");
          break;
        case "company-stock-gear":
        case "company-take-gear":
          fire(name === "company-stock-gear" ? "company_deposit_gear" :
            "company_withdraw_gear", {
            company_id: companyId, gear_id: whole(company,
              name === "company-stock-gear" ? "personal-gear" : "company-gear", 1),
          }, "Company equipment updated");
          break;
        case "job-offer":
          fire("offer_job", {
            company_id: companyId,
            worker_id: value(company, "worker-id"),
            gold: whole(company, "offer-gold"),
            item: value(company, "offer-item"),
            quantity: whole(company, "offer-quantity", 0, 10000),
          }, "Employment offer sent");
          break;
        case "job-wage": {
          const row = element.closest("[data-econ-staff]");
          fire("change_job_wage", {
            company_id: companyId, worker_id: element.dataset.worker,
            gold: whole(row, "wage-gold"),
            item: value(row, "wage-item"),
            quantity: whole(row, "wage-quantity", 0, 10000),
          }, "Employment wages updated");
          break;
        }
        case "job-accept":
        case "job-leave":
        case "job-shift":
          fire(name === "job-accept" ? "accept_job" :
            name === "job-leave" ? "leave_job" : "shift", {
            company_id: companyId,
          }, name === "job-accept" ? "Employment accepted" :
            name === "job-leave" ? "Employment ended" : "Shift completed and wages paid");
          break;
        case "company-perks":
          fire("set_perks", {
            company_id: companyId,
            perks: [...company.querySelectorAll("[data-econ-perk]:checked")]
              .map(x => x.dataset.econPerk),
          }, "Company benefits updated");
          break;
        case "company-upgrade":
          fire("upgrade_facility", { company_id: companyId }, "Company facility upgraded");
          break;
        case "list-goods":
          fire("post_offer", {
            seller_id: value(listingForm, "seller"),
            item: value(listingForm, "listing-item"),
            quantity: whole(listingForm, "listing-quantity", 1, 10000),
            unit_price: whole(listingForm, "listing-price", 1),
          }, "Goods listed in market escrow");
          break;
        case "list-gear":
          fire("post_equipment_offer", {
            seller_id: value(listingForm, "seller"),
            gear_id: whole(listingForm, "listing-gear", 1),
            unit_price: whole(listingForm, "listing-price", 1),
          }, "Equipment listed in market escrow");
          break;
        case "listing-buy": {
          const row = element.closest("[data-econ-listing-id]");
          fire("accept_offer", {
            buyer_id: value(stalls, "buyer") || actorId,
            offer_id: Number(element.dataset.offerId),
            quantity: whole(row, "buy-quantity", 1, 10000),
          }, "Market purchase settled");
          break;
        }
        case "listing-cancel":
          fire("cancel_offer", {
            offer_id: Number(element.dataset.offerId),
          }, "Market listing canceled; escrow returned");
          break;
        default:
          return false;
      }
    } catch (err) {
      ctx.notify(err.message || "Invalid economy action", true);
    }
    return true;
  }
  return { handleEconomyClick };
}
