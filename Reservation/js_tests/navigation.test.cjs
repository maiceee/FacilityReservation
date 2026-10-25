const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../static/Reservation/js/workspace.js'), 'utf8');

function click(overrides = {}, attributes = {}) {
    let handler, prevented = false;
    const link = { href: 'https://campus.test/manage/', target: '',
        hasAttribute: key => Boolean(attributes[key]), closest: () => null, ...attributes };
    const document = {
        querySelectorAll: () => [], getElementById: () => null,
        addEventListener: (name, callback) => { if (name === 'click') handler = callback; }
    };
    vm.runInNewContext(code, { document, HTMLElement: class {}, location: { href: 'https://campus.test/manage/' } });
    handler({ button: 0, target: { closest: () => link },
        preventDefault: () => { prevented = true; }, ...overrides });
    return prevented;
}

test('clicking the current sidebar destination avoids a redundant document load', () => {
    assert.equal(click(), true);
});

test('different destinations, queries and fragments retain ordinary navigation', () => {
    for (const suffix of ['reports/', '?search=room', '#details']) {
        assert.equal(click({}, { href: `https://campus.test/manage/${suffix}` }), false);
    }
});

test('modified clicks, editor links, downloads and earlier guards remain intact', () => {
    for (const override of [{ button: 1 }, { ctrlKey: true }, { metaKey: true },
                            { shiftKey: true }, { altKey: true }, { defaultPrevented: true }]) {
        assert.equal(click(override), false);
    }
    for (const attrs of [{ 'data-edit-dialog': true }, { download: true }, { target: '_blank' }]) {
        assert.equal(click({}, attrs), false);
    }
});
