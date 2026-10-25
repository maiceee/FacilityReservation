/* Selection is deliberately limited to the displayed page (25 records). */
(() => {
    const form = document.querySelector('[data-bulk-form]');
    if (!form) return;
    const rows = [...document.querySelectorAll('[data-select-record]')];
    const all = document.querySelector('[data-select-page]');
    const actions = [...form.querySelectorAll('[data-bulk-action]')];
    let submitting = false;
    const selected = () => rows.filter(row => row.checked);
    const applies = (row, operation) => row.value.endsWith(operation === 'activate' ? ':0' : ':1');
    const refresh = () => {
        const count = selected().length;
        form.querySelector('[data-selection-count]').textContent = count ? `${count} selected · this page only` : 'Select records on this page';
        const busy = submitting || Boolean(window.SpasyoNotifications?.hasPendingAction());
        actions.forEach(button => {
            button.disabled = busy || !selected().some(row => applies(row, button.value));
        });
        if (all) { all.checked = count > 0 && count === rows.length; all.indeterminate = count > 0 && count < rows.length; }
    };
    all?.addEventListener('change', () => { rows.forEach(row => { row.checked = all.checked; }); refresh(); });
    rows.forEach(row => row.addEventListener('change', refresh));
    window.SpasyoNotifications?.subscribePending(refresh);
    window.addEventListener('pageshow', () => { submitting = false; refresh(); });
    refresh();
    form.addEventListener('submit', event => {
        event.preventDefault();
        if (submitting || window.SpasyoNotifications?.hasPendingAction() || !event.submitter) return;
        const operation = event.submitter.value;
        if (!['activate', 'deactivate'].includes(operation)) return;
        const selection = selected().filter(row => applies(row, operation))
            .map(row => ({ value: row.value, name: row.dataset.name }));
        if (!selection.length) return;
        const skipped = selected().length - selection.length;
        const label = operation === 'activate' ? 'Activate' : 'Deactivate';
        // Snapshot IDs + expected status at confirmation, never read a later selection.
        const submit = () => {
            if (submitting) return;
            submitting = true;
            form.querySelectorAll('[data-bulk-snapshot]').forEach(node => node.remove());
            rows.forEach(row => { row.disabled = true; });
            for (const [name, value] of [...selection.map(row => ['selected', row.value]), ['operation', operation]]) {
                const input = document.createElement('input');
                input.type = 'hidden'; input.name = name; input.value = value;
                input.dataset.bulkSnapshot = 'true'; form.append(input);
            }
            actions.forEach(button => { button.disabled = true; });
            form.submit();
        };
        const options = {
            title: `${label} ${selection.length} ${selection.length === 1 ? 'record' : 'records'}?`,
            record: selection.map(row => row.name).join(', '),
            description: skipped ? `${skipped} already ${operation === 'activate' ? 'active' : 'inactive'} will stay unchanged.` : '',
            actionLabel: label, onConfirm: submit
        };
        if (!window.SpasyoConfirm?.open(options) && window.confirm(`${options.title}\n${options.record}`)) submit();
    });
})();

(() => {
    const filter = document.querySelector('.report-facility-filter');
    if (!filter) return;
    filter.querySelector('[data-report-search]').addEventListener('input', event => {
        const query = event.target.value.trim().toLowerCase();
        filter.querySelectorAll('[data-report-option]').forEach(option => { option.hidden = !option.textContent.toLowerCase().includes(query); });
    });
    const countSelection = () => { const count = filter.querySelectorAll('input[type="checkbox"]:checked').length; filter.querySelector('summary span').textContent = count ? `(${count})` : '(All)'; };
    filter.addEventListener('change', countSelection);
    filter.querySelector('[data-report-clear]').addEventListener('click', () => {
        filter.querySelectorAll('input[type="checkbox"]').forEach(input => { input.checked = false; });
        countSelection();
    });
    document.addEventListener('click', event => { if (!filter.contains(event.target)) filter.open = false; });
    filter.addEventListener('keydown', event => { if (event.key === 'Escape') { filter.open = false; filter.querySelector('summary').focus(); } });
})();
