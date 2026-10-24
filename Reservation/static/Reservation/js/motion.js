/* Keep dialog content in place during its native exit transition.
   Closing, focus restoration, form actions and validation are never delayed. */
(() => {
    'use strict';
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    const pending = new Map();
    const reveals = new Map();
    const durationFor = (element, name, fallback) => {
        const token = getComputedStyle(element).getPropertyValue(name).trim();
        const value = parseFloat(token);
        return Number.isFinite(value) ? Math.max(0, value * (token.endsWith('ms') ? 1 : 1000)) : fallback;
    };
    const finish = (dialog) => {
        const entry = pending.get(dialog);
        if (!entry) return;
        clearTimeout(entry.timer);
        pending.delete(dialog);
        if (!dialog.open) entry.cleanup();
    };
    window.SpasyoMotion = {
        reveal(element) {
            reveals.get(element)?.cancel();
            reveals.delete(element);
            if (reducedMotion.matches || typeof element.animate !== 'function') return;
            const animation = element.animate([{ opacity: .5 }, { opacity: 1 }], {
                duration: durationFor(element, '--duration-normal', 180),
                easing: getComputedStyle(element).getPropertyValue('--ease-standard').trim() || 'ease-out'
            });
            reveals.set(element, animation);
            const release = () => { if (reveals.get(element) === animation) reveals.delete(element); };
            animation.finished.then(release, release);
        },
        afterClose(dialog, cleanup) {
            const previous = pending.get(dialog);
            if (previous) clearTimeout(previous.timer);
            pending.delete(dialog);
            if (reducedMotion.matches || !CSS.supports('transition-behavior', 'allow-discrete')) {
                if (!dialog.open) cleanup();
                return;
            }
            const duration = durationFor(dialog, '--duration-dialog', 220);
            pending.set(dialog, { cleanup, timer: setTimeout(() => finish(dialog), duration + 30) });
        }
    };
    reducedMotion.addEventListener('change', () => {
        if (reducedMotion.matches) {
            [...pending.keys()].forEach(finish);
            [...reveals.values()].forEach((animation) => animation.finish());
            reveals.clear();
        }
    });
})();
