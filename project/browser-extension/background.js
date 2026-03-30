
let tabStates = {};
let currentTabId = null;
let currentUrl = null;

const IDLE_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes, matches config default

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
        trackingEnabled: true,
        idleThresholdSeconds: 300 // 5 minutes
      }
    });
  }
  await syncIdleDetectionInterval();
}

async function syncIdleDetectionInterval() {
  const { config } = await chrome.storage.local.get('config');
  const threshold = config?.idleThresholdSeconds ?? 300;
  chrome.idle.setDetectionInterval(Math.max(15, threshold));
}

// --- Helpers ---

function extractDomain(url) {
  try {
    const domain = new URL(url).hostname.replace('www.', '');
    if (domain === 'localhost' || domain === 'newtab' || url.startsWith('chrome://newtab')) {
      return null;
    }
    return domain;
  } catch {
    return 'unknown';
  }
}

function categorizeWebsite(domain) {
  const categories = {
    video: ['youtube.com', 'netflix.com', 'vimeo.com', 'twitch.tv', 'hulu.com', 'primevideo.com', 'hotstar.com', 'sonyliv.com', 'zee5.com'],
    social: ['facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com', 'reddit.com', 'tiktok.com', 'x.com', 'snapchat.com', 'discord.com', 'web.whatsapp.com'],
    email: ['gmail.com', 'mail.google.com', 'outlook.com', 'outlook.live.com', 'mail.yahoo.com', 'protonmail.com', 'icloud.com'],
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

async function sendToBackend(domain, duration, status, totalTime = 0) {
  try {
    await fetch('http://localhost:5000/api/activity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'browser',
        domain,
        duration,
        totalTime,
        timestamp: Date.now(),
        category: categorizeWebsite(domain),
        status
      })
    });
  } catch (error) {
    console.error('Backend error:', error);
  }
}


// --- Core Logic Functions ---

function initTabState(tabId, url, status = 'running') {
  tabStates[tabId] = {
    url,
    category: categorizeWebsite(extractDomain(url)),
    status,
    totalTime: 0,
    segmentStart: status === 'running' ? Date.now() : null,
    backgroundSince: status === 'running' ? null : Date.now(), // track when sent to background
    visits: 1,
    lastVisit: Date.now()
  };
}

/**
 * Flush the current active segment's time into totalTime.
 * Does NOT reset totalTime — only closes the open segment.
 */
async function flushTabTime(tabId) {
  const state = tabStates[tabId];
  if (!state || !state.segmentStart || state.status !== 'running') return;

  const segmentDuration = (Date.now() - state.segmentStart) / 1000;
  if (segmentDuration >= 0.5) {
    state.totalTime += segmentDuration;
  }
  state.segmentStart = null;

  await persistTabToStorage(tabId);
  sendToBackend(extractDomain(state.url), segmentDuration, state.status, state.totalTime);
}

/**
 * Resume an existing tab (switching back to it) or start fresh if unknown.
 * totalTime is preserved — only segmentStart resets.
 */
async function resumeOrStartTab(tabId, url) {
  if (!url || url.startsWith('chrome://') || url.startsWith('chrome-extension://')) return;

  if (tabStates[tabId] && tabStates[tabId].url === url) {
    // Known tab — resume without resetting totalTime
    const state = tabStates[tabId];
    state.status = 'running';
    state.segmentStart = Date.now();
    state.backgroundSince = null; // no longer in background
    state.visits += 1;
    state.lastVisit = Date.now();
    console.log(`Tab ${tabId} resumed: ${extractDomain(url)} (totalTime: ${state.totalTime.toFixed(1)}s)`);
  } else {
    // New or navigated tab — carry forward previous totalTime for this domain
    initTabState(tabId, url, 'running');
    const domain = extractDomain(url);
    const { activityData = {} } = await chrome.storage.local.get('activityData');
    if (activityData[domain] && activityData[domain].totalTime > 0) {
      tabStates[tabId].totalTime = activityData[domain].totalTime;
      tabStates[tabId].visits = (activityData[domain].visits || 0) + 1;
      console.log(`Tab ${tabId} started: ${domain} (resumed totalTime: ${tabStates[tabId].totalTime.toFixed(1)}s)`);
    } else {
      console.log(`Tab ${tabId} started: ${domain} (fresh)`);
    }
  }

  sendToBackend(extractDomain(url), 0, 'running', tabStates[tabId].totalTime);
  await persistTabToStorage(tabId);
}

