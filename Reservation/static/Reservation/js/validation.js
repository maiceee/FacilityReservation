/* Accessible native/server feedback, full-page submission status, and the
   debounced facility-code availability check. Server validation remains final. */
(() => {
    'use strict';
    const groups = '.field, .user-form-group, .rv-form-field, .facility-form-group, .master-form-group, .closures-form-group, .system-settings-field';
    const clientErrors = new WeakMap();
    const pendingSummaries = new Set();
    const buttonDefaults = new WeakMap();
    const submitting = new Map();
    const facilityCodeForms = new WeakSet();
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
        if (form.classList.contains('register-form')) {
            summary?.remove();
            return null;
        }
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
    const initializeFacilityCodeChecks = (root) => {
        const forms = root.matches?.('.facility-detail-form[data-facility-code-check-url]')
            ? [root]
            : [...root.querySelectorAll('.facility-detail-form[data-facility-code-check-url]')];

        forms.forEach((form) => {
            if (facilityCodeForms.has(form)) return;

            const control = form.querySelector('[name="facility_code"]');
            const group = control?.closest('.facility-form-group');
            const endpoint = form.dataset.facilityCodeCheckUrl;

            if (!control || !group || !endpoint) return;

            facilityCodeForms.add(form);
            let debounceTimer = null;
            let request = null;
            let checkedValue = null;
            const message = (
                'A facility with this code already exists. '
                + 'Enter a unique facility code.'
            );

            const removeDescription = (id) => {
                if (!id) return;
                const ids = (control.getAttribute('aria-describedby') || '')
                    .split(/\s+/)
                    .filter((value) => value && value !== id);

                if (ids.length) control.setAttribute('aria-describedby', ids.join(' '));
                else control.removeAttribute('aria-describedby');
            };

            const clearLiveError = () => {
                const error = group.querySelector('[data-facility-code-live-error]');
                if (error) {
                    removeDescription(error.id);
                    error.remove();
                }
                control.setCustomValidity('');
                if (!group.querySelector('[role="alert"]')) {
                    control.removeAttribute('aria-invalid');
                }
                scheduleSummary(form);
            };

            const clearStaleServerError = () => {
                const error = group.querySelector(
                    '.facility-field-error:not([data-facility-code-live-error])'
                );
                if (!error) return;
                removeDescription(error.id);
                error.remove();
                scheduleSummary(form);
            };

            const showDuplicateError = () => {
                clearLiveError();
                const error = document.createElement('div');
                const paragraph = document.createElement('p');
                error.className = 'facility-field-error';
                error.id = `facility-code-live-error-${++nextId}`;
                error.dataset.facilityCodeLiveError = '';
                error.setAttribute('role', 'alert');
                paragraph.textContent = message;
                error.append(paragraph);
                group.append(error);
                control.setCustomValidity(message);
                describe(control, error);
                scheduleSummary(form);
            };

            const checkAvailability = async (value) => {
                request?.abort();
                const controller = new AbortController();
                request = controller;
                const parameters = new URLSearchParams({ facility_code: value });
                if (form.dataset.facilityId) {
                    parameters.set('exclude_facility', form.dataset.facilityId);
                }

                try {
                    const response = await fetch(`${endpoint}?${parameters}`, {
                        credentials: 'same-origin',
                        headers: { Accept: 'application/json' },
                        signal: controller.signal,
                    });
                    const contentType = response.headers.get('content-type') || '';
                    if (!response.ok || !contentType.includes('application/json')) {
                        throw new Error('Facility code check unavailable');
                    }
                    const result = await response.json();
                    if (controller.signal.aborted || control.value.trim() !== value) return;
                    checkedValue = value;
                    if (result.exists) showDuplicateError();
                    else clearLiveError();
                } catch (error) {
                    if (error.name !== 'AbortError') {
                        checkedValue = null;
                        clearLiveError();
                    }
                }
            };

            control.addEventListener('input', () => {
                const value = control.value.trim();
                window.clearTimeout(debounceTimer);
                request?.abort();
                clearStaleServerError();

                if (!value) {
                    checkedValue = null;
                    clearLiveError();
                    return;
                }

                if (value !== checkedValue) clearLiveError();
                debounceTimer = window.setTimeout(
                    () => checkAvailability(value),
                    450,
                );
            });
        });
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
    initializeFacilityCodeChecks(document);
    document.addEventListener('workspace:form-ready', (event) => {
        initialize(event.target);
        initializeFacilityCodeChecks(event.target);
    });
})();
