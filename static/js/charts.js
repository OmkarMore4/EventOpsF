// Admin dashboard charts. Called once from admin/dashboard.html with the
// server-computed data (see routes/admin.py: dashboard()).

function initDashboardCharts(data) {
  if (!window.Chart) return;

  var trendCtx = document.getElementById('trend-chart');
  if (trendCtx) {
    new Chart(trendCtx, {
      type: 'line',
      data: {
        labels: data.trendLabels,
        datasets: [{
          label: 'Volunteers checked in',
          data: data.trendValues,
          borderColor: '#D97706',
          backgroundColor: 'rgba(217, 118, 6, 0.12)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: '#D97706',
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { padding: 10, cornerRadius: 8 } },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: 'rgba(20,23,28,0.06)' } },
          x: { grid: { display: false } },
        },
      },
    });
  }

  var taskCtx = document.getElementById('task-chart');
  if (taskCtx) {
    new Chart(taskCtx, {
      type: 'doughnut',
      data: {
        labels: data.taskLabels,
        datasets: [{
          data: data.taskValues,
          backgroundColor: ['#F59E0B', '#3C6E9E', '#3F7D58'],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, padding: 14, font: { size: 11 } } },
          tooltip: { padding: 10, cornerRadius: 8 },
        },
      },
    });
  }

  var domainCtx = document.getElementById('domain-chart');
  if (domainCtx) {
    new Chart(domainCtx, {
      type: 'bar',
      data: {
        labels: data.domainLabels,
        datasets: [{
          data: data.domainValues,
          backgroundColor: '#14171C',
          borderRadius: 4,
          maxBarThickness: 26,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { padding: 10, cornerRadius: 8 } },
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: 'rgba(20,23,28,0.06)' } },
          y: { grid: { display: false } },
        },
      },
    });
  }
}