/**
 * Send a tab to background — flush its time, set backgroundSince,
 * but keep status as 'running' until the threshold elapses.
 */
async function sendTabToBackground(tabId) {
  const state = tabStates[tabId];
  if (!state) return;

  await flushTabTime(tabId);         // save the segment time accumulated so far
  state.backgroundSince = Date.now(); // start the background idle clock
  // status stays 'running' — heartbeat will flip to 'idle' after threshold
  console.log(`Tab ${tabId} sent to background: ${extractDomain(state.url)} (status stays running for now)`);
}

async function persistTabToStorage(tabId) {
  const state = tabStates[tabId];
  if (!state) return;

  const domain = extractDomain(state.url);
  const { activityData = {} } = await chrome.storage.local.get('activityData');

  if (!activityData[domain]) {
    activityData[domain] = { totalTime: 0, visits: 0, category: state.category, lastVisit: state.lastVisit, status: state.status };
  }

  activityData[domain].totalTime = state.totalTime;
  activityData[domain].visits = state.visits;
  activityData[domain].lastVisit = state.lastVisit;
  activityData[domain].status = state.status;

  await chrome.storage.local.set({ activityData });
}

// --- Event Listeners ---

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const previousTabId = currentTabId;

  // Send previous tab to background (status stays 'running' until threshold)
  if (previousTabId && tabStates[previousTabId]) {
    await sendTabToBackground(previousTabId);
  }

  currentTabId = activeInfo.tabId;

  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab?.url) {
      currentUrl = tab.url;
      await resumeOrStartTab(activeInfo.tabId, tab.url);
    }
  } catch (error) {
    console.error("Error on tab activation:", error);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!changeInfo.url) return;

  if (tabId === currentTabId) {
    await flushTabTime(tabId);
    currentUrl = changeInfo.url;
    initTabState(tabId, changeInfo.url, 'running');
    sendToBackend(extractDomain(changeInfo.url), 0, 'running', 0);
  } else {
    // Background tab navigated — reset state, preserve background clock
    initTabState(tabId, changeInfo.url, 'running');
    tabStates[tabId].segmentStart = null;
    tabStates[tabId].backgroundSince = Date.now();
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) {
    // Window lost focus — send current tab to background
    if (currentTabId && tabStates[currentTabId]) {
      await sendTabToBackground(currentTabId);
    }
  } else {
    const [tab] = await chrome.tabs.query({ active: true, windowId });
    if (tab) {
      currentTabId = tab.id;
      currentUrl = tab.url;
      await resumeOrStartTab(tab.id, tab.url);
    }
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  // Clear active-tab pointer FIRST to prevent onActivated race condition.
  // If onActivated fires for the next tab before onRemoved finishes,
  // it would try to sendTabToBackground(currentTabId) — which is the
  // now-dead tab — corrupting its segment.
  const wasActiveTab = (tabId === currentTabId);
  if (wasActiveTab) {
    currentTabId = null;
    currentUrl = null;
  }

  const state = tabStates[tabId];
  if (state) {
    // Force-flush any open segment regardless of status.
    // flushTabTime() guards on status === 'running', but the active tab
    // might have been marked 'idle' by chrome.idle while still having an
    // open segmentStart (edge case). We handle it directly here.
    if (state.segmentStart) {
      const now = Date.now();
      const segmentDuration = (now - state.segmentStart) / 1000;
      if (segmentDuration >= 0.5) {
        state.totalTime += segmentDuration;
      }
      state.segmentStart = null;
    }

    // Mark completed and persist
    state.status = 'completed';
    const domain = extractDomain(state.url);

    await persistTabToStorage(tabId);
    await sendToBackend(domain, 0, 'completed', state.totalTime);

    // --- Manual input prompt for email / cloud categories ---
    const category = categorizeWebsite(domain);
    if (category === 'email' || category === 'cloud') {
      promptManualInput(category);
    }

    console.log(`Tab ${tabId} closed -> completed (${domain}, totalTime: ${state.totalTime.toFixed(1)}s, wasActive: ${wasActiveTab})`);
    delete tabStates[tabId];
  }
});

