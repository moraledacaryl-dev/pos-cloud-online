'use client';

import { useEffect, useRef } from 'react';

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useDialogFocus(open, onEscape, dialogIdentity = open) {
  const escapeRef = useRef(onEscape);

  useEffect(() => {
    escapeRef.current = onEscape;
  }, [onEscape]);

  useEffect(() => {
    if (!open || typeof document === 'undefined') return undefined;
    const previouslyFocused = document.activeElement;
    const dialog = Array.from(document.querySelectorAll('[role="dialog"][aria-modal="true"]')).at(-1);
    if (!dialog) return undefined;

    const focusable = () => Array.from(dialog.querySelectorAll(FOCUSABLE)).filter((node) => !node.hidden && node.getAttribute('aria-hidden') !== 'true');
    const frame = window.requestAnimationFrame(() => (focusable()[0] || dialog).focus());
    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        escapeRef.current?.();
        return;
      }
      if (event.key !== 'Tab') return;
      const rows = focusable();
      if (!rows.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = rows[0];
      const last = rows.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', onKeyDown);
      if (previouslyFocused instanceof HTMLElement && previouslyFocused.isConnected) previouslyFocused.focus();
    };
  }, [open, dialogIdentity]);
}
