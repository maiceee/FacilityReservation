/* Shared presentation interactions. No submission shortcuts or business rules. */
(() => {
    'use strict';
    const visible = (element) => element && element.getClientRects().length && !element.disabled;

    // Keep Tab at the dialog boundaries rather than letting focus reach browser chrome.
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab' || event.defaultPrevented) return;
        const dialog = event.target.closest('dialog[open]') || [...document.querySelectorAll('dialog[open]')].at(-1);
        if (!dialog) return;
        const controls = [...dialog.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')]
            .filter((control) => visible(control) && control.tabIndex >= 0 && !control.closest('[hidden], [inert]'));
        if (!controls.length) { event.preventDefault(); return; }
        const first = controls[0], last = controls.at(-1);
        if (!dialog.contains(document.activeElement) || (!event.shiftKey && document.activeElement === last)) {
            event.preventDefault(); first.focus();
        } else if (event.shiftKey && document.activeElement === first) {
            event.preventDefault(); last.focus();
        }
    });

    // Both ends of a backdrop click must be outside: dragging from a form is safe.
    document.querySelectorAll('dialog').forEach((dialog) => {
        let startedOutside = false;
        const outside = (event) => {
            const box = dialog.getBoundingClientRect();
            return event.target === dialog && (event.clientX < box.left || event.clientX > box.right
                || event.clientY < box.top || event.clientY > box.bottom);
        };
        dialog.addEventListener('pointerdown', (event) => { startedOutside = outside(event); });
        dialog.addEventListener('click', (event) => {
            if (startedOutside && outside(event) && dialog.open && !dialog.querySelector('form[data-saving="true"]')) {
                if (dialog.id === 'table-edit-dialog' && window.SpasyoEditor) window.SpasyoEditor.requestClose();
                else dialog.close();
            }
            startedOutside = false;
        });
    });
    const dismissLegacy = (backdrop) => {
        backdrop.querySelector('.admin-modal-close')?.click();
    };
    document.querySelectorAll('.admin-modal-backdrop').forEach((backdrop) => {
        let startedOutside = false;
        backdrop.addEventListener('pointerdown', (event) => { startedOutside = event.target === backdrop; });
        backdrop.addEventListener('click', (event) => {
            if (startedOutside && event.target === backdrop && !backdrop.hidden) dismissLegacy(backdrop);
            startedOutside = false;
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape' || event.defaultPrevented) return;
        const backdrop = document.querySelector('.admin-modal-backdrop:not([hidden])');
        if (backdrop) dismissLegacy(backdrop);
    });
    document.querySelectorAll('[data-edit-close], [data-preview-close], .admin-modal-close, [data-dialog-close], [data-admin-confirm-close], [data-signout-close]').forEach((close) => {
        const key = document.createElement('kbd');
        key.textContent = 'Esc';
        key.setAttribute('aria-hidden', 'true');
        close.append(key);
        close.classList.add('shortcut-close');
        close.title = 'Close (Esc)';
    });

    // Details remains the readable no-JS / no-Popover-API fallback for hints.
    if (!('showPopover' in HTMLElement.prototype)) return;
    let popupId = 0;
    const connectPopover = (trigger, popup, beside = false) => {
        popup.popover = 'auto';
        popup.id ||= `context-help-${++popupId}`;
        trigger.setAttribute('aria-controls', popup.id);
        trigger.setAttribute('aria-expanded', 'false');
        const place = () => {
            const box = trigger.getBoundingClientRect();
            const rect = popup.getBoundingClientRect();
            let x = beside ? box.right + 8 : box.right - rect.width;
            let y = beside ? box.top : box.bottom + 8;
            if (beside && x + rect.width > innerWidth - 12) {
                x = box.left - rect.width - 8;
                if (x < 12) { x = box.left; y = box.bottom + 8; }
            }
            popup.style.left = `${Math.max(12, Math.min(x, innerWidth - rect.width - 12))}px`;
            popup.style.top = `${Math.max(12, Math.min(y, innerHeight - rect.height - 12))}px`;
        };
        trigger.addEventListener('click', (event) => {
            event.preventDefault();
            if (popup.matches(':popover-open')) popup.hidePopover();
            else { popup.showPopover(); place(); }
        });
        popup.addEventListener('toggle', () => trigger.setAttribute('aria-expanded', String(popup.matches(':popover-open'))));
        popup.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            popup.hidePopover();
            trigger.focus();
        });
        window.addEventListener('resize', () => { if (popup.matches(':popover-open')) popup.hidePopover(); });
        document.addEventListener('scroll', (event) => {
            if (popup.matches(':popover-open') && !popup.contains(event.target)) popup.hidePopover();
        }, { capture: true, passive: true });
    };
    const tools = document.querySelector('.keyboard-tools');
    if (!tools) return;
    const help = tools.querySelector('.keyboard-help-trigger');
    const popup = tools.querySelector('.keyboard-help');
    connectPopover(help, popup);
    tools.hidden = false;
    const search = [...document.querySelectorAll('input[type="search"], input[name="search"], input[name="q"]')].find(visible);
    const create = [...document.querySelectorAll('main a[href]')].find((link) => visible(link)
        && /\/(add|create|request)\/$/.test(new URL(link.href).pathname));
    popup.querySelector('[data-shortcut-search]').hidden = !search;
    popup.querySelector('[data-shortcut-new]').hidden = !create;
    const badges = [];
    if (search) {
        const wrap = document.createElement('span');
        wrap.className = 'shortcut-search-control';
        search.before(wrap);
        wrap.append(search);
        const key = document.createElement('kbd');
        key.textContent = '/';
        key.setAttribute('aria-hidden', 'true');
        wrap.append(key);
        badges.push(key);
    }
    if (create) {
        popup.querySelector('[data-shortcut-new] > span').textContent = create.textContent.trim();
        const key = document.createElement('kbd');
        key.textContent = 'Alt N';
        key.setAttribute('aria-hidden', 'true');
        create.append(key);
        badges.push(key);
    }
    const setting = tools.querySelector('[data-quick-keys]');
    try { setting.checked = sessionStorage.getItem('spasyo.quickKeys') !== 'off'; } catch (_) { /* Optional UI preference. */ }
    const update = () => {
        badges.forEach((badge) => { badge.hidden = !setting.checked; });
        help.querySelector('kbd').hidden = !setting.checked;
        [[help, 'Shift+/'], [search, '/'], [create, 'Alt+n']].forEach(([control, keys]) => {
            if (!control) return;
            if (setting.checked) control.setAttribute('aria-keyshortcuts', keys);
            else control.removeAttribute('aria-keyshortcuts');
        });
    };
    setting.addEventListener('change', () => {
        update();
        try { sessionStorage.setItem('spasyo.quickKeys', setting.checked ? 'on' : 'off'); } catch (_) { /* Keep current-page preference. */ }
    });
    update();
    document.addEventListener('keydown', (event) => {
        if (!setting.checked || event.defaultPrevented || event.repeat || event.isComposing || event.ctrlKey || event.metaKey) return;
        if (event.target.closest('input, textarea, select, [role="textbox"], [role="combobox"], [contenteditable]:not([contenteditable="false"])')) return;
        if (document.querySelector('dialog[open], .admin-modal-backdrop:not([hidden])')) return;
        if (event.key === '?' && !event.altKey) { event.preventDefault(); help.focus(); help.click(); }
        else if (event.key === '/' && !event.altKey && search) {
            event.preventDefault();
            document.querySelectorAll(':popover-open').forEach((open) => open.hidePopover());
            search.focus();
        } else if (event.altKey && event.key.toLowerCase() === 'n' && create) {
            event.preventDefault();
            create.click();
        }
    });
})();