/**
 * Open a styled popup window for manual activity input when
 * an email or cloud tab is closed.
 */
async function promptManualInput(category) {
  try {
    const baseUrl = chrome.runtime.getURL('manual-input.html');
    const popupUrl = `${baseUrl}?category=${category}`;

    // Size the popup to fit each form
    const width = 440;
    const height = category === 'cloud' ? 540 : 400;

    chrome.windows.create({
      url: popupUrl,
      type: 'popup',
      width,
      height,
      focused: true
    });

    console.log(`Manual input popup opened for category: ${category}`);
  } catch (error) {
    console.error('Error opening manual input popup:', error);
  }
}


chrome.idle.onStateChanged.addListener(async (state) => {
  if (!currentTabId || !tabStates[currentTabId]) return;

  const category = tabStates[currentTabId].category;
  const isMedia = ['video', 'meeting', 'streaming'].includes(category);
  if (isMedia) return;

  if (state === 'idle' || state === 'locked') {
    await flushTabTime(currentTabId);
    tabStates[currentTabId].status = 'idle';
    tabStates[currentTabId].backgroundSince = Date.now();
    sendToBackend(
      extractDomain(tabStates[currentTabId].url),
      0, 'idle',
      tabStates[currentTabId].totalTime
    );
  } else if (state === 'active') {
    if (tabStates[currentTabId].status === 'idle') {
      tabStates[currentTabId].status = 'running';
      tabStates[currentTabId].segmentStart = Date.now();
      tabStates[currentTabId].backgroundSince = null;
      sendToBackend(
        extractDomain(tabStates[currentTabId].url),
        0, 'running',
        tabStates[currentTabId].totalTime
      );
    }
  }
});

// --- Heartbeat (every 15s) ---

setInterval(async () => {
  const { config } = await chrome.storage.local.get('config');
  const idleThresholdMs = (config?.idleThresholdSeconds ?? 300) * 1000;
  const now = Date.now();

  for (const [tabIdStr, state] of Object.entries(tabStates)) {
    const tabId = parseInt(tabIdStr);
    const domain = extractDomain(state.url);
    const isMedia = ['video', 'meeting', 'streaming'].includes(state.category);

    if (tabId === currentTabId) {
      // --- Active tab ---
      if (isMedia || state.status === 'running') {
        // Flush and restart segment
        await flushTabTime(tabId);
        state.segmentStart = Date.now();
      }
    } else {
      // --- Background tab ---
      const timeInBackground = state.backgroundSince ? now - state.backgroundSince : Infinity;

      if (isMedia) {
        // Media tabs (video/streaming/meeting) NEVER go idle — always running
        if (state.status === 'idle') {
          state.status = 'running';
          state.segmentStart = null;
          state.backgroundSince = now;
        }
        sendToBackend(domain, 0, 'running', state.totalTime);
        console.log(`Background media tab ${tabId} always running: ${domain}`);
      } else if (state.status === 'running' && timeInBackground >= idleThresholdMs) {
        // Threshold crossed — flip to idle
        state.status = 'idle';
        await persistTabToStorage(tabId);
        sendToBackend(domain, 0, 'idle', state.totalTime);
        console.log(`Background tab ${tabId} idle after ${Math.round(timeInBackground / 1000)}s: ${domain}`);
      } else if (state.status === 'running') {
        // Still within threshold — send running pulse with time remaining
        const remaining = Math.round((idleThresholdMs - timeInBackground) / 1000);
        sendToBackend(domain, 0, 'running', state.totalTime);
        console.log(`Background tab ${tabId} still running, ${remaining}s until idle: ${domain}`);
      } else if (state.status === 'idle') {
        // Already idle — periodic idle pulse
        sendToBackend(domain, 0, 'idle', state.totalTime);
      }
    }
  }
}, 15000);