// Run with: node --test Reservation/js_tests/workspace-editor.test.cjs
// DOM stubs exercise request/state transitions; they do not replace browser QA.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const code = fs.readFileSync(path.join(__dirname, '../static/Reservation/js/table-editor.js'), 'utf8');

class Element {
    constructor() {
        this.dataset = {};
        this.attributes = {};
        this.childNodes = [];
        this.disabled = false;
        this.listeners = {};
        this.classList = { contains: () => false, add() {} };
    }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name] ?? null; }
    removeAttribute(name) { delete this.attributes[name]; }
    addEventListener(name, handler) { this.listeners[name] = handler; }
    querySelectorAll() { return []; }
    querySelector() { return null; }
    append(...items) { this.childNodes.push(...items); }
    prepend(...items) { this.childNodes.unshift(...items); }
    replaceChildren(...items) { this.childNodes = items; }
    focus() { this.focused = true; }
    dispatchEvent() {}
    remove() { this.removed = true; }
}

function harness({ kind = 'reservation', endpoint = '/portal/reservations/request/',
    workspace = '/portal/facilities/', receipt, failure = false, unexpectedRedirect = false,
    errors = true, initial, pause = false, conflictDetails = false, asyncClose = false } = {}) {
    const listeners = {}, windowListeners = {};
    const requests = [];
    const origin = 'http://localhost';
    const body = new Element(), close = new Element(), title = new Element(), description = new Element();
    const error = new Element(), footer = new Element();
    const submit = new Element(), cancel = new Element();
    const icon = { name: 'icon', cloneNode() { return { ...this }; } };
    submit.childNodes = [icon];
    submit.name = 'operation'; submit.value = 'save';
    const field = new Element(), lockedField = new Element();
    lockedField.disabled = true;
    const form = new Element();
    form.elements = [];
    form.action = origin + endpoint;
    form.matches = () => true;
    form.closest = () => dialog;
    form.querySelector = (selector) => selector.includes('submit') ? submit : null;
    form.querySelectorAll = (selector) => selector === 'button' ? [submit, cancel]
        : selector === 'input, select, textarea' ? [field, lockedField] : [];
    const bound = new Element();
    const draftField = {name: 'event_name', value: '', type: 'text'};
    bound.elements = [draftField];
    bound.action = form.action;
    bound.matches = () => true;
    bound.querySelector = (selector) => selector.includes('role=') || selector.includes('errorlist')
        ? (errors ? error : null) : selector.includes('footer') ? footer : null;
    const wrapper = new Element();
    wrapper.matches = () => false;
    wrapper.querySelector = () => bound;
    const original = new Element();
    original.method = 'post';
    original.querySelector = () => errors ? error : null;
    const page = {
        querySelector(selector) {
            if (selector === '[data-editor-content]') return conflictDetails ? wrapper : null;
            if (selector === 'main h1') return { textContent: 'Test editor' };
            return original;
        }
    };
    const keep = new Element(), discard = new Element(), discardDialog = new Element();
    discardDialog.showModal = () => { discardDialog.open = true; };
    discardDialog.close = () => { discardDialog.open = false; discardDialog.listeners.close?.(); };
    discardDialog.querySelector = selector => selector === '[data-keep-editing]' ? keep : discard;
    const dialog = new Element();
    dialog.dataset.editor = kind;
    dialog.open = true;
    dialog.showModal = () => { dialog.open = true; };
    dialog.close = () => { dialog.open = false; if (!asyncClose) dialog.listeners.close?.(); };
    dialog.querySelector = (selector) => ({
        '[data-edit-body]': body, '[data-edit-close]': close,
        '#table-edit-title': title, '#table-edit-description': description
    })[selector];
    const location = {
        origin, href: origin + workspace + (initial ? '?editor=' + encodeURIComponent(initial) : ''),
        assign(value) { this.assigned = value; }
    };
    const history = { replaceState(_, __, url) { location.href = String(url); } };
    let release;
    const pending = pause ? new Promise((resolve) => { release = resolve; }) : Promise.resolve();
    const document = new Element();
    document.addEventListener = (name, handler) => { listeners[name] = handler; };
    document.getElementById = (id) => id === 'table-edit-dialog' ? dialog : id === 'editor-discard-dialog' ? discardDialog : null;
    document.createElement = () => new Element();
    document.importNode = (source) => source === wrapper ? wrapper : bound;
    const response = {
        ok: !failure, status: failure ? 503 : 200, redirected: unexpectedRedirect,
        url: origin + endpoint,
        headers: { get: () => receipt ? 'application/json' : 'text/html' },
        json: async () => receipt, text: async () => ''
    };
    vm.runInNewContext(code, {
        document, location, history, window: {addEventListener: (name, fn) => { windowListeners[name] = fn; }}, URL, AbortController,
        FormData: class { constructor(source) { this.source = source; this.values = []; } append(...args) { this.values.push(args); } },
        CustomEvent: class {}, DOMParser: class { parseFromString() { return page; } },
        fetch: async (url, options) => { requests.push({ url, options }); await pending; return response; }
    });
    const send = () => {
        const event = { target: form, submitter: submit, preventDefault() { this.defaultPrevented = true; } };
        return listeners.submit(event);
    };
    return { windowListeners, draftField, keep, discard, discardDialog, send, release, requests, form, bound, wrapper, body, close, dialog, location, error, submit, cancel, field, lockedField };
}

