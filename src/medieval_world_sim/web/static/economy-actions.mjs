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
          const name = root.querySelector("#economy-new-id")?.value.trim();
          const form = root.querySelector("#economy-new-id")?.closest(".economy-controls");
          if (!/^[A-Za-z][A-Za-z0-9 &'._-]{2,39}$/.test(name || "")) {
            throw Error("Use 3–40 characters for a company name; spaces are allowed");
          }
          fire("found_named_company", {
            name, industry: value(form, "industry"),
            investment: whole(form, "investment", 1),
          }, "Company founded");
          break;
        }
        case "company-product":
          fire("company_set_product", {
            company_id: companyId, product: value(company, "product"),
          }, "Company production updated");
          break;
        case "company-hiring": {
          const business = (ctx.getState().economy?.owned || [])
            .find(c => c.id === companyId);
          if (!business) throw Error("Not your company");
          fire("company_set_hiring", {
            company_id: companyId, hiring: !business.hiring
          }, "Hiring availability updated");
          break;
        }
        case "company-apply":
        case "company-withdraw-application":
          fire(name === "company-apply" ? "company_apply" :
            "company_withdraw_application", {
            company_id: companyId
          }, name === "company-apply" ? "Application submitted" :
            "Application withdrawn");
          break;
        case "company-list-for-sale":
          fire("company_list_for_sale", {
            company_id: companyId, price: whole(company, "sale-price", 1)
          }, "Company listed for sale");
          break;
        case "company-cancel-sale":
          fire("company_list_for_sale", {
            company_id: companyId, price: 0
          }, "Company listing canceled");
          break;
        case "company-buy": {
          const listing = (ctx.getState().economy?.directory || [])
            .find(c => c.id === companyId);
          if (!listing || !listing.can_buy) throw Error("Company purchase unavailable");
          ctx.confirmAction({
            title: "Buy " + listing.name + "?",
            description: "Pay " + listing.sale_price +
              " gold to acquire this company, including its assets and employment agreements.",
            button: "Buy company", command: "company_buy",
            params: {company_id:companyId}, success: "Company purchased"
          });
          break;
        }
        case "company-dissolve": {
          const companyName = (ctx.getState().economy?.owned || [])
            .find(c => c.id === companyId)?.name || companyId;
          ctx.confirmAction({
            title: "Dissolve " + companyName + "?",
            description: "Close the company and release its employees. " +
              "All treasury gold, goods, equipment and market listings will be returned to you. This cannot be undone.",
            button: "Dissolve company", command: "company_dissolve",
            params: {company_id:companyId}, success: "Company dissolved"
          });
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
