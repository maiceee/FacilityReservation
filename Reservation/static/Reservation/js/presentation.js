/* Presentation only: no requests, business rules, or stored data. */
(() => {
    'use strict';

    // Keep Django's error messages associated with their own controls.
    document.querySelectorAll('.field').forEach((field) => {
        const control = field.querySelector('input, select, textarea');
        const error = field.querySelector('.field-error');
        if (!control || !error) return;
        control.setAttribute('aria-invalid', 'true');
        const describedBy = new Set((control.getAttribute('aria-describedby') || '').split(' ').filter(Boolean));
        describedBy.add(error.id);
        control.setAttribute('aria-describedby', [...describedBy].join(' '));
    });

    // Preserve the existing sign-in password visibility control.
    document.querySelectorAll('.password-toggle').forEach((toggle) => {
        const password = document.getElementById(toggle.getAttribute('aria-controls'));
        if (!password) return;
        toggle.addEventListener('click', () => {
            const reveal = password.type === 'password';
            password.type = reveal ? 'text' : 'password';
            toggle.textContent = reveal ? 'Hide' : 'Show';
            toggle.setAttribute('aria-pressed', String(reveal));
            password.focus();
        });
    });

    // Replace the browser confirmation with the Figma dialog.
    // The original form still submits to the same protected POST endpoint.
    const cancelForm = document.querySelector('[data-confirm-cancellation]');
    const dialog = document.getElementById('cancel-confirmation');
    if (!cancelForm || !dialog) return;
    cancelForm.dataset.confirmationReady = 'true';
    let confirmed = false;
    let pending = false;
    let submitter = null;
    cancelForm.addEventListener('submit', (event) => {
        if (confirmed) return;
        if (typeof dialog.showModal !== 'function') {
            if (!window.confirm('Are you sure you want to cancel this reservation?')) event.preventDefault();
            return;
        }
        event.preventDefault();
        pending = true;
        submitter = event.submitter;
        dialog.showModal();
    });
    dialog.querySelector('[data-dialog-close]').addEventListener('click', () => dialog.close());
    dialog.querySelector('[data-confirm-submit]').addEventListener('click', () => {
        if (!pending) return;
        pending = false;
        dialog.close();
        const action = () => {
            confirmed = true;
            cancelForm.requestSubmit(submitter || undefined);
        };
        if (window.SpasyoNotifications) window.SpasyoNotifications.deferAction({ label: 'Cancel reservation', record: document.querySelector('h1')?.textContent.trim(), action });
        else action();
    });
    dialog.addEventListener('close', () => { pending = false; });
    window.addEventListener('pageshow', () => { confirmed = false; pending = false; submitter = null; });
})();
