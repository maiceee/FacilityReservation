/* Shared geometry and CSS transition for tabs, sidebar links and inbox filters. */
(() => {
    'use strict';
    const mount = (list, selection = '[aria-selected="true"], [aria-current="page"], [aria-pressed="true"]') => {
        list.classList.add('tab-indicator-root');
        const items = [...list.querySelectorAll('a, button')];
        const selected = () => items.find(item => item.matches(selection));
        let current;
        const move = (item = selected()) => {
            if (!item || !item.offsetWidth || !item.offsetHeight) return;
            current = item;
            const { offsetLeft, offsetTop, offsetWidth, offsetHeight } = item;
            list.style.setProperty('--tab-left', `${offsetLeft}px`);
            list.style.setProperty('--tab-top', `${offsetTop}px`);
            list.style.setProperty('--tab-width', `${offsetWidth}px`);
            list.style.setProperty('--tab-height', `${offsetHeight}px`);
            items.forEach(candidate => candidate.dataset.pillSelected = String(candidate === item));
            list.classList.add('has-tab-indicator');
        };
        if (typeof ResizeObserver === 'function') new ResizeObserver(() => move(current || selected())).observe(list);
        move();
        return { move, reset: () => move(selected()) };
    };
    window.SpasyoTabMotion = { mount };
    let navigationTimer;
    document.querySelectorAll('.directory-tabs, .sidebar-nav, .user-sidebar-nav').forEach(list => {
        const sidebar = list.matches('.sidebar-nav, .user-sidebar-nav');
        const pill = sidebar ? mount(list, 'a.active') : mount(list);
        // Last bubbling handler lets existing document/capture guards veto navigation.
        window.addEventListener('click', event => {
            if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            const link = event.target.closest('a[href]');
            if (!link || !list.contains(link) || link.hasAttribute('data-edit-dialog') || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
            if (link.origin !== location.origin || (!sidebar && link.pathname !== location.pathname)) return;
            event.preventDefault();
            clearTimeout(navigationTimer);
            if (link.href === location.href) { pill.reset(); return; }
            pill.move(link);
            const raw = getComputedStyle(list).getPropertyValue('--duration-fast').trim();
            const duration = parseFloat(raw) * (raw.endsWith('ms') ? 1 : 1000);
            const navigate = () => location.assign(link.href);
            if (matchMedia('(prefers-reduced-motion: reduce)').matches) navigate();
            else navigationTimer = setTimeout(navigate, Number.isFinite(duration) ? duration : 140);
        });
        window.addEventListener('pageshow', () => { clearTimeout(navigationTimer); pill.reset(); });
    });
})();
