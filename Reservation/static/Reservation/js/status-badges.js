/* The text remains the status; Lucide symbols provide a second visual cue. */
(() => {
    'use strict';
    const source = document.querySelector('[data-toast-stack]')?.dataset.iconSprite;
    if (!source) return;
    const selector = '.status-badge, .user-status-badge, .management-status, .closures-status, .closures-conflict-status';
    const initialize = (root) => {
        const badges = [...root.querySelectorAll(selector)];
        if (root.matches?.(selector)) badges.unshift(root);
        badges.forEach((badge) => {
            if (badge.querySelector('[data-status-icon]')) return;
            const name = badge.className;
            const symbol = /pending/.test(name) ? 'clock-3'
                : /approved/.test(name) ? 'calendar-check-2'
                : /checked_in/.test(name) ? 'users'
                : /completed/.test(name) ? 'circle-check'
                : /rejected|cancelled/.test(name) ? 'x'
                : /no_show|conflict/.test(name) ? 'circle-alert'
                : /is-archived/.test(name) ? 'archive'
                : /is-inactive/.test(name) ? 'x' : 'circle-check';
            badge.querySelectorAll('.management-status-dot, .closures-status-dot').forEach((dot) => dot.remove());
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('class', 'icon status-icon');
            svg.setAttribute('aria-hidden', 'true');
            svg.setAttribute('data-status-icon', '');
            const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
            use.setAttribute('href', `${source}#${symbol}`);
            svg.append(use);
            badge.prepend(svg);
        });
    };
    initialize(document);
    new MutationObserver((records) => records.forEach((record) => record.addedNodes.forEach((node) => {
        if (node.nodeType === 1) initialize(node);
    }))).observe(document.body, { childList: true, subtree: true });
})();
