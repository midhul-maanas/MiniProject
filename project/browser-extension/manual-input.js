// CO2 factors — must match dashboard.html
const CO2_FACTORS = {
  email: { sent: 0.004, received: 0.0005 },
  cloud: { upload: 0.00003, download: 0.00003 }
};

// Read category from URL params
const params = new URLSearchParams(window.location.search);
const category = params.get('category');

// Show the right form
if (category === 'email') {
  document.getElementById('email-form').style.display = 'block';
} else if (category === 'cloud') {
  document.getElementById('cloud-form').style.display = 'block';
}

// Focus the first input
setTimeout(() => {
  const visibleForm = document.querySelector('[id$="-form"][style*="block"]');
  const firstInput = visibleForm?.querySelector('input[type="number"]');
  if (firstInput) firstInput.focus();
}, 200);

// --- Email handlers ---
document.getElementById('btn-submit-email').addEventListener('click', async () => {
  const sent = parseInt(document.getElementById('email-sent').value, 10) || 0;
  const received = parseInt(document.getElementById('email-received').value, 10) || 0;
  const co2 = (sent * CO2_FACTORS.email.sent) + (received * CO2_FACTORS.email.received);

  try {
    await fetch('http://localhost:5000/api/manual-activity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: { sent, received, co2 } })
    });
    showSuccess();
  } catch (e) {
    console.error('Failed to send email data:', e);
    window.close();
  }
});

document.getElementById('btn-skip-email').addEventListener('click', () => {
  window.close();
});

// --- Cloud handlers ---
document.getElementById('btn-submit-cloud').addEventListener('click', async () => {
  const upload_size = parseFloat(document.getElementById('cloud-upload-size').value) || 0;
  const download_size = parseFloat(document.getElementById('cloud-download-size').value) || 0;
  const co2 = (upload_size * CO2_FACTORS.cloud.upload) + (download_size * CO2_FACTORS.cloud.download);

  try {
    await fetch('http://localhost:5000/api/manual-activity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cloud: { upload_size, download_size, co2 } })
    });
    showSuccess();
  } catch (e) {
    console.error('Failed to send cloud data:', e);
    window.close();
  }
});

document.getElementById('btn-skip-cloud').addEventListener('click', () => {
  window.close();
});

// Enter key submits, Escape closes
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const visibleSubmit = document.querySelector('[id$="-form"][style*="block"] .btn-submit');
    if (visibleSubmit) visibleSubmit.click();
  }
  if (e.key === 'Escape') {
    window.close();
  }
});

function showSuccess() {
  document.getElementById('email-form').style.display = 'none';
  document.getElementById('cloud-form').style.display = 'none';
  document.getElementById('success-msg').style.display = 'block';
  setTimeout(() => window.close(), 800);
}
