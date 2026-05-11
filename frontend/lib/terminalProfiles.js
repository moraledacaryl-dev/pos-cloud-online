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
  if (explicit?.modifier_groups?.length || explicit?.bundle_choices?.length || explicit?.prompt_note_label) {
    return {
      profile_key: explicit.profile_key || slug(item?.display_name || item?.menu_item_name),
      customer_display_name: explicit.customer_display_name || item?.display_name || item?.menu_item_name,
      prompt_note_label: explicit.prompt_note_label || '',
      modifier_groups: explicit.modifier_groups || [],
      bundle_choices: explicit.bundle_choices || [],
      shortcuts: explicit.shortcuts || [],
    };
  }
  const hay = `${item?.display_name || ''} ${item?.menu_item_name || ''} ${item?.category_name || ''} ${item?.module_slug || ''}`.toLowerCase();
  const groups = [];
  const bundles = [];
  let prompt = '';
  const beverageLike = /(coffee|latte|cappuccino|mocha|frappe|tea|juice|shake|smoothie|drink|soda|cola|espresso|americano|matcha|chocolate)/.test(hay);
  const burgerLike = /(burger|sandwich|club|monte cristo|wrap)/.test(hay);
  const breakfastLike = /(silog|breakfast|tocino|longganisa|bangus|bacon|hamsilog|american breakfast|english breakfast|pancake)/.test(hay);
  const pastaLike = /(pasta|carbonara|spaghetti|marinara|bolognese)/.test(hay);
  const riceMealLike = /(rice|chicken|wings|steak|tenderloin|meal|plate|platter)/.test(hay);
  if (beverageLike) {
    groups.push({ id: 'size', label: 'Size', mode: 'single', required: true, options: [option('Regular', 0, { is_default: true }), option('Large', 30), option('Upsize', 45)] });
    groups.push({ id: 'temperature', label: 'Style', mode: 'single', required: true, options: [option('Standard', 0, { is_default: true }), option('Iced', 10), option('Less Ice', 0)] });
    groups.push({ id: 'coffee_addons', label: 'Add-ons', mode: 'multi', required: false, options: [option('Extra shot', 30), option('Oat milk', 25), option('Whipped cream', 20), option('Syrup boost', 15)] });
    prompt = 'Name or custom request';
  }
  if (burgerLike || pastaLike || riceMealLike) {
    groups.push({ id: 'addons', label: 'Kitchen Add-ons', mode: 'multi', required: false, options: [option('Cheese', 25), option('Egg', 20), option('Bacon', 35), option('Extra sauce', 15)] });
  }
  if (breakfastLike) {
    groups.push({ id: 'egg_style', label: 'Egg Style', mode: 'single', required: true, options: [option('Sunny side up', 0, { is_default: true }), option('Scrambled', 0), option('Over easy', 0)] });
    bundles.push({ id: 'breakfast_drink', label: 'Breakfast Pairing', required: false, options: [option('No pairing', 0, { is_default: true }), option('Brewed coffee', 35), option('Fresh juice', 55), option('Hot chocolate', 45)] });
    prompt = prompt || 'Special breakfast note';
  }
  if (burgerLike) {
    bundles.push({ id: 'side_pair', label: 'Pairing', required: false, options: [option('No pairing', 0, { is_default: true }), option('Fries combo', 79), option('Fries + iced tea combo', 129)] });
  }
  return { profile_key: slug(item?.display_name || item?.menu_item_name), customer_display_name: item?.display_name || item?.menu_item_name, prompt_note_label: prompt, modifier_groups: groups, bundle_choices: bundles, shortcuts: [] };
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
  const suggestions = [];
  const lines = cart.map((line) => ({ line, tags: getLineTags(line) }));
  const beverageLines = lines.filter((row) => row.tags.has('beverage'));
  const sandwichLines = lines.filter((row) => row.tags.has('sandwich'));
  const sideLines = lines.filter((row) => row.tags.has('side'));
  const breakfastLines = lines.filter((row) => row.tags.has('breakfast'));
  const hour = now.getHours();
  if (beverageLines.length && hour >= 14 && hour < 18) suggestions.push({ code: 'happy_hour_beverage', label: 'Happy Hour Beverage 10%', description: '10% off beverage lines from 2PM to 6PM.', kind: 'percent', value: 0.10, line_ids: beverageLines.map((row) => row.line.local_id), override_required: false });
  if (sandwichLines.length && sideLines.length && beverageLines.length) suggestions.push({ code: 'meal_combo_30', label: 'Meal Combo Less ₱30', description: 'Burger or sandwich with a side and a drink qualifies for ₱30 off.', kind: 'fixed', value: 30, line_ids: [sandwichLines[0].line.local_id], override_required: false });
  if (orderType === 'dine_in' && breakfastLines.length && beverageLines.length) suggestions.push({ code: 'breakfast_pair_20', label: 'Breakfast Pair Less ₱20', description: 'Breakfast plate with any drink gets ₱20 off.', kind: 'fixed', value: 20, line_ids: [breakfastLines[0].line.local_id], override_required: false });
  return suggestions;
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
