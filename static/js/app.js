/**
 * WX-Station Dashboard JavaScript
 * Handles SVG Gauges, Live-Data Polling, RRD Charts and Statistics.
 */

(function () {
  'use strict';

  let currentPeriod = '24h';
  let currentChartType = 'temp';
  let historyCache = {};
  let chartInstance = null;

  // DOM Elements
  const elLiveClock = document.getElementById('live-clock');
  const elLiveDate = document.getElementById('live-date');
  const elLastUpdate = document.getElementById('last-update-time');
  const elSensorBadge = document.getElementById('sensor-badge');
  const elStatusBadge = document.getElementById('status-badge');

  // Value Display Elements
  const elValTemp = document.getElementById('val-temp');
  const elValDew = document.getElementById('val-dew');
  const elValHum = document.getElementById('val-hum');
  const elHumComfort = document.getElementById('hum-comfort-text');
  const elValPressQnh = document.getElementById('val-press-qnh');
  const elValPressQfe = document.getElementById('val-press-qfe');

  // Stats Summary Elements
  const elStatTempMin = document.getElementById('stat-temp-min');
  const elStatTempAvg = document.getElementById('stat-temp-avg');
  const elStatTempMax = document.getElementById('stat-temp-max');

  const elStatHumMin = document.getElementById('stat-hum-min');
  const elStatHumAvg = document.getElementById('stat-hum-avg');
  const elStatHumMax = document.getElementById('stat-hum-max');

  const elStatQnhMin = document.getElementById('stat-qnh-min');
  const elStatQnhAvg = document.getElementById('stat-qnh-avg');
  const elStatQnhMax = document.getElementById('stat-qnh-max');

  const elStatDewMin = document.getElementById('stat-dew-min');
  const elStatDewAvg = document.getElementById('stat-dew-avg');
  const elStatDewMax = document.getElementById('stat-dew-max');

  // Gauge SVGs
  const svgTemp = document.getElementById('gauge-temp');
  const svgHum = document.getElementById('gauge-hum');
  const svgPress = document.getElementById('gauge-press');

  /* =========================================================================
     1. Clock & Timing
     ========================================================================= */
  function updateClock() {
    const now = new Date();
    elLiveClock.textContent = now.toLocaleTimeString('de-CH', { hour12: false });
    elLiveDate.textContent = now.toLocaleDateString('de-CH', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' });
  }
  setInterval(updateClock, 1000);
  updateClock();

  /* =========================================================================
     2. SVG Gauge Drawing Engine & Theme Helpers
     ========================================================================= */
  function getThemeColors() {
    const isLight = document.documentElement.getAttribute('data-theme') === 'light';
    return {
      isLight: isLight,
      trackColor: isLight ? '#e2e8f0' : '#1e293b',
      centerFill: isLight ? '#ffffff' : '#0f172a',
      labelColor: isLight ? '#64748b' : '#94a3b8',
      chartText: isLight ? '#334155' : '#cbd5e1',
      chartGrid: isLight ? 'rgba(203, 213, 225, 0.6)' : 'rgba(51, 65, 85, 0.3)',
      tooltipBg: isLight ? '#ffffff' : '#0f172a',
      tooltipBorder: isLight ? '#cbd5e1' : '#334155',
      tooltipTitle: isLight ? '#0284c7' : '#38bdf8',
    };
  }

  function polarToCartesian(cx, cy, radius, angleInDegrees) {
    const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
    return {
      x: cx + (radius * Math.cos(angleInRadians)),
      y: cy + (radius * Math.sin(angleInRadians))
    };
  }

  function describeArc(cx, cy, radius, startAngle, endAngle) {
    const start = polarToCartesian(cx, cy, radius, endAngle);
    const end = polarToCartesian(cx, cy, radius, startAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';
    return [
      'M', start.x, start.y,
      'A', radius, radius, 0, largeArcFlag, 0, end.x, end.y
    ].join(' ');
  }

  function renderGauge(svg, minVal, maxVal, currentVal, options) {
    if (!svg) return;
    const theme = getThemeColors();
    const cx = 100;
    const cy = 95;
    const radius = 70;
    const startAngle = -120;
    const endAngle = 120;
    const totalAngle = endAngle - startAngle;

    const clamped = Math.max(minVal, Math.min(maxVal, currentVal !== null && currentVal !== undefined ? currentVal : minVal));
    const ratio = (clamped - minVal) / (maxVal - minVal);
    const valueAngle = startAngle + (ratio * totalAngle);

    // Track arc
    const bgArcPath = describeArc(cx, cy, radius, startAngle, endAngle);
    // Value arc
    const valArcPath = describeArc(cx, cy, radius, startAngle, valueAngle);

    // Pointer
    const needleTip = polarToCartesian(cx, cy, radius - 6, valueAngle);
    const needleBaseLeft = polarToCartesian(cx, cy, 10, valueAngle - 90);
    const needleBaseRight = polarToCartesian(cx, cy, 10, valueAngle + 90);

    const needlePath = [
      'M', needleBaseLeft.x, needleBaseLeft.y,
      'L', needleTip.x, needleTip.y,
      'L', needleBaseRight.x, needleBaseRight.y,
      'Z'
    ].join(' ');

    const strokeColor = options.color || (theme.isLight ? '#0284c7' : '#38bdf8');
    const trackColor = theme.trackColor;

    svg.innerHTML = `
      <!-- Background Track -->
      <path d="${bgArcPath}" fill="none" stroke="${trackColor}" stroke-width="12" stroke-linecap="round"/>
      <!-- Value Arc -->
      <path d="${valArcPath}" fill="none" stroke="${strokeColor}" stroke-width="12" stroke-linecap="round"/>
      <!-- Min/Max labels -->
      <text x="25" y="112" font-size="10" fill="${theme.labelColor}" text-anchor="middle">${minVal}</text>
      <text x="175" y="112" font-size="10" fill="${theme.labelColor}" text-anchor="middle">${maxVal}</text>
      <!-- Needle -->
      <path d="${needlePath}" fill="${strokeColor}" opacity="0.9"/>
      <circle cx="${cx}" cy="${cy}" r="6" fill="${theme.centerFill}" stroke="${strokeColor}" stroke-width="3"/>
    `;
  }

  /* =========================================================================
     3. Live Data Polling
     ========================================================================= */
  async function fetchCurrentData() {
    try {
      const res = await fetch('/api/current?t=' + Date.now());
      if (!res.ok) throw new Error('API returned ' + res.status);
      const data = await res.json();

      // Update badge
      if (elSensorBadge && data.sensor_model) {
        elSensorBadge.textContent = 'Sensor: ' + data.sensor_model;
      }
      if (elStatusBadge) {
        elStatusBadge.innerHTML = '<span class="dot"></span> Online';
      }

      // Update Text Values
      if (elValTemp) elValTemp.textContent = data.temperature.toFixed(1);
      if (elValDew) elValDew.textContent = data.dew_point.toFixed(1);

      if (elValHum) elValHum.textContent = data.humidity.toFixed(0);
      if (elHumComfort) {
        if (data.humidity < 35) elHumComfort.textContent = 'Zustand: Eher trocken';
        else if (data.humidity <= 65) elHumComfort.textContent = 'Zustand: Behaglich / Optimal';
        else elHumComfort.textContent = 'Zustand: Eher feucht';
      }

      if (elValPressQnh) elValPressQnh.textContent = data.pressure_qnh.toFixed(1);
      if (elValPressQfe) elValPressQfe.textContent = data.pressure.toFixed(1);

      // Render Gauges
      renderGauge(svgTemp, -20, 50, data.temperature, { color: '#f97316' });
      renderGauge(svgHum, 0, 100, data.humidity, { color: '#06b6d4' });
      renderGauge(svgPress, 950, 1050, data.pressure_qnh, { color: '#10b981' });

      // Last updated note
      if (elLastUpdate && data.timestamp) {
        const d = new Date(data.timestamp * 1000);
        elLastUpdate.textContent = d.toLocaleTimeString('de-CH', { hour12: false });
      }
    } catch (err) {
      console.warn('Failed to fetch live readings:', err);
      if (elStatusBadge) {
        elStatusBadge.innerHTML = '<span class="dot" style="background:#ef4444;box-shadow:0 0 8px #ef4444;"></span> Verbindungsproblem';
      }
    }
  }

  /* =========================================================================
     4. Historical Data & Charts
     ========================================================================= */
  async function fetchHistory(period) {
    try {
      const res = await fetch(`/api/history?period=${period}&t=${Date.now()}`);
      if (!res.ok) throw new Error('API returned ' + res.status);
      const data = await res.json();
      historyCache[period] = data;

      updateStatsSummary(data.stats);
      renderChart(data);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  }

  function updateStatsSummary(stats) {
    if (!stats) return;

    function setStat(minEl, avgEl, maxEl, stat) {
      if (!stat) return;
      if (minEl) minEl.textContent = stat.min !== null ? stat.min.toFixed(1) : '--';
      if (avgEl) avgEl.textContent = stat.avg !== null ? stat.avg.toFixed(1) : '--';
      if (maxEl) maxEl.textContent = stat.max !== null ? stat.max.toFixed(1) : '--';
    }

    setStat(elStatTempMin, elStatTempAvg, elStatTempMax, stats.temp);
    setStat(elStatHumMin, elStatHumAvg, elStatHumMax, stats.hum);
    setStat(elStatQnhMin, elStatQnhAvg, elStatQnhMax, stats.qnh);
    setStat(elStatDewMin, elStatDewAvg, elStatDewMax, stats.dew);
  }

  function formatTimestamp(ts, period) {
    const d = new Date(ts * 1000);
    if (period === '24h') {
      return d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit', hour12: false });
    } else if (period === '7d') {
      return d.toLocaleDateString('de-CH', { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' ' +
             d.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit', hour12: false });
    } else {
      return d.toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit' });
    }
  }

  function renderChart(data) {
    const ctx = document.getElementById('historyChart');
    if (!ctx || !window.Chart) return;

    const timestamps = data.timestamps || [];
    const labels = timestamps.map(t => formatTimestamp(t, currentPeriod));

    let datasets = [];

    if (currentChartType === 'temp') {
      datasets = [
        {
          label: 'Temperatur (°C)',
          data: data.series.temp,
          borderColor: '#f97316',
          backgroundColor: 'rgba(249, 115, 22, 0.1)',
          fill: true,
          tension: 0.25,
          pointRadius: timestamps.length > 100 ? 0 : 2,
        },
        {
          label: 'Taupunkt (°C)',
          data: data.series.dew,
          borderColor: '#a855f7',
          borderDash: [4, 4],
          backgroundColor: 'transparent',
          tension: 0.25,
          pointRadius: 0,
        }
      ];
    } else if (currentChartType === 'hum') {
      datasets = [
        {
          label: 'Luftfeuchtigkeit (%)',
          data: data.series.hum,
          borderColor: '#06b6d4',
          backgroundColor: 'rgba(6, 182, 212, 0.15)',
          fill: true,
          tension: 0.25,
          pointRadius: timestamps.length > 100 ? 0 : 2,
        }
      ];
    } else if (currentChartType === 'press') {
      datasets = [
        {
          label: 'Luftdruck QNH (hPa)',
          data: data.series.qnh,
          borderColor: '#10b981',
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          fill: true,
          tension: 0.25,
          pointRadius: timestamps.length > 100 ? 0 : 2,
        },
        {
          label: 'Station QFE (hPa)',
          data: data.series.press,
          borderColor: '#64748b',
          borderDash: [3, 3],
          backgroundColor: 'transparent',
          tension: 0.25,
          pointRadius: 0,
        }
      ];
    }

    if (chartInstance) {
      chartInstance.destroy();
    }

    const theme = getThemeColors();

    chartInstance = new window.Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            labels: {
              color: theme.chartText,
              font: { family: 'inherit' }
            }
          },
          tooltip: {
            backgroundColor: theme.tooltipBg,
            titleColor: theme.tooltipTitle,
            bodyColor: theme.chartText,
            borderColor: theme.tooltipBorder,
            borderWidth: 1,
            padding: 10
          }
        },
        scales: {
          x: {
            grid: { color: theme.chartGrid },
            ticks: {
              color: theme.labelColor,
              maxTicksLimit: 12
            }
          },
          y: {
            grid: { color: theme.chartGrid },
            ticks: { color: theme.labelColor }
          }
        }
      }
    });
  }

  /* =========================================================================
     5. Event Listeners & Initialization
     ========================================================================= */
  // Manual refresh button
  const btnRefresh = document.getElementById('btn-refresh-live');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', () => {
      fetchCurrentData();
      fetchHistory(currentPeriod);
    });
  }

  // Period buttons (24h, 7d, 30d)
  document.querySelectorAll('.btn-period').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.btn-period').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentPeriod = btn.getAttribute('data-period');
      fetchHistory(currentPeriod);
    });
  });

  // Chart type tabs
  document.querySelectorAll('.chart-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentChartType = tab.getAttribute('data-chart');
      if (historyCache[currentPeriod]) {
        renderChart(historyCache[currentPeriod]);
      } else {
        fetchHistory(currentPeriod);
      }
    });
  });

  // Initial runs
  fetchCurrentData();
  fetchHistory(currentPeriod);

  // Periodic poll for live data (15 seconds)
  setInterval(fetchCurrentData, 15000);
})();
