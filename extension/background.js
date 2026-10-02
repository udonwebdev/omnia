const OMNIA_BUS_URL = "http://127.0.0.1:8000/api/context/tab";

async function harvestTab(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab.url || tab.url.startsWith("chrome://") || tab.url.startsWith("edge://")) return;

    // Execute script to grab visible DOM text
    const injection = await chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: () => {
        return {
          title: document.title,
          textSample: document.body ? document.body.innerText.slice(0, 4000) : ""
        };
      }
    });

    if (injection && injection[0] && injection[0].result) {
      const payload = {
        tab_id: tab.id,
        url: tab.url,
        title: injection[0].result.title,
        content: injection[0].result.textSample,
        timestamp: Date.now()
      };

      await fetch(OMNIA_BUS_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    }
  } catch (err) {
    // Ignore context invalidation on protected pages
  }
}

// Listen to navigation completions and tab activations
chrome.tabs.onActivated.addListener((activeInfo) => harvestTab(activeInfo.tabId));
chrome.webNavigation.onCompleted.addListener((details) => {
  if (details.frameId === 0) harvestTab(details.tabId);
});
