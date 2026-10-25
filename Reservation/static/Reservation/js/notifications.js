/* Server messages become compact toasts. Undo cancels a delayed action BEFORE
   its original POST; it never claims to reverse an already saved operation. */
(() => {
    'use strict';
    const stack = document.querySelector('[data-toast-stack]');
    if (!stack) return;
    const sprite = stack.dataset.iconSprite;
    const undoDelay = 12000;
    const jobs = new Set();
    let pending = null;
    const pendingListeners = new Set();
    const notifyPending = () => pendingListeners.forEach(listener => listener(Boolean(pending)));
    const icon = (name) => {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'icon');
        svg.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        use.setAttribute('href', `${sprite}#${name}`);
        svg.append(use);
        return svg;
    };
    const host = () => {
        const dialog = document.activeElement?.closest('dialog[open]') || [...document.querySelectorAll('dialog[open]')].at(-1);
        const parent = dialog || document.body;
        if (stack.parentElement !== parent) parent.append(stack);
        stack.hidden = !stack.children.length;
        if (typeof stack.showPopover === 'function') {
            if (stack.children.length && !stack.matches(':popover-open')) stack.showPopover();
            else if (!stack.children.length && stack.matches(':popover-open')) stack.hidePopover();
        }
    };
    const remove = (job) => {
        clearTimeout(job.timer);
        jobs.delete(job);
        const dismiss = () => { job.element.remove(); host(); };
        if (typeof job.element.animate === 'function' && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
            job.element.style.pointerEvents = 'none';
            job.element.animate([{ opacity: 1, transform: 'translateY(0)' }, { opacity: 0, transform: 'translateY(-6px)' }], { duration: parseFloat(getComputedStyle(job.element).getPropertyValue('--duration-toast-exit')) || 140, easing: getComputedStyle(job.element).getPropertyValue('--ease-exit').trim() || 'ease-out', fill: 'forwards' }).finished.then(dismiss, dismiss);
        } else dismiss();
        if (pending === job) { pending = null; notifyPending(); }
        host();
    };
    const schedule = (job) => {
        if (!jobs.has(job)) return;
        const now = Date.now();
        if (!document.hidden && (!job.action || (!job.hovered && !job.focused && !document.querySelector('dialog[open]')))) job.remaining -= Math.max(0, now - job.last);
        job.last = now;
        if (job.counter) job.counter.textContent = `${Math.max(0, Math.ceil(job.remaining / 1000))}s`;
        if (job.progress) job.progress.value = Math.max(0, job.remaining);
        if (job.remaining <= 0) {
            const action = job.action;
            remove(job);
            action?.();
        } else job.timer = setTimeout(() => schedule(job), Math.min(150, job.remaining));
    };
    const show = (message, options = {}) => {
        const severity = options.severity || 'info';
        const element = document.createElement('div');
        element.className = `ui-toast toast-${severity}`;
        element.setAttribute('role', severity === 'error' ? 'alert' : 'status');
        element.setAttribute('aria-atomic', 'true');
        const mark = document.createElement('span');
        mark.className = 'toast-mark';
        mark.append(icon(severity === 'success' ? 'circle-check' : severity === 'error' || severity === 'warning' ? 'circle-alert' : 'info'));
        const text = document.createElement('div');
        text.className = 'toast-copy';
        const label = document.createElement('p');
        label.textContent = message;
        text.append(label);
        if (options.description) {
            const detail = document.createElement('small');
            detail.textContent = options.description;
            text.append(detail);
        }
        element.append(mark, text);
        const duration = options.duration ?? (severity === 'error' || severity === 'warning' ? 0 : 8000);
        const job = { element, remaining: duration, last: Date.now(), action: options.action, hovered: false, focused: false };
        const actions = document.createElement('div');
        actions.className = 'toast-actions';
        const makeButton = (label, callback) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = label;
            button.addEventListener('click', callback);
            actions.append(button);
            return button;
        };
        if (options.undo) {
            makeButton('Undo', () => { if (!jobs.has(job)) return; remove(job); show('Undone. No changes made.', { severity: 'info', duration: 3500 }); });
            makeButton('Apply now', () => { if (!jobs.has(job)) return; const action = job.action; remove(job); action(); });
            const counter = document.createElement('span');
            counter.className = 'toast-countdown';
            counter.setAttribute('aria-hidden', 'true');
            actions.append(counter);
            job.counter = counter;
        } else {
            const close = makeButton('', () => remove(job));
            close.className = 'toast-dismiss';
            close.setAttribute('aria-label', 'Dismiss notification');
            close.append(icon('x'));
        }
        element.append(actions);
        element.addEventListener('pointerenter', () => { job.hovered = true; });
        element.addEventListener('pointerleave', () => { job.hovered = false; job.last = Date.now(); });
        element.addEventListener('focusin', () => { job.focused = true; });
        element.addEventListener('focusout', (event) => {
            if (!element.contains(event.relatedTarget)) { job.focused = false; job.last = Date.now(); }
        });
        jobs.add(job);
        stack.append(element);
        host();
        if (duration) schedule(job);
        // Keep the compact stack bounded; persistent errors and pending Undo stay.
        const expiring = [...jobs].filter((item) => item !== pending && item !== job && !item.action && item.remaining > 0);
        while (stack.children.length > 3 && expiring.length) remove(expiring.shift());
        return job;
    };
    const consume = (root = document) => {
        root.querySelectorAll('.messages-container > .message, .user-flash-messages > .user-flash-message').forEach((message) => {
            const severity = ['error', 'warning', 'success', 'info'].find((name) => message.classList.contains(name)) || 'info';
            const text = message.textContent.trim()
                .replace(/^Facility category archived\.$/, 'Category deactivated.')
                .replace(/^Amenity archived\.$/, 'Amenity deactivated.')
                .replace(/^Facility archived successfully\.$/, 'Facility deactivated.');
            show(text, { severity });
            const container = message.parentElement;
            message.remove();
            if (!container.children.length) container.remove();
        });
    };
    window.SpasyoNotifications = {
        show, consume,
        hasPendingAction: () => Boolean(pending),
        subscribePending(listener) {
            pendingListeners.add(listener);
            return () => pendingListeners.delete(listener);
        },
        deferAction({ label, record, action }) {
            if (pending) {
                show('Finish or undo the pending action first.', { severity: 'warning' });
                return;
            }
            pending = show(`${label}${record ? `: ${record}` : ''} scheduled.`, {
                severity: 'info', duration: undoDelay, undo: true, action,
                description: 'Not submitted yet. Apply now or Undo before leaving this page.'
            });
            notifyPending();
        }
    };
    // Prevent ordinary page navigation from silently abandoning a queued POST.
    // Never auto-submit on unload: the user must resolve the original action.
    const explainPending = () => {
        show('Apply or undo the pending action before leaving this page.', { severity: 'warning', duration: 5000 });
        pending?.element.querySelector('button')?.focus();
    };
    document.addEventListener('click', (event) => {
        if (!pending || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest('a[href]');
        if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
        const url = new URL(link.href, location.href);
        const current = new URL(location.href);
        if (url.hash && url.origin === current.origin && url.pathname === current.pathname && url.search === current.search) return;
        event.preventDefault();
        explainPending();
    }, true);
    document.addEventListener('submit', (event) => {
        if (!pending) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        explainPending();
    }, true);
    window.addEventListener('beforeunload', (event) => {
        if (!pending) return;
        event.preventDefault();
        event.returnValue = '';
    });
    document.addEventListener('visibilitychange', () => jobs.forEach((job) => { job.last = Date.now(); }));
    document.addEventListener('toggle', (event) => { if (event.target.tagName === 'DIALOG') host(); }, true);
    window.addEventListener('pagehide', () => {
        jobs.forEach((job) => { clearTimeout(job.timer); job.element.remove(); });
        jobs.clear(); pending = null; stack.hidden = true; notifyPending();
    });
    consume();
})();
