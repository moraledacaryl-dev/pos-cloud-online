'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';

function ensureDialogName(dialog, index) {
  if (dialog.hasAttribute('aria-label') || dialog.hasAttribute('aria-labelledby')) return;
  const heading = dialog.querySelector('h1, h2, h3');
  if (heading) {
    if (!heading.id) heading.id = `pos-dialog-title-${index}`;
    dialog.setAttribute('aria-labelledby', heading.id);
    return;
  }
  dialog.setAttribute('aria-label', 'Dialog');
}

function ensureSelectName(select) {
  if (select.labels?.length || select.hasAttribute('aria-label') || select.hasAttribute('aria-labelledby')) return;
  const optionText = Array.from(select.options || []).map((option) => option.textContent?.trim().toLowerCase() || '');
  if (optionText.includes('all items') || optionText.includes('available only')) {
    select.setAttribute('aria-label', 'Availability filter');
    return;
  }
  if (optionText.includes('verified close') || optionText.includes('blind close')) {
    select.setAttribute('aria-label', 'Close mode');
    return;
  }
  select.setAttribute('aria-label', 'Selection');
}

function ensureTableHeaderNames() {
  document.querySelectorAll('th').forEach((header) => {
    if (!header.textContent?.trim() && !header.hasAttribute('aria-label')) {
      header.setAttribute('aria-label', 'Actions');
    }
  });
}

function ensureTerminalSemantics() {
  const terminalMain = document.querySelector('main.terminal-main');
  if (terminalMain && !terminalMain.querySelector('h1')) {
    const heading = document.createElement('h1');
    heading.className = 'sr-only';
    heading.textContent = 'Point of Sale';
    heading.setAttribute('data-accessibility-heading', 'true');
    terminalMain.prepend(heading);
  }

  document.querySelectorAll('main.order-items-panel').forEach((panel) => {
    panel.setAttribute('role', 'region');
    if (!panel.hasAttribute('aria-label') && !panel.hasAttribute('aria-labelledby')) {
      panel.setAttribute('aria-label', 'Menu items');
    }
  });
}

function ensureScrollableRegions() {
  const candidates = document.querySelectorAll('.table, .cart-lines-box, .section');
  candidates.forEach((element) => {
    const style = window.getComputedStyle(element);
    const horizontal = element.scrollWidth > element.clientWidth + 1 && ['auto', 'scroll'].includes(style.overflowX);
    const vertical = element.scrollHeight > element.clientHeight + 1 && ['auto', 'scroll'].includes(style.overflowY);
    if (!horizontal && !vertical) return;

    if (!element.hasAttribute('tabindex')) element.setAttribute('tabindex', '0');
    if (!element.hasAttribute('aria-label') && !element.hasAttribute('aria-labelledby')) {
      element.setAttribute('aria-label', element.matches('table') ? 'Scrollable data table' : 'Scrollable content');
    }
    if (horizontal && element.scrollLeft !== 0) element.scrollLeft = 0;
  });
}

function applyAccessibilityRepairs() {
  ensureTerminalSemantics();
  ensureTableHeaderNames();
  document.querySelectorAll('[role="dialog"]').forEach(ensureDialogName);
  document.querySelectorAll('select').forEach(ensureSelectName);
  ensureScrollableRegions();
}

export default function AccessibilityRuntime() {
  const pathname = usePathname();

  useEffect(() => {
    let frame = 0;
    const schedule = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        applyAccessibilityRepairs();
      });
    };

    schedule();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', schedule);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', schedule);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [pathname]);

  return null;
}
