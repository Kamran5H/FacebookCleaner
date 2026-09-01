chrome.action.onClicked.addListener(async (tab) => {
  if (tab.id && tab.url && tab.url.includes('facebook.com')) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });
    } catch (e) {
      console.error('Failed to inject Zenith cleaner:', e);
    }
  } else {
    chrome.tabs.create({ url: 'https://www.facebook.com/me/friends' });
  }
});
