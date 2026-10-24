/* Examples explain input, never set values or change native form constraints. */
(() => {
    'use strict';
    const examples = {
        first_name: 'e.g. Alex', last_name: 'e.g. Reyes', username: 'e.g. alex.reyes',
        email: 'e.g. alex.reyes@example.com', contact_number: 'e.g. 09171234567',
        department: 'e.g. College of Information Technology',
        password: 'Enter your password', password1: 'Create a password', password2: 'Repeat your password',
        facility_code: 'e.g. ROOM-101', location: 'e.g. Science Building, 2nd floor',
        capacity: 'e.g. 40', description: 'e.g. A quiet room for group meetings and presentations.',
        event_name: 'e.g. Student Research Forum', expected_attendees: 'e.g. 25',
        purpose: 'e.g. Present student research and hold a group discussion.',
        max_event_duration_hours: 'e.g. 4', advance_booking_days: 'e.g. 30',
        incident_notes: 'e.g. Projector stopped working during the event.',
        decision_reason: 'e.g. Schedule and facility requirements have been reviewed.',
        reason: 'e.g. The event has moved to a different date.'
    };
    const groups = '.field, .rv-form-field, .facility-form-group, .master-form-group, .closures-form-group, .system-settings-field, .user-filter-field, .calendar-field, .ra-field, .rv-field, .facility-search-field, .management-search-field, .system-search-field';
    let nextId = 0;
    const placeholderFor = (control) => {
        if (control.name === 'name') {
            const path = control.form?.action || location.pathname;
            return path.includes('amenities') ? 'e.g. Projector' : path.includes('categories') ? 'e.g. Meeting spaces' : 'e.g. Conference Room A';
        }
        if (control.name === 'search') {
            const path = location.pathname;
            if (path.includes('amenities')) return 'e.g. Projector';
            if (path.includes('categories')) return 'e.g. Meeting spaces';
            if (path.includes('users')) return 'e.g. Alex Reyes or alex.reyes';
            if (path.includes('audit')) return 'e.g. reservation or username';
            if (path.includes('reservations')) return 'e.g. Student Research Forum';
            return 'e.g. ROOM-101 or Science Building';
        }
        if (control.name === 'reason' && control.form?.classList.contains('closures-detail-form')) return 'e.g. Preventive maintenance of the air conditioning.';
        if (control.id === 'rejection-reason') return 'e.g. The requested time conflicts with an existing booking.';
        return examples[control.name];
    };
    const describe = (control, text) => {
        const group = control.closest(groups) || control.parentElement;
        if (!group || group === control.form) return;
        let example = group.querySelector('.field-example');
        if (!example) {
            const help = group.querySelector('.field-help, .rv-form-help, .master-field-help, .facility-field-help, .closures-field-help, .ui-field-help, .system-field-description');
            example = document.createElement(help ? 'span' : 'small');
            example.className = 'field-example';
            example.id = `field-example-${++nextId}`;
            example.textContent = text;
            if (help) {
                example.classList.add('is-inline');
                help.id ||= `field-guidance-${++nextId}`;
                help.append(example);
            } else group.append(example);
        }
        const ids = new Set((control.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        ids.add(example.classList.contains('is-inline') ? example.parentElement.id : example.id);
        control.setAttribute('aria-describedby', [...ids].join(' '));
        // Also support controls enhanced before this event, without replacing their labels.
        control.closest('.select-control')?.querySelector('.control-trigger')?.setAttribute('aria-describedby', [...ids].join(' '));
    };
    const enhance = (root) => {
        root.querySelectorAll('input[name]:not([type="hidden"]), select[name], textarea[name]').forEach((control) => {
            if (control.dataset.exampleReady || ['submit', 'button', 'file', 'reset'].includes(control.type)) return;
            control.dataset.exampleReady = 'true';
            if (control.tagName === 'SELECT') {
                const option = [...control.options].find((item) => item.value && !item.disabled);
                if (option) describe(control, `e.g. ${option.textContent.trim()}`);
                return;
            }
            if (control.type === 'checkbox' || control.type === 'radio') {
                if (control.name === 'is_active') describe(control, 'On: available · Off: unavailable');
                // Amenity labels already provide real, selectable examples.
                return;
            }
            if (['date', 'datetime-local', 'time'].includes(control.type)) {
                const tomorrow = new Date();
                tomorrow.setDate(tomorrow.getDate() + 1);
                const date = tomorrow.toLocaleDateString('en-PH', { day: 'numeric', month: 'short', year: 'numeric' });
                const time = control.name === 'closing_time' ? '8:00 PM' : control.name === 'end_datetime' ? '11:00 AM' : '9:00 AM';
                describe(control, control.type === 'time' ? `e.g. ${time}` : `e.g. ${date}${control.type === 'datetime-local' ? `, ${time} · Philippine time` : ''}`);
                return;
            }
            const example = placeholderFor(control);
            if (example) control.placeholder = example;
        });
    };
    enhance(document);
    document.addEventListener('workspace:form-ready', (event) => enhance(event.target));
})();
