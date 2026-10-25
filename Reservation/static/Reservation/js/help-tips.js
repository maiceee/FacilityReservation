/* Optional guidance is disclosed on request; form errors and constraints stay intact. */
(() => {
    'use strict';
    const supportsPopover = 'showPopover' in HTMLElement.prototype;
    const sources = '.field-help, .rv-form-help, .master-field-help, .facility-field-help, .closures-field-help, .ui-field-help, .system-field-description, .field-example:not(.is-inline), .modal-description, [data-help-description]';
    const groups = '.field, .rv-form-field, .master-form-group, .facility-form-group, .closures-form-group, .system-settings-field, .user-filter-field, .calendar-field, .ra-field, .rv-field';
    const sprite = document.querySelector('.icon use')?.getAttribute('href')?.split('#')[0];
    if (!sprite) return;
    const enhance = (root) => {
        root.querySelectorAll(sources).forEach(source => {
            if (!source.textContent.trim() || source.closest('.ui-hint, .auth-form-wrapper') || source.getAttribute('role') === 'alert') return;
            const header = source.classList.contains('modal-description') || source.hasAttribute('data-help-description');
            const group = header ? source.parentElement : source.closest(groups);
            const label = header ? group.querySelector('h2, h3') : group?.querySelector('label');
            if (!label) return;
            let row = label.closest('.help-label-row');
            if (!row) {
                row = document.createElement('div'); row.className = 'help-label-row';
                label.before(row); row.append(label);
            }
            const existing = row.querySelector('.ui-hint');
            if (existing) { existing.querySelector('.ui-hint-content').append(source); return; }
            const hint = document.createElement('details'); hint.className = 'ui-hint';
            const trigger = document.createElement('summary');
            const title = label.textContent.replace(/\s*\*\s*$/, '').trim();
            trigger.setAttribute('aria-label', `Help: ${title}`); trigger.dataset.noTooltip = '';
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'icon'); svg.setAttribute('aria-hidden', 'true');
            const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
            use.setAttribute('href', `${sprite}#circle-help`); svg.append(use); trigger.append(svg);
            const content = document.createElement('div'); content.className = 'ui-hint-content';
            content.append(source); hint.append(trigger, content); row.append(hint);
        });
        if (supportsPopover) root.querySelectorAll('details.ui-hint').forEach(details => {
            const summary = details.querySelector('summary'), content = details.querySelector('.ui-hint-content');
            if (!summary || !content) return;
            const hint = document.createElement('span'); hint.className = details.className;
            const button = document.createElement('button'); button.type = 'button';
            button.setAttribute('aria-label', summary.getAttribute('aria-label') || 'Help');
            button.setAttribute('aria-expanded', 'false'); button.dataset.noTooltip = '';
            button.append(...summary.childNodes); content.hidden = true;
            hint.append(button, content); details.replaceWith(hint);
        });
        root.querySelectorAll('.help-label-row').forEach(row => {
            const heading = row.querySelector('h2, h3'), button = row.querySelector('.ui-hint > button');
            if (heading && button) {
                button.setAttribute('aria-label', `Help: ${heading.textContent.trim()}`);
                button.closest('.ui-hint').hidden = !row.querySelector('.ui-hint-content').textContent.trim();
            }
        });
    };
    enhance(document);
    document.addEventListener('workspace:form-ready', event => enhance(event.target.closest('dialog') || event.target));
    if (!supportsPopover) return; // Native details fallback.
    const popup = document.createElement('div');
    popup.id = 'workspace-help-tip'; popup.className = 'context-popover hint-popover';
    popup.popover = 'manual'; popup.setAttribute('role', 'note');
    const content = document.createElement('div'); content.className = 'help-tip-text'; popup.append(content);
    document.body.append(popup);
    let active;
    const close = () => {
        if (popup.matches(':popover-open')) popup.hidePopover();
        active?.setAttribute('aria-expanded', 'false'); active?.removeAttribute('aria-describedby'); active = null;
    };
    const plainText = node => node.nodeType === 3 ? node.textContent : [...node.childNodes].map(plainText).join(' ');
    const place = () => {
        if (!active) return;
        const box = active.getBoundingClientRect(), rect = popup.getBoundingClientRect();
        let side = 'right', x = box.right + 8, y = box.top + (box.height - rect.height) / 2;
        if (x + rect.width > innerWidth - 8) { side = 'left'; x = box.left - rect.width - 8; }
        if (x < 8) { side = 'bottom'; x = box.left; y = box.bottom + 8; }
        if (side === 'bottom' && y + rect.height > innerHeight - 8) { side = 'top'; y = box.top - rect.height - 8; }
        x = Math.max(8, Math.min(x, innerWidth - rect.width - 8));
        y = Math.max(8, Math.min(y, innerHeight - rect.height - 8));
        popup.setAttribute('data-side', side);
        const arrow = side === 'right' || side === 'left'
            ? Math.max(10, Math.min(box.top + box.height / 2 - y, rect.height - 10))
            : Math.max(10, Math.min(box.left + box.width / 2 - x, rect.width - 10));
        popup.style.setProperty('--help-arrow', `${arrow}px`);
        popup.style.left = `${x}px`;
        popup.style.top = `${y}px`;
    };
    document.addEventListener('click', event => {
        const trigger = event.target.closest('.ui-hint > button');
        if (!trigger) { if (!popup.contains(event.target)) close(); return; }
        event.preventDefault();
        if (active === trigger && popup.matches(':popover-open')) { close(); return; }
        close(); active = trigger;
        content.textContent = plainText(trigger.parentElement.querySelector('.ui-hint-content')).replace(/\s+/g, ' ').trim();
        trigger.setAttribute('role', 'button');
        (trigger.closest('dialog[open]') || document.body).append(popup);
        trigger.setAttribute('aria-controls', popup.id);
        trigger.setAttribute('aria-expanded', 'true');
        trigger.setAttribute('aria-describedby', popup.id);
        popup.showPopover(); place();
    });
    popup.addEventListener('toggle', () => {
        if (!popup.matches(':popover-open')) { active?.setAttribute('aria-expanded', 'false'); active?.removeAttribute('aria-describedby'); active = null; }
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || !popup.matches(':popover-open')) return;
        event.preventDefault(); event.stopImmediatePropagation();
        const trigger = active; close(); trigger?.focus();
    }, true);
    document.addEventListener('scroll', event => { if (!popup.contains(event.target)) close(); }, {capture: true, passive: true});
    document.addEventListener('close', close, true);
    window.addEventListener('resize', close);
})();
