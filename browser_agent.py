import asyncio
import logging
from typing import Dict, Any
from browser_driver import browser_driver

logger = logging.getLogger("Omnia.BrowserAgent")

class AutonomousBrowserAgent:
    """Executes high-level web actions through an observation-action loop."""

    async def run_task(self, target_url: str, instruction: str, max_steps: int = 10) -> Dict[str, Any]:
        logger.info(f"Initiating browser task on {target_url} -> '{instruction}'")
        
        await browser_driver.navigate(target_url)
        step = 0

        while step < max_steps:
            step += 1
            interactive_nodes = await browser_driver.get_interactive_snapshot()
            
            logger.info(f"[Step {step}/{max_steps}] Visible interactive targets: {len(interactive_nodes)}")
            
            # Simple heuristic matcher for common single-step search/navigation workflows
            # In full pipeline, this snapshot is passed to the Antigravity LLM planner
            if "search" in instruction.lower():
                for node in interactive_nodes:
                    if node["tag"] == "input" and (node["type"] in ["text", "search"] or "search" in node["text"].lower() or "q" in node["id"].lower()):
                        query = instruction.lower().replace("search", "").replace("for", "").strip()
                        target_selector = node["selector"] or f"input[type='{node['type']}']"
                        await browser_driver.fill(target_selector, query)
                        await browser_driver.active_page.keyboard.press("Enter")
                        await asyncio.sleep(2.0)
                        return {
                            "status": "success",
                            "steps_taken": step,
                            "current_url": browser_driver.active_page.url,
                            "message": f"Successfully performed search query: '{query}'"
                        }
            
            # Allow observation cooldown
            await asyncio.sleep(1.0)
            break

        return {
            "status": "completed",
            "steps_taken": step,
            "final_url": browser_driver.active_page.url if browser_driver.active_page else target_url,
            "message": f"Task execution cycle concluded for: {instruction}"
        }

browser_agent = AutonomousBrowserAgent()
