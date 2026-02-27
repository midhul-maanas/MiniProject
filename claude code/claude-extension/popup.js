document.addEventListener('DOMContentLoaded', async () => {
  await loadData();
  setupEventListeners();
});

async function loadData() {
  const data = await chrome.storage.local.get(['activityData', 'config']);
  const activityData = data.activityData || {};
  const config = data.config || { emissionFactor: 0.475 };
  
  displaySummary(activityData, config);
  displayActivities(activityData, config);
}

function displaySummary(activityData, config) {
  let totalCO2 = 0;
  
  for (const [domain, data] of Object.entries(activityData)) {
    const energy = calculateEnergy(data.category, data.totalTime);
    const co2 = energy * config.emissionFactor;
    totalCO2 += co2;
  }
  
  document.getElementById('totalCO2').textContent = `${totalCO2.toFixed(2)} kg`;
  
  const status = getStatusLevel(totalCO2);
  const statusElement = document.getElementById('status');
  statusElement.textContent = status.label;
  statusElement.className = `badge ${status.class}`;
}

function displayActivities(activityData, config) {
  const activityList = document.getElementById('activityList');
  
  if (Object.keys(activityData).length === 0) {
    activityList.innerHTML = '<p class="no-data">No activity data yet</p>';
    return;
  }
  
  const activities = Object.entries(activityData)
    .map(([domain, data]) => {
      const energy = calculateEnergy(data.category, data.totalTime);
      const co2 = energy * config.emissionFactor;
      return { domain, data, co2 };
    })
    .sort((a, b) => b.co2 - a.co2)
    .slice(0, 10);
  
  activityList.innerHTML = activities.map(({ domain, data, co2 }) => `
    <div class="activity-item">
      <div>
        <div class="activity-name">${domain}</div>
        <div class="activity-time">${formatTime(data.totalTime)}</div>
      </div>
      <div class="activity-co2">${co2.toFixed(3)} kg</div>
    </div>
  `).join('');
}

function calculateEnergy(category, duration) {
  const energyRates = {
    'video': 0.15,
    'meeting': 0.12,
    'social': 0.05,
    'email': 0.02,
    'cloud': 0.08,
    'work': 0.06,
    'browsing': 0.03
  };
  
  const rate = energyRates[category] || energyRates['browsing'];
  const hours = duration / 3600;
  
  return hours * rate;
}

function getStatusLevel(totalCO2) {
  if (totalCO2 < 1) {
    return { label: 'Low', class: 'low' };
  } else if (totalCO2 < 5) {
    return { label: 'Moderate', class: 'moderate' };
  } else if (totalCO2 < 10) {
    return { label: 'High', class: 'high' };
  } else {
    return { label: 'Very High', class: 'very-high' };
  }
}

function formatTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

function setupEventListeners() {
  document.getElementById('viewDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:5000/dashboard' });
  });
  
  document.getElementById('resetData').addEventListener('click', async () => {
    if (confirm('Are you sure you want to reset all tracking data?')) {
      await chrome.storage.local.set({ activityData: {} });
      await loadData();
    }
  });
}