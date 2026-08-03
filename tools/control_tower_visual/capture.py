from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

def repository_root() -> Path:
    script_path = Path(__file__).resolve()
    root = script_path.parent.parent.parent
    if not (root / "src").is_dir():
        raise RuntimeError(f"Could not resolve dashboard-odoo repository root from {script_path}")
    return root


REPO_ROOT = repository_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BASE_URL = os.environ.get("CONTROL_TOWER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DASHBOARD_PATH = "/dashboard/control-tower"

PROFILES = {
    "desk-1680x896": {"width": 1680, "height": 896},
    "office-1920x1080": {"width": 1920, "height": 1080},
}

STATES = (
    "01-overview",
    "02-temuan-expanded",
    "03-hover-manufacturing-order",
    "04-stock-check-unmapped",
    "05-manufacturing-order-mapped",
    "06-purchase-order-mapped",
)

STABILITY_CSS = """
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  caret-color: transparent !important;
}
"""


def get_credentials() -> tuple[str, str]:
    username = os.environ.get("DASHBOARD_USERNAME", "")
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if username and password:
        return username, password

    try:
        from src.utils.settings import get_settings

        settings = get_settings()
        return str(settings.dashboard_username), str(settings.dashboard_password)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Dashboard credentials were not available. Set DASHBOARD_USERNAME and "
            "DASHBOARD_PASSWORD, or run from the dashboard-odoo repository root."
        ) from exc


def launch_browser(playwright: Playwright) -> Browser:
    errors: list[str] = []
    for channel in ("msedge", "chrome"):
        try:
            return playwright.chromium.launch(channel=channel, headless=True)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{channel}: {exc}")
    raise RuntimeError(
        "Could not launch Microsoft Edge or Google Chrome through Playwright.\n"
        + "\n".join(errors)
    )


def wait_for_map(page: Page) -> None:
    page.wait_for_selector("[data-ct-map-stage]", state="visible", timeout=20_000)
    page.wait_for_function(
        """
        () => {
          const nodes = [...document.querySelectorAll('[data-ct-process-node]')];
          return nodes.length > 0 && nodes.every((node) => Boolean(node.dataset.evidenceState));
        }
        """,
        timeout=25_000,
    )
    page.evaluate("document.fonts && document.fonts.ready")
    page.wait_for_timeout(250)


def ensure_login(page: Page) -> None:
    page.goto(f"{BASE_URL}{DASHBOARD_PATH}", wait_until="domcontentloaded", timeout=30_000)
    if page.locator('form[action="/login"]').count() > 0:
        username, password = get_credentials()
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_url(f"**{DASHBOARD_PATH}**", timeout=20_000)
    wait_for_map(page)


def prepare_page(context: BrowserContext, selected_process: str | None = None) -> Page:
    page = context.new_page()
    target = f"{BASE_URL}{DASHBOARD_PATH}"
    if selected_process:
        target += f"?selected_process={selected_process}"
    page.goto(target, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('form[action="/login"]').count() > 0:
        username, password = get_credentials()
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_url(f"**{DASHBOARD_PATH}**", timeout=20_000)
        if selected_process:
            page.goto(target, wait_until="domcontentloaded", timeout=30_000)
    wait_for_map(page)
    page.add_style_tag(content=STABILITY_CSS)
    page.evaluate(
        """
        () => {
          const mapScroll = document.querySelector('[data-ct-map-scroll]');
          if (mapScroll) {
            mapScroll.scrollLeft = 0;
            mapScroll.scrollTop = 0;
          }
          window.scrollTo(0, 0);
        }
        """
    )
    page.wait_for_timeout(100)
    return page


def capture_state(context: BrowserContext, output_dir: Path, state: str) -> None:
    selected_by_state = {
        "04-stock-check-unmapped": "stock-check",
        "05-manufacturing-order-mapped": "manufacturing-order",
        "06-purchase-order-mapped": "material-purchase-order",
    }
    page = prepare_page(context, selected_by_state.get(state))
    try:
        if state == "02-temuan-expanded":
            toggle = page.locator("[data-ct-temuan-toggle]")
            if toggle.get_attribute("aria-expanded") != "true":
                toggle.click()
                page.wait_for_timeout(100)
        elif state == "03-hover-manufacturing-order":
            page.locator('[data-process-key="manufacturing-order"]').hover()
            page.locator("[data-ct-hover-preview]").wait_for(state="visible", timeout=5_000)
            page.wait_for_timeout(100)

        page.screenshot(path=str(output_dir / f"{state}.png"), full_page=False)
    finally:
        page.close()


def capture(profile_names: Iterable[str], output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        try:
            for profile_name in profile_names:
                viewport = PROFILES[profile_name]
                profile_dir = output_root / profile_name
                profile_dir.mkdir(parents=True, exist_ok=True)
                context = browser.new_context(
                    viewport=viewport,
                    device_scale_factor=1,
                    locale="id-ID",
                    reduced_motion="reduce",
                    color_scheme="light",
                )
                try:
                    bootstrap = context.new_page()
                    ensure_login(bootstrap)
                    bootstrap.close()
                    for state in STATES:
                        print(f"Capturing {profile_name}/{state} ...")
                        capture_state(context, profile_dir, state)
                finally:
                    context.close()
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture deterministic Control Tower screenshots.")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output root for screenshot profiles.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PROFILES),
        help="Capture only the named profile. Repeat to capture multiple profiles.",
    )
    args = parser.parse_args()
    profiles = args.profile or list(PROFILES)
    capture(profiles, args.output.resolve())
    print(f"Screenshots written to: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
