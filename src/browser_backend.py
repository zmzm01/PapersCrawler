"""Browser backend adapters for publisher access.

The module keeps Camoufox and Cloakbrowser lifecycle differences out of the
publisher scrapers while exposing a regular Playwright ``BrowserContext``.
"""

from dataclasses import dataclass


SUPPORTED_BROWSER_BACKENDS = frozenset({"camoufox", "cloakbrowser"})


@dataclass
class BrowserBackendSession:
    """Own a Playwright context and all objects required to close it."""

    backend: str
    context: object
    manager: object | None = None

    def close(self):
        """Close the context, browser process, and backend manager safely."""
        browser = getattr(self.context, "browser", None)
        try:
            self.context.close()
        finally:
            if self.manager is not None:
                self.manager.__exit__(None, None, None)
            elif browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass


def launch_browser_backend(backend, user_data_dir, proxy=None,
                           headless=False, humanize=True):
    """Launch a persistent Playwright context using the selected backend.

    Parameters
    ----------
    backend : str
        ``camoufox`` or ``cloakbrowser``.
    user_data_dir : str
        Persistent browser profile directory.
    proxy : dict, optional
        Playwright-compatible proxy settings.
    headless : bool, optional
        Whether to launch without a visible browser window.
    humanize : bool, optional
        Whether to enable backend-provided human cursor movement.

    Returns
    -------
    BrowserBackendSession
        Backend owner whose ``context`` exposes the Playwright API.
    """
    normalized = str(backend).strip().lower()
    if normalized not in SUPPORTED_BROWSER_BACKENDS:
        raise ValueError(f"Unsupported browser backend: {backend}")

    if normalized == "camoufox":
        from camoufox.sync_api import Camoufox

        manager = Camoufox(
            persistent_context=True,
            user_data_dir=str(user_data_dir),
            headless=headless,
            proxy=proxy,
            humanize=humanize,
        )
        try:
            context = manager.__enter__()
        except Exception:
            manager.__exit__(None, None, None)
            raise
        return BrowserBackendSession(normalized, context, manager)

    from cloakbrowser import launch_persistent_context

    context = launch_persistent_context(
        user_data_dir=str(user_data_dir),
        headless=headless,
        proxy=proxy,
        humanize=humanize,
    )
    return BrowserBackendSession(normalized, context)
