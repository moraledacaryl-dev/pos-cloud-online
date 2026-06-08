export function num(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function maybeParseJson(raw) {
  if (!raw) return null;
  const text = String(raw).trim();
  if (!text) return null;
  const candidate = text.startsWith('POSCFG:') ? text.slice(7).trim() : text;
  if (!candidate.startsWith('{')) return null;
  try { return JSON.parse(candidate); } catch { return null; }
}

function slug(text) {
  return String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'group';
}

function option(label, priceDelta = 0, extra = {}) {
  return { label, price_delta: priceDelta, ...extra };
}

export function getProductProfile(item) {
  const explicit = maybeParseJson(item?.notes);
  return {
    profile_key: explicit?.profile_key || slug(item?.display_name || item?.menu_item_name),
    customer_display_name: explicit?.customer_display_name || item?.display_name || item?.menu_item_name,
    prompt_note_label: explicit?.prompt_note_label || '',
    // Sellable variants and add-ons must exist as Accounting-managed SKUs so inventory follows the sale.
    modifier_groups: [],
    bundle_choices: [],
    shortcuts: [],
  };
}

export function createDefaultSelections(profile) {
  const selected = {};
  [...(profile?.modifier_groups || []), ...(profile?.bundle_choices || [])].forEach((group) => {
    if (group.mode === 'multi') { selected[group.id] = (group.options || []).filter((opt) => opt.is_default).map((opt) => opt.label); return; }
    const def = (group.options || []).find((opt) => opt.is_default) || group.options?.[0] || null;
    selected[group.id] = def?.label || '';
  });
  return { selected, custom_note: '', quantity: 1 };
}

function selectedOptionsForGroup(group, selection) {
  if (group.mode === 'multi') {
    const wanted = new Set(Array.isArray(selection) ? selection : []);
    return (group.options || []).filter((opt) => wanted.has(opt.label));
  }
  const chosen = (group.options || []).find((opt) => opt.label === selection);
  return chosen ? [chosen] : [];
}

export function buildConfiguredLine(item, profile, selectionState, localIdFactory) {
  const basePrice = num(item?.price);
  const metadata = { product_profile: profile?.profile_key || '', groups: [], bundles: [] };
  let extra = 0;
  const noteParts = [];
  [...(profile?.modifier_groups || []), ...(profile?.bundle_choices || [])].forEach((group) => {
    const selections = selectedOptionsForGroup(group, selectionState?.selected?.[group.id]);
    if (!selections.length) return;
    const labels = selections.map((opt) => opt.label);
    extra += selections.reduce((sum, opt) => sum + num(opt.price_delta), 0);
    noteParts.push(`${group.label}: ${labels.join(', ')}`);
    const target = (profile?.bundle_choices || []).some((g) => g.id === group.id) ? metadata.bundles : metadata.groups;
    target.push({ id: group.id, label: group.label, selections });
  });
  if (selectionState?.custom_note?.trim()) noteParts.push(selectionState.custom_note.trim());
  return recalcLine({ local_id: localIdFactory(), catalog_item_id: item.id, name: item.display_name, customer_display_name: profile?.customer_display_name || item.display_name, sku_code: item.sku_code, base_price: basePrice, price: Math.round((basePrice + extra) * 100) / 100, quantity: Math.max(1, num(selectionState?.quantity, 1)), note: noteParts.join(' · '), metadata, manual_discount_amount: 0, promo_discount_amount: 0, discount_amount: 0 });
}

export function recalcLine(line) {
  const manual = num(line.manual_discount_amount);
  const promo = num(line.promo_discount_amount);
  return { ...line, discount_amount: Math.round((manual + promo) * 100) / 100 };
}

export function updateLineWithDiscount(line, manualDiscount) {
  return recalcLine({ ...line, manual_discount_amount: Math.max(0, num(manualDiscount)) });
}

export function getLineTags(line) {
  const hay = `${line?.name || ''} ${line?.note || ''}`.toLowerCase();
  const tags = new Set();
  if (/(coffee|latte|tea|juice|shake|frappe|drink|cola|soda|espresso|americano|matcha|chocolate)/.test(hay)) tags.add('beverage');
  if (/(burger|sandwich|wrap|club|monte cristo)/.test(hay)) tags.add('sandwich');
  if (/(fries|chips|wedges)/.test(hay)) tags.add('side');
  if (/(silog|breakfast|tocino|longganisa|bangus|bacon|hamsilog|american breakfast|english breakfast|pancake)/.test(hay)) tags.add('breakfast');
  return tags;
}

export function getPromotionSuggestions(cart, orderType, now = new Date()) {
  return [];
}

export function applyPromotion(cart, promotion) {
  const eligibleIds = new Set(promotion.line_ids || []);
  const eligibleLines = cart.filter((line) => eligibleIds.has(line.local_id));
  if (!eligibleLines.length) return cart;
  const totalEligible = eligibleLines.reduce((sum, line) => sum + (num(line.price) * num(line.quantity)), 0);
  return cart.map((line) => {
    if (!eligibleIds.has(line.local_id)) return recalcLine({ ...line, promo_discount_amount: 0, applied_promo_code: undefined });
    let promoDiscount = 0;
    if (promotion.kind === 'percent') promoDiscount = (num(line.price) * num(line.quantity)) * num(promotion.value);
    else {
      const weight = totalEligible ? ((num(line.price) * num(line.quantity)) / totalEligible) : 0;
      promoDiscount = num(promotion.value) * weight;
    }
    return recalcLine({ ...line, promo_discount_amount: Math.round(promoDiscount * 100) / 100, applied_promo_code: promotion.code });
  });
}

export function resetPromotions(cart) {
  return cart.map((line) => recalcLine({ ...line, promo_discount_amount: 0, applied_promo_code: undefined }));
}

export function serializeCustomerDisplay({ cart, totals, guestName, tableLabel, orderType, currentOrderNo }) {
  return { updated_at: new Date().toISOString(), order_no: currentOrderNo || '', guest_name: guestName || 'Walk-in', table_label: tableLabel || orderType || '-', cart: cart.map((line) => ({ local_id: line.local_id, name: line.customer_display_name || line.name, quantity: num(line.quantity), total: Math.max((num(line.price) * num(line.quantity)) - num(line.discount_amount), 0), note: line.note || '' })), totals };
}
