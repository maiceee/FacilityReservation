/* Presentation only. Native form controls, names, validation and submission remain intact. */
(() => {
    'use strict';
    // Labelled form submissions share a text-only treatment; navigation and icon-only controls keep icons.
    document.querySelectorAll('form:not([data-signout]) button[type="submit"]').forEach((button) => {
        if (button.textContent.trim() && !button.classList.contains('icon-button')) {
            button.querySelectorAll('svg.icon').forEach((icon) => icon.remove());
        }
    });

    // Tabs progressively enhance panels: without JS all existing content remains readable.
    document.querySelectorAll('[data-tabs]').forEach((root) => {
        const list = root.querySelector('[data-tablist]');
        if (!list) return;
        const tabs = [...list.querySelectorAll('[data-tab]')];
        const panels = tabs.map((tab) => document.getElementById(tab.dataset.tab));
        if (panels.some((panel) => !panel)) return;
        list.hidden = false;
        list.setAttribute('role', 'tablist');
        const moveIndicator = () => {
            const active = list.querySelector('[aria-selected="true"]');
            if (!active) return;
            list.style.setProperty('--tab-left', `${active.offsetLeft}px`);
            list.style.setProperty('--tab-top', `${active.offsetTop}px`);
            list.style.setProperty('--tab-width', `${active.offsetWidth}px`);
            list.style.setProperty('--tab-height', `${active.offsetHeight}px`);
            list.classList.add('has-tab-indicator');
        };
        const activate = (index, focus = false) => {
            tabs.forEach((tab, i) => {
                tab.id ||= `${tab.dataset.tab}-tab`;
                tab.setAttribute('role', 'tab');
                tab.setAttribute('aria-controls', panels[i].id);
                tab.setAttribute('aria-selected', String(i === index));
                tab.tabIndex = i === index ? 0 : -1;
                panels[i].hidden = i !== index;
                panels[i].setAttribute('role', 'tabpanel');
                panels[i].setAttribute('aria-labelledby', tab.id);
            });
            moveIndicator();
            if (focus) tabs[index].focus();
            window.dispatchEvent(new Event('resize'));
        };
        tabs.forEach((tab, index) => {
            tab.addEventListener('click', () => {
                activate(index);
                if (root.hasAttribute('data-reset-scroll')) {
                    const content = root.closest('.content');
                    if (content) content.scrollTop = 0;
                }
            });
            tab.addEventListener('keydown', (event) => {
                let next;
                if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
                if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
                if (event.key === 'Home') next = 0;
                if (event.key === 'End') next = tabs.length - 1;
                if (next === undefined) return;
                event.preventDefault();
                activate(next, true);
            });
        });
        activate(0);
        if (typeof ResizeObserver === "function") new ResizeObserver(moveIndicator).observe(list);
    });

    // Full day/booking details use a bounded dialog; hints use adjacent popovers.
    const preview = document.getElementById('workspace-preview');
    if (preview && typeof preview.showModal === 'function') {
        const body = preview.querySelector('[data-preview-body]');
        const title = preview.querySelector('h2');
        preview.querySelector('[data-preview-close]').addEventListener('click', () => preview.close());
        document.addEventListener('click', (event) => {
            const trigger = event.target.closest('[data-preview]');
            if (!trigger || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            const template = trigger.dataset.preview && document.getElementById(trigger.dataset.preview);
            if (!template) return;
            event.preventDefault();
            title.textContent = trigger.dataset.previewTitle || trigger.getAttribute('aria-label') || 'Details';
            body.replaceChildren(template.content.cloneNode(true));
            preview.showModal();
        });
        preview.addEventListener('close', () => {
            const cleanup = () => body.replaceChildren();
            if (window.SpasyoMotion) window.SpasyoMotion.afterClose(preview, cleanup);
            else cleanup();
        });
    }

    // Popovers retain native fallbacks in browsers without the Popover API.
    if (!('showPopover' in HTMLElement.prototype)) return;
    let controlId = 0;
    const make = (tag, className, text) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    };
    const icon = (name) => {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'icon');
        svg.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        const source = document.querySelector('.icon use').getAttribute('href').split('#')[0];
        use.setAttribute('href', `${source}#${name}`);
        svg.append(use);
        return svg;
    };
    const button = (className, label) => {
        const result = make('button', className, label);
        result.type = 'button';
        return result;
    };
    const setupPopover = (trigger, popup, width = 280) => {
        popup.popover = 'auto';
        popup.id = `control-popup-${++controlId}`;
        trigger.setAttribute('aria-controls', popup.id);
        trigger.setAttribute('aria-expanded', 'false');
        const place = () => {
            const box = trigger.getBoundingClientRect();
            const popupWidth = Math.min(Math.max(box.width, width), window.innerWidth - 24);
            const below = window.innerHeight - box.bottom - 12;
            const above = box.top - 12;
            const available = below >= 220 || below >= above ? below : above;
            const height = Math.min(360, Math.max(100, available));
            popup.style.width = `${popupWidth}px`;
            popup.style.maxHeight = `${height}px`;
            popup.style.left = `${Math.max(12, Math.min(box.left, window.innerWidth - popupWidth - 12))}px`;
            popup.style.top = `${below >= 220 || below >= above ? box.bottom + 6 : Math.max(12, box.top - height - 6)}px`;
        };
        trigger.addEventListener('click', () => {
            if (popup.matches(':popover-open')) popup.hidePopover();
            else { place(); popup.showPopover(); }
        });
        popup.addEventListener('toggle', () => {
            const open = popup.matches(':popover-open');
            trigger.setAttribute('aria-expanded', String(open));
            if (open) popup.querySelector('[data-picker-focus]')?.focus();
        });
        popup.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            popup.hidePopover();
            trigger.focus();
        });
    };
    window.addEventListener('resize', () => {
        document.querySelectorAll('.control-popover:popover-open').forEach((popup) => popup.hidePopover());
    });
    document.addEventListener('scroll', (event) => {
        document.querySelectorAll('.control-popover:popover-open').forEach((popup) => {
            if (!popup.contains(event.target)) popup.hidePopover();
        });
    }, { capture: true, passive: true });

    // Searchable options update the original select; no options or values are invented.
    const enhanceSelects = (root) => root.querySelectorAll('select:not([multiple]):not(.native-select)').forEach((select) => {
        const wrap = make('div', 'select-control');
        const trigger = button('control-trigger');
        const value = make('span');
        trigger.append(value, icon('chevron-down'));
        trigger.id = `select-trigger-${++controlId}`;
        const label = [...select.labels].map((item) => item.textContent.trim()).join(' ') || 'Select option';
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.disabled = select.disabled;
        const popup = make('div', 'control-popover');
        const search = make('input');
        search.type = 'search';
        search.placeholder = 'Find an option…';
        search.setAttribute('aria-label', `Search ${label.toLowerCase()}`);
        search.dataset.pickerFocus = '';
        const list = make('div', 'control-options');
        list.setAttribute('role', 'listbox');
        list.setAttribute('aria-label', label);
        popup.append(search, list);
        select.before(wrap);
        wrap.append(select, trigger, popup);
        select.classList.add('native-select');
        select.tabIndex = -1;
        select.setAttribute('aria-hidden', 'true');
        [...select.labels].forEach((item) => { item.htmlFor = trigger.id; });
        const refresh = () => {
            value.textContent = select.selectedOptions[0]?.textContent.trim() || 'Select…';
            trigger.setAttribute('aria-label', `${label}: ${value.textContent}`);
            if (select.getAttribute('aria-invalid')) trigger.setAttribute('aria-invalid', select.getAttribute('aria-invalid'));
            if (select.getAttribute('aria-describedby')) trigger.setAttribute('aria-describedby', select.getAttribute('aria-describedby'));
            list.replaceChildren();
            [...select.options].forEach((option) => {
                if (!option.textContent.toLowerCase().includes(search.value.toLowerCase())) return;
                const choice = button('control-option', option.textContent);
                choice.disabled = option.disabled || option.parentElement.disabled;
                choice.setAttribute('role', 'option');
                choice.setAttribute('aria-selected', String(option.selected));
                choice.addEventListener('click', () => {
                    select.value = option.value;
                    select.dispatchEvent(new Event('input', { bubbles: true }));
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                    popup.hidePopover();
                    trigger.focus();
                });
                list.append(choice);
            });
            if (!list.children.length) list.append(make('p', 'control-empty', 'No matching options'));
        };
        setupPopover(trigger, popup);
        popup.addEventListener('beforetoggle', (event) => {
            if (event.newState === 'open') { search.value = ''; refresh(); }
        });
        search.addEventListener('input', refresh);
        select.addEventListener('change', refresh);
        select.addEventListener('focus', () => trigger.focus());
        select.addEventListener('invalid', () => trigger.focus());
        select.form?.addEventListener('reset', () => queueMicrotask(refresh));
        popup.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && event.target === search) {
                event.preventDefault();
                list.querySelector('button:not(:disabled)')?.click();
                return;
            }
            if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
            if (event.target === search && !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
            const choices = [...list.querySelectorAll('button:not(:disabled)')];
            if (!choices.length) return;
            event.preventDefault();
            const current = choices.indexOf(document.activeElement);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1
                : current < 0 ? (event.key === 'ArrowUp' ? choices.length - 1 : 0)
                : (current + (event.key === 'ArrowUp' ? -1 : 1) + choices.length) % choices.length;
            choices[next].focus();
        });
        refresh();
    });

    // Branded date/calendar picker; original date and datetime-local inputs stay editable.
    const isoDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const localDate = (value) => {
        const [year, month, day] = value.split('-').map(Number);
        return new Date(year, month - 1, day);
    };
    const enhanceDates = (root) => root.querySelectorAll('input[type="date"], input[type="datetime-local"]').forEach((input) => {
        if (input.disabled || input.readOnly || input.closest('.date-control')) return;
        const wrap = make('div', 'date-control');
        const trigger = button('date-picker-trigger');
        const label = [...input.labels].map((item) => item.textContent.trim()).join(' ') || 'Date';
        trigger.setAttribute('aria-label', `Choose ${label.toLowerCase()}`);
        trigger.title = `Choose ${label.toLowerCase()}`;
        trigger.setAttribute('aria-haspopup', 'dialog');
        trigger.append(icon('calendar-days'));
        const popup = make('div', 'control-popover');
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-label', `Choose ${label.toLowerCase()}`);
        const header = make('div', 'date-picker-header');
        const previous = button('icon-button');
        previous.setAttribute('aria-label', 'Previous month');
        previous.append(icon('arrow-left'));
        const heading = make('strong');
        heading.setAttribute('aria-live', 'polite');
        const next = button('icon-button');
        next.setAttribute('aria-label', 'Next month');
        next.append(icon('arrow-right'));
        header.append(previous, heading, next);
        const week = make('div', 'date-picker-week');
        ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'].forEach((day) => week.append(make('span', '', day)));
        const grid = make('div', 'date-picker-grid');
        grid.setAttribute('role', 'group');
        grid.setAttribute('aria-label', 'Calendar days');
        popup.append(header, week, grid);
        let selected = input.value.slice(0, 10) || isoDate(new Date());
        let month = localDate(selected);
        month.setDate(1);
        const withTime = input.type === 'datetime-local';
        const time = make('input');
        time.type = 'time';
        time.setAttribute('aria-label', `${label} time`);
        const commit = () => {
            input.value = selected + (withTime ? `T${time.value || '09:00'}` : '');
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            popup.hidePopover();
            trigger.focus();
        };
        if (withTime) {
            const footer = make('div', 'date-picker-footer');
            const apply = button('button button-primary', 'Apply');
            apply.addEventListener('click', commit);
            time.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') { event.preventDefault(); commit(); }
            });
            footer.append(time, apply);
            popup.append(footer);
        }
        const render = (focusDate) => {
            heading.textContent = month.toLocaleDateString('en', { month: 'long', year: 'numeric' });
            grid.replaceChildren();
            const start = new Date(month);
            start.setDate(1 - (month.getDay() + 6) % 7);
            for (let i = 0; i < 42; i++) {
                const date = new Date(start);
                date.setDate(start.getDate() + i);
                const value = isoDate(date);
                const day = button(date.getMonth() !== month.getMonth() ? 'is-outside' : '', String(date.getDate()));
                day.dataset.date = value;
                day.setAttribute('aria-label', date.toLocaleDateString('en', { dateStyle: 'full' }));
                day.setAttribute('aria-pressed', String(value === selected));
                day.disabled = Boolean((input.min && value < input.min.slice(0, 10)) || (input.max && value > input.max.slice(0, 10)));
                if (value === selected) day.dataset.pickerFocus = '';
                day.addEventListener('click', () => { selected = value; if (withTime) render(value); else commit(); });
                day.addEventListener('keydown', (event) => {
                    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key];
                    if (!step) return;
                    event.preventDefault();
                    const target = new Date(date);
                    target.setDate(target.getDate() + step);
                    month = new Date(target.getFullYear(), target.getMonth(), 1);
                    render(isoDate(target));
                });
                grid.append(day);
            }
            if (focusDate) grid.querySelector(`[data-date="${focusDate}"]:not(:disabled)`)?.focus();
            if (popup.matches(':popover-open')) window.SpasyoMotion?.reveal(grid);
        };
        previous.addEventListener('click', () => { month.setMonth(month.getMonth() - 1); render(); });
        next.addEventListener('click', () => { month.setMonth(month.getMonth() + 1); render(); });
        input.before(wrap);
        wrap.append(input, trigger, popup);
        setupPopover(trigger, popup, 288);
        trigger.addEventListener('click', () => {
            selected = input.value.slice(0, 10) || isoDate(new Date());
            month = localDate(selected);
            month.setDate(1);
            time.value = input.value.slice(11, 16) || '09:00';
            render();
        });
        render();
    });
    const enhance = (root) => { enhanceSelects(root); enhanceDates(root); };
    enhance(document);
    document.addEventListener('workspace:form-ready', (event) => enhance(event.target));
})();
