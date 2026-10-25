/* One workspace editor for protected admin/user forms. The server owns all
   validation and success destinations; failed saves never discard the form. */
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
        facility: '',
        closure: 'Block a facility for maintenance or another unavailable period.',
        reservation: '',
        profile: 'Update your personal information. Account details are read-only.',
        settings: 'Set the booking limits used across campus reservations.',
        reschedule: 'Choose a new schedule and explain the change.',
        simple: ''
    };
    const fieldHints = {
        is_active: 'Inactive items cannot be selected.',
        facility_code: 'Must be unique.',
        capacity: 'Maximum number of people.',
        closing_time: 'Reservations must finish within opening hours.',
        end_datetime: 'Must follow the start time and stay within facility hours.',
        expected_attendees: 'Must not exceed facility capacity.',
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
    let saving = false;
    let activeForm = null;
    let baseline = '';
    let hasRejectedEntries = false;
    const discardDialog = document.getElementById('editor-discard-dialog');
    let returnFocus = null;
    // Compare actual values, so changing a field back does not leave it dirty.
    // No draft data is persisted to browser storage.
    const values = (form) => JSON.stringify([...form.elements].filter((control) => control.name
        && !['hidden', 'submit', 'button', 'reset'].includes(control.type) && !control.disabled)
        .map((control) => [control.name, ['checkbox', 'radio'].includes(control.type)
            ? control.checked : control.tagName === 'SELECT' && control.multiple
                ? [...control.selectedOptions].map((option) => option.value) : control.value]));
    const dirty = () => Boolean(activeForm && (hasRejectedEntries || values(activeForm) !== baseline));
    const requestClose = () => {
        if (saving) return;
        if (!dirty()) { dialog.close(); return; }
        if (!discardDialog) return;
        if (!discardDialog.open) {
            returnFocus = document.activeElement;
            discardDialog.showModal();
            discardDialog.querySelector('[data-keep-editing]').focus();
        }
    };
    window.SpasyoEditor = { requestClose };
    if (discardDialog) {
        discardDialog.querySelector('[data-keep-editing]').addEventListener('click', () => discardDialog.close());
        discardDialog.querySelector('[data-discard-edits]').addEventListener('click', () => {
            activeForm = null;
            discardDialog.close();
            dialog.close();
        });
        discardDialog.addEventListener('close', () => {
            if (dialog.open && returnFocus?.isConnected) returnFocus.focus();
        });
    }
    window.addEventListener('beforeunload', (event) => {
        if (!saving && !dirty()) return;
        event.preventDefault();
        event.returnValue = '';
    });
    const formSelector = 'form.master-detail-form, form.facility-detail-form, form.closures-detail-form, form.user-reservation-form, form.system-settings-form, form.rv-stacked-form';
    const headers = { 'X-Spasyo-Editor': '1' };
    const editorRoutes = [
        [/^\/manage\/categories\/(?:add|\d+\/edit)\/$/, 'category'],
        [/^\/manage\/amenities\/(?:add|\d+\/edit)\/$/, 'amenity'],
        [/^\/manage\/facilities\/(?:add|\d+\/edit)\/$/, 'facility'],
        [/^\/manage\/closures\/add\/$/, 'closure'],
        [/^\/manage\/settings\/$/, 'settings'],
        [/^\/manage\/reservations\/\d+\/reschedule\/$/, 'reschedule'],
        [/^\/portal\/reservations\/request\/$/, 'reservation'],
        [/^\/portal\/profile\/$/, 'profile']
    ];
    const kindFor = (url) => url.origin === location.origin
        ? editorRoutes.find(([pattern]) => pattern.test(url.pathname))?.[1] : null;
    const clearEditorURL = () => {
        const url = new URL(location.href);
        if (!url.searchParams.has('editor')) return;
        url.searchParams.delete('editor');
        history.replaceState(history.state, '', url);
    };
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

    dialog.querySelector('[data-edit-close]').addEventListener('click', requestClose);
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); requestClose(); });
    dialog.addEventListener('close', () => {
        activeForm = null;
        hasRejectedEntries = false;
        request?.abort();
        request = null;
        const cleanup = () => body.replaceChildren();
        if (window.SpasyoMotion) window.SpasyoMotion.afterClose(dialog, cleanup);
        else cleanup();
        body.setAttribute('aria-busy', 'false');
        clearEditorURL();
        if (launcher?.isConnected) launcher.focus();
        else {
            const heading = document.querySelector('main h1');
            if (heading) { heading.tabIndex = -1; heading.focus(); }
        }
    });

    const installForm = (page, original, action) => {
        // Closure conflict details and profile account details sit outside the
        // form. Import their shared content too, including bound error states.
        const source = page.querySelector('[data-editor-content]') || original;
        const content = document.importNode(source, true);
        uniqueIds(content);
        const form = content.matches('form') ? content : content.querySelector('form');
        form.action = action;
        form.querySelectorAll('input[type="checkbox"][name="is_active"]').forEach((control) => control.setAttribute('role', 'switch'));
        if (form.classList.contains('facility-detail-form')) {
            const capacity = form.querySelector('[name="capacity"]')?.closest('.facility-form-group');
            const active = form.querySelector('[name="is_active"]')?.closest('.facility-form-group');
            if (capacity && active) capacity.after(active);
        }
        form.querySelectorAll('.master-cancel-button, .facility-form-cancel, .closures-form-footer a, .user-form-footer a, .rv-form-actions a').forEach((link) => link.remove());
        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'button';
        cancel.dataset.editorCancel = '';
        cancel.textContent = 'Cancel';
        cancel.addEventListener('click', requestClose);
        form.querySelector('.master-form-footer, .facility-form-footer, .closures-form-footer, .user-form-footer, .rv-form-actions, .system-settings-footer')?.prepend(cancel);
        addFieldHints(form);
        normalizeActions(form);
        body.replaceChildren(content);
        form.dispatchEvent(new CustomEvent('workspace:form-ready', { bubbles: true }));
        activeForm = form;
        baseline = values(form);
        hasRejectedEntries = Boolean(form.querySelector('[role="alert"], .errorlist'));
        body.setAttribute('aria-busy', 'false');
        const error = form.querySelector('.ui-validation-summary, [role="alert"], .errorlist');
        if (error) { error.tabIndex = -1; error.focus(); }
        else form.querySelector('input:not([type="hidden"]), select, textarea')?.focus();
        return form;
    };

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
            const response = await fetch(url, { credentials: 'same-origin', headers, signal: controller.signal });
            status = response.status;
            if (!response.ok || new URL(response.url).origin !== location.origin) throw new Error('Editor unavailable');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            const original = page.querySelector(formSelector);
            if (!original || original.method.toLowerCase() !== 'post') throw new Error('Editor unavailable');
            if (!dialog.open || controller.signal.aborted) return;
            title.textContent = page.querySelector('main h1')?.textContent.trim() || title.textContent;
            installForm(page, original, new URL(original.getAttribute('action') || response.url, response.url).href);
        } catch (error) {
            if (error.name === 'AbortError' || controller.signal.aborted || !dialog.open || request !== controller) return;
            body.setAttribute('aria-busy', 'false');
            const panel = document.createElement('div');
            panel.className = 'editor-load-error';
            panel.setAttribute('role', 'alert');
            panel.tabIndex = -1;
            const message = document.createElement('p');
            message.textContent = status === 403 ? 'You no longer have access to this form. Close the dialog and refresh the workspace.'
                : status === 404 ? 'This form is no longer available. Return to the list and refresh it.'
                : 'The form could not load. Try again or close the dialog to return to the workspace.';
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
            panel.append(message, actions);
            body.replaceChildren(panel);
            panel.focus();
        }
    };
    const openEditor = (url, link = null) => {
        const kind = kindFor(url);
        if (!kind || saving) return;
        if (dialog.open && dirty()) { activeForm.querySelector('input:not([type="hidden"]), select, textarea')?.focus(); return; }
        launcher = link;
        dialog.dataset.editor = kind;
        description.textContent = descriptions[kind];
        title.textContent = link?.dataset.editorTitle || link?.getAttribute('aria-label') || 'Loading form…';
        if (!dialog.open) dialog.showModal();
        loadForm(url);
    };
    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[data-edit-dialog]');
        if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const url = new URL(link.href, location.href);
        if (!kindFor(url)) return;
        event.preventDefault();
        openEditor(url, link);
    });

    document.addEventListener('submit', async (event) => {
        const form = event.target;
        if (event.defaultPrevented || !form.closest('#table-edit-dialog') || !form.matches(formSelector)) return;
        event.preventDefault();
        if (saving) return;
        // Build the payload before disabling anything, preserving submitter values.
        const payload = new FormData(form);
        if (event.submitter?.name) payload.append(event.submitter.name, event.submitter.value);
        const endpoint = new URL(form.action);
        if (!kindFor(endpoint)) return;
        saving = true;
        form.dataset.saving = 'true';
        form.setAttribute('aria-busy', 'true');
        form.querySelector('.editor-save-error')?.remove();
        const buttons = [...form.querySelectorAll('button')].map((button) => ({
            button, disabled: button.disabled, content: [...button.childNodes].map((node) => node.cloneNode(true))
        }));
        const fields = [...form.querySelectorAll('input, select, textarea')].map((control) => ({
            control, disabled: control.disabled
        }));
        fields.forEach(({ control }) => { control.disabled = true; });
        buttons.forEach(({ button }) => { button.disabled = true; });
        const submit = event.submitter || form.querySelector('button[type="submit"]');
        if (submit) { submit.textContent = 'Saving…'; submit.setAttribute('aria-busy', 'true'); }
        const close = dialog.querySelector('[data-edit-close]');
        close.disabled = true;
        try {
            const response = await fetch(endpoint, { method: 'POST', credentials: 'same-origin', headers, body: payload });
            // The server returns a save receipt instead of following the success
            // redirect inside fetch. Its flash message survives the next GET.
            if (!response.ok || response.redirected || new URL(response.url).origin !== location.origin) throw new Error('Save could not be confirmed');
            if ((response.headers.get('Content-Type') || '').includes('application/json')) {
                const receipt = await response.json();
                if (receipt.saved !== true || typeof receipt.redirect_url !== 'string' || !receipt.redirect_url.trim()) throw new Error('Save could not be confirmed');
                const destination = new URL(receipt.redirect_url, location.href);
                if (destination.origin !== location.origin) throw new Error('Save could not be confirmed');
                // Profile/settings return to the current workspace. Directory
                // saves retain the list's filters and pagination when possible.
                const current = new URL(location.href);
                current.searchParams.delete('editor');
                const stay = ['profile', 'settings'].includes(dialog.dataset.editor) || destination.pathname === current.pathname;
                activeForm = null;
                hasRejectedEntries = false;
                saving = false;
                dialog.close();
                location.assign(stay ? current.href : destination.href);
                return;
            }
            if (new URL(response.url).pathname !== endpoint.pathname) throw new Error('Save could not be confirmed');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            const original = page.querySelector(formSelector);
            if (!original?.querySelector('[role="alert"], .errorlist')) throw new Error('Save could not be confirmed');
            installForm(page, original, endpoint.href);
        } catch (_) {
            const error = document.createElement('div');
            error.className = 'ui-validation-summary editor-save-error';
            error.setAttribute('role', 'alert');
            error.tabIndex = -1;
            const text = document.createElement('p');
            text.textContent = 'We couldn’t confirm this save. Your entries are still here. Check the workspace before submitting again.';
            const review = document.createElement('a');
            const workspace = new URL(location.href);
            workspace.searchParams.delete('editor');
            review.href = workspace.href;
            review.textContent = 'Check workspace';
            error.append(text, review);
            form.prepend(error);
            error.focus();
        } finally {
            saving = false;
            form.dataset.saving = 'false';
            form.removeAttribute('aria-busy');
            fields.forEach(({ control, disabled }) => { control.disabled = disabled; });
            buttons.forEach(({ button, disabled, content }) => {
                button.disabled = disabled;
                button.replaceChildren(...content);
            });
            submit?.removeAttribute('aria-busy');
            close.disabled = false;
        }
    });

    // Direct form URLs arrive at their workspace with a server-generated editor
    // query parameter. Only known same-origin form routes may open a dialog.
    const initial = new URL(location.href).searchParams.get('editor');
    if (initial) {
        try {
            const url = new URL(initial, location.href);
            if (kindFor(url)) openEditor(url);
            else clearEditorURL();
        } catch (_) { clearEditorURL(); }
    }
})();
