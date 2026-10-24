/* Existing protected forms in a native dialog. Directory/reservation saves retain
   full-page submission; profile/settings display the same HTML responses in place. */
(() => {
    'use strict';
    const normalizeActions = (root) => {
        root.querySelectorAll('.master-form-footer, .facility-form-footer, .closures-form-footer, .user-form-footer, .rv-form-actions, .system-settings-footer, .dialog-actions, .admin-modal-footer, .admin-confirm-actions').forEach((footer) => {
            footer.classList.add('modal-form-actions');
            footer.querySelectorAll('button[type="submit"]').forEach((button) => {
                button.classList.add('button', 'button-primary');
                button.querySelectorAll('svg.icon').forEach((icon) => icon.remove());
            });
        });
    };
    normalizeActions(document);
    const descriptions = {
        amenity: 'Name the equipment or service available with a campus facility.',
        category: 'Use a clear category to group similar campus spaces.',
        facility: 'Set the space details, opening hours, and available amenities.',
        closure: 'Block a facility for maintenance or another unavailable period.',
        reservation: 'Choose a facility and schedule. Your request needs administrator approval.',
        profile: 'Update your personal information. Account details are read-only.',
        settings: 'Set the booking limits used across campus reservations.',
        simple: 'Review the details below. Fields marked * are required.'
    };
    const fieldHints = {
        name: 'Choose a clear, recognizable name.',
        is_active: 'Keep this on to make the item available for selection.',
        facility_code: 'Use a unique code, such as ROOM-101.',
        category: 'Select the group this space belongs to.',
        location: 'Include the building and floor so users can find it.',
        capacity: 'Maximum number of people the space can hold.',
        description: 'Briefly describe the space and its intended use.',
        opening_time: 'Earliest time the space is available.',
        closing_time: 'Reservations must finish within opening hours.',
        amenities: 'Select the equipment and services provided.',
        facility: 'Choose the campus space you want to reserve.',
        event_name: 'Use a short title that identifies your event.',
        start_datetime: 'Use Philippine local date and time.',
        end_datetime: 'Choose a time after the start, within facility hours.',
        expected_attendees: 'Include everyone attending; stay within facility capacity.',
        purpose: 'Explain the activity and how the space will be used.'
    };
    const addFieldHints = (form) => {
        form.querySelectorAll('input[name]:not([type="hidden"]), select[name], textarea[name]').forEach((control) => {
            const group = control.closest('.field, .master-form-group, .facility-form-group, .closures-form-group');
            if (!group) return;
            let help = group.querySelector('.field-help, .master-field-help, .facility-field-help, .closures-field-help, .ui-field-help');
            if (!help && fieldHints[control.name]) {
                help = document.createElement('div');
                help.className = 'ui-field-help';
                help.id = `editor-help-${control.name}`;
                help.textContent = fieldHints[control.name];
                group.append(help);
            }
            if (help?.id) {
                const ids = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
                ids.add(help.id);
                control.setAttribute('aria-describedby', [...ids].join(' '));
            }
        });
    };
    document.querySelectorAll('input[type="checkbox"][name="is_active"]').forEach((control) => {
        control.setAttribute('role', 'switch');
    });
    const dialog = document.getElementById('table-edit-dialog');
    if (!dialog || typeof dialog.showModal !== 'function') return;
    const body = dialog.querySelector('[data-edit-body]');
    const title = dialog.querySelector('#table-edit-title');
    const description = dialog.querySelector('#table-edit-description');
    let request = null;
    let launcher = null;
    let importedId = 0;
    const uniqueIds = (root) => {
        const ids = new Map();
        root.querySelectorAll('[id]').forEach((element) => {
            if (!document.getElementById(element.id)) return;
            const old = element.id;
            element.id = `editor-${++importedId}-${old}`;
            ids.set(old, element.id);
        });
        root.querySelectorAll('[for], [aria-describedby], [aria-labelledby], [aria-controls], a[href^="#"]').forEach((element) => {
            ['for', 'aria-describedby', 'aria-labelledby', 'aria-controls'].forEach((name) => {
                const value = element.getAttribute(name);
                if (value) element.setAttribute(name, value.split(/\s+/).map((id) => ids.get(id) || id).join(' '));
            });
            const href = element.getAttribute('href');
            if (href?.startsWith('#') && ids.has(href.slice(1))) element.setAttribute('href', `#${ids.get(href.slice(1))}`);
        });
    };

    dialog.querySelector('[data-edit-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => {
        request?.abort();
        request = null;
        const cleanup = () => body.replaceChildren();
        if (window.SpasyoMotion) window.SpasyoMotion.afterClose(dialog, cleanup);
        else cleanup();
        body.setAttribute('aria-busy', 'false');
        launcher?.focus();
    });

    const loadForm = async (url) => {
        request?.abort();
        const loading = document.createElement('p');
        loading.setAttribute('role', 'status');
        loading.textContent = 'Loading form…';
        body.replaceChildren(loading);
        body.setAttribute('aria-busy', 'true');
        if (dialog.open) dialog.querySelector('[data-edit-close]').focus();
        const controller = new AbortController();
        request = controller;
        let status = 0;
        try {
            const response = await fetch(url, { credentials: 'same-origin', signal: controller.signal });
            status = response.status;
            if (!response.ok || new URL(response.url).origin !== location.origin) throw new Error('Editor unavailable');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            const original = page.querySelector('form.master-detail-form, form.facility-detail-form, form.closures-detail-form, form.user-reservation-form, form.system-settings-form');
            if (!original || original.method.toLowerCase() !== 'post') throw new Error('Editor unavailable');
            if (!dialog.open || controller.signal.aborted) return;
            const originalContent = dialog.dataset.editor === 'profile' ? page.querySelector('[data-editor-content]') || original : original;
            const content = document.importNode(originalContent, true);
            uniqueIds(content);
            const form = content.matches('form') ? content : content.querySelector('form');
            form.action = new URL(original.getAttribute('action') || response.url, response.url).href;
            form.querySelectorAll('input[type="checkbox"][name="is_active"]').forEach((control) => {
                control.setAttribute('role', 'switch');
            });
            if (form.classList.contains('facility-detail-form')) {
                const capacity = form.querySelector('[name="capacity"]')?.closest('.facility-form-group');
                const active = form.querySelector('[name="is_active"]')?.closest('.facility-form-group');
                if (capacity && active) capacity.after(active);
            }
            if (form.classList.contains('closures-detail-form')) {
                // Retain the full-page closure form's existing busy-button feedback.
                form.addEventListener('submit', () => {
                    if (!form.checkValidity()) return;
                    const submit = form.querySelector('#closure-submit-button');
                    submit.disabled = true;
                    submit.textContent = 'Creating…';
                });
            }
            form.querySelectorAll('.master-cancel-button, .facility-form-cancel, .closures-form-footer a, .user-form-footer a').forEach((link) => {
                const cancel = document.createElement('button');
                cancel.type = 'button';
                cancel.className = 'button';
                cancel.textContent = 'Cancel';
                cancel.addEventListener('click', () => dialog.close());
                link.replaceWith(cancel);
            });
            if (['profile', 'settings'].includes(dialog.dataset.editor)) {
                const cancel = document.createElement('button');
                cancel.type = 'button'; cancel.className = 'button'; cancel.textContent = 'Cancel';
                cancel.addEventListener('click', () => { if (form.dataset.saving !== 'true') dialog.close(); });
                form.querySelector('.user-form-footer, .system-settings-footer')?.prepend(cancel);
            }
            addFieldHints(form);
            normalizeActions(form);
            body.replaceChildren(content);
            form.dispatchEvent(new CustomEvent('workspace:form-ready', { bubbles: true }));
            body.setAttribute('aria-busy', 'false');
            if (!form.contains(document.activeElement)) form.querySelector('input:not([type="hidden"]), select, textarea')?.focus();
        } catch (error) {
            if (error.name === 'AbortError' || controller.signal.aborted || !dialog.open || request !== controller) return;
            body.setAttribute('aria-busy', 'false');
            const panel = document.createElement('div');
            panel.className = 'editor-load-error';
            panel.setAttribute('role', 'alert');
            panel.tabIndex = -1;
            const message = document.createElement('p');
            message.textContent = status === 403 ? 'You no longer have access to this form. Open its page to check your access.'
                : status === 404 ? 'This form is no longer available. Return to the list and refresh it.'
                : 'The form could not load. Try again, or open its page to continue.';
            const actions = document.createElement('div');
            actions.className = 'editor-load-actions';
            const retryable = status !== 403 && status !== 404;
            if (retryable) {
                const retry = document.createElement('button');
                retry.type = 'button';
                retry.className = 'button button-primary';
                retry.textContent = 'Try again';
                retry.addEventListener('click', () => loadForm(url));
                actions.append(retry);
            }
            const fallback = document.createElement('a');
            fallback.href = url.href;
            fallback.className = retryable ? 'button' : 'button button-primary';
            fallback.textContent = 'Open form page';
            actions.append(fallback);
            panel.append(message, actions);
            body.replaceChildren(panel);
            panel.focus();
        }
    };
    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[data-edit-dialog]');
        if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const url = new URL(link.href, location.href);
        if (url.origin !== location.origin) return;
        event.preventDefault();
        launcher = link;
        dialog.dataset.editor = link.dataset.editorKind || (link.classList.contains('facility-edit-button') ? 'facility' : 'simple');
        const kind = url.pathname.includes('/amenities/') ? 'amenity' : url.pathname.includes('/categories/') ? 'category' : dialog.dataset.editor;
        description.textContent = descriptions[kind] || descriptions.simple;
        const heading = link.cloneNode(true);
        heading.querySelectorAll('kbd, [aria-hidden="true"]').forEach((item) => item.remove());
        title.textContent = link.dataset.editorTitle || link.getAttribute('aria-label') || heading.textContent.trim();
        loadForm(url);
        dialog.showModal();
    });

    // These two small editors retain their existing protected POST and HTML
    // validation responses, while keeping the current workspace behind them.
    document.addEventListener('submit', async (event) => {
        const form = event.target;
        if (event.defaultPrevented || !form.closest('#table-edit-dialog') || !['profile', 'settings'].includes(dialog.dataset.editor)) return;
        event.preventDefault();
        if (form.dataset.saving === 'true') return;
        form.dataset.saving = 'true';
        const submit = event.submitter || form.querySelector('button[type="submit"]');
        const label = submit?.textContent;
        const disabled = submit?.disabled;
        if (submit) { submit.disabled = true; submit.textContent = 'Saving…'; submit.setAttribute('aria-busy', 'true'); }
        const close = dialog.querySelector('[data-edit-close]');
        close.disabled = true;
        const preventDismiss = (dismissal) => dismissal.preventDefault();
        dialog.addEventListener('cancel', preventDismiss);
        const payload = new FormData(form);
        if (event.submitter?.name) payload.append(event.submitter.name, event.submitter.value);
        try {
            const response = await fetch(form.action, { method: 'POST', credentials: 'same-origin', body: payload });
            const endpoint = new URL(form.action);
            if (!response.ok || new URL(response.url).origin !== location.origin || new URL(response.url).pathname !== endpoint.pathname) throw new Error('Save could not be confirmed');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            const original = page.querySelector(dialog.dataset.editor === 'settings' ? 'form.system-settings-form' : 'form.user-reservation-form');
            if (!original) throw new Error('Save could not be confirmed');
            if (original.querySelector('[role="alert"], .errorlist')) {
                const content = document.importNode(dialog.dataset.editor === 'profile' ? page.querySelector('[data-editor-content]') || original : original, true);
                uniqueIds(content);
                const bound = content.matches('form') ? content : content.querySelector('form');
                bound.action = form.action;
                const cancel = document.createElement('button');
                cancel.type = 'button'; cancel.className = 'button'; cancel.textContent = 'Cancel';
                cancel.addEventListener('click', () => { if (bound.dataset.saving !== 'true') dialog.close(); });
                bound.querySelector('.modal-form-actions, .user-form-footer, .system-settings-footer')?.prepend(cancel);
                normalizeActions(content);
                body.replaceChildren(content);
                bound.dispatchEvent(new CustomEvent('workspace:form-ready', { bubbles: true }));
                return;
            }
            if (!response.redirected) throw new Error('Save could not be confirmed');
            const name = page.querySelector('.user-topbar-name')?.textContent;
            if (name) document.querySelectorAll('.user-topbar-name').forEach((item) => { item.textContent = name; });
            if (location.pathname === endpoint.pathname) {
                const current = document.querySelector('main .workspace-page');
                const updated = page.querySelector('main .workspace-page');
                if (current && updated) {
                    const replacement = document.importNode(updated, true);
                    current.replaceWith(replacement);
                    replacement.dispatchEvent(new CustomEvent('workspace:form-ready', { bubbles: true }));
                }
            }
            dialog.close();
            window.SpasyoNotifications?.consume(page);
        } catch (_) {
            form.querySelector('.editor-save-error')?.remove();
            const error = document.createElement('div');
            error.className = 'ui-validation-summary editor-save-error';
            error.setAttribute('role', 'alert'); error.tabIndex = -1;
            const text = document.createElement('p');
            text.textContent = 'We couldn’t confirm this save. Your entries are still here. Check the saved values before trying again.';
            const link = document.createElement('a');
            link.href = form.action; link.textContent = 'Open form page';
            error.append(text, link); form.prepend(error); error.focus();
        } finally {
            form.dataset.saving = 'false';
            if (submit) { submit.disabled = disabled; submit.textContent = label; submit.removeAttribute('aria-busy'); }
            close.disabled = false;
            dialog.removeEventListener('cancel', preventDismiss);
        }
    });
})();
