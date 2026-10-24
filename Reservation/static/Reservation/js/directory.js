/* Selection is deliberately limited to the displayed page (25 records). */
(() => {
    const form = document.querySelector('[data-bulk-form]');
    if (!form) return;
    const rows = [...document.querySelectorAll('[data-select-record]')];
    const all = document.querySelector('[data-select-page]');
    const actions = [...form.querySelectorAll('[data-bulk-action]')];
    const selected = () => rows.filter(row => row.checked);
    const refresh = () => {
        const count = selected().length;
        form.querySelector('[data-selection-count]').textContent = count ? `${count} selected · this page only` : 'Select records on this page';
        actions.forEach(button => { button.disabled = !count; });
        if (all) { all.checked = count > 0 && count === rows.length; all.indeterminate = count > 0 && count < rows.length; }
    };
    all?.addEventListener('change', () => { rows.forEach(row => { row.checked = all.checked; }); refresh(); });
    rows.forEach(row => row.addEventListener('change', refresh));
    refresh();
    form.addEventListener('submit', event => {
        event.preventDefault();
        const selection = selected().map(row => ({ value: row.value, name: row.dataset.name }));
        if (!selection.length || !event.submitter) return;
        const operation = event.submitter.value;
        const label = operation === 'activate' ? 'Activate' : 'Deactivate';
        // Snapshot IDs + expected status at confirmation, never read a later selection.
        const submit = () => {
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
            title: `${label} ${selection.length} selected record(s)?`,
            record: `${selection.length} selected record(s)`,
            details: selection.map(row => row.name).join(', '),
            description: 'Only these selected records will change. Existing reservations stay in the system. Already-matching statuses are skipped.',
            actionLabel: label, onConfirm: submit
        };
        if (!window.SpasyoConfirm?.open(options) && window.confirm(`${options.title}\n${options.details}`)) submit();
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
