export function resolveConditionalBasePrice(item, cartItems, rules) {
  const active = (cartItems || []).filter((row) => row && row.is_active !== false && row.is_available !== false);
  const tags = new Set(active.flatMap((row) => row.pricing_tags || []));
  const prices = item.conditional_prices || [];
  const targetTags = item.pricing_tags || [];
  if (prices.length && targetTags.length) {
    const candidates = prices.flatMap((entry) => {
      const rule = (rules || []).find((row) => String(row.id) === String(entry.rule_id));
      if (!rule || rule.is_active === false || !targetTags.includes(rule.target_tag) || !tags.has(rule.qualifier_tag)) return [];
      const price = Number(entry.price);
      return Number.isFinite(price) && price >= 0 ? [{ price, priority: Number(rule.priority ?? 100), id: String(rule.id) }] : [];
    });
    candidates.sort((a, b) => a.price - b.price || a.priority - b.priority || a.id.localeCompare(b.id));
    return candidates[0]?.price ?? Number(item.price);
  }
  const hasDrink = active.some((row) => row.pricing_role === 'drink');
  return hasDrink && item.pricing_role === 'pastry' && item.with_drink_price != null ? Number(item.with_drink_price) : Number(item.price);
}
