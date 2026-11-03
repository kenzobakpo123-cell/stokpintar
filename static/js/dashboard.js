const chartElement = document.getElementById('stockTrendChart');

if (chartElement && window.Chart) {
  const { labels, stockIn, stockOut } = chartElement.dataset;

  new Chart(chartElement.querySelector('canvas'), {
    type: 'line',
    data: {
      labels: JSON.parse(labels),
      datasets: [
        {
          label: 'Stok masuk',
          data: JSON.parse(stockIn),
          borderColor: '#198754',
          backgroundColor: 'rgba(25, 135, 84, 0.12)',
          pointBackgroundColor: '#198754',
          tension: 0.35,
          fill: true
        },
        {
          label: 'Stok keluar',
          data: JSON.parse(stockOut),
          borderColor: '#dc3545',
          backgroundColor: 'rgba(220, 53, 69, 0.08)',
          pointBackgroundColor: '#dc3545',
          tension: 0.35,
          fill: true
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        legend: { position: 'bottom', labels: { usePointStyle: true, padding: 20 } }
      },
      scales: {
        y: {
          beginAtZero: true,
          title: { display: true, text: 'Jumlah unit' },
          grid: { color: 'rgba(148, 163, 184, 0.15)' }
        },
        x: { grid: { display: false } }
      }
    }
  });
}
