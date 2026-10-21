const paths = {
  terminal: ['M4 4h16v12H4z', 'M8 20h8M12 16v4', 'M8 8h8M8 12h4'],
  orders: ['M6 3h12v18l-3-2-3 2-3-2-3 2z', 'M9 7h6M9 11h6M9 15h3'],
  shift: ['M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9', 'M12 7v5l3 2'],
  cash: ['M3 6h18v12H3z', 'M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0', 'M6 12h.01M18 12h.01'],
  sync: ['M20 7h-5V2M4 17h5v5', 'M20 7a9 9 0 0 0-15-2M4 17a9 9 0 0 0 15 2'],
  menu: ['M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z'],
  coffee: ['M4 8h12v7a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z', 'M16 9h2a3 3 0 0 1 0 6h-2M3 22h16M7 2v3M12 2v3'],
  drink: ['M6 8h12l-2 14H8z', 'M12 8l2-6h5M7 12h10'],
  food: ['M4 15a8 8 0 0 1 16 0M2 18h20M12 5V3M10 3h4'],
  dessert: ['M4 10l15-6v15H4z', 'M4 15h15M19 4c0-2-4-2-4 0'],
  arrow: ['M5 12h14M13 6l6 6-6 6'],
};
export function menuIcon(category = '') {
  const name = String(category || '').toLowerCase();
  if (/coffee|espresso|latte|tea/.test(name)) return 'coffee';
  if (/drink|juice|cooler|beverage/.test(name)) return 'drink';
  if (/dessert|cake|pastry|sweet/.test(name)) return 'dessert';
  return 'food';
}
export default function PosIcon({ name = 'terminal', className = '' }) {
  return <svg className={`pos-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{(paths[name] || paths.terminal).map(path => <path key={path} d={path} />)}</svg>;
}