const editors = [
    ['reservation', '/portal/reservations/request/'], ['profile', '/portal/profile/'],
    ['settings', '/manage/settings/'], ['category', '/manage/categories/add/'],
    ['amenity', '/manage/amenities/1/edit/'], ['facility', '/manage/facilities/add/'],
    ['closure', '/manage/closures/add/'], ['reschedule', '/manage/reservations/1/reschedule/']
];
for (const [kind, endpoint] of editors) {
    test(`${kind}: bound server errors stay in the modal and focus the error`, async () => {
        const h = harness({ kind, endpoint });
        await h.send();
        assert.equal(h.body.childNodes[0], h.bound);
        assert.equal(h.bound.action, 'http://localhost' + endpoint);
        assert.equal(h.error.focused, true);
        assert.equal(h.dialog.open, true);
        assert.equal(h.location.assigned, undefined);
        assert.equal(h.close.disabled, false);
        assert.equal(h.requests[0].options.headers['X-Spasyo-Editor'], '1');
        assert.deepEqual(h.requests[0].options.body.values, [['operation', 'save']]);
        assert.equal(h.submit.childNodes[0].name, 'icon');
    });
}
test('closure conflicts outside the form remain visible in the modal', async () => {
    const h = harness({ kind: 'closure', endpoint: '/manage/closures/add/', conflictDetails: true });
    await h.send();
    assert.equal(h.body.childNodes[0], h.wrapper);
});
test('saving disables Submit, Cancel, Close and Escape; duplicate submission is ignored', async () => {
    const h = harness({ pause: true });
    const saving = h.send();
    assert.equal(h.submit.disabled, true);
    assert.equal(h.cancel.disabled, true);
    assert.equal(h.close.disabled, true);
    assert.equal(h.field.disabled, true);
    let prevented = false;
    h.dialog.listeners.cancel({ preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
    await h.send();
    assert.equal(h.requests.length, 1);
    h.release(); await saving;
    assert.equal(h.submit.disabled, false);
    assert.equal(h.field.disabled, false);
    assert.equal(h.lockedField.disabled, true);
});
test('failed or unexpected responses preserve entries and restore controls', async () => {
    for (const options of [{ failure: true }, { unexpectedRedirect: true }, { errors: false }]) {
        const h = harness(options);
        await h.send();
        assert.equal(h.dialog.open, true);
        assert.equal(h.location.assigned, undefined);
        assert.equal(h.form.childNodes[0].attributes.role, 'alert');
        assert.equal(h.close.disabled, false);
        assert.equal(h.submit.disabled, false);
    }
});
test('confirmed reservation save navigates once to its detail destination', async () => {
    const h = harness({ receipt: { saved: true, redirect_url: '/portal/reservations/42/' } });
    await h.send();
    assert.equal(h.location.assigned, 'http://localhost/portal/reservations/42/');
    assert.equal(h.dialog.open, false);
    assert.equal(h.requests.length, 1);
});
test('directory saves retain filters and remove the direct-link editor parameter', async () => {
    const h = harness({ kind: 'category', endpoint: '/manage/categories/add/',
        workspace: '/manage/categories/?search=Rooms&state=all',
        receipt: { saved: true, redirect_url: '/manage/categories/' } });
    await h.send();
    assert.equal(h.location.assigned, 'http://localhost/manage/categories/?search=Rooms&state=all');
});
test('profile/settings saves return to the workspace behind the modal', async () => {
    for (const [kind, endpoint, workspace] of [
        ['profile', '/portal/profile/', '/portal/'], ['settings', '/manage/settings/', '/manage/']
    ]) {
        const h = harness({ kind, endpoint, workspace, receipt: { saved: true, redirect_url: endpoint } });
        await h.send();
        assert.equal(h.location.assigned, 'http://localhost' + workspace);
    }
});
test('direct links load their form into the workspace modal', async () => {
    const h = harness({ initial: '/portal/reservations/request/?facility=3' });
    await new Promise(setImmediate);
    assert.equal(h.requests.length, 1);
    assert.equal(h.requests[0].url.searchParams.get('facility'), '3');
    assert.equal(h.body.childNodes[0], h.bound);
    h.dialog.close();
    assert.equal(new URL(h.location.href).searchParams.has('editor'), false);
});
test('unrecognized or external editor URLs never load', () => {
    for (const initial of ['https://example.com/portal/profile/', '/logout/']) {
        const h = harness({ initial });
        assert.equal(h.requests.length, 0);
        assert.equal(new URL(h.location.href).searchParams.has('editor'), false);
    }
});
test('malformed save receipts keep the form open instead of navigating', async () => {
    for (const receipt of [{ saved: true }, { saved: true, redirect_url: '' },
        { saved: true, redirect_url: 'https://example.com/' }, { saved: false, redirect_url: '/portal/' }]) {
        const h = harness({ receipt });
        await h.send();
        assert.equal(h.location.assigned, undefined);
        assert.equal(h.dialog.open, true);
        assert.equal(h.field.disabled, false);
        assert.equal(h.form.childNodes[0].attributes.role, 'alert');
    }
});


test('clean and reverted forms close without discard confirmation', async () => {
    for (const revert of [false, true]) {
        const h = harness({ initial: '/portal/reservations/request/', errors: false });
        await new Promise(setImmediate);
        if (revert) { h.draftField.value = 'Changed'; h.draftField.value = ''; }
        h.close.listeners.click();
        assert.equal(h.dialog.open, false);
        assert.equal(Boolean(h.discardDialog.open), false);
    }
});
test('Close and Escape protect changed entries; Keep editing retains them; Discard clears', async () => {
    for (const escape of [false, true]) {
        const h = harness({ initial: '/portal/reservations/request/', errors: false });
        await new Promise(setImmediate);
        h.draftField.value = 'Important draft';
        if (escape) h.dialog.listeners.cancel({preventDefault(){}});
        else h.close.listeners.click();
        assert.equal(h.dialog.open, true);
        assert.equal(h.discardDialog.open, true);
        assert.equal(h.keep.focused, true);
        h.keep.listeners.click();
        assert.equal(h.dialog.open, true);
        assert.equal(h.draftField.value, 'Important draft');
        h.close.listeners.click();
        h.discard.listeners.click();
        assert.equal(h.dialog.open, false);
        assert.equal(h.body.childNodes.length, 0);
    }
});
test('reload/leave warning applies to changed forms and releases after discard', async () => {
    const h = harness({ initial: '/portal/reservations/request/', errors: false });
    await new Promise(setImmediate);
    let warnings = 0;
    const event = {preventDefault(){warnings++;}};
    h.windowListeners.beforeunload(event);
    assert.equal(warnings, 0);
    h.draftField.value = 'Draft';
    h.windowListeners.beforeunload(event);
    assert.equal(warnings, 1);
    h.close.listeners.click(); h.discard.listeners.click();
    h.windowListeners.beforeunload(event);
    assert.equal(warnings, 1);
});
test('bound validation entries remain protected without another keystroke', async () => {
    const h = harness();
    await h.send();
    h.close.listeners.click();
    assert.equal(h.dialog.open, true);
    assert.equal(h.discardDialog.open, true);
});
test('confirmed save clears leave warnings before navigation', async () => {
    const h = harness({receipt: {saved: true, redirect_url: '/portal/reservations/42/'}});
    await h.send();
    let warned = false;
    h.windowListeners.beforeunload({preventDefault(){warned = true;}});
    assert.equal(warned, false);
});


test('checkbox and multiple-select edits are tracked; reverting restores clean state', async () => {
    const other = harness({initial: '/portal/reservations/request/', errors: false});
    other.draftField.type = 'checkbox'; other.draftField.checked = false;
    await new Promise(setImmediate);
    other.draftField.checked = true;
    other.close.listeners.click(); assert.equal(other.discardDialog.open, true);
    other.keep.listeners.click(); other.draftField.checked = false;
    other.close.listeners.click(); assert.equal(other.dialog.open, false);
    const multi = harness({initial: '/portal/reservations/request/', errors: false});
    multi.draftField.tagName = 'SELECT'; multi.draftField.multiple = true;
    multi.draftField.selectedOptions = [{value:'1'}];
    await new Promise(setImmediate);
    multi.draftField.selectedOptions = [{value:'1'},{value:'2'}];
    multi.close.listeners.click(); assert.equal(multi.discardDialog.open, true);
    multi.keep.listeners.click(); multi.draftField.selectedOptions = [{value:'1'}];
    multi.close.listeners.click(); assert.equal(multi.dialog.open, false);
});


test('backdrop dismissal delegates to the editor guard and ignores inside drags', () => {
    let guarded=0, closed=0;
    const handlers={};
    const dialog={id:'table-edit-dialog',open:true,querySelector:()=>null,
        getBoundingClientRect:()=>({left:20,right:200,top:20,bottom:200}),
        addEventListener:(name,fn)=>{handlers[name]=fn;},close:()=>closed++};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/Reservation/js/interactions.js'),'utf8'), {
        document:{addEventListener(){},querySelectorAll:s=>s==='dialog'?[dialog]:[]},
        window:{SpasyoEditor:{requestClose:()=>guarded++}},HTMLElement:{prototype:{}}
    });
    const outside={target:dialog,clientX:1,clientY:1};
    handlers.pointerdown(outside);handlers.click(outside);
    assert.equal(guarded,1);assert.equal(closed,0);
    handlers.pointerdown({target:dialog,clientX:40,clientY:40});handlers.click(outside);
    assert.equal(guarded,1);
});


test('save clears a dirty form before the browser queues its asynchronous close event', async () => {
    const h = harness({initial:'/portal/reservations/request/',errors:false,asyncClose:true,
        receipt:{saved:true,redirect_url:'/portal/reservations/42/'}});
    await new Promise(setImmediate);
    h.draftField.value = 'Saved draft';
    await h.send();
    let warnings=0;
    h.windowListeners.beforeunload({preventDefault(){warnings++;}});
    assert.equal(warnings,0);
    assert.equal(h.location.assigned,'http://localhost/portal/reservations/42/');
});
