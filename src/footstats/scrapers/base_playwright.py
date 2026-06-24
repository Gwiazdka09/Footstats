"""Shared Playwright helpers for betting site scrapers."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from footstats.core.circuit_breaker import CircuitBreaker
from footstats.core.exceptions import FootStatsCircuitOpenError

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import Browser, Error as PWError, Page, TimeoutError as PWTimeout, sync_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False
    logger.info("[BasePlaywright] UWAGA: playwright niedostepny, zainstaluj: pip install playwright && playwright install chromium")

_T = TypeVar("_T")

playwright_circuit = CircuitBreaker("playwright", failure_threshold=3, recovery_timeout=120)
DEFAULT_TIMEOUT_MS = 30000


@contextmanager
def browser_context(headless: bool = True, **launch_kwargs: Any) -> Generator[Browser, None, None]:
    """Context manager for Playwright browser lifecycle.

    Ensures browser.close() is called even on exception.

    Usage:
        with browser_context(headless=True) as browser:
            ctx = browser.new_context()
            page = ctx.new_page()
            # ... use page
            page.close()
    """
    p = sync_playwright().start()
    browser = None
    try:
        browser = p.chromium.launch(headless=headless, **launch_kwargs)
        yield browser
    except (PWTimeout, PWError) as e:
        logger.error("[PW] Błąd w browser context: %s", e)
        raise
    finally:
        if browser:
            try:
                browser.close()
                logger.debug("[PW] Browser zamknięty")
            except (PWTimeout, PWError) as e:
                logger.warning("[PW] Błąd przy zamykaniu browsera: %s", e)
        p.stop()


@contextmanager
def page_context(browser: Browser, **context_kwargs: Any) -> Generator[Page, None, None]:
    """Context manager for Playwright page lifecycle.

    Creates context and page, sets default timeout, ensures cleanup.

    Usage:
        with browser_context() as browser:
            with page_context(browser) as page:
                page.goto(...)
    """
    ctx = None
    page = None
    try:
        ctx = browser.new_context(**context_kwargs)
        page = ctx.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        yield page
    except PWTimeout as e:
        logger.error("[PW] Timeout (> %dms): %s", DEFAULT_TIMEOUT_MS, e)
        if page:
            try:
                page.screenshot(path=f"pw_timeout_{datetime.now().isoformat()}.png")
            except (PWTimeout, PWError, OSError):
                pass
        raise
    except (PWTimeout, PWError) as e:
        logger.error("[PW] Błąd na stronie: %s", e)
        if page:
            try:
                page.screenshot(path=f"pw_error_{datetime.now().isoformat()}.png")
            except (PWTimeout, PWError, OSError):
                pass
        raise
    finally:
        if page:
            try:
                page.close()
            except (PWTimeout, PWError) as e:
                logger.warning("[PW] Błąd przy zamykaniu page: %s", e)
        if ctx:
            try:
                ctx.close()
            except (PWTimeout, PWError) as e:
                logger.warning("[PW] Błąd przy zamykaniu context: %s", e)


def retry_with_backoff(
    fn: Callable[..., _T],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> _T:
    """Exponential backoff retry. Raises last exception after max_retries."""
    last_exc: Exception = RuntimeError("no attempts")
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: broad-except — retry wrapper must catch any callable exception
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning("[PW] Retry %d/%d po %.1fs: %s", attempt + 1, max_retries, delay, exc)
                time.sleep(delay)
    raise last_exc


def navigate_with_retry(page: Page, url: str, max_retries: int = 3, timeout: int = 30000) -> None:
    """Navigate with exponential backoff on failure."""
    retry_with_backoff(page.goto, url, max_retries=max_retries, base_delay=2.0, timeout=timeout)


@dataclass(frozen=True)
class SiteConfig:
    name: str
    url: str
    cache_dir: Path
    login_env: str
    password_env: str
    popup_selectors: tuple[str, ...] = (
        "#onetrust-accept-btn-handler",
        "button:has-text('Akceptuję')",
        "[aria-label='Zamknij']",
        "button.close",
    )
    email_selectors: tuple[str, ...] = (
        "input[type='email']",
        "input[placeholder*='e-mail']",
        "input[placeholder*='E-mail']",
    )
    password_selectors: tuple[str, ...] = (
        "input[type='password']",
        "input[placeholder*='Hasło']",
    )
    login_button_selector: str = "button:has-text('Zaloguj się')"
    login_trigger_selector: str = "button:has-text('Zaloguj się'), a:has-text('Zaloguj się')"
    login_success_hidden: str = "button:has-text('Zaloguj się')"
    avatar_selectors: tuple[str, ...] = (
        "[data-cy='user-avatar']",
        ".user-avatar",
        ".profile-icon",
    )


STS_CONFIG = SiteConfig(
    name="STS",
    url="https://www.sts.pl",
    cache_dir=Path("cache/sts"),
    login_env="STS_LOGIN",
    password_env="STS_HASLO",
)

SUPERBET_CONFIG = SiteConfig(
    name="Superbet",
    url="https://www.superbet.pl",
    cache_dir=Path("cache/superbet"),
    login_env="SUPERBET_LOGIN",
    password_env="SUPERBET_PASSWORD",
    popup_selectors=(
        "#onetrust-accept-btn-handler",
        "button:has-text('Akceptuję')",
        "button:has-text('Zgadzam się')",
        "button:has-text('Akceptuj wszystkie')",
        "button:has-text('Akceptuj')",
        "button:has-text('Zamknij')",
        "[aria-label='close']",
        "[aria-label='Zamknij']",
        "button.close",
    ),
    email_selectors=(
        "input[name='username']",
        "input[id*='username']",
        "input[placeholder*='użytkownika']",
        "input[placeholder*='uzytkownika']",
        "input[placeholder*='Nazwa']",
        "input[placeholder*='mail']",
        "input[placeholder*='Login']",
        "input[placeholder*='login']",
        "input[type='email']",
        "input[name='email']",
        "input[name='login']",
    ),
    login_trigger_selector="button:has-text('Zaloguj'), a:has-text('Zaloguj')",
    login_success_hidden="button:has-text('Zaloguj')",
)

SUPEROFERTA_CONFIG = SiteConfig(
    name="STS",
    url="https://www.sts.pl",
    cache_dir=Path("cache/superoferta"),
    login_env="STS_LOGIN",
    password_env="STS_HASLO",
    popup_selectors=(
        "button#onetrust-accept-btn-handler",
        "[aria-label='Zamknij']",
        "button:has-text('Akceptuję')",
    ),
)


def zamknij_popup(page: Page, cfg: SiteConfig) -> None:
    for sel in cfg.popup_selectors:
        try:
            page.click(sel, timeout=2000)
            time.sleep(0.3)
            logger.debug("[%s] Popup zamknięty: %s", cfg.name, sel)
            return
        except (PWTimeout, PWError):
            pass


def akceptuj_cookies(page: Page, cfg: SiteConfig) -> None:
    for sel in cfg.popup_selectors:
        try:
            page.wait_for_selector(sel, timeout=5000)
            page.click(sel)
            logger.info("[%s] Zaakceptowano cookies", cfg.name)
            time.sleep(1)
            return
        except (PWTimeout, PWError):
            pass
    logger.info("[%s] Baner cookie nie pojawił się lub już zaakceptowany", cfg.name)


def _zaloguj_impl(page: Page, cfg: SiteConfig) -> bool:
    login = os.getenv(cfg.login_env, "").strip()
    haslo = os.getenv(cfg.password_env, "").strip()

    if not login or not haslo:
        logger.info("[%s] Brak %s lub %s w .env", cfg.name, cfg.login_env, cfg.password_env)
        return False

    try:
        page.click(cfg.login_trigger_selector, timeout=3000)
        time.sleep(1.5)
    except (PWTimeout, PWError):
        pass

    email_combined = ", ".join(cfg.email_selectors)
    try:
        page.wait_for_selector(email_combined, timeout=5000)
    except PWTimeout:
        logger.info("[%s] Formularz logowania nie pojawił się", cfg.name)
        return False

    for sel in cfg.email_selectors:
        try:
            page.fill(sel, login, timeout=2000)
            break
        except (PWTimeout, PWError):
            continue

    time.sleep(0.3)

    for sel in cfg.password_selectors:
        try:
            page.fill(sel, haslo, timeout=2000)
            break
        except (PWTimeout, PWError):
            continue

    time.sleep(0.3)

    def _click_login() -> None:
        page.click(cfg.login_button_selector, timeout=5000)

    retry_with_backoff(_click_login, max_retries=3, base_delay=1.0)
    time.sleep(3)

    try:
        page.wait_for_selector(cfg.login_success_hidden, state="hidden", timeout=5000)
        logger.info("[%s] Zalogowano", cfg.name)
        return True
    except PWTimeout:
        for sel in cfg.avatar_selectors:
            if page.query_selector(sel):
                logger.info("[%s] Zalogowano", cfg.name)
                return True
        logger.info("[%s] Logowanie mogło się nie udać — kontynuuję", cfg.name)
        return False


def zaloguj(page: Page, cfg: SiteConfig) -> bool:
    try:
        with playwright_circuit:
            return _zaloguj_impl(page, cfg)
    except FootStatsCircuitOpenError as exc:
        logger.error("[%s] Circuit open, pomijam logowanie: %s", cfg.name, exc)
        return False
    except (PWTimeout, PWError) as exc:
        logger.info("[%s] Logowanie nieudane: %s", cfg.name, exc)
        return False


def zapisz_cache(dane: list, cfg: SiteConfig, nazwa: str = "kupony") -> Path:
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    sciezka = cfg.cache_dir / f"{nazwa}_{ts}.json"
    sciezka.write_text(json.dumps(dane, ensure_ascii=False, indent=2), encoding="utf-8")
    return sciezka
