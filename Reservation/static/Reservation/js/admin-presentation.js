/* Administrator presentation only. No requests, business decisions, or stored data. */
(() => {
    'use strict';

    // Keep keyboard navigation inside the existing account/archive dialogs.
    // Their original open, close, Escape, and submit handlers remain unchanged.
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Tab') return;
        const modal = document.querySelector('.admin-modal-backdrop:not([hidden]) .admin-modal');
        if (!modal) return;
        const controls = [...modal.querySelectorAll('a[href], button, input, select, textarea, [tabindex="0"]')]
            .filter((control) => !control.disabled && control.getClientRects().length);
        if (!controls.length) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!modal.contains(document.activeElement)) {
            event.preventDefault();
            first.focus();
        } else if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });

    const dialog = document.getElementById('admin-action-confirmation');
    if (!dialog || typeof dialog.showModal !== 'function') return;

    const title = dialog.querySelector('#admin-action-title');
    const context = dialog.querySelector('#admin-action-context');
    const record = dialog.querySelector('[data-confirm-record]');
    const details = dialog.querySelector('[data-confirm-details]');
    const description = dialog.querySelector('#admin-action-description');
    const confirmButton = dialog.querySelector('[data-admin-confirm-submit]');
    let pendingAction = null;
    let pendingOptions = null;
    let confirmedForm = null;

    // Shared presentation for archive handlers; their original submit callbacks stay intact.
    const open = (options) => {
        pendingAction = options.onConfirm;
        pendingOptions = options;
        title.textContent = options.title;
        record.textContent = options.record || '';
        details.textContent = options.details || '';
        details.hidden = !options.details;
        context.hidden = !options.record && !options.details;
        description.textContent = options.description ?? 'Confirm to submit this action, or go back to review your changes.';
        description.hidden = !description.textContent;
        confirmButton.textContent = options.actionLabel || 'Confirm';
        dialog.showModal();
        return true;
    };
    window.SpasyoConfirm = { open };

    // Retain each original inline confirmation as the no-JavaScript fallback.
    // Only enhance the existing simple confirm() forms, leaving other handlers alone.
    const enhancedForms = new WeakSet();
    const initialize = (root) => {
        const forms = root.matches?.('form[onsubmit]') ? [root] : root.querySelectorAll('form[onsubmit]');
        forms.forEach((form) => {
            if (enhancedForms.has(form)) return;
            const original = form.getAttribute('onsubmit');
            const match = original.match(/^\s*return confirm\((['"])(.*?)\1\);?\s*$/);
            if (!match) return;
            enhancedForms.add(form);

            form.onsubmit = null;
            form.addEventListener('submit', (event) => {
                if (confirmedForm === form) {
                    confirmedForm = null;
                    return;
                }
                event.preventDefault();
                const submitter = event.submitter;
                open({
                    title: match[2],
                    record: form.dataset.confirmRecord || document.querySelector('.reservation-panel-header h2')?.textContent.trim()
                        || document.querySelector('.content h1')?.textContent.trim() || '',
                    details: form.dataset.confirmDetails,
                    actionLabel: form.dataset.confirmAction || submitter?.textContent.trim() || 'Confirm',
                    onConfirm: () => {
                        confirmedForm = form;
                        // Retain validation, the original method/action, and submitter values.
                        form.requestSubmit(submitter || undefined);
                    }
                });
            });
        });
    };
    initialize(document);
    document.addEventListener('workspace:form-ready', (event) => initialize(event.target));

    dialog.querySelector('[data-admin-confirm-close]').addEventListener('click', () => dialog.close());
    confirmButton.addEventListener('click', () => {
        if (!pendingAction) return;
        const action = pendingAction;
        const options = pendingOptions;
        pendingAction = null;
        dialog.close();
        if (window.SpasyoNotifications && /archive|activate|cancel/i.test(`${options?.title} ${options?.actionLabel}`)) {
            window.SpasyoNotifications.deferAction({ label: options.actionLabel || 'Action', record: options.record, action });
        } else action();
    });
    dialog.addEventListener('close', () => {
        pendingAction = null;
        pendingOptions = null;
    });
})();
