/* Small, selective tooltips for ambiguous icons and clipped content. */
(() => {
    'use strict';
    if (!('showPopover' in HTMLElement.prototype)) return;
    const selector = '[title], [data-tooltip], .icon-button[aria-label], .ui-hint > summary';
    const tooltip = document.createElement('div');
    tooltip.id = 'workspace-tooltip';
    tooltip.className = 'context-popover ui-tooltip';
    tooltip.popover = 'manual';
    tooltip.setAttribute('role', 'tooltip');
    document.body.append(tooltip);
    let active = null;
    let pending = null;
    let showTimer = null;
    let hideTimer = null;
    let hovered = false;
    let closingDialog = false;
    let keyboardFocus = false;
    const clipped = (control) => control.scrollWidth > control.clientWidth + 1 || control.scrollHeight > control.clientHeight + 1;

    const eligible = (control) => {
        if (control.matches('.shortcut-close, .keyboard-help-trigger, [data-no-tooltip]')) return false;
        if (control.matches('.ui-hint > summary')) return true;
        if (control.dataset.tooltip) return control.dataset.tooltipClipped !== 'true' || clipped(control);
        if (control.matches('.icon-button[aria-label]')) {
            return !control.closest('.control-popover') && !/^(close|search|apply|clear|choose|previous|next|first page|last page)/i.test(control.getAttribute('aria-label'));
        }
        return control.hasAttribute('title') && !control.matches('a, button, input, summary');
    };

    const prepare = (control) => {
        if (control.hasAttribute('title')) {
            if (!control.matches('a, button, input, select, textarea, summary, .icon-button[aria-label]') && !control.dataset.tooltip) {
                control.dataset.tooltip = control.getAttribute('title');
                control.dataset.tooltipClipped = 'true';
            } else if (eligible(control) && !control.dataset.tooltip) control.dataset.tooltip = control.getAttribute('title');
            control.removeAttribute('title');
        }
        return control;
    };
    document.querySelectorAll(selector).forEach(prepare);
    const label = (control) => {
        const hint = control.closest('.ui-hint')?.querySelector('.ui-hint-content');
        const text = hint?.textContent.trim() || control.dataset.tooltip || control.getAttribute('aria-label');
        return text?.length > 140 ? `${text.slice(0, 137).trim()}…` : text;
    };
    const hide = () => {
        clearTimeout(showTimer);
        clearTimeout(hideTimer);
        pending = null;
        if (tooltip.matches(':popover-open')) tooltip.hidePopover();
        if (active) {
            const ids = (active.getAttribute('aria-describedby') || '').split(/\s+/).filter((id) => id && id !== tooltip.id);
            if (ids.length) active.setAttribute('aria-describedby', ids.join(' '));
            else active.removeAttribute('aria-describedby');
        }
        active = null;
        hovered = false;
    };
    const show = (control) => {
        hide();
        if (!eligible(control) || !control.isConnected || !control.getClientRects().length || control.getAttribute('aria-expanded') === 'true') return;
        const text = label(control);
        if (!text) return;
        active = control;
        tooltip.textContent = text;
        (control.closest('dialog[open]') || document.body).append(tooltip);
        tooltip.showPopover();
        const box = control.getBoundingClientRect();
        const rect = tooltip.getBoundingClientRect();
        const below = box.bottom + 7;
        tooltip.style.left = `${Math.max(12, Math.min(box.left + (box.width - rect.width) / 2, innerWidth - rect.width - 12))}px`;
        tooltip.style.top = `${Math.max(12, Math.min(below + rect.height <= innerHeight - 12 ? below : box.top - rect.height - 7, innerHeight - rect.height - 12))}px`;
        const ids = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        ids.add(tooltip.id);
        control.setAttribute('aria-describedby', [...ids].join(' '));
    };
    const scheduleHide = () => {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            if (!hovered && (!keyboardFocus || document.activeElement !== active)) hide();
        }, 160);
    };
    document.addEventListener('pointerover', (event) => {
        if (event.pointerType === 'touch') return;
        const control = event.target.closest(selector);
        if (!control || !eligible(control) || control.contains(event.relatedTarget) || active === control || pending === control) return;
        clearTimeout(showTimer);
        prepare(control);
        pending = control;
        showTimer = setTimeout(() => show(control), 300);
    });
    document.addEventListener('pointerout', (event) => {
        const control = event.target.closest(selector);
        if (!control || control.contains(event.relatedTarget)) return;
        clearTimeout(showTimer);
        pending = null;
        scheduleHide();
    });
    tooltip.addEventListener('pointerenter', () => { hovered = true; clearTimeout(hideTimer); });
    tooltip.addEventListener('pointerleave', () => { hovered = false; scheduleHide(); });
    document.addEventListener('focusin', (event) => {
        if (closingDialog || !keyboardFocus) return;
        const control = event.target.closest(selector);
        if (control && eligible(control)) show(prepare(control));
        else hide();
    });
    document.addEventListener('focusout', scheduleHide);
    document.addEventListener('pointerdown', () => { keyboardFocus = false; hide(); }, true);
    document.addEventListener('click', hide);
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Tab') keyboardFocus = true;
        if (event.key === 'Escape') hide();
    }, true);
    document.addEventListener('scroll', (event) => { if (!tooltip.contains(event.target)) hide(); }, { capture: true, passive: true });
    document.addEventListener('close', () => {
        hide();
        closingDialog = true;
        queueMicrotask(() => { closingDialog = false; });
    }, true);
    window.addEventListener('resize', hide);
})();
