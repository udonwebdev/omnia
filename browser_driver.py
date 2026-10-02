import asyncio
import logging
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.BrowserDriver")

class BrowserDriver:
    """Manages browser connectivity via CDP remote debugging or standalone Playwright."""

    def __init__(self, cdp_port: int = 9222):
        self.cdp_port = cdp_port
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.active_page: Optional[Page] = None

    async def initialize(self):
        """Attempts connection to local running Chrome CDP, otherwise launches dedicated instance."""
        self.playwright = await async_playwright().start()
        endpoint_url = f"http://127.0.0.1:{self.cdp_port}"
        
        try:
            logger.info(f"Attempting to attach to active browser session at {endpoint_url}...")
            self.browser = await self.playwright.chromium.connect_over_cdp(endpoint_url)
            contexts = self.browser.contexts
            self.context = contexts[0] if contexts else await self.browser.new_context()
            pages = self.context.pages
            self.active_page = pages[0] if pages else await self.context.new_page()
            logger.info("Successfully connected to active browser session via CDP.")
        except Exception as e:
            logger.warning(f"CDP connection unavailable ({e}). Launching local managed browser...")
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    channel="chrome",
                    args=["--disable-blink-features=AutomationControlled"]
                )
            except Exception:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    channel="msedge",
                    args=["--disable-blink-features=AutomationControlled"]
                )
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self.active_page = await self.context.new_page()
            logger.info("Dedicated managed browser initialized.")

    async def navigate(self, url: str) -> str:
        """Navigates to a given URL and waits for network idle state."""
        if not self.active_page:
            await self.initialize()
        await self.active_page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return self.active_page.url

    async def get_interactive_snapshot(self) -> List[Dict[str, Any]]:
        """Parses interactive DOM elements (buttons, inputs, links) with stable selectors."""
        if not self.active_page:
            return []

        js_eval = """
        () => {
            const elements = [];
            const interactive = document.querySelectorAll('button, a, input, select, textarea, [role="button"]');
            interactive.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const isVisible = rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).visibility !== 'hidden';
                if (isVisible) {
                    elements.push({
                        index: index,
                        tag: el.tagName.toLowerCase(),
                        type: el.type || '',
                        text: (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80),
                        id: el.id || '',
                        selector: el.id ? '#' + el.id : (el.name ? `[name="${el.name}"]` : null)
                    });
                }
            });
            return elements.slice(0, 50); // Limit payload
        }
        """
        return await self.active_page.evaluate(js_eval)

    async def click(self, selector: str) -> bool:
        """Clicks an element by selector or text heuristic."""
        if not self.active_page:
            return False
        try:
            await self.active_page.click(selector, timeout=5000)
            return True
        except Exception as e:
            logger.error(f"Click failed for selector {selector}: {e}")
            return False

    async def fill(self, selector: str, value: str) -> bool:
        """Fills an input field."""
        if not self.active_page:
            return False
        try:
            await self.active_page.fill(selector, value, timeout=5000)
            return True
        except Exception as e:
            logger.error(f"Fill failed for selector {selector}: {e}")
            return False

    async def close(self):
        """Cleans up browser processes."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

browser_driver = BrowserDriver()
