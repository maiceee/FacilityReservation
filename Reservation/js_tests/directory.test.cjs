const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../static/Reservation/js/directory.js'), 'utf8');

function fixture(states) {
    const rows = states.map((active, i) => ({ value: `${i + 1}:${+active}`, dataset: { name: `Record ${i + 1}` }, checked: true, addEventListener() {} }));
    const actions = ['activate', 'deactivate'].map(value => ({ value }));
    const handlers = {}, events = {}, inputs = [], count = {};
    let confirmation, pending = false, subscriber, submissions = 0;
    const all = { addEventListener() {} };
    const form = {
        querySelectorAll: selector => selector === '[data-bulk-action]' ? actions : [],
        querySelector: () => count,
        addEventListener: (name, callback) => { handlers[name] = callback; },
        append: input => inputs.push(input), submit: () => { submissions++; }
    };
    const document = {
        querySelector: selector => selector === '[data-bulk-form]' ? form : selector === '[data-select-page]' ? all : null,
        querySelectorAll: () => rows,
        createElement: () => ({ dataset: {} })
    };
    const window = {
        addEventListener: (name, callback) => { events[name] = callback; },
        SpasyoNotifications: { hasPendingAction: () => pending, subscribePending: callback => { subscriber = callback; } },
        SpasyoConfirm: { open: options => { confirmation = options; return true; } }
    };
    vm.runInNewContext(code, { document, window });
    return {
        rows, actions, inputs,
        get confirmation() { return confirmation; },
        get submissions() { return submissions; },
        submit: value => handlers.submit({ preventDefault() {}, submitter: { value } }),
        setPending: value => { pending = value; subscriber(); },
        refresh: () => events.pageshow()
    };
}

test('active-only, inactive-only and empty selections enable only applicable actions', () => {
    for (const [states, expected] of [[[true, true], [true, false]], [[false, false], [false, true]], [[], [true, true]]]) {
        const f = fixture(states);
        assert.deepEqual(f.actions.map(action => action.disabled), expected);
        f.submit(states[0] ? 'activate' : 'deactivate');
        assert.equal(f.confirmation, undefined);
    }
});

test('mixed selection confirms and posts only affected rows, with a stable snapshot', () => {
    const f = fixture([true, false, false]);
    assert.deepEqual(f.actions.map(action => action.disabled), [false, false]);
    f.submit('activate');
    assert.equal(f.confirmation.title, 'Activate 2 records?');
    assert.equal(f.confirmation.record, 'Record 2, Record 3');
    assert.equal(f.confirmation.description, '1 already active will stay unchanged.');
    f.rows.forEach(row => { row.checked = false; });
    f.confirmation.onConfirm();
    f.confirmation.onConfirm();
    assert.equal(f.submissions, 1);
    assert.deepEqual(f.inputs.map(input => [input.name, input.value]), [['selected', '2:0'], ['selected', '3:0'], ['operation', 'activate']]);
});

test('pending action locks both controls and Undo unlocks only applicable actions', () => {
    const f = fixture([true]);
    f.setPending(true);
    assert.deepEqual(f.actions.map(action => action.disabled), [true, true]);
    f.submit('deactivate');
    assert.equal(f.confirmation, undefined);
    f.setPending(false);
    assert.deepEqual(f.actions.map(action => action.disabled), [true, false]);
    f.submit('deactivate');
    assert.equal(f.confirmation.description, '');
    assert.equal(f.confirmation.record, 'Record 1');
});

test('unrecognized operations cannot open a confirmation', () => {
    const f = fixture([true, false]);
    f.submit('delete');
    assert.equal(f.confirmation, undefined);
    assert.equal(f.submissions, 0);
});
