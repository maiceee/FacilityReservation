/* Durable, account-scoped inbox. Existing action toasts and Undo remain separate. */
(() => {
    const root = document.querySelector('[data-notification-center]');
    if (!root) return;
    const toggle = root.querySelector('[data-inbox-toggle]');
    const panel = root.querySelector('.notification-inbox');
    const list = panel.querySelector('[data-inbox-items]');
    const count = root.querySelector('[data-inbox-count]');
    const live = root.querySelector('[data-inbox-live]');
    const readAll = panel.querySelector('[data-inbox-read-all]');
    const previous = panel.querySelector('[data-inbox-prev]');
    const next = panel.querySelector('[data-inbox-next]');
    const token = panel.querySelector('[name=csrfmiddlewaretoken]').value;
    document.body.append(panel);
    const pill = window.SpasyoTabMotion.mount(panel.querySelector('.inbox-tabs'));
    let tab = 'unread', page = 1, latest = null, unread = null, requestNumber = 0;
    let controller, saving = false;
    const text = (tag, value, className) => {
        const node = document.createElement(tag);
        node.textContent = value;
        if (className) node.className = className;
        return node;
    };
    const position = () => {
        const rect = toggle.getBoundingClientRect();
        panel.style.right = `${Math.max(12, innerWidth - rect.right)}px`;
        panel.style.top = `${Math.max(12, Math.min(rect.bottom + 8, innerHeight - 140))}px`;
        panel.style.maxHeight = `${Math.max(100, Math.min(480, innerHeight - parseFloat(panel.style.top) - 12))}px`;
    };
    const close = (restore = false) => {
        panel.hidden = true;
        toggle.setAttribute('aria-expanded', 'false');
        if (restore) toggle.focus();
    };
    const badge = (value) => {
        count.hidden = !value;
        count.textContent = value > 99 ? '99+' : String(value);
        toggle.setAttribute('aria-label', value ? `Notifications, ${value} unread` : 'Notifications');
        if (unread !== value && unread !== null) live.textContent = `${value} unread notifications`;
        unread = value;
        readAll.disabled = !value || saving;
    };
    const markRead = async (payload) => {
        const response = await fetch(root.dataset.read, { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token }, body: JSON.stringify(payload) });
        if (!response.ok) throw new Error('Could not mark notifications as read. Try again.');
    };
    const render = (data) => {
        list.replaceChildren();
        if (!data.items.length) list.append(text('p', tab === 'unread' ? 'You’re all caught up.' : 'No notifications yet.', 'inbox-empty'));
        data.items.forEach((item) => {
            const row = document.createElement(item.url ? 'a' : 'div');
            row.className = `inbox-item${item.unread ? ' is-unread' : ''}`;
            if (item.url) row.href = item.url;
            const symbol = text('span', '', 'inbox-symbol');
            symbol.append(toggle.querySelector('svg').cloneNode(true));
            const copy = text('div', '', 'inbox-copy');
            copy.append(text('strong', item.title), text('p', item.message));
            const date = new Date(item.created_at);
            const time = text('time', new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Manila' }).format(date));
            time.dateTime = item.created_at;
            copy.append(time);
            row.append(symbol, copy);
            if (item.unread) row.append(text('span', '', 'inbox-dot'));
            row.addEventListener('click', async (event) => {
                if (!item.url || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                // Do not bypass the existing pending-action navigation guard.
                if (window.SpasyoNotifications?.hasPendingAction()) return;
                if (saving) return;
                saving = true;
                try { await markRead({ id: item.id }); location.assign(item.url); }
                catch (error) { window.SpasyoNotifications?.show(error.message, { severity: 'error', duration: 6000 }); }
                finally { saving = false; }
            });
            list.append(row);
        });
        previous.disabled = page === 1;
        next.disabled = !data.has_next;
        panel.querySelector('[data-inbox-page]').textContent = `Page ${page}`;
    };
    const load = async (background = false) => {
        const number = ++requestNumber;
        controller?.abort();
        controller = new AbortController();
        if (!background) {
            list.setAttribute('aria-busy', 'true');
            previous.disabled = next.disabled = true;
            if (!list.children.length) list.append(text('p', 'Loading notifications…', 'inbox-empty'));
        }
        try {
            const response = await fetch(`${root.dataset.feed}?tab=${tab}&page=${page}`, {
                credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
            if (!response.ok || response.redirected) throw new Error('Notifications unavailable.');
            const data = await response.json();
            if (number !== requestNumber) return;
            if (latest !== null && data.latest_unread?.id > latest) {
                window.SpasyoNotifications?.show(`${data.latest_unread.title}. Open Notifications to review.`, { severity: 'info', duration: 6000 });
            }
            latest = data.latest_id;
            badge(data.unread_count);
            if (!panel.hidden) {
                // Avoid replacing a row while someone is using its keyboard focus.
                if (!background || !list.contains(document.activeElement)) render(data);
            }
        } catch (error) {
            if (error.name === 'AbortError' || background) return;
            list.replaceChildren(text('p', 'Couldn’t load notifications.', 'inbox-empty'));
            const retry = text('button', 'Try again', 'inbox-text-button');
            retry.type = 'button'; retry.addEventListener('click', () => load()); list.append(retry);
            previous.disabled = next.disabled = true;
        } finally { if (number === requestNumber) list.setAttribute('aria-busy', 'false'); }
    };
    toggle.addEventListener('click', () => {
        if (!panel.hidden) { close(); return; }
        panel.hidden = false; toggle.setAttribute('aria-expanded', 'true'); position();
        pill.reset(); load(); panel.querySelector('[data-inbox-tab]').focus();
    });
    panel.querySelectorAll('[data-inbox-tab]').forEach((button) => button.addEventListener('click', () => {
        if (tab === button.dataset.inboxTab) return;
        tab = button.dataset.inboxTab; page = 1;
        panel.querySelectorAll('[data-inbox-tab]').forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
        pill.reset(); load();
    }));
    previous.addEventListener('click', () => { if (page > 1) { page--; load(); } });
    next.addEventListener('click', () => { page++; load(); });
    readAll.addEventListener('click', async () => {
        if (saving || !latest) return;
        saving = true; readAll.disabled = true;
        try { await markRead({ through: latest }); page = 1; await load(); }
        catch (error) { live.textContent = error.message; window.SpasyoNotifications?.show(error.message, { severity: 'error', duration: 6000 }); }
        finally { saving = false; readAll.disabled = !unread; }
    });
    document.addEventListener('click', (event) => { if (!root.contains(event.target) && !panel.contains(event.target)) close(); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); close(true); } });
    document.addEventListener('focusin', (event) => { if (!root.contains(event.target) && !panel.contains(event.target)) close(); });
    window.addEventListener('resize', () => { if (!panel.hidden) position(); });
    const timer = setInterval(() => { if (!document.hidden && !saving) load(true); }, 30000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) load(true); });
    window.addEventListener('pagehide', () => { clearInterval(timer); controller?.abort(); });
    window.addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });
    load(true);
})();
