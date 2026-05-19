(function () {
    const DEFAULT_ENDPOINT = '/api/suggestions/';
    const MIN_QUERY_LENGTH = 2;
    const DEBOUNCE_MS = 220;

    function initSuggestionInput(input, options) {
        if (!input || input.dataset.suggestionReady === '1') return null;
        const settings = Object.assign({
            context: input.dataset.smartSuggest || 'chat',
            endpoint: DEFAULT_ENDPOINT,
            limit: 8,
            placement: 'below',
            onSelect: null
        }, options || {});

        input.dataset.suggestionReady = '1';
        const anchor = input.parentElement;
        if (!anchor) return null;
        anchor.classList.add('suggestion-anchor', 'smart-suggest-anchor');

        const dropdown = document.createElement('div');
        dropdown.className = 'suggestion-dropdown smart-suggest-panel';
        if (settings.placement === 'above') {
            dropdown.classList.add('suggestion-dropdown--above');
        }
        dropdown.setAttribute('role', 'listbox');
        dropdown.hidden = true;
        anchor.appendChild(dropdown);

        let timer = null;
        let abortController = null;
        let items = [];
        let activeIndex = -1;
        let suppressUntil = 0;

        function hide() {
            dropdown.hidden = true;
            dropdown.innerHTML = '';
            activeIndex = -1;
            items = [];
            if (abortController) {
                abortController.abort();
                abortController = null;
            }
        }

        function setActive(nextIndex) {
            const rows = Array.from(dropdown.querySelectorAll('.suggestion-item'));
            if (!rows.length) {
                activeIndex = -1;
                return;
            }
            activeIndex = (nextIndex + rows.length) % rows.length;
            rows.forEach((row, index) => {
                const active = index === activeIndex;
                row.classList.toggle('is-active', active);
                row.setAttribute('aria-selected', active ? 'true' : 'false');
                if (active) row.scrollIntoView({ block: 'nearest' });
            });
        }

        function select(item) {
            if (!item) return;
            suppressUntil = Date.now() + 450;
            hide();
            if (typeof settings.onSelect === 'function') {
                settings.onSelect(item, input);
            } else {
                input.value = item.label || item.title || '';
            }
        }

        function render(suggestions) {
            items = (suggestions || [])
                .filter(Boolean)
                .filter((item) => {
                    const label = String(item.label || item.title || '').trim().toLowerCase();
                    return label && label !== 'smart suggestion';
                })
                .slice(0, settings.limit || 8);

            dropdown.innerHTML = '';
            activeIndex = -1;
            if (!items.length) {
                hide();
                return;
            }

            items.forEach((item, index) => {
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'suggestion-item smart-suggest-item';
                row.setAttribute('role', 'option');
                row.setAttribute('aria-selected', 'false');
                row.onmousedown = (event) => event.preventDefault();
                row.onclick = () => select(item);

                const title = document.createElement('span');
                title.className = 'suggestion-title smart-suggest-title';
                title.textContent = item.label || item.title || 'Gợi ý';

                const subtitle = document.createElement('span');
                subtitle.className = 'suggestion-subtitle smart-suggest-subtitle';
                subtitle.textContent = item.subtitle || item.type || item.kind || '';

                row.appendChild(title);
                if (subtitle.textContent) row.appendChild(subtitle);
                dropdown.appendChild(row);

                if (index === 0) setActive(0);
            });
            dropdown.hidden = false;
        }

        function fetchSuggestions() {
            const value = input.value.trim();
            if (Date.now() < suppressUntil) return;
            if (value.replace(/\s+/g, '').length < MIN_QUERY_LENGTH) {
                hide();
                return;
            }

            if (abortController) abortController.abort();
            abortController = new AbortController();
            const params = new URLSearchParams({
                q: value,
                context: settings.context || 'chat'
            });

            fetch(settings.endpoint + '?' + params.toString(), {
                signal: abortController.signal,
                headers: { 'Accept': 'application/json' }
            })
                .then((response) => response.json())
                .then((data) => {
                    render(data && data.ok !== false ? (data.suggestions || []) : []);
                })
                .catch((error) => {
                    if (error.name !== 'AbortError') hide();
                });
        }

        input.addEventListener('input', () => {
            window.clearTimeout(timer);
            if (!input.value.trim()) {
                hide();
                return;
            }
            timer = window.setTimeout(fetchSuggestions, DEBOUNCE_MS);
        });

        input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                hide();
                return;
            }
            if (dropdown.hidden || !items.length) return;
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                setActive(activeIndex + 1);
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                setActive(activeIndex - 1);
            } else if (event.key === 'Enter' && activeIndex >= 0) {
                event.preventDefault();
                event.stopPropagation();
                select(items[activeIndex]);
            }
        }, true);

        input.addEventListener('blur', () => {
            window.setTimeout(hide, 120);
        });

        document.addEventListener('mousedown', (event) => {
            if (!anchor.contains(event.target)) hide();
        });

        return {
            hide,
            refresh: fetchSuggestions
        };
    }

    window.TravelSuggestion = Object.assign({}, window.TravelSuggestion || {}, {
        initSuggestionInput
    });
}());
