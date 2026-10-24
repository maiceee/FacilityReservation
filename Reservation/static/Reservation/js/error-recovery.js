/* Use browser history to recover the existing form; never retry a POST automatically. */
(() => {
    'use strict';
    const back = document.querySelector('[data-error-back]');
    if (back && history.length > 1 && document.referrer) {
        try {
            if (new URL(document.referrer).origin === location.origin) {
                back.hidden = false;
                back.addEventListener('click', () => history.back());
            }
        } catch (_) { /* Workspace recovery remains available. */ }
    }
    document.addEventListener('DOMContentLoaded', () => {
        const review = document.querySelector('[data-error-review]');
        const recovery = window.SpasyoFormRecovery;
        const url = recovery?.reviewURL();
        if (!review || !url) return;
        review.href = url;
        review.hidden = false;
        document.querySelector('.auth-error-actions a[href]:not([data-error-review])')?.classList.remove('button-primary');
        review.addEventListener('click', (event) => {
            if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            if (!recovery.prepareReview()) { event.preventDefault(); review.hidden = true; }
        });
    });
})();
