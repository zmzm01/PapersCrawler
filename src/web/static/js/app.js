// PapersCrawler Web UI JavaScript

// Auto-refresh dashboard stats every 10 seconds
document.addEventListener('DOMContentLoaded', function() {
  const labels = document.querySelectorAll('[data-auto-refresh]');
  if (labels.length) {
    setInterval(() => {
      labels.forEach(el => {
        const url = el.dataset.url || '/pipeline/status';
        fetch(url).then(r => r.json()).then(data => {
          // Update elements as needed
        }).catch(() => {});
      });
    }, 10000);
  }
});

// SSE log streaming helper
function connectLogStream(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const evtSource = new EventSource('/pipeline/logs');
  evtSource.onmessage = function(e) {
    const data = JSON.parse(e.data);
    container.innerHTML += data.text;
    container.scrollTop = container.scrollHeight;
  };
  evtSource.onerror = function() {
    // Reconnect after 3s
    setTimeout(() => connectLogStream(containerId), 3000);
  };
}
