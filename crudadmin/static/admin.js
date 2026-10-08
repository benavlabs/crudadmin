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

    sendCsrfTokenWithHtmxRequests();
    sendCsrfTokenWithFetchCalls();
    submitPostFormsWithCsrfToken();
})();
