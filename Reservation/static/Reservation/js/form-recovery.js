/* Temporary, tab-scoped recovery for protected data forms.
   Capture only a submitted form; never store passwords, files, CSRF/security tokens,
   or confirmation-only actions. Restoration is explicit and never submits a form. */
(() => {
    'use strict';
    const key = 'spasyo.formRecovery.v1';
    const reviewKey = 'spasyo.formRecovery.review';
    const lifetime = 10 * 60 * 1000;
    const allowed = '.master-detail-form, .facility-detail-form, .closures-detail-form, .user-reservation-form, .rv-stacked-form, .system-settings-form, .reservation-action-form, .reservation-cancellation-form, .reservation-completion-form';
    const actor = document.body.dataset.formActor;
    const clear = () => { try { sessionStorage.removeItem(key); sessionStorage.removeItem(reviewKey); } catch (_) { /* Browser history remains available. */ } };
    const safeURL = (value) => {
        try { const url = new URL(value, location.href); return url.origin === location.origin ? url : null; }
        catch (_) { return null; }
    };
    const read = () => {
        try {
            const draft = JSON.parse(sessionStorage.getItem(key));
            if (!draft) return null;
            const age = Date.now() - draft.created;
            if (draft.version !== 1 || !Array.isArray(draft.fields) || !safeURL(draft.action) || !safeURL(draft.reviewURL) || age < 0 || age > lifetime) { clear(); return null; }
            return draft;
        } catch (_) { clear(); return null; }
    };
    const write = (draft) => { try { sessionStorage.setItem(key, JSON.stringify(draft)); return true; } catch (_) { return false; } };
    const controlsFor = (form) => [...form.elements].filter((control) => control.name && !control.disabled
        && !['hidden', 'password', 'file', 'submit', 'button', 'reset'].includes(control.type)
        && !/password|csrf|token/i.test(control.name));
    const prepareReview = () => {
        const draft = read();
        if (!draft?.failed) return false;
        try { sessionStorage.setItem(reviewKey, draft.id); return true; } catch (_) { return false; }
    };
    window.SpasyoFormRecovery = {
        reviewURL: () => { const draft = read(); return draft?.failed ? safeURL(draft.reviewURL).href : null; },
        prepareReview
    };
    const notice = (message, canReview = false) => {
        const page = document.querySelector('.workspace-page');
        if (!page || page.querySelector('.ui-recovery-notice')) return;
        const panel = document.createElement('div');
        panel.className = 'ui-recovery-notice';
        panel.setAttribute('role', 'status');
        const text = document.createElement('p');
        text.textContent = message;
        panel.append(text);
        if (canReview) {
            const link = document.createElement('a');
            link.className = 'button button-primary';
            link.href = window.SpasyoFormRecovery.reviewURL();
            link.textContent = 'Review entries';
            link.addEventListener('click', (event) => {
                if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                if (!prepareReview()) { event.preventDefault(); panel.remove(); }
            });
            panel.append(link);
        }
        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.className = 'button';
        dismiss.textContent = canReview ? 'Discard' : 'Dismiss';
        dismiss.addEventListener('click', () => { if (canReview) clear(); panel.remove(); });
        panel.append(dismiss);
        page.prepend(panel);
    };
    const restore = (root) => {
        const draft = read();
        if (!draft) return;
        if (!actor || actor !== draft.actor) { clear(); return; }
        let requested = false;
        try { requested = sessionStorage.getItem(reviewKey) === draft.id; } catch (_) { return; }
        if (!requested) {
            if (draft.failed) notice('Your previous entries are available to review for 10 minutes.', true);
            else clear(); // Success or a bound server-validation response has taken over.
            return;
        }
        const forms = root.matches?.('form') ? [root] : [...root.querySelectorAll('form')];
        const form = forms.find((item) => item.matches(allowed) && safeURL(item.action)?.href === safeURL(draft.action).href);
        if (!form) return;
        const controls = controlsFor(form);
        let changedChoices = false;
        draft.fields.forEach((field) => {
            const matches = controls.filter((control) => control.name === field.name);
            if (!matches.length || !Array.isArray(field.values)) return;
            matches.forEach((control) => {
                if (['checkbox', 'radio'].includes(control.type)) control.checked = field.values.includes(control.value);
                else if (control.tagName === 'SELECT') {
                    [...control.options].forEach((option) => { option.selected = field.values.includes(option.value); });
                    if (field.values.some((value) => value && ![...control.options].some((option) => option.value === value))) changedChoices = true;
                } else control.value = field.values[0] || '';
            });
        });
        clear();
        notice(changedChoices ? 'Your entries were restored. Some choices changed; review the form before submitting.' : 'Your entries were restored. Review them before submitting.');
    };
    if (document.body.classList.contains('error-page')) {
        const draft = read();
        if (draft) { draft.failed = true; write(draft); }
    } else restore(document);
    document.addEventListener('workspace:form-ready', (event) => restore(event.target));
    document.addEventListener('submit', (event) => {
        const form = event.target;
        queueMicrotask(() => {
            if (event.defaultPrevented || form.method.toLowerCase() !== 'post') return;
            if (form.matches('[data-signout]')) { clear(); return; }
            if (!actor || !form.matches(allowed)) return;
            const action = safeURL(form.action);
            const reviewURL = safeURL(form.closest('#table-edit-dialog') ? form.action : location.href);
            if (!action || !reviewURL) return;
            const controls = controlsFor(form);
            const names = [...new Set(controls.map((control) => control.name))];
            const fields = names.map((name) => {
                const matches = controls.filter((control) => control.name === name);
                return { name, values: matches.flatMap((control) => ['checkbox', 'radio'].includes(control.type)
                    ? control.checked ? [control.value] : []
                    : control.tagName === 'SELECT' ? [...control.selectedOptions].map((option) => option.value) : [control.value]) };
            });
            if (!fields.length) return;
            write({ version: 1, id: `${Date.now()}-${Math.random()}`, created: Date.now(), actor, action: action.href, reviewURL: reviewURL.href, fields, failed: false });
        });
    });
    window.addEventListener('pageshow', (event) => {
        if (event.persisted && !document.body.classList.contains('error-page')) restore(document);
    });
})();
