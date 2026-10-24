/* Form feedback only: native/server errors and full-page submission status.
   No validation rules, field values, endpoints, or submitter values are changed. */
(() => {
    'use strict';
    const groups = '.field, .user-form-group, .rv-form-field, .facility-form-group, .master-form-group, .closures-form-group, .system-settings-field';
    const clientErrors = new WeakMap();
    const pendingSummaries = new Set();
    const buttonDefaults = new WeakMap();
    const submitting = new Map();
    let nextId = 0;
    const targetFor = (control) => control.closest('.select-control')?.querySelector('.control-trigger') || control;
    const describe = (control, error) => {
        error.id ||= `ui-field-error-${++nextId}`;
        const ids = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        ids.add(error.id);
        control.setAttribute('aria-describedby', [...ids].join(' '));
        control.setAttribute('aria-invalid', 'true');
        const target = targetFor(control);
        target.setAttribute('aria-invalid', 'true');
        target.setAttribute('aria-describedby', [...ids].join(' '));
    };
    const summarize = (form) => {
        let summary = form.querySelector('.ui-validation-summary');
        const errors = [...form.querySelectorAll(groups)].flatMap((group) => {
            const error = group.querySelector('[role="alert"]');
            const control = group.querySelector('input[name], select[name], textarea[name]');
            return error && control ? [{ group, error, control }] : [];
        });
        if (!errors.length) { summary?.remove(); return null; }
        if (!summary) {
            summary = document.createElement('div');
            summary.className = 'ui-validation-summary';
            summary.setAttribute('role', 'alert');
            summary.tabIndex = -1;
            form.prepend(summary);
        }
        const heading = document.createElement('strong');
        heading.textContent = `Check ${errors.length === 1 ? 'this field' : `these ${errors.length} fields`} before continuing.`;
        const links = document.createElement('div');
        links.className = 'ui-validation-links';
        errors.forEach(({ group, control, error }) => {
            describe(control, error);
            const link = document.createElement('a');
            link.href = `#${targetFor(control).id || control.id}`;
            link.textContent = (group.querySelector('label')?.textContent || control.name).replace(/\*/g, '').trim();
            link.addEventListener('click', (event) => { event.preventDefault(); targetFor(control).focus(); });
            links.append(link);
        });
        summary.replaceChildren(heading, links);
        return summary;
    };
    const initialize = (root) => {
        const forms = root.matches?.('form') ? [root] : [...root.querySelectorAll('form')];
        let firstError = null;
        forms.forEach((form) => {
            form.querySelectorAll('button[type="submit"]').forEach((button) => {
                if (!buttonDefaults.has(button)) buttonDefaults.set(button, {
                    content: [...button.childNodes].map((node) => node.cloneNode(true)), disabled: button.disabled,
                    minWidth: button.style.minWidth, busy: button.getAttribute('aria-busy')
                });
            });
            const summary = summarize(form);
            const error = summary || form.querySelector('[role="alert"]');
            if (error) { error.tabIndex = -1; firstError ||= error; }
        });
        firstError ||= root.querySelector('.auth-alert[role="alert"]');
        if (firstError) { firstError.tabIndex = -1; firstError.focus(); }
    };
    const scheduleSummary = (form) => {
        if (pendingSummaries.has(form)) return;
        pendingSummaries.add(form);
        queueMicrotask(() => { pendingSummaries.delete(form); summarize(form); });
    };
    document.addEventListener('invalid', (event) => {
        const control = event.target;
        const group = control.closest(groups);
        if (!control.form || !group) return;
        const serverError = group.querySelector('[role="alert"]:not(.ui-client-error)');
        if (serverError) { describe(control, serverError); return; }
        let entry = clientErrors.get(control);
        if (!entry) {
            const error = document.createElement('div');
            error.className = 'field-error ui-client-error';
            error.setAttribute('role', 'alert');
            entry = { error, originalInvalid: control.getAttribute('aria-invalid') };
            clientErrors.set(control, entry);
            group.append(error);
        }
        entry.error.textContent = control.validationMessage || 'Check this field before continuing.';
        describe(control, entry.error);
        scheduleSummary(control.form);
    }, true);
    const clearValid = (event) => {
        const control = event.target;
        const entry = clientErrors.get(control);
        if (!entry || !control.validity.valid) return;
        const ids = (control.getAttribute('aria-describedby') || '').split(/\s+/).filter((id) => id && id !== entry.error.id);
        [control, targetFor(control)].forEach((target) => {
            if (ids.length) target.setAttribute('aria-describedby', ids.join(' '));
            else target.removeAttribute('aria-describedby');
            if (entry.originalInvalid === null) target.removeAttribute('aria-invalid');
            else target.setAttribute('aria-invalid', entry.originalInvalid);
        });
        entry.error.remove();
        clientErrors.delete(control);
        summarize(control.form);
    };
    document.addEventListener('input', clearValid);
    document.addEventListener('change', clearValid);
    document.addEventListener('submit', (event) => {
        const form = event.target;
        const button = event.submitter;
        queueMicrotask(() => {
            if (event.defaultPrevented || form.method.toLowerCase() !== 'post' || !button || submitting.has(button)) return;
            const original = buttonDefaults.get(button);
            if (!original) return;
            submitting.set(button, { original, form });
            button.style.minWidth = `${button.getBoundingClientRect().width}px`;
            button.setAttribute('aria-busy', 'true');
            if (button.textContent.trim()) button.textContent = 'Please wait…';
            form.classList.add('is-submitting');
        });
    });
    window.addEventListener('pageshow', () => {
        submitting.forEach(({ original, form }, button) => {
            button.replaceChildren(...original.content.map((node) => node.cloneNode(true)));
            button.disabled = original.disabled;
            button.style.minWidth = original.minWidth;
            if (original.busy === null) button.removeAttribute('aria-busy');
            else button.setAttribute('aria-busy', original.busy);
            form.classList.remove('is-submitting');
        });
        submitting.clear();
    });
    initialize(document);
    document.addEventListener('workspace:form-ready', (event) => initialize(event.target));
})();
