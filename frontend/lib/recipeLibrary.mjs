export const MAX_RECIPE_PDF_BYTES = 15 * 1024 * 1024;

export function validateRecipePdfFile(file) {
  if (!file) return 'Choose a PDF file to upload.';
  if (!String(file.name || '').toLowerCase().endsWith('.pdf')) return 'Choose a PDF file.';
  if (file.type && file.type !== 'application/pdf') return 'Choose a PDF file.';
  if (Number(file.size || 0) > MAX_RECIPE_PDF_BYTES) return 'Recipe PDF must be 15 MB or smaller.';
  return '';
}

export function filterRecipeDishes(rows, { q = '', category = 'all', status = 'all' } = {}) {
  const needle = String(q || '').trim().toLowerCase();
  return (Array.isArray(rows) ? rows : []).filter((row) => {
    if (category !== 'all' && (row.category_name || 'Uncategorized') !== category) return false;
    if (status === 'with_pdf' && !row.recipe) return false;
    if (status === 'missing_pdf' && row.recipe) return false;
    if (!needle) return true;
    return [
      row.dish_name,
      row.category_name,
      row.module_slug,
      ...(Array.isArray(row.variants) ? row.variants : []),
    ].filter(Boolean).join(' ').toLowerCase().includes(needle);
  });
}
