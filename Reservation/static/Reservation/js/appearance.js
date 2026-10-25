/* Runs before styles paint. Appearance is local to this browser, not a server form field. */
(() => {
    'use strict';
    const key = 'spasyo.appearance';
    const valid = value => ['light', 'dark', 'system'].includes(value) ? value : 'system';
    const read = () => { try { return valid(localStorage.getItem(key)); } catch (_) { return 'system'; } };
    const system = matchMedia('(prefers-color-scheme: dark)');
    const root = document.documentElement;
    const printDocument = root.hasAttribute('data-print-document');
    const pills = new WeakMap();
    let preference = read();
    const sync = () => {
        document.querySelectorAll('[data-appearance]').forEach(group => {
            group.querySelectorAll('[data-theme-choice]').forEach(button => {
                button.setAttribute('aria-pressed', String(button.dataset.themeChoice === preference));
            });
            if (window.SpasyoTabMotion) {
                if (!pills.has(group)) pills.set(group, window.SpasyoTabMotion.mount(group));
                pills.get(group).reset();
            }
        });
    };
    const apply = () => {
        const theme = printDocument ? 'light' : preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
        root.dataset.theme = theme;
        root.style.colorScheme = theme;
        sync();
        document.dispatchEvent(new CustomEvent('spasyo:theme-change', {detail: {preference, theme}}));
    };
    const setPreference = value => {
        const next = valid(value);
        if (next === preference) return;
        preference = next;
        try { localStorage.setItem(key, preference); } catch (_) { /* Current page still works without storage. */ }
        apply();
    };
    window.SpasyoAppearance = { getPreference: () => preference, setPreference };
    apply();
    document.addEventListener('DOMContentLoaded', sync);
    document.addEventListener('workspace:form-ready', sync);
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-appearance] [data-theme-choice]');
        if (!button) return;
        event.preventDefault();
        setPreference(button.dataset.themeChoice);
    });
    const followSystem = () => { if (preference === 'system') apply(); };
    if (system.addEventListener) system.addEventListener('change', followSystem);
    else system.addListener?.(followSystem);
    window.addEventListener('storage', event => {
        if (event.key !== key && event.key !== null) return;
        preference = read(); apply();
    });
})();
