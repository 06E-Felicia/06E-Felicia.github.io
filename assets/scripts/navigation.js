// Shared navigation for the weather pages.
function initDropdownMenus() {
    const items = [...document.querySelectorAll('.nav-bar .dropdown')];
    function closeMenus(except = null) {
        items.forEach(item => {
            if (item === except) return;
            item.classList.remove('is-open');
            item.querySelector('.nav-item').setAttribute('aria-expanded', 'false');
        });
    }
    items.forEach((item, index) => {
        const trigger = item.querySelector('.nav-item'), menu = item.querySelector('.dropdown-menu');
        menu.id ||= `nav-dropdown-${index}`;
        trigger.setAttribute('aria-controls', menu.id);
        trigger.setAttribute('aria-expanded', 'false');
        function openMenu() {
            closeMenus(item);
            item.classList.add('is-open');
            trigger.setAttribute('aria-expanded', 'true');
        }
        // No mouseleave handler: crossing the gap must not close the disclosure.
        item.addEventListener('mouseenter', openMenu);
        trigger.addEventListener('focus', openMenu);
        trigger.addEventListener('click', event => { event.preventDefault(); openMenu(); });
        trigger.addEventListener('keydown', event => {
            if (event.key === ' ' || event.key === 'ArrowDown') {
                event.preventDefault(); openMenu();
                menu.querySelector('a')?.focus();
            }
        });
        menu.addEventListener('click', event => { if (event.target.closest('a')) closeMenus(); });
        item.addEventListener('focusout', event => {
            if (!item.contains(event.relatedTarget)) closeMenus();
        });
    });
    document.addEventListener('click', event => {
        if (!event.target.closest('.nav-bar .dropdown')) closeMenus();
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        const opened = items.find(item => item.classList.contains('is-open'));
        if (opened) {
            // Focusing first avoids a focus handler reopening the dismissed menu.
            opened.querySelector('.nav-item').focus();
            closeMenus();
        }
    });
}

initDropdownMenus();

