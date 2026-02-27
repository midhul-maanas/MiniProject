let currentTabId = null;
let currentUrl = null;
let startTime = null;
let isIdle = false;

chrome.runtime.onInstalled.addListener(() => {
  console.log('Digital Carbon Footprint Tracker installed');
  initializeStorage();
});

async function initializeStorage() {
  const data = await chrome.storage.local.get(['activityData', 'config']);
  
  if (!data.activityData) {
    await chrome.storage.local.set({ activityData: {} });
  }
  
  if (!data.config) {
    await chrome.storage.local.set({
      config: {
        region: 'global',
        emissionFactor: 0.475,
        trackingEnabled: true
      }
    });
  }
}

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  await saveCurrentActivity();
  
  const tab = await chrome.tabs.get(activeInfo.tabId);
  startTracking(tab.id, tab.url);
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.url && tabId === currentTabId) {
    await saveCurrentActivity();
    startTracking(tabId, changeInfo.url);
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    await saveCurrentActivity();
    currentTabId = null;
    currentUrl = null;
  } else {
    const [tab] = await chrome.tabs.query({ active: true, windowId: windowId });
    if (tab) {
      startTracking(tab.id, tab.url);
    }
  }
});

chrome.idle.onStateChanged.addListener((state) => {
  isIdle = (state === 'idle' || state === 'locked');
  
  if (isIdle) {
    saveCurrentActivity();
  }
});

function startTracking(tabId, url) {
  if (!url || url.startsWith('chrome://') || url.startsWith('chrome-extension://')) {
    return;
  }
  
  currentTabId = tabId;
  currentUrl = url;
  startTime = Date.now();
}

async function saveCurrentActivity() {
  if (!currentUrl || !startTime || isIdle) {
    return;
  }
  
  const endTime = Date.now();
  const duration = (endTime - startTime) / 1000;
  
  if (duration < 1) return;
  
  const domain = extractDomain(currentUrl);
  
  const data = await chrome.storage.local.get(['activityData']);
  const activityData = data.activityData || {};
  
  if (!activityData[domain]) {
    activityData[domain] = {
      totalTime: 0,
      visits: 0,
      category: categorizeWebsite(domain),
      lastVisit: endTime
    };
  }
  
  activityData[domain].totalTime += duration;
  activityData[domain].visits += 1;
  activityData[domain].lastVisit = endTime;
  
  await chrome.storage.local.set({ activityData });
  
  sendToBackend(domain, duration);
}

function extractDomain(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.replace('www.', '');
  } catch (e) {
    return 'unknown';
  }
}

function categorizeWebsite(domain) {
  const categories = {
    'video': ['youtube.com', 'netflix.com', 'vimeo.com', 'twitch.tv', 'hulu.com', 'primevideo.com'],
    'social': ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'reddit.com', 'tiktok.com'],
    'email': ['gmail.com', 'outlook.com', 'mail.yahoo.com', 'protonmail.com'],
    'meeting': ['zoom.us', 'meet.google.com', 'teams.microsoft.com', 'webex.com'],
    'cloud': ['drive.google.com', 'dropbox.com', 'onedrive.com', 'icloud.com'],
    'work': ['docs.google.com', 'office.com', 'notion.so', 'slack.com', 'trello.com']
  };
  
  for (const [category, domains] of Object.entries(categories)) {
    if (domains.some(d => domain.includes(d))) {
      return category;
    }
  }
  
  return 'browsing';
}

async function sendToBackend(domain, duration) {
  try {
    await fetch('http://localhost:5000/api/activity', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        source: 'browser',
        domain: domain,
        duration: duration,
        timestamp: Date.now(),
        category: categorizeWebsite(domain)
      })
    });
  } catch (error) {
    console.error('Failed to send data to backend:', error);
  }
}

setInterval(async () => {
  if (!isIdle) {
    await saveCurrentActivity();
    if (currentTabId && currentUrl) {
      startTime = Date.now();
    }
  }
}, 30000);