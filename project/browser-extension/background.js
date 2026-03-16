// let currentTabId = null;
// let currentUrl = null;
// let startTime = null;
// let isIdle = false;
// let currentStatus = 'completed';  // ✅ NEW: Track status

// chrome.runtime.onInstalled.addListener(() => {
//   console.log('Digital Carbon Footprint Tracker installed');
//   initializeStorage();
// });

// async function initializeStorage() {
//   const data = await chrome.storage.local.get(['activityData', 'config']);

//   if (!data.activityData) {
//     await chrome.storage.local.set({ activityData: {} });
//   }

//   if (!data.config) {
//     await chrome.storage.local.set({
//       config: {
//         region: 'global',
//         emissionFactor: 0.475,
//         trackingEnabled: true
//       }
//     });
//   }
// }

// chrome.tabs.onActivated.addListener(async (activeInfo) => {
//   await saveCurrentActivity();

//   const tab = await chrome.tabs.get(activeInfo.tabId);
//   startTracking(tab.id, tab.url);
// });

// chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
//   if (changeInfo.url && tabId === currentTabId) {
//     await saveCurrentActivity();
//     startTracking(tabId, changeInfo.url);
//   }
// });

// chrome.windows.onFocusChanged.addListener(async (windowId) => {
//   if (windowId === chrome.windows.WINDOW_ID_NONE) {
//     await saveCurrentActivity();
//     currentTabId = null;
//     currentUrl = null;
//     currentStatus = 'completed';  // ✅ Window lost focus = completed
//   } else {
//     const [tab] = await chrome.tabs.query({ active: true, windowId: windowId });
//     if (tab) {
//       startTracking(tab.id, tab.url);
//     }
//   }
// });

// chrome.idle.onStateChanged.addListener((state) => {
//   const domain = extractDomain(currentUrl);
//   const category = categorizeWebsite(domain);

//   // ✅ FIXED: Never mark video/meeting/streaming as idle
//   if (category === 'video' || category === 'meeting' || category === 'streaming') {
//     isIdle = false;
//     currentStatus = 'running';  // ✅ Always running
//     return;
//   }

//   // For other categories, handle idle normally
//   const wasIdle = isIdle;
//   isIdle = (state === 'idle' || state === 'locked');

//   if (isIdle && !wasIdle) {
//     // ✅ Entering idle state
//     currentStatus = 'idle';
//     saveCurrentActivity();  // Save with 'idle' status
//   } else if (!isIdle && wasIdle) {
//     // ✅ Exiting idle state (resume)
//     currentStatus = 'running';
//     if (currentTabId && currentUrl) {
//       startTime = Date.now();  // Resume tracking
//     }
//   }
// });

// // ✅ Listen for tab close
// chrome.tabs.onRemoved.addListener(async (tabId, removeInfo) => {
//   if (tabId === currentTabId) {
//     currentStatus = 'completed';  // ✅ Tab closed
//     await saveCurrentActivity();
//     currentTabId = null;
//     currentUrl = null;
//     startTime = null;
//   }
// });

// function startTracking(tabId, url) {
//   if (!url || url.startsWith('chrome://') || url.startsWith('chrome-extension://')) {
//     return;
//   }

//   currentTabId = tabId;
//   currentUrl = url;
//   startTime = Date.now();

//   const domain = extractDomain(url);
//   const category = categorizeWebsite(domain);

//   // ✅ Set initial status based on category
//   if (category === 'video' || category === 'meeting' || category === 'streaming') {
//     currentStatus = 'running';  // Always running, never idle
//     isIdle = false;
//   } else {
//     currentStatus = 'running';  // Normal running
//   }

//   console.log(`Started tracking: ${domain} (${category}) - Status: ${currentStatus}`);
// }

// async function saveCurrentActivity() {
//   if (!currentUrl || !startTime) {
//     return;
//   }

//   const endTime = Date.now();
//   const duration = (endTime - startTime) / 1000;

//   // ✅ Save even if idle (with idle status)
//   if (duration < 1) return;

//   const domain = extractDomain(currentUrl);
//   const category = categorizeWebsite(domain);

//   const data = await chrome.storage.local.get(['activityData']);
//   const activityData = data.activityData || {};

//   if (!activityData[domain]) {
//     activityData[domain] = {
//       totalTime: 0,
//       visits: 0,
//       category: category,
//       lastVisit: endTime,
//       status: currentStatus  // ✅ Store status
//     };
//   }

//   activityData[domain].totalTime += duration;
//   activityData[domain].visits += 1;
//   activityData[domain].lastVisit = endTime;
//   activityData[domain].status = currentStatus;  // ✅ Update status

//   await chrome.storage.local.set({ activityData });

//   console.log(`${domain} (${category}) - Duration: ${duration}s - Status: ${currentStatus}`);

//   sendToBackend(domain, duration, currentStatus);
// }

// function extractDomain(url) {
//   try {
//     const urlObj = new URL(url);
//     return urlObj.hostname.replace('www.', '');
//   } catch (e) {
//     return 'unknown';
//   }
// }

// function categorizeWebsite(domain) {
//   const categories = {
//     'video': ['youtube.com', 'netflix.com', 'vimeo.com', 'twitch.tv', 'hulu.com', 'primevideo.com'],
//     'social': ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'reddit.com', 'tiktok.com', 'x.com'],
//     'email': ['gmail.com', 'outlook.com', 'mail.yahoo.com', 'protonmail.com'],
//     'meeting': ['zoom.us', 'meet.google.com', 'teams.microsoft.com', 'webex.com'],
//     'cloud': ['drive.google.com', 'dropbox.com', 'onedrive.com', 'icloud.com'],
//     'work': ['docs.google.com', 'office.com', 'notion.so', 'slack.com', 'trello.com'],
//     'streaming': ['spotify.com', 'music.youtube.com', 'soundcloud.com', 'apple.com/music'],  // ✅ Added streaming
//     'ai': ['chatgpt.com', 'openai.com', 'gemini.google.com', 'bard.google.com', 'claude.ai', 'copilot.microsoft.com', 'perplexity.ai', 'grok.com'],
//   };

//   for (const [category, domains] of Object.entries(categories)) {
//     if (domains.some(d => domain.includes(d))) {
//       return category;
//     }
//   }

//   return 'browsing';
// }

// async function sendToBackend(domain, duration, status) {
//   try {
//     await fetch('http://localhost:5000/api/activity', {
//       method: 'POST',
//       headers: {
//         'Content-Type': 'application/json',
//       },
//       body: JSON.stringify({
//         source: 'browser',
//         domain: domain,
//         duration: duration,
//         timestamp: Date.now(),
//         category: categorizeWebsite(domain),
//         status: status  // ✅ Send status to backend
//       })
//     });
//   } catch (error) {
//     console.error('Failed to send data to backend:', error);
//   }
// }

// // ✅ FIXED: Periodic save with proper idle handling
// setInterval(async () => {
//   if (!currentUrl || !currentTabId) {
//     return;
//   }

//   const domain = extractDomain(currentUrl);
//   const category = categorizeWebsite(domain);

//   // ✅ Video/meeting/streaming: Always save, never idle
//   if (category === 'video' || category === 'meeting' || category === 'streaming') {
//     isIdle = false;
//     currentStatus = 'running';
//     await saveCurrentActivity();
//     startTime = Date.now();  // Reset for next interval
//     return;
//   }

//   // ✅ Other categories: Only save if not idle
//   if (!isIdle) {
//     currentStatus = 'running';
//     await saveCurrentActivity();
//     startTime = Date.now();  // Reset for next interval
//   } else {
//     // ✅ If idle, just update status but don't save duration
//     currentStatus = 'idle';
//   }
// }, 15000);  // Every 15 seconds

let currentTabId = null;
let currentUrl = null;
let startTime = null;
let isIdle = false;
let currentStatus = 'completed';
let tabUrls = {};

// --- Initialization ---

chrome.runtime.onInstalled.addListener(() => {
  console.log('Digital Carbon Footprint Tracker installed');
  initializeStorage();
});

async function initializeStorage() {
  const data = await chrome.storage.local.get(['activityData', 'config']);
  if (!data.activityData) await chrome.storage.local.set({ activityData: {} });
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

// --- Event Listeners ---

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  await saveCurrentActivity();
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab && tab.url) {
      startTracking(tab.id, tab.url);
    }
  } catch (error) {
    console.error("Error on tab activation:", error);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.url) {
    tabUrls[tabId] = changeInfo.url;
    if (tabId === currentTabId) {
      await saveCurrentActivity();
      startTracking(tabId, changeInfo.url);
    }
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    currentStatus = 'completed';
    await saveCurrentActivity();
    resetTrackingState();
  } else {
    const [tab] = await chrome.tabs.query({ active: true, windowId });
    if (tab) startTracking(tab.id, tab.url);
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const closedUrl = tabUrls[tabId];
  if (tabId === currentTabId) {
    currentStatus = 'completed';
    await saveCurrentActivity();
    resetTrackingState();
    console.log("Active tab closed -> completed");
  } else if (closedUrl) {
    // Notify backend that an inactive tab was closed
    sendToBackend(extractDomain(closedUrl), 0, 'completed');
    console.log(`Inactive tab closed -> completed: ${extractDomain(closedUrl)}`);
  }
  delete tabUrls[tabId];
});

chrome.idle.onStateChanged.addListener(async (state) => {
  if (!currentUrl) return;

  const category = categorizeWebsite(extractDomain(currentUrl));
  const isMedia = ['video', 'meeting', 'streaming'].includes(category);

  if (isMedia) {
    isIdle = false;
    currentStatus = 'running';
    return;
  }

  if (state === 'idle' || state === 'locked') {
    if (!isIdle) {
      isIdle = true;
      currentStatus = 'idle';
      await saveCurrentActivity();
    }
  } else {
    if (isIdle) {
      isIdle = false;
      currentStatus = 'running';
      startTime = Date.now();
    }
  }
});

// --- Core Logic Functions ---

function startTracking(tabId, url) {
  if (!url || url.startsWith('chrome://') || url.startsWith('chrome-extension://')) return;

  currentTabId = tabId;
  currentUrl = url;
  startTime = Date.now();
  tabUrls[tabId] = url;

  const category = categorizeWebsite(extractDomain(url));
  currentStatus = 'running';
  isIdle = false;

  console.log(`Tracking: ${extractDomain(url)} (${category})`);
  sendToBackend(extractDomain(url), 0, 'running');
}

async function saveCurrentActivity() {
  if (!currentUrl || !startTime) return;

  const endTime = Date.now();
  const duration = (endTime - startTime) / 1000;
  if (duration < 0.5) return; // Ignore micro-durations

  const domain = extractDomain(currentUrl);
  const category = categorizeWebsite(domain);

  const data = await chrome.storage.local.get(['activityData']);
  const activityData = data.activityData || {};

  if (!activityData[domain]) {
    activityData[domain] = { totalTime: 0, visits: 0, category, lastVisit: endTime, status: currentStatus };
  }

  activityData[domain].totalTime += duration;
  activityData[domain].visits += 1;
  activityData[domain].lastVisit = endTime;
  activityData[domain].status = currentStatus;

  await chrome.storage.local.set({ activityData });
  sendToBackend(domain, duration, currentStatus);
}

function resetTrackingState() {
  currentTabId = null;
  currentUrl = null;
  startTime = null;
  isIdle = false;
}

// --- Helpers ---

function extractDomain(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname.replace('www.', '');
  } catch {
    return 'unknown';
  }
}

