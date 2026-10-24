/* Confirm the existing CSRF-protected logout POST without changing its endpoint. */
(() => {
    'use strict';
    const dialog = document.getElementById('signout-confirmation');
    if (!dialog) return;
    let pendingForm = null;
    let pendingSubmitter = null;
    let confirmed = null;
    const confirm = dialog.querySelector('[data-signout-confirm]');
    document.querySelectorAll('form[data-signout]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            if (confirmed === form) { confirmed = null; return; }
            if (typeof dialog.showModal !== 'function') {
                if (!window.confirm('Sign out of Spasyo?')) event.preventDefault();
                return;
            }
            event.preventDefault();
            pendingForm = form;
            pendingSubmitter = event.submitter;
            confirm.disabled = false;
            dialog.showModal();
        });
    });
    dialog.querySelector('[data-signout-close]').addEventListener('click', () => dialog.close());
    confirm.addEventListener('click', () => {
        if (!pendingForm || confirm.disabled) return;
        const form = pendingForm;
        const submitter = pendingSubmitter;
        confirmed = form;
        confirm.disabled = true;
        dialog.close();
        form.requestSubmit(submitter || undefined);
    });
    dialog.addEventListener('close', () => { pendingForm = null; pendingSubmitter = null; });
})();
