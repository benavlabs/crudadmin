(function () {
    "use strict";

    const SAFE_METHODS = ["GET", "HEAD", "OPTIONS"];
    const CSRF_HEADER = "X-CSRF-Token";
    const FORM_SUBMITTED_BY_FETCH_HEADER = "X-CRUDAdmin-Fetch";
    const REDIRECT_TARGET_HEADER = "X-CRUDAdmin-Location";
    const csrfCookieName =
        document.querySelector('meta[name="csrf-cookie-name"]')?.content || "crudadmin_csrf";

    function readCsrfTokenFromCookie() {
        const prefix = csrfCookieName + "=";
        for (const part of document.cookie.split(";")) {
            const cookie = part.trim();
            if (cookie.startsWith(prefix)) {
                return decodeURIComponent(cookie.slice(prefix.length));
            }
        }
        return "";
    }

    function changesState(method) {
        return !SAFE_METHODS.includes(method.toUpperCase());
    }

    function isSameOrigin(url) {
        return new URL(url, window.location.href).origin === window.location.origin;
    }

    function sendCsrfTokenWithHtmxRequests() {
        document.addEventListener("htmx:configRequest", function (event) {
            if (changesState(event.detail.verb)) {
                event.detail.headers[CSRF_HEADER] = readCsrfTokenFromCookie();
            }
        });
    }

    function sendCsrfTokenWithFetchCalls() {
        const nativeFetch = window.fetch.bind(window);
        window.fetch = function (input, init) {
            init = init || {};
            const isRequestObject = input instanceof Request;
            const method = init.method || (isRequestObject ? input.method : "GET");
            const url = isRequestObject ? input.url : String(input);
            if (changesState(method) && isSameOrigin(url)) {
                const headers = new Headers(
                    init.headers || (isRequestObject ? input.headers : undefined)
                );
                if (!headers.has(CSRF_HEADER)) {
                    headers.set(CSRF_HEADER, readCsrfTokenFromCookie());
                }
                init = Object.assign({}, init, { headers: headers });
            }
            return nativeFetch(input, init);
        };
    }

    function isPostFormNeedingCsrfToken(form) {
        return (
            form instanceof HTMLFormElement &&
            (form.getAttribute("method") || "get").toUpperCase() === "POST" &&
            !form.hasAttribute("data-native-submit") &&
            !form.hasAttribute("hx-post") &&
            isSameOrigin(form.action)
        );
    }

    async function showResponseAsBrowserWould(response) {
        const redirectTarget = response.headers.get(REDIRECT_TARGET_HEADER);
        if (redirectTarget) {
            window.location.assign(redirectTarget);
            return;
        }
        if (response.redirected) {
            window.location.assign(response.url);
            return;
        }
        const html = await response.text();
        document.open();
        document.write(html);
        document.close();
    }

    function submitPostFormsWithCsrfToken() {
        document.addEventListener("submit", async function (event) {
            const form = event.target;
            if (!isPostFormNeedingCsrfToken(form)) return;

            event.preventDefault();
            const submitter = event.submitter;
            const body = new FormData(form, submitter || undefined);
            if (submitter) submitter.disabled = true;
            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    body: body,
                    credentials: "same-origin",
                    headers: { [FORM_SUBMITTED_BY_FETCH_HEADER]: "1" },
                });
                await showResponseAsBrowserWould(response);
            } catch (error) {
                if (submitter) submitter.disabled = false;
                console.error("Form submission failed", error);
                alert("The request could not be sent. Check your connection and try again.");
            }
        });
    }

    function onAction(eventType, action, handler) {
        document.addEventListener(eventType, function (event) {
            const element = event.target.closest('[data-action="' + action + '"]');
            if (element) handler(element, event);
        });
    }

    function markCurrentSidebarLink() {
        const currentPath = window.location.pathname;
        document.querySelectorAll(".sidebar-link").forEach(function (link) {
            link.classList.toggle("active", link.getAttribute("href") === currentPath);
        });
    }

    function sidebarSectionKey(header) {
        const title = header.querySelector(".sidebar-section-title");
        return "sidebar-" + (title ? title.textContent : "");
    }

    function rememberedSidebarSections() {
        document.querySelectorAll('[data-action="toggle-sidebar-section"]').forEach(function (header) {
            try {
                if (localStorage.getItem(sidebarSectionKey(header)) === "collapsed") {
                    header.parentElement.classList.add("collapsed");
                }
            } catch (error) {
                return;
            }
        });
    }

    function toggleSidebarSections() {
        onAction("click", "toggle-sidebar-section", function (header) {
            const section = header.parentElement;
            const collapsed = section.classList.toggle("collapsed");
            try {
                localStorage.setItem(sidebarSectionKey(header), collapsed ? "collapsed" : "");
            } catch (error) {
                return;
            }
        });
    }

    function dismissSuccessBanner() {
        const banner = document.getElementById("successBanner");
        if (!banner) return;
        onAction("click", "dismiss-banner", function () {
            banner.remove();
        });
        setTimeout(function () {
            banner.remove();
        }, 4000);
        const url = new URL(window.location);
        url.searchParams.delete("success");
        window.history.replaceState({}, "", url);
    }

    function selectedRows() {
        return document.querySelectorAll('input[name="rowSelect"]:checked');
    }

    function showActionsForSelection() {
        const count = selectedRows().length;
        const createButton = document.getElementById("createButton");
        const updateButton = document.getElementById("updateButton");
        const deleteButton = document.getElementById("deleteButton");
        if (createButton) createButton.classList.toggle("hidden", count !== 0);
        if (updateButton) updateButton.classList.toggle("hidden", count !== 1);
        if (deleteButton) deleteButton.classList.toggle("hidden", count === 0);
    }

    function selectRows() {
        document.addEventListener("change", function (event) {
            const checkbox = event.target;
            if (checkbox.name === "select-all") {
                document.querySelectorAll('input[name="rowSelect"]').forEach(function (row) {
                    row.checked = checkbox.checked;
                });
            } else if (checkbox.name === "rowSelect") {
                const selectAll = document.querySelector('input[name="select-all"]');
                const rows = document.querySelectorAll('input[name="rowSelect"]');
                if (selectAll) selectAll.checked = rows.length === selectedRows().length;
            } else {
                return;
            }
            showActionsForSelection();
        });
        document.addEventListener("htmx:afterSwap", showActionsForSelection);
        showActionsForSelection();
    }

    function updateSelectedRow() {
        onAction("click", "update-selected", function (button, event) {
            event.preventDefault();
            const selected = selectedRows();
            if (selected.length !== 1) return;
            window.location.href = button.dataset.url + encodeURIComponent(selected[0].value);
        });
    }

    function currentListPage() {
        const info = document.querySelector(".pagination-info");
        const match = info ? info.textContent.match(/Page (\d+) of/) : null;
        return match ? match[1] : "1";
    }

    function selectedIds(pkType) {
        return Array.from(selectedRows()).map(function (box) {
            const value = box.value.trim();
            if (pkType !== "int") return value;
            const number = parseInt(value, 10);
            if (isNaN(number)) throw new Error("Invalid integer value: " + value);
            return number;
        });
    }

    function deleteSelectedRows() {
        onAction("click", "delete-selected", async function (button) {
            if (selectedRows().length === 0) {
                alert("Please select items to delete");
                return;
            }
            if (!confirm("Are you sure you want to delete the selected items?")) return;

            const modelList = document.getElementById("model-list");
            const rowsPerPage = document.querySelector('[name="rows-per-page-select"]');
            const query = new URLSearchParams({
                page: currentListPage(),
                "rows-per-page-select": rowsPerPage ? rowsPerPage.value : "10",
            });
            try {
                const response = await fetch(button.dataset.url + "?" + query, {
                    method: "DELETE",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ids: selectedIds(modelList.dataset.pkType) }),
                });
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error((error.detail && error.detail[0] && error.detail[0].message) || "Error deleting items");
                }
                const container = document.createElement("div");
                container.innerHTML = await response.text();
                const refreshedList = container.firstElementChild;
                modelList.replaceWith(refreshedList);
                htmx.process(refreshedList);
                showActionsForSelection();
            } catch (error) {
                alert(error.message || "Failed to delete items");
            }
        });
    }

    function expandRows() {
        onAction("click", "toggle-row", function (button) {
            const row = button.closest("tr");
            const expanded = document.getElementById("expanded-" + row.dataset.rowId);
            if (!expanded) return;
            const opening = expanded.style.display === "none";
            document.querySelectorAll(".expanded-row").forEach(function (other) {
                if (other === expanded) return;
                other.style.display = "none";
                const otherButton = other.previousElementSibling.querySelector(".expand-btn");
                if (otherButton) otherButton.classList.remove("expanded");
            });
            expanded.style.display = opening ? "table-row" : "none";
            button.classList.toggle("expanded", opening);
            const section = expanded.querySelector(".relationship-section");
            if (opening && section) htmx.trigger(section, "intersect");
        });
    }

    const EVENT_FILTERS = {
        username: "username",
        "event-type": "event_type",
        status: "status",
        "start-date": "start_date",
        "end-date": "end_date",
    };

    function loadEvents(url) {
        const query = new URLSearchParams();
        Object.entries(EVENT_FILTERS).forEach(function ([id, name]) {
            const input = document.getElementById(id);
            if (input && input.value) query.append(name, input.value);
        });
        htmx.ajax("GET", url + "?" + query, { target: "#events-content", swap: "innerHTML" });
    }

    function filterEvents() {
        onAction("click", "apply-event-filters", function (button) {
            loadEvents(button.dataset.url);
        });
        onAction("click", "reset-event-filters", function (button) {
            Object.keys(EVENT_FILTERS).forEach(function (id) {
                const input = document.getElementById(id);
                if (input) input.value = "";
            });
            loadEvents(button.dataset.url);
        });
        onAction("click", "toggle-event-details", function (summary) {
            summary.classList.toggle("expanded");
            summary.nextElementSibling.classList.toggle("visible");
        });
    }

    function formatJsonFields() {
        document.addEventListener("focusout", function (event) {
            const field = event.target;
            if (!(field instanceof HTMLTextAreaElement) || !field.name.endsWith("json")) return;
            const value = field.value.trim();
            if (!value) return;
            try {
                field.value = JSON.stringify(JSON.parse(value), null, 2);
            } catch (error) {
                return;
            }
        });
    }

    sendCsrfTokenWithHtmxRequests();
    sendCsrfTokenWithFetchCalls();
    submitPostFormsWithCsrfToken();
    markCurrentSidebarLink();
    rememberedSidebarSections();
    toggleSidebarSections();
    dismissSuccessBanner();
    selectRows();
    updateSelectedRow();
    deleteSelectedRows();
    expandRows();
    filterEvents();
    formatJsonFields();
})();