function categorizeWebsite(domain) {
  // const categories = {
  //   video: ['youtube.com', 'netflix.com', 'vimeo.com', 'twitch.tv', 'hulu.com', 'primevideo.com'],
  //   social: ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'reddit.com', 'tiktok.com', 'x.com'],
  //   email: ['gmail.com', 'outlook.com', 'mail.yahoo.com', 'protonmail.com'],
  //   meeting: ['zoom.us', 'meet.google.com', 'teams.microsoft.com', 'webex.com'],
  //   cloud: ['drive.google.com', 'dropbox.com', 'onedrive.com', 'icloud.com'],
  //   work: ['docs.google.com', 'office.com', 'notion.so', 'slack.com', 'trello.com'],
  //   streaming: ['music.youtube.com', 'soundcloud.com', 'spotify.com', 'deezer.com'],
  //   ai: ['chatgpt.com', 'openai.com', 'gemini.google.com', 'claude.ai', 'perplexity.ai', 'grok.com']
  // };
  const categories = {
    video: ['youtube.com', 'netflix.com', 'vimeo.com', 'twitch.tv', 'hulu.com', 'primevideo.com', 'hotstar.com', 'sonyliv.com', 'zee5.com'],
    social: ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'reddit.com', 'tiktok.com', 'x.com', 'snapchat.com', 'discord.com', 'web.whatsapp.com'],
    email: ['gmail.com', 'outlook.com', 'mail.yahoo.com', 'protonmail.com', 'icloud.com'],
    meeting: ['zoom.us', 'meet.google.com', 'teams.microsoft.com', 'webex.com'],
    cloud: ['drive.google.com', 'dropbox.com', 'onedrive.com', 'icloud.com', 'mega.nz'],
    work: ['docs.google.com', 'office.com', 'notion.so', 'slack.com', 'trello.com', 'asana.com', 'clickup.com', 'miro.com'],
    productivity: ['calendar.google.com', 'todoist.com', 'ticktick.com', 'obsidian.md'],
    streaming: ['music.youtube.com', 'soundcloud.com', 'spotify.com', 'deezer.com', 'gaana.com', 'jiosaavn.com', 'wynk.in'],
    ai: ['chatgpt.com', 'openai.com', 'gemini.google.com', 'bard.google.com', 'claude.ai', 'perplexity.ai', 'copilot.microsoft.com', 'grok.com', 'character.ai'],
    shopping: ['amazon.com', 'amazon.in', 'flipkart.com', 'myntra.com', 'ajio.com', 'meesho.com', 'snapdeal.com', 'tatacliq.com', 'nykaa.com'],
    sports: ['espn.com', 'espncricinfo.com', 'cricbuzz.com', 'icc-cricket.com', 'fotmob.com'],
    news: ['bbc.com', 'cnn.com', 'ndtv.com', 'timesofindia.com', 'indianexpress.com', 'thehindu.com', 'hindustantimes.com'],
    education: ['coursera.org', 'udemy.com', 'edx.org', 'khanacademy.org', 'byjus.com', 'unacademy.com']
  };

  for (const [category, domains] of Object.entries(categories)) {
    if (domains.some(d => domain.includes(d))) return category;
  }
  return 'browsing';
}

async function sendToBackend(domain, duration, status) {
  try {
    await fetch('http://localhost:5000/api/activity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'browser',
        domain: domain,
        duration: duration,
        timestamp: Date.now(),
        category: categorizeWebsite(domain),
        status: status
      })
    });
  } catch (error) {
    console.error('Backend error:', error);
  }
}

// --- Heartbeat ---

setInterval(async () => {
  if (!currentUrl || !currentTabId || !startTime) return;

  const category = categorizeWebsite(extractDomain(currentUrl));
  const isMedia = ['video', 'meeting', 'streaming'].includes(category);

  if (isMedia || !isIdle) {
    await saveCurrentActivity();
    startTime = Date.now();
  } else {
    // Send periodic idle pulse to keep backend status accurate
    sendToBackend(extractDomain(currentUrl), 0, 'idle');
  }
}, 15000);