# iphone/web_server.py
# Pythonista 3 - Flask Companion App Server + Mobile Web UI
# Mở trên iPhone: Safari → http://localhost:8080
import json
import time

try:
    import http.server
    import socketserver
    import threading
    import urllib.parse
    import requests
    HAS_SERVER = True
except ImportError:
    HAS_SERVER = False

try:
    import speech  # Native iOS Text-to-Speech
    HAS_SPEECH = True
except ImportError:
    HAS_SPEECH = False
    speech = None

# HTML cho companion web app - Mobile-first design
HTML_PAGE = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>🏍️ Tequila Navigator Premium</title>
<style>
  :root {
    --bg: #06060c;
    --panel: rgba(18, 18, 32, 0.75);
    --panel-border: rgba(0, 191, 255, 0.2);
    --blue: #00bfff;
    --green: #00ff87;
    --red: #ff3366;
    --orange: #ff9900;
    --text: #f0f3f8;
    --sub: #90a0b7;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  }
  
  * { box-sizing: border-box; margin: 0; padding: 0; }
  
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    min-height: 100vh;
    padding: 16px;
    background-image: radial-gradient(circle at 50% 5%, #181b36 0%, #06060c 80%);
    overflow-x: hidden;
  }
  
  header {
    margin-bottom: 16px;
    text-align: center;
  }
  
  h1 {
    color: var(--blue);
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 3px;
    text-shadow: 0 0 15px rgba(0, 191, 255, 0.5);
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .subtitle {
    font-size: 11px;
    color: var(--sub);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-top: 4px;
    font-weight: 600;
  }
  
  .card {
    background: var(--panel);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-radius: 24px;
    padding: 20px;
    margin-bottom: 16px;
    border: 1px solid var(--panel-border);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .card-title {
    color: var(--blue);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  /* Map Container */
  .map-wrapper {
    position: relative;
    border-radius: 24px;
    overflow: hidden;
    border: 1px solid rgba(0, 191, 255, 0.25);
    box-shadow: 0 10px 30px rgba(0,0,0,0.6);
    margin-bottom: 16px;
  }

  #map {
    height: 320px;
    width: 100%;
    z-index: 1;
  }

  /* Dark mode Leaflet overlay */
  .leaflet-container {
    background: #06060c !important;
  }
  .leaflet-tile {
    filter: brightness(0.55) invert(1) contrast(2.8) hue-rotate(200deg) saturate(0.25) !important;
  }
  
  input[type=text] {
    width: 100%;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(0, 191, 255, 0.2);
    border-radius: 14px;
    color: var(--text);
    padding: 14px 16px;
    font-size: 15px;
    outline: none;
    margin-bottom: 12px;
    transition: all 0.3s;
  }
  
  input[type=text]:focus {
    border-color: var(--blue);
    box-shadow: 0 0 12px rgba(0, 191, 255, 0.25);
    background: rgba(255, 255, 255, 0.07);
  }
  
  .btn {
    width: 100%;
    padding: 15px;
    border: none;
    border-radius: 16px;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
    margin-bottom: 8px;
    transition: all 0.2s ease;
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
  }
  
  .btn:active { transform: scale(0.97); opacity: 0.9; }
  .btn-primary { background: linear-gradient(135deg, #0088ff, #00bfff); color: #fff; box-shadow: 0 4px 15px rgba(0, 191, 255, 0.3); }
  .btn-success { background: linear-gradient(135deg, #00cd77, #00ff87); color: #06060c; font-weight: 800; box-shadow: 0 4px 15px rgba(0, 255, 135, 0.3); }
  .btn-danger  { background: linear-gradient(135deg, #e6005c, #ff3366); color: #fff; box-shadow: 0 4px 15px rgba(255, 51, 102, 0.35); }
  .btn-add     { background: rgba(0, 191, 255, 0.08); color: var(--blue); border: 1px dashed rgba(0, 191, 255, 0.3); }
  
  .status-bar  { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 12px; margin-bottom: 16px; }
  .status-item { background: var(--panel); backdrop-filter: blur(10px); border-radius: 14px; padding: 10px 12px; border: 1px solid rgba(255,255,255,0.03); display: flex; align-items: center; gap: 8px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .dot-green { background: var(--green); box-shadow: 0 0 10px var(--green); }
  .dot-red   { background: var(--red);   box-shadow: 0 0 10px var(--red); }
  
  .waypoint-item { display: flex; align-items: center; margin-bottom: 10px; gap: 10px; }
  .wp-num { background: rgba(0, 191, 255, 0.15); color: var(--blue); border: 1px solid var(--blue); border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
  .wp-del { color: var(--red); font-size: 18px; cursor: pointer; padding: 0 8px; }

  /* Speed, turns panel */
  .nav-instruction { font-size: 20px; font-weight: 800; color: #fff; margin-bottom: 6px; text-align: center; }
  .nav-dist { color: var(--blue); font-size: 14px; font-weight: 700; text-align: center; margin-bottom: 10px; }
  .speed-display { font-size: 64px; font-weight: 900; color: var(--green); text-align: center; text-shadow: 0 0 20px rgba(0, 255, 135, 0.4); font-family: monospace; line-height: 1; }
  .speed-unit { font-size: 12px; color: var(--sub); text-align: center; text-transform: uppercase; letter-spacing: 1.5px; margin-top: 4px; margin-bottom: 16px; }
  .eta-row { display: flex; justify-content: space-between; font-size: 13px; color: var(--sub); font-weight: 600; background: rgba(255,255,255,0.03); padding: 10px 14px; border-radius: 12px; }

  /* 3 Routes Selection CSS */
  .route-option {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 12px;
    cursor: pointer;
    transition: all 0.25s ease;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .route-option:hover {
    background: rgba(0, 191, 255, 0.06);
    border-color: rgba(0, 191, 255, 0.4);
    transform: translateY(-2px);
  }
  .route-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .route-label {
    font-size: 14px;
    font-weight: 800;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .route-meta {
    font-size: 12px;
    color: var(--sub);
    font-weight: 500;
  }
  .route-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    margin-top: 4px;
  }
  .route-stat {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .cam-alert {
    background: rgba(255, 51, 102, 0.12);
    border: 1px solid var(--red);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--red);
    display: none;
    font-weight: 700;
    text-align: center;
    box-shadow: 0 0 15px rgba(255, 51, 102, 0.2);
  }
  .cam-alert.show { display: block; animation: pulse 1.2s infinite; }
  
  @keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.01); }
    100% { transform: scale(1); }
  }

  .voice-bubble {
    background: rgba(0, 191, 255, 0.08);
    border-left: 4px solid var(--blue);
    border-radius: 0 16px 16px 0;
    padding: 12px 16px;
    font-size: 13.5px;
    color: var(--text);
    margin-bottom: 14px;
    font-style: italic;
    display: none;
  }
  
  #route-select-panel { display: none; }
  #journey-panel { display: none; }
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>

<header>
  <h1>🏍️ TEQUILA NAVIGATOR</h1>
  <div class="subtitle">Premium Realtime motorcycle companion</div>
</header>

<!-- Status Bar -->
<div class="status-bar">
  <div class="status-item">
    <span class="dot dot-green" id="wifi-dot"></span>
    <span id="wifi-status">Đang quét...</span>
  </div>
  <div class="status-item">
    <span class="dot" id="gps-dot" style="background:#888;"></span>
    <span id="gps-status">📍 GPS: Đang định vị...</span>
  </div>
  <div class="status-item">
    <span id="findmy-dot" style="width:8px;height:8px;border-radius:50%;display:inline-block;background:#555;margin-right:4px;"></span>
    <span id="findmy-status" style="font-size:11px;color:#aaa;">🍎 Find My</span>
  </div>
</div>



<!-- Map: Always Visible -->
<div class="map-wrapper">
  <div id="map"></div>
</div>

<!-- Voice Reply Bubble -->
<div class="voice-bubble" id="voice-bubble"></div>

<!-- Settings & Config Panel -->
<div class="card">
  <div class="card-title">⚙️ Cấu hình thiết bị & Trợ lý</div>
  <input type="text" id="esp32-ip" placeholder="Địa chỉ IP của ESP32 (VD: 172.20.10.2)" value="172.20.10.2">
  <input type="text" id="gemini-key" placeholder="Google Gemini AI API Key" value="AIzaSyDtJSYHSN_cviBBHfgpKItuDaOsg-i7fq0">
</div>

<!-- Setup Panel -->
<div class="card" id="setup-panel">
  <div class="card-title">🎯 Tìm kiếm lộ trình</div>
  <input type="text" id="destination" placeholder="Ngài muốn đi đâu hôm nay?">
  
  <div class="card-title" style="margin-top:14px; font-size:12px;">📍 Điểm dừng dọc đường</div>
  <div id="waypoint-list"></div>
  <button class="btn btn-add" onclick="addWaypoint()">+ Thêm điểm dừng</button>
  
  <div style="margin-top:18px;">
    <button class="btn btn-success" onclick="getAlternativeRoutes()">🚀 TÌM ĐƯỜNG & SO SÁNH</button>
    <button class="btn btn-primary" onclick="optimizeRoute()">✨ AI TỐI ƯU CÁC ĐIỂM DỪNG</button>
  </div>
</div>

<!-- Apple Find My Setup Panel - dung <details> thuan HTML, khong can JS toggle -->
<div class="card" style="border:2px solid #4a90d9; padding:14px;">
  <div style="font-size:14px;font-weight:700;color:#4a90d9;margin-bottom:8px;">
    &#127822; Ket Noi Apple Find My
  </div>
  <p style="color:#aaa;font-size:12px;margin-bottom:12px;">
    Dang nhap Apple ID 1 lan de server tu doc GPS tu app Tim.
    Khong can mo Safari hay app nao nua.
  </p>
  <a href="/setup-findmy"
     style="display:block;width:100%;padding:12px;background:#4a90d9;color:#fff;
            text-align:center;border-radius:10px;font-size:15px;font-weight:700;
            text-decoration:none;">
    &#127822; Mo trang Setup Apple Find My
  </a>
  <div id="findmy-status-msg" style="display:none;"></div>
</div>

<!-- 3 Alternatives Route Selection Panel -->
<div class="card" id="route-select-panel">
  <div class="card-title" style="color: var(--orange)">🗺️ Lựa chọn tuyến đường tối ưu</div>
  <div id="routes-container">
    <!-- Tuyến 1, 2, 3 load động -->
  </div>
  <button class="btn btn-danger" onclick="cancelRouteSelection()" style="margin-top: 10px;">✕ HUỶ BỎ</button>
</div>

<!-- Active Journey Panel -->
<div class="card" id="journey-panel">
  <div class="cam-alert" id="cam-alert">⚠️ <span id="cam-alert-text"></span></div>
  
  <div class="nav-instruction" id="nav-instruction">Đang điều hướng...</div>
  <div class="nav-dist" id="nav-dist"></div>
  
  <div class="speed-display" id="speed-display">0</div>
  <div class="speed-unit">km/h</div>
  
  <div class="eta-row">
    <span id="eta-text">ETA: -- phút</span>
    <span id="dist-remain">-- km còn lại</span>
  </div>
  
  <button class="btn btn-danger" onclick="stopNavigation()" style="margin-top: 20px;">⏹ DỪNG HÀNH TRÌNH</button>
</div>

<script>
let waypoints = [];
let map = null;
let carMarker = null;
let activePolyline = null;
let previewPolylines = [];
let cameraMarkers = [];
let lastVoiceReply = '';

// ─── Apple Find My Setup Functions ───
function toggleFindMyPanel() {
  const p = document.getElementById('findmy-panel');
  p.style.display = (p.style.display === 'none' || p.style.display === '') ? 'block' : 'none';
}

async function setupFindMy() {
  const appleId  = document.getElementById('apple-id-input').value.trim();
  const password = document.getElementById('apple-pw-input').value;
  if (!appleId || !password) { alert('Nhập Apple ID và mật khẩu!'); return; }
  const msg = document.getElementById('findmy-status-msg');
  msg.style.display = 'block'; msg.style.color = '#f0a500';
  msg.textContent = '⏳ Đang kết nối Apple ID... (chờ 20-40 giây)';
  try {
    const r = await fetch('/api/setup-findmy', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ apple_id: appleId, password: password })
    });
    const d = await r.json();
    if (d.status === '2fa_required') {
      msg.style.color = '#f0a500';
      msg.textContent = '📱 Apple gửi mã 2FA về iPhone của bạn. Nhập vào ô bên dưới.';
      document.getElementById('findmy-form-area').style.display = 'none';
      document.getElementById('findmy-2fa-area').style.display = 'block';
      document.getElementById('findmy-2fa-input').focus();
    } else if (d.status === 'ok') {
      msg.style.color = '#00ff87';
      msg.textContent = '✅ Đăng nhập thành công! GPS tự động từ Find My.';
      document.getElementById('findmy-dot').style.background = '#00ff87';
      document.getElementById('findmy-status').textContent = '🍎 Find My ✅';
      const mainBtn = document.getElementById('findmy-main-btn');
      if (mainBtn) {
        mainBtn.textContent = '🍎 Find My ✅ Đang hoạt động';
        mainBtn.style.borderColor = '#00ff87';
        mainBtn.style.color = '#00ff87';
        mainBtn.style.background = 'linear-gradient(135deg,#0a2a1a,#0a3a2a)';
      }
    } else {
      msg.style.color = '#ff4444';
      msg.textContent = '❌ ' + (d.message || d.error || JSON.stringify(d));
    }
  } catch(e) {
    msg.style.color='#ff4444'; msg.textContent='❌ Lỗi: '+e.message;
  }
}

async function submit2FA() {
  const code = document.getElementById('findmy-2fa-input').value.trim();
  if (code.length < 6) { alert('Mã 2FA phải đủ 6 chữ số!'); return; }
  const msg = document.getElementById('findmy-status-msg');
  msg.style.color = '#f0a500'; msg.textContent = '⏳ Đang xác nhận mã 2FA...';
  try {
    const r = await fetch('/api/findmy-2fa', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ code: code })
    });
    const d = await r.json();
    if (d.status === 'ok') {
      msg.style.color = '#00ff87';
      msg.textContent = '✅ 2FA thành công! Find My đang chạy.';
      document.getElementById('findmy-dot').style.background = '#00ff87';
      document.getElementById('findmy-status').textContent = '🍎 Find My ✅';
      const mainBtn2 = document.getElementById('findmy-main-btn');
      if (mainBtn2) {
        mainBtn2.textContent = '🍎 Find My ✅ Đang hoạt động';
        mainBtn2.style.borderColor = '#00ff87';
        mainBtn2.style.color = '#00ff87';
        mainBtn2.style.background = 'linear-gradient(135deg,#0a2a1a,#0a3a2a)';
      }
      document.getElementById('findmy-2fa-area').style.display = 'none';
      setTimeout(()=>{ document.getElementById('findmy-panel').style.display='none'; }, 3000);
    } else {
      msg.style.color='#ff4444';
      msg.textContent='❌ Mã sai hoặc hết hạn: '+(d.error||'Thử lại');
    }
  } catch(e) {
    msg.style.color='#ff4444'; msg.textContent='❌ Lỗi: '+e.message;
  }
}

// Khởi tạo bản đồ ngay từ đầu
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  
  // Khôi phục cài đặt lưu trữ
  const savedIP = localStorage.getItem('esp32_ip');
  if (savedIP) {
    document.getElementById('esp32-ip').value = savedIP;
  }
  const savedKey = localStorage.getItem('gemini_key');
  if (savedKey) {
    document.getElementById('gemini-key').value = savedKey;
    saveGeminiKey(savedKey);
  }
  
  // Polling trạng thái liên tục mỗi 1.5 giây
  setInterval(fetchStatus, 1500);
});

// Gán sự kiện lưu config
document.getElementById('esp32-ip').addEventListener('change', (e) => {
  localStorage.setItem('esp32_ip', e.target.value.trim());
});
document.getElementById('gemini-key').addEventListener('change', (e) => {
  const key = e.target.value.trim();
  localStorage.setItem('gemini_key', key);
  saveGeminiKey(key);
});

async function saveGeminiKey(key) {
  try {
    await fetch('/api/set-gemini-key', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ gemini_api_key: key })
    });
  } catch(e){}
}

function initMap() {
  if (map) return;
  // Mặc định trung tâm Sài Gòn
  map = L.map('map', { zoomControl: false }).setView([10.7769, 106.7009], 14);
  
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
  }).addTo(map);

  const motoIcon = L.divIcon({
    html: '<div style="font-size: 26px; filter: drop-shadow(0 0 8px #00ff87);">🏍️</div>',
    iconSize: [26, 26],
    iconAnchor: [13, 13]
  });

  carMarker = L.marker([10.7769, 106.7009], { icon: motoIcon }).addTo(map);
}


async function fetchStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    updateUI(d);
  } catch(e){}
}

// ── GPS Safari iPhone → Cloud server (fix: auto-zoom, instant fix, dot indicator) ──
let _gpsFirstFix = false;
let _lastGpsSend = 0;

function _sendGpsToServer(lat, lon, speed, heading, accuracy) {
  const now = Date.now();
  if (now - _lastGpsSend < 1800) return;
  _lastGpsSend = now;
  fetch('/api/update-gps', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ lat, lon, speed, heading, accuracy })
  }).then(r => {
    if (r.ok) {
      const dot = document.getElementById('gps-dot');
      if (dot) dot.style.background = '#00ff87';
      document.getElementById('gps-status').textContent =
        `📍 GPS: ${lat.toFixed(5)}, ${lon.toFixed(5)} (±${Math.round(accuracy||0)}m)`;
    }
  }).catch(() => {
    const dot = document.getElementById('gps-dot');
    if (dot) dot.style.background = '#ff4444';
  });
  if (map && carMarker) {
    carMarker.setLatLng([lat, lon]);
    if (!_gpsFirstFix) {
      map.setView([lat, lon], 16);
      _gpsFirstFix = true;
    }
  }
}

if (navigator.geolocation) {
  const gpsOpts = { enableHighAccuracy: true, maximumAge: 0, timeout: 10000 };
  navigator.geolocation.watchPosition(pos => {
    const { latitude: lat, longitude: lon, speed, heading, accuracy } = pos.coords;
    _sendGpsToServer(lat, lon, speed ? speed * 3.6 : 0, heading || 0, accuracy || 0);
  }, err => {
    let msg = '❌ GPS: ';
    if (err.code === 1) msg += 'Bị từ chối quyền vị trí — vào Settings > Safari > Vị trí > Cho phép';
    else if (err.code === 2) msg += 'Không lấy được tín hiệu GPS';
    else msg += 'Hết thời gian chờ GPS';
    document.getElementById('gps-status').textContent = msg;
  }, gpsOpts);
  // Lấy vị trí ngay lập tức không chờ watchPosition
  navigator.geolocation.getCurrentPosition(pos => {
    const { latitude: lat, longitude: lon, speed, heading, accuracy } = pos.coords;
    _sendGpsToServer(lat, lon, speed ? speed * 3.6 : 0, heading || 0, accuracy || 0);
  }, () => {}, gpsOpts);
} else {
  document.getElementById('gps-status').textContent = '❌ Trình duyệt không hỗ trợ GPS';
}

function clearPreviewPolylines() {
  previewPolylines.forEach(pl => map.removeLayer(pl));
  previewPolylines = [];
}

function clearCameraMarkers() {
  cameraMarkers.forEach(m => map.removeLayer(m));
  cameraMarkers = [];
}

function updateUI(d) {
  // 1. Đồng bộ kết nối wifi & định vị
  if (d.wifi_connected) {
    document.getElementById('wifi-dot').className = 'dot dot-green';
    document.getElementById('wifi-status').textContent = `ESP32 connected`;
  } else {
    document.getElementById('wifi-dot').className = 'dot dot-red';
    document.getElementById('wifi-status').textContent = `ESP32 offline`;
  }
  
  if (d.gps_lat) {
    document.getElementById('gps-status').textContent = `📍 GPS: ${d.gps_lat.toFixed(5)}, ${d.gps_lon.toFixed(5)}`;
    if (map && carMarker) {
      const pos = [d.gps_lat, d.gps_lon];
      carMarker.setLatLng(pos);
      // Chỉ zoom pan khi đang dẫn đường active
      if (d.is_navigating) {
        map.panTo(pos);
      }
    }
  }
  
  // 2. Đồng bộ hộp thoại giọng nói
  const bubble = document.getElementById('voice-bubble');
  if (d.voice_reply) {
    bubble.style.display = 'block';
    bubble.textContent = `Tequila: "${d.voice_reply}"`;
    
    if (d.voice_reply !== lastVoiceReply) {
      lastVoiceReply = d.voice_reply;
      let utterance = new SpeechSynthesisUtterance(d.voice_reply);
      utterance.lang = 'vi-VN';
      window.speechSynthesis.speak(utterance);
    }
  } else {
    bubble.style.display = 'none';
  }

  // 3. Trạng thái 1: Đang hiển thị so sánh 3 tuyến đường
  if (d.selecting_route && d.pending_routes && d.pending_routes.length > 0) {
    document.getElementById('setup-panel').style.display = 'none';
    document.getElementById('route-select-panel').style.display = 'block';
    document.getElementById('journey-panel').style.display = 'none';
    
    // Vẽ 3 tuyến đường lên bản đồ với 3 màu khác biệt
    clearPreviewPolylines();
    const container = document.getElementById('routes-container');
    container.innerHTML = '';
    
    const colors = ["#00bfff", "#00ff87", "#ff9900"]; // Cyan, Green, Orange
    const bounds = L.latLngBounds();
    
    d.pending_routes.forEach((rt, i) => {
      const polyCoords = rt.polyline.map(p => [p[0], p[1]]);
      const color = colors[i] || '#ffffff';
      
      const pl = L.polyline(polyCoords, {
        color: color,
        weight: i === 0 ? 7 : 5,
        opacity: 0.8,
        lineJoin: 'round'
      }).addTo(map);
      
      previewPolylines.push(pl);
      polyCoords.forEach(c => bounds.extend(c));
      
      // Tạo HTML Card cho tuyến đường này
      container.innerHTML += `
        <div class="route-option" onclick="selectRoute(${rt.index})">
          <div class="route-header">
            <span class="route-label" style="color: ${color}">
              <span style="font-size: 16px">${i === 0 ? '🏆' : '📍'}</span>
              ${rt.label}
            </span>
            <span class="route-meta">${rt.summary}</span>
          </div>
          <div class="route-stats">
            <div class="route-stat">📏 ${rt.total_distance_km} km</div>
            <div class="route-stat">⏱️ ${rt.total_duration_min} phút</div>
          </div>
          <div class="route-stats" style="font-size: 11px; color: var(--sub); margin-top: 4px;">
            <div class="route-stat">⚡ Tốc độ tối đa: ${rt.max_speed} km/h</div>
            <div class="route-stat">📷 Camera phạt nguội: ${rt.camera_count}</div>
          </div>
        </div>
      `;
    });
    
    if (previewPolylines.length > 0) {
      map.fitBounds(bounds, { padding: [40, 40] });
    }
    
    return;
  }

  // 4. Trạng thái 2: Đang điều hướng chủ động
  if (d.is_navigating) {
    document.getElementById('setup-panel').style.display = 'none';
    document.getElementById('route-select-panel').style.display = 'none';
    document.getElementById('journey-panel').style.display = 'block';
    
    clearPreviewPolylines();
    
    // Vẽ đường đi đậm màu xanh dương
    if (map && d.route_polyline && d.route_polyline.length > 0) {
      const coords = d.route_polyline.map(p => [p[0], p[1]]);
      if (activePolyline) {
        activePolyline.setLatLngs(coords);
      } else {
        activePolyline = L.polyline(coords, {
          color: '#00bfff',
          weight: 7,
          opacity: 0.9,
          lineJoin: 'round'
        }).addTo(map);
      }
    }
    
    // Cập nhật text & camera phạt nguội
    document.getElementById('nav-instruction').textContent = d.current_instruction || 'Đi thẳng';
    if (d.dist_to_turn) {
      document.getElementById('nav-dist').textContent = `Cách ${d.dist_to_turn} mét`;
    } else {
      document.getElementById('nav-dist').textContent = '';
    }
    
    document.getElementById('speed-display').textContent = Math.round(d.speed_kmh || 0);
    document.getElementById('eta-text').textContent = `ETA: ${d.eta_min || '--'} phút`;
    document.getElementById('dist-remain').textContent = `${d.dist_remain_km || '--'} km còn lại`;
    
    if (d.camera_warning) {
      document.getElementById('cam-alert').className = 'cam-alert show';
      document.getElementById('cam-alert-text').textContent = d.camera_warning;
    } else {
      document.getElementById('cam-alert').className = 'cam-alert';
    }
    
    // Vẽ các marker camera phạt nguội gần đó lên bản đồ
    clearCameraMarkers();
    if (d.cameras_nearby) {
      d.cameras_nearby.forEach(cam => {
        const camIcon = L.divIcon({
          html: '<div style="font-size: 16px; background: rgba(255, 51, 102, 0.2); border: 1px solid #ff3366; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center;">📷</div>',
          iconSize: [24, 24],
          iconAnchor: [12, 12]
        });
        const m = L.marker([cam.lat, cam.lon], {icon: camIcon}).addTo(map)
                   .bindPopup(`<b>Camera phạt nguội</b><br>Giới hạn: ${cam.speed_limit} km/h`);
        cameraMarkers.push(m);
      });
    }
  } else {
    // Trạng thái 3: Sẵn sàng tìm kiếm
    document.getElementById('setup-panel').style.display = 'block';
    document.getElementById('route-select-panel').style.display = 'none';
    document.getElementById('journey-panel').style.display = 'none';
    
    if (activePolyline) {
      map.removeLayer(activePolyline);
      activePolyline = null;
    }
    clearPreviewPolylines();
    clearCameraMarkers();
  }
}

// Thêm điểm dừng
function addWaypoint() {
  waypoints.push('');
  renderWaypoints();
}

function renderWaypoints() {
  const list = document.getElementById('waypoint-list');
  list.innerHTML = '';
  waypoints.forEach((wp, i) => {
    list.innerHTML += `
      <div class="waypoint-item">
        <div class="wp-num">${i + 1}</div>
        <input type="text" id="wp-${i}" value="${wp}" placeholder="Nhập điểm trung gian ${i+1}..." style="margin:0; flex:1;">
        <span class="wp-del" onclick="removeWaypoint(${i})">✕</span>
      </div>`;
  });
}

function removeWaypoint(i) {
  waypoints.splice(i, 1);
  renderWaypoints();
}

// Bấm "Tìm đường & So sánh"
async function getAlternativeRoutes() {
  const dest = document.getElementById('destination').value.trim();
  const espIP = document.getElementById('esp32-ip').value.trim();
  
  if (!dest) { alert('Vui lòng nhập điểm đến!'); return; }
  if (!espIP) { alert('Vui lòng cấu hình IP ESP32!'); return; }
  
  const wps = [];
  waypoints.forEach((_, i) => {
    const val = document.getElementById(`wp-${i}`)?.value.trim();
    if (val) wps.push(val);
  });
  
  // Gửi yêu cầu tính 3 tuyến đường
  await fetch('/api/get-routes', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ destination: dest, waypoints: wps, esp32_ip: espIP })
  });
  fetchStatus();
}

// Bấm Chọn 1 trong 3 tuyến đường
async function selectRoute(idx) {
  await fetch('/api/select-route', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ route_index: idx })
  });
  fetchStatus();
}

// Huỷ bỏ lựa chọn
async function cancelRouteSelection() {
  await fetch('/api/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})
  });
  fetchStatus();
}

// AI tối ưu hoá đường đi các điểm dừng
async function optimizeRoute() {
  const dest = document.getElementById('destination').value.trim();
  const wps = [];
  waypoints.forEach((_, i) => {
    const val = document.getElementById(`wp-${i}`)?.value.trim();
    if (val) wps.push(val);
  });
  
  if (!dest && !wps.length) { alert('Nhập ít nhất 1 điểm!'); return; }
  
  const r = await fetch('/api/optimize', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ destination: dest, waypoints: wps })
  });
  const d = await r.json();
  if (d.optimized_order) {
    alert('Thứ tự tối ưu AI:\n' + d.optimized_order.join(' → '));
  }
}

// Dừng hành trình
async function stopNavigation() {
  if (!confirm('Dừng dẫn đường hành trình hiện tại?')) return;
  await fetch('/api/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({})
  });
  fetchStatus();
}
</script>
</body>
</html>"""



FINDMY_SETUP_PAGE = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tequila Map - Setup GPS iPhone</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d1a;color:#eee;font-family:-apple-system,BlinkMacSystemFont,sans-serif;
     padding:24px 18px;min-height:100vh}
.card{background:#12122a;border-radius:16px;padding:20px;margin-bottom:14px}
.card-blue{border:1.5px solid #4a90d9}
.card-green{border:1.5px solid #00cc66}
.card-orange{border:1.5px solid #f0a500}
h1{color:#4a90d9;font-size:18px;margin-bottom:8px}
h2{font-size:15px;margin-bottom:10px}
p,li{color:#aaa;font-size:13px;line-height:1.7}
ol{padding-left:18px;margin-bottom:12px}
li{margin-bottom:6px}
.highlight{color:#00ff87;font-weight:700}
.url{background:#0a0a20;color:#4a90d9;padding:8px 12px;border-radius:8px;
     font-size:13px;word-break:break-all;margin:8px 0;display:block}
.step{background:#1a1a3e;border-radius:10px;padding:12px;margin-bottom:8px}
.step-num{color:#4a90d9;font-weight:700;font-size:16px}
.note{background:#1a1200;border:1px solid #f0a500;border-radius:8px;
      padding:10px;color:#f0a500;font-size:12px;margin-top:10px}
a.btn{display:block;padding:13px;background:#00cc66;color:#000;font-weight:700;
      border-radius:10px;text-align:center;text-decoration:none;font-size:15px;margin:10px 0}
a.back{color:#4a90d9;font-size:13px;display:block;text-align:center;margin-top:16px}
{MSG_STYLE}
</style>
</head>
<body>
{MSG}

<div class="card card-blue">
  <h1>&#128241; GPS tu Dong qua iPhone Shortcuts</h1>
  <p>Khong can dang nhap gi ca. Tao 1 Shortcut tren iPhone de tu dong gui GPS len server.</p>
</div>

<div class="card card-green">
  <h2>&#9989; Buoc 1 - Tao Shortcut GPS</h2>
  <ol>
    <li>Mo app <span class="highlight">Phim Tat (Shortcuts)</span> tren iPhone</li>
    <li>Bam dau <span class="highlight">+</span> goc tren phai</li>
    <li>Bam <span class="highlight">Them Hanh Dong</span></li>
    <li>Tim va chon: <span class="highlight">Lay Vi Tri Hien Tai</span></li>
    <li>Bam <span class="highlight">+</span> them hanh dong thu 2</li>
    <li>Tim va chon: <span class="highlight">Lay Noi Dung URL</span></li>
    <li>Dien URL nhu sau:</li>
  </ol>
  <code class="url">https://tequilamap.onrender.com/api/update-gps?lat=[Latitude]&lon=[Longitude]&source=shortcut</code>
  <p style="color:#aaa;font-size:12px;margin-top:6px;">
    [Latitude] va [Longitude]: bam vao o URL, bam bien so do, chon <b>Vi Tri > Vi Do / Kinh Do</b>
  </p>
  <li style="margin-top:8px;color:#aaa;font-size:13px;">8. Dat ten Shortcut la <span class="highlight">Tequila GPS</span> roi bam Xong</li>
</div>

<div class="card card-orange">
  <h2>&#9203; Buoc 2 - Cai Dat Tu Dong Chay</h2>
  <ol>
    <li>Trong app Phim Tat, chuyen sang tab <span class="highlight">Tu Dong Hoa</span></li>
    <li>Bam dau <span class="highlight">+</span></li>
    <li>Chon <span class="highlight">Thoi Gian</span></li>
    <li>Chon <span class="highlight">Lap Lai</span> → moi <span class="highlight">1 Phut</span></li>
    <li>Bam <span class="highlight">Tiep Theo</span> → chon <span class="highlight">Tequila GPS</span></li>
    <li>TAT "Hoi Truoc Khi Chay" → bam <span class="highlight">Xong</span></li>
  </ol>
  <div class="note">
    Shortcut tu dong chay ngam moi 1 phut, gui GPS len server.<br>
    Khong can mo app, khong can man hinh bat sang.
  </div>
</div>

<div class="card" style="border:1px solid #333;">
  <h2 style="color:#aaa;">&#128640; Ket Qua</h2>
  <p>Sau khi cai Shortcut:
    <br>&#10003; Server nhan GPS tu iPhone moi 1 phut
    <br>&#10003; Ban do ESP32 cap nhat tu dong
    <br>&#10003; Camera, toc do, canh bao hoat dong binh thuong
    <br>&#10003; Khong can mo Safari, khong can gi them
  </p>
</div>

<a href="/" class="back">&larr; Quay lai ban do</a>
</body>
</html>'''


FINDMY_2FA_PAGE = '''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tequila Map - Xac nhan 2FA</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d1a;color:#eee;font-family:-apple-system,BlinkMacSystemFont,sans-serif;
     display:flex;flex-direction:column;align-items:center;padding:30px 20px;min-height:100vh}
.card{background:#12122a;border:1.5px solid #f0a500;border-radius:16px;
      padding:24px;width:100%;max-width:420px}
h1{color:#f0a500;font-size:20px;margin-bottom:6px}
p{color:#aaa;font-size:13px;margin-bottom:16px;line-height:1.6}
input{width:100%;padding:14px;background:#1a1a3e;color:#eee;
      border:1px solid #f0a500;border-radius:10px;font-size:28px;
      text-align:center;letter-spacing:16px;font-weight:700;margin-bottom:12px}
button{width:100%;padding:14px;background:#f0a500;color:#000;
       border:none;border-radius:10px;font-size:16px;font-weight:700;cursor:pointer}
a{color:#4a90d9;font-size:14px}
.back{margin-top:20px;text-align:center}
</style>
</head>
<body>
<div class="card">
  <h1>&#128241; Nhap Ma 2FA</h1>
  <p>Apple da gui ma 6 chu so ve iPhone cua ban qua thong bao he thong.</p>
  <form method="POST" action="/api/setup-findmy-2fa">
    <input type="text" name="code" placeholder="000000" maxlength="6"
           inputmode="numeric" pattern="[0-9]{6}" required autofocus>
    <button type="submit">Xac nhan</button>
  </form>
</div>
<div class="back"><a href="/">&larr; Quay lai ban do</a></div>
</body>
</html>'''

class NavigatorWebServer:
    """Flask-style HTTP server chạy trên Pythonista iPhone qua mạng WiFi Hotspot."""
    
    def __init__(self, port=8080, nav_engine=None, esp32_ip="172.20.10.2",
                 camera_engine=None, gps_tracker=None):
        self.port = port
        self.nav_engine = nav_engine
        self.esp32_ip = esp32_ip
        self.cam_engine = camera_engine
        self.gps = gps_tracker
        self.status = {
            "wifi_connected": True,
            "gps_lat": None, "gps_lon": None,
            "is_navigating": False,
            "current_instruction": "Sẵn sàng",
            "dist_to_turn": None,
            "speed_kmh": 0,
            "eta_min": None,
            "dist_remain_km": None,
            "camera_warning": None,
            "battery_pct": 100,
            "gemini_api_key": "AIzaSyDtJSYHSN_cviBBHfgpKItuDaOsg-i7fq0",
            "voice_reply": None,
            "route_polyline": [],       # Polyline hiển thị trên Web UI
            "pending_routes": [],       # 3 tuyến đường đang chờ user chọn
            "selecting_route": False,   # True khi đang ở màn chọn tuyến
            "pending_resume": False,    # True khi chờ user xác nhận tiếp tục hành trình cũ
            # ── Dữ liệu cảnh báo realtime cho ESP32 Cloud Polling ──
            "speed_limit_now": 60,      # Giới hạn tốc độ đoạn đường hiện tại (km/h)
            "camera_dist_m": 9999,      # Khoảng cách camera gần nhất (mét)
            "camera_type": "speed",     # Loại camera: speed / redlight
            "cameras_nearby": [],       # Danh sách camera gần (50–300m)
            "arrived_text": "",         # Thông báo đã đến đích (xóa sau khi ESP32 đọc)
        }
        self.device_state = {
            "update": None,      # Gói tin update bản đồ cho ESP32
            "alert": None,       # Gói tin alert cho ESP32
            "voice": None,       # Phản hồi chữ đè màn hình cho ESP32
            "stop": False,       # Lệnh dừng dẫn đường cho ESP32
            "show_routes": None, # 3 tuyến đường gửi ESP32 hiển thị chọn
        }
        self.tts_audio_buffer = None
        self._server = None
        self._thread = None

        # FindMy Reader - doc GPS tu Apple Find My
        try:
            from findmy_reader import FindMyReader
            def _fm_cb(lat, lon, acc, ts):
                self.update_status(gps_lat=lat, gps_lon=lon, wifi_connected=True)
                print(f'[FindMy] GPS: {lat:.5f},{lon:.5f}')
            self.findmy_reader = FindMyReader(update_callback=_fm_cb)
            if self.findmy_reader.is_setup:
                self.findmy_reader.start_background_polling()
                print('[FindMy] Da kich hoat polling GPS tu Apple Find My.')
        except Exception as _fm_err:
            print('[FindMy] Khong tai duoc FindMyReader:', _fm_err)
            class _NoFindMy:
                is_setup = False
                last_location = None
                def generate_key_pair(self): return {"status":"error","message":"pip install findmy cryptography"}
                def setup_apple_auth(self, a, p): return {"status":"error","message":"pip install findmy"}
                def submit_2fa(self, c): return {"status":"error","message":"pip install findmy"}
                def fetch_location_once(self): return None
            self.findmy_reader = _NoFindMy()

    def _save_journey_state(self, destination, waypoints):
        try:
            with open("journey_state.json", "w", encoding="utf-8") as f:
                json.dump({
                    "destination": destination,
                    "waypoints": waypoints,
                    "completed": False
                }, f, ensure_ascii=False, indent=2)
            print("[WebServer] Đã lưu hành trình chưa hoàn thành.")
        except Exception as e:
            print("[WebServer] Lỗi lưu hành trình:", e)

    def _load_journey_state(self):
        try:
            import os
            import json
            if os.path.exists("journey_state.json"):
                with open("journey_state.json", "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print("[WebServer] Lỗi đọc hành trình:", e)
        return None

    def _clear_journey_state(self):
        try:
            import os
            if os.path.exists("journey_state.json"):
                os.remove("journey_state.json")
            print("[WebServer] Đã xóa hành trình lưu trữ.")
        except Exception as e:
            print("[WebServer] Lỗi xóa hành trình:", e)

    def _trigger_routes_search(self, destination, waypoints_text):
        """Tính toán 3 tuyến đường tối ưu nhất từ Gemini/Google Maps và thông báo ra loa."""
        server_self = self
        msg_init = "Đợi em chút, em sẽ tìm tuyến đường tối ưu nhất"
        server_self.update_status(voice_reply=msg_init)
        server_self.trigger_voice_alert(msg_init)
        server_self._send_text_to_esp32(msg_init)

        def calc_routes():
            try:
                import requests
                pos = server_self.gps.get_current() if server_self.gps else (10.7769, 106.7009)
                wp_coords = []
                for wp in waypoints_text:
                    c = server_self.nav_engine.geocode(wp)
                    if c: wp_coords.append(c)
                
                # Tìm 3 tuyến đường thay thế
                routes = server_self.nav_engine.get_route_alternatives(
                    pos[0], pos[1], destination, wp_coords or None
                )
                if routes:
                    # Phân tích camera phạt nguội và tốc độ tối đa cho mỗi tuyến
                    for rt in routes:
                        cameras_count = 0
                        max_speed = 60
                        # Count cameras along the route (within 100 meters)
                        all_cams = server_self.cam_engine._merged_cameras if hasattr(server_self.cam_engine, '_merged_cameras') else []
                        if all_cams and rt.get("full_polyline"):
                            counted_cams = set()
                            for pt in rt["full_polyline"]:
                                for cam in all_cams:
                                    cam_id = (cam["lat"], cam["lon"])
                                    if cam_id in counted_cams:
                                        continue
                                    if abs(cam["lat"] - pt[0]) < 0.001 and abs(cam["lon"] - pt[1]) < 0.001:
                                        dist = server_self.cam_engine._dist_m(cam["lat"], cam["lon"], pt[0], pt[1])
                                        if dist <= 100:
                                            counted_cams.add(cam_id)
                                            cameras_count += 1
                        
                        # Get speed limit for sample points
                        if rt.get("full_polyline") and hasattr(server_self.nav_engine, 'osm') and server_self.nav_engine.osm:
                            poly = rt["full_polyline"]
                            n = len(poly)
                            sample_pts = poly if n <= 10 else [poly[i] for i in range(0, n, max(1, n//10))]
                            for pt in sample_pts:
                                limit, _ = server_self.nav_engine.osm.get_speed_limit_at(pt[0], pt[1], search_radius_m=100)
                                if limit and limit > max_speed:
                                    max_speed = limit
                        elif rt.get("full_polyline") and hasattr(server_self.cam_engine, 'osm') and server_self.cam_engine.osm:
                            poly = rt["full_polyline"]
                            n = len(poly)
                            sample_pts = poly if n <= 10 else [poly[i] for i in range(0, n, max(1, n//10))]
                            for pt in sample_pts:
                                limit, _ = server_self.cam_engine.osm.get_speed_limit_at(pt[0], pt[1], search_radius_m=100)
                                if limit and limit > max_speed:
                                    max_speed = limit
                                    
                        rt["camera_count"] = cameras_count
                        rt["max_speed"] = max_speed

                    # Lưu thông tin tìm kiếm
                    server_self.update_status(
                        pending_routes=routes,
                        selecting_route=True,
                        is_navigating=False,
                        destination_text=destination,
                        waypoints_text=waypoints_text
                    )
                    
                    # Phát thông tin 3 tuyến đường ra loa theo đúng yêu cầu
                    speech_msg = "tôi có 3 tuyến đường phù hợp: "
                    for idx, rt in enumerate(routes):
                        label_name = f"tuyến đường {idx + 1}"
                        if idx == 0:
                            label_name += " ưu tiên"
                        speech_msg += (
                            f"{label_name} có quãng đường là {rt['total_distance_km']} km, "
                            f"tốc độ tối đa được di chuyển là {rt['max_speed']} km/giờ, "
                            f"có {rt['camera_count']} camera phạt nguội. "
                        )
                    
                    server_self.update_status(voice_reply=speech_msg)
                    server_self.trigger_voice_alert(speech_msg)
                    server_self._send_text_to_esp32("Chọn tuyến đường trên màn hình...")

                    # Chuẩn bị payload gửi ESP32
                    esp_payload = {
                        "routes": [
                            {
                                "index": rt["index"],
                                "label": rt["label"],
                                "dist_km": rt["total_distance_km"],
                                "eta_min": rt["total_duration_min"],
                                "summary": rt["summary"][:20],
                                "polyline": [[p[0], p[1]] for p in rt["polyline"][:30]],
                            }
                            for rt in routes
                        ]
                    }
                    server_self.device_state["show_routes"] = esp_payload
                    
                    # Gửi trực tiếp ESP32
                    def send_routes_bg():
                        try:
                            url = f"http://{server_self.esp32_ip}/show-routes"
                            requests.post(url, json=esp_payload, timeout=2)
                        except Exception:
                            pass
                    threading.Thread(target=send_routes_bg, daemon=True).start()
                    print(f"[WebServer] Gửi {len(routes)} tuyến đường alternatives lên ESP32 thành công.")
                else:
                    server_self.update_status(
                        pending_routes=[],
                        selecting_route=False,
                        voice_reply="Không tìm thấy tuyến đường nào phù hợp."
                    )
                    server_self.trigger_voice_alert("Không tìm thấy tuyến đường nào phù hợp.")
            except Exception as e:
                print("[WebServer] Lỗi trong calc_routes:", e)

        threading.Thread(target=calc_routes, daemon=True).start()
        
    def generate_tts_pcm(self, text):
        """Tạo giọng nói Việt chuẩn từ Google TTS và convert sang raw PCM 16kHz 16-bit Mono."""
        try:
            import urllib.parse
            import requests
            import subprocess
            import os
            
            # 1. Tải file MP3 từ Google Translate TTS (hoàn toàn miễn phí, giọng đọc chuẩn)
            q = urllib.parse.quote(text)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl=vi&client=tw-ob&q={q}"
            headers = {"User-Agent": "Mozilla/5.0"}
            
            print(f"[TTS Server] Đang gọi Google Translate TTS cho câu: '{text}'...")
            r = requests.get(url, headers=headers, timeout=8)
            mp3_path = "temp_tts.mp3"
            pcm_path = "temp_tts.pcm"
            
            with open(mp3_path, "wb") as f:
                f.write(r.content)
                
            # 2. Convert MP3 sang Raw PCM 16kHz Mono 16-bit LE dùng static-ffmpeg
            try:
                import static_ffmpeg
                static_ffmpeg.add_paths()
                ffmpeg_bin = "ffmpeg"
            except Exception:
                ffmpeg_bin = "ffmpeg" # Fallback if system already has it
                
            # Chạy câu lệnh ffmpeg convert âm thanh
            cmd = [
                ffmpeg_bin, "-y",
                "-i", mp3_path,
                "-f", "s16le",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                pcm_path
            ]
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Đọc dữ liệu PCM thô
            if os.path.exists(pcm_path):
                with open(pcm_path, "rb") as f:
                    pcm_bytes = f.read()
                
                # Cleanup
                try:
                    os.remove(mp3_path)
                    os.remove(pcm_path)
                except Exception:
                    pass
                print(f"[TTS Server] Sinh PCM thô thành công, dung lượng: {len(pcm_bytes)} bytes")
                return pcm_bytes
        except Exception as e:
            print("[TTS Server] ❌ Lỗi phát sinh giọng nói PCM:", e)
        return None

    def trigger_voice_alert(self, text):
        """Tạo cảnh báo giọng nói, sinh PCM thô và gán trạng thái cho ESP32 Polling."""
        print(f"[Voice Alert] Thiết lập câu cảnh báo giọng nói xe máy: '{text}'")
        pcm_bytes = self.generate_tts_pcm(text)
        if pcm_bytes:
            self.tts_audio_buffer = pcm_bytes
            self.device_state["voice"] = {
                "has_audio": True,
                "text": text
            }
        else:
            # Fallback nếu không sinh được PCM
            self.device_state["voice"] = {
                "has_audio": False,
                "text": text
            }

    def update_status(self, **kwargs):
        """Cập nhật trạng thái server từ background navigation loop."""
        self.status.update(kwargs)
        
    def query_gemini(self, query_text, api_key):
        """Truy vấn chatbot Gemini 1.5 Flash miễn phí của Google để đàm thoại."""
        if not api_key:
            return "Vui lòng dán khóa API của Gemini trên màn hình điện thoại!"
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        system_instruction = (
            "Bạn là trợ lý xe máy thông minh 'Tequila'. "
            "Nhiệm vụ cực kỳ quan trọng: Nếu người dùng muốn đi đâu đó, muốn chỉ đường, tìm đường, hoặc chỉ nói tên địa danh/địa điểm cụ thể (ví dụ: 'ngã tư thủ đức', 'chợ bến thành', 'chỉ đường tới vũng tàu', 'tới cgv'), bạn PHẢI trả về câu trả lời ở định dạng chính xác: 'NAV: <Tên địa điểm>' (ví dụ: 'NAV: Ngã tư Thủ Đức') và KHÔNG nói thêm bất cứ từ nào khác. "
            "Nếu người dùng chỉ trò chuyện thông thường hoặc hỏi đáp (ví dụ: 'kể chuyện cười', 'thời tiết thế nào', 'bạn là ai'), hãy trả lời ngắn gọn dưới 35 từ."
        )
        payload = {
            "contents": [{
                "parts": [{"text": f"Chỉ thị hệ thống: {system_instruction}\nYêu cầu của người dùng: {query_text}"}]
            }]
        }
        try:
            print(f"[Gemini AI] Gửi yêu cầu: '{query_text}'...")
            r = requests.post(url, json=payload, headers=headers, timeout=8)
            data = r.json()
            if "candidates" in data and data["candidates"]:
                response_text = data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"[Gemini AI] Phản hồi: {response_text}")
                return response_text
            else:
                print("[Gemini AI] Cấu trúc lỗi:", data)
                return "Tôi gặp khó khăn khi kết nối với máy chủ AI."
        except Exception as e:
            print("[Gemini AI] Lỗi kết nối:", e)
            return "Lỗi kết nối mạng AI."

    def _transcribe_audio(self, pcm_data):
        """Chuyển đổi luồng âm thanh PCM 16kHz thô từ Mic ESP32 thành văn bản tiếng Việt."""
        import struct
        sample_rate = 16000
        bits = 16
        channels = 1
        
        # Tạo WAV Header 44 bytes để hợp lệ hóa file WAV thô
        header = struct.pack('<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            len(pcm_data) + 36,
            b'WAVE',
            b'fmt ',
            16, 1, channels,
            sample_rate,
            sample_rate * channels * bits // 8,
            channels * bits // 8,
            bits,
            b'data',
            len(pcm_data)
        )
        wav_data = header + pcm_data
        
        # Gọi cổng nhận dạng giọng nói miễn phí của Google
        url = "https://www.google.com/speech-api/v1/recognize?client=chromium&lang=vi-VN"
        headers = {"Content-Type": "audio/x-wav; rate=16000"}
        try:
            print(f"[STT] Đang dịch {len(pcm_data)} bytes âm thanh...")
            r = requests.post(url, data=wav_data, headers=headers, timeout=8)
            lines = r.text.strip().split("\n")
            for line in lines:
                data = json.loads(line)
                if "hypotheses" in data and data["hypotheses"]:
                    text = data["hypotheses"][0]["utterance"]
                    print(f"[STT] Kết quả dịch giọng nói: '{text}'")
                    return text
        except Exception as e:
            print("[STT] ❌ Lỗi nhận diện giọng nói tiếng Việt:", e)
        return None

    def _send_text_to_esp32(self, text):
        """Gửi văn bản thông báo đè lên màn hình ESP32 xe máy."""
        try:
            url = f"http://{self.esp32_ip}/voice"
            requests.post(url, json={"text": text}, timeout=1.5)
        except Exception:
            pass

    def _handle_request(self, handler_class):
        """Tạo request handler với closure để truy cập biến self."""
        server_self = self
        
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass  # Tắt log console để giảm lag
                
            def send_json(self, data, code=200):
                body = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(body)
                
            def do_GET(self):
                if self.path == '/' or self.path == '/index.html':
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(HTML_PAGE.encode('utf-8'))

                # ─── Trang setup Apple Find My (khong can JS) ───
                elif self.path == '/setup-findmy':
                    is_setup = server_self.findmy_reader.is_setup
                    if is_setup:
                        msg = '<div class="msg msg-ok">&#9989; Da ket noi Apple Find My thanh cong! Server dang doc GPS tu dong.</div>'
                    else:
                        msg = ''
                    page = FINDMY_SETUP_PAGE.replace('{MSG}', msg)
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(page.encode('utf-8'))

                # ─── GPS tu iPhone Shortcuts (GET request) ───
                elif self.path.startswith('/api/update-gps?') or (self.path == '/api/update-gps' and 'lat' in self.path):
                    import urllib.parse as _up
                    _qs = _up.parse_qs(_up.urlparse(self.path).query)
                    _lat = float(_qs.get('lat',['0'])[0])
                    _lon = float(_qs.get('lon',['0'])[0])
                    _spd = float(_qs.get('speed',['0'])[0])
                    _hdg = float(_qs.get('heading',['0'])[0])
                    if _lat != 0 and _lon != 0:
                        server_self.update_status(
                            gps_lat=_lat, gps_lon=_lon,
                            speed_kmh=_spd, wifi_connected=True
                        )
                        print(f'[Shortcut GPS] {_lat:.5f},{_lon:.5f}')
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","source":"shortcut"}')

                elif self.path == '/api/status':
                    # Lấy GPS real-time cập nhật vào status
                    if server_self.gps:
                        pos = server_self.gps.get_current()
                        server_self.update_status(
                            gps_lat=pos[0], gps_lon=pos[1],
                            speed_kmh=server_self.gps.get_speed_kmh()
                        )

                    # Tính cảnh báo realtime cho ESP32 Cloud Polling
                    try:
                        lat = server_self.status.get("gps_lat")
                        lon = server_self.status.get("gps_lon")
                        if lat and lon and server_self.cam_engine:
                            nearby_cams = server_self.cam_engine.get_nearby_cameras(
                                lat, lon, radius_m=300
                            )
                            if nearby_cams:
                                closest = min(nearby_cams,
                                              key=lambda c: c.get("distance_m", 9999))
                                server_self.update_status(
                                    camera_dist_m=int(closest.get("distance_m", 9999)),
                                    camera_type=closest.get("type", "speed"),
                                    cameras_nearby=[
                                        {
                                            "lat": c["lat"], "lon": c["lon"],
                                            "type": c.get("type", "speed"),
                                            "speed_limit": c.get("speed_limit", 60),
                                            "distance_m": int(c.get("distance_m", 9999))
                                        }
                                        for c in nearby_cams[:5]
                                    ]
                                )
                            else:
                                server_self.update_status(
                                    camera_dist_m=9999,
                                    cameras_nearby=[]
                                )
                    except Exception:
                        pass

                    # Xoá arrived_text sau khi ESP32 đọc
                    status_copy = dict(server_self.status)
                    if status_copy.get("arrived_text"):
                        server_self.status["arrived_text"] = ""
                    self.send_json(status_copy)
                elif self.path == '/api/poll-device':
                    # Trả trạng thái thiết bị gom được cho ESP32 Polling
                    state = server_self.device_state.copy()
                    # Reset các tin nhắn/lệnh một lần
                    server_self.device_state["voice"] = None
                    server_self.device_state["stop"] = False
                    self.send_json(state)
                elif self.path == '/api/get-audio':
                    # Trả về luồng âm thanh PCM nhị phân thô cho ESP32 phát qua Loa
                    if hasattr(server_self, 'tts_audio_buffer') and server_self.tts_audio_buffer:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Content-Length', str(len(server_self.tts_audio_buffer)))
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(server_self.tts_audio_buffer)
                        server_self.tts_audio_buffer = None
                    else:
                        self.send_response(404)
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                # ── Find My: Tao key pair ──
                elif self.path == '/api/gen-findmy-key':
                    result = server_self.findmy_reader.generate_key_pair()
                    self.send_json(result)
                # ── Find My: Doc vi tri hien tai ──
                elif self.path == '/api/findmy-location':
                    loc = server_self.findmy_reader.last_location
                    if loc:
                        self.send_json(loc)
                    else:
                        loc_live = server_self.findmy_reader.fetch_location_once()
                        self.send_json(loc_live or {"error": "Chua co vi tri"})
                else:
                    self.send_response(404)
                    self.end_headers()
                    
            def do_POST(self):
                content_len = int(self.headers.get('Content-Length', 0))
                
                # ─── 1. TIẾP NHẬN FILE GHI ÂM TỪ MIC ESP32 (Raw PCM Binary hoặc Simulator Text) ───
                if self.path == '/api/voice-command':
                    content_type = self.headers.get('Content-Type', '')
                    if 'application/json' in content_type:
                        audio_data = self.rfile.read(content_len)
                        try:
                            data = json.loads(audio_data) if audio_data else {}
                            text = data.get("text", "")
                        except Exception:
                            text = ""
                            
                        def process_text():
                            if not text:
                                server_self.update_status(voice_reply="Tôi không nghe rõ.")
                                server_self.trigger_voice_alert("Xin lỗi, tôi không nghe rõ giọng nói của bạn.")
                                return
                            
                            server_self.device_state["voice"] = {"text": f"🗣️ Bạn hỏi: '{text}'", "has_audio": False}
                            server_self._send_text_to_esp32(f"🗣️ Bạn nói: '{text}'")
                            
                            text_lower = text.lower().strip()
                            
                            # 1. Kiểm tra trạng thái đang chờ trả lời có tiếp tục hành trình cũ không
                            if server_self.status.get("pending_resume"):
                                if any(x in text_lower for x in ["có", "uốn", "tiếp tục", "chạy tiếp", "đồng ý", "yes", "ok"]):
                                    server_self.status["pending_resume"] = False
                                    saved = server_self._load_journey_state()
                                    if saved and saved.get("destination"):
                                        msg = f"Đang tiếp tục hành trình cũ tới {saved['destination']}"
                                        server_self.update_status(voice_reply=msg)
                                        server_self.trigger_voice_alert(msg)
                                        server_self._send_text_to_esp32(msg)
                                        server_self._trigger_navigation_directly(saved["destination"], saved.get("waypoints", []))
                                    else:
                                        server_self.trigger_voice_alert("Không tìm thấy hành trình cũ.")
                                    return
                                elif any(x in text_lower for x in ["không", "hủy", "bỏ", "no"]):
                                    server_self.status["pending_resume"] = False
                                    server_self._clear_journey_state()
                                    msg = "Đã hủy hành trình cũ. Hôm nay Ngài muốn đi đâu?"
                                    server_self.update_status(voice_reply=msg)
                                    server_self.trigger_voice_alert(msg)
                                    server_self._send_text_to_esp32(msg)
                                    return

                            is_nav_command = False
                            
                            for keyword in ["đi đến", "đến", "tới", "chỉ đường tới", "chỉ đường đến", "navigate to"]:
                                if keyword in text_lower:
                                    destination = text_lower.split(keyword, 1)[1].strip()
                                    if destination:
                                        server_self._trigger_routes_search(destination, [])
                                        is_nav_command = True
                                        break
                            
                            if not is_nav_command:
                                gemini_key = server_self.status.get("gemini_api_key", "")
                                reply = server_self.query_gemini(text, gemini_key)
                                if reply.strip().startswith("NAV:"):
                                    destination = reply.replace("NAV:", "").strip()
                                    server_self._trigger_routes_search(destination, [])
                                else:
                                    server_self.update_status(voice_reply=reply)
                                    server_self.trigger_voice_alert(reply)
                                    server_self._send_text_to_esp32(reply)
                                
                        threading.Thread(target=process_text, daemon=True).start()
                        self.send_json({"status": "ok"})
                        return
                    else:
                        # Từ thiết bị thật gửi PCM nhị phân thô
                        audio_data = self.rfile.read(content_len)
                        
                        def process_audio():
                            try:
                                # 1. Dịch âm thanh ra text
                                text = server_self._transcribe_audio(audio_data)
                                if not text:
                                    try:
                                        speech.say("Xin lỗi, tôi không nghe rõ giọng nói của bạn.", "vi-VN")
                                    except Exception:
                                        pass
                                    server_self.update_status(voice_reply="Xin lỗi, tôi không nghe rõ giọng nói của bạn.")
                                    server_self.trigger_voice_alert("Xin lỗi, tôi không nghe rõ giọng nói của bạn.")
                                    return
                                
                                # Hiển thị câu hỏi của user lên màn hình
                                server_self.device_state["voice"] = {"text": f"🗣️ Bạn hỏi: '{text}'", "has_audio": False}
                                server_self._send_text_to_esp32(f"🗣️ Bạn nói: '{text}'")
                                
                                text_lower = text.lower().strip()
                                
                                # 1. Kiểm tra trạng thái đang chờ trả lời có tiếp tục hành trình cũ không
                                if server_self.status.get("pending_resume"):
                                    if any(x in text_lower for x in ["có", "uốn", "tiếp tục", "chạy tiếp", "đồng ý", "yes", "ok"]):
                                        server_self.status["pending_resume"] = False
                                        saved = server_self._load_journey_state()
                                        if saved and saved.get("destination"):
                                            msg = f"Đang tiếp tục hành trình cũ tới {saved['destination']}"
                                            try:
                                                speech.say(msg, "vi-VN")
                                            except Exception:
                                                pass
                                            server_self.update_status(voice_reply=msg)
                                            server_self.trigger_voice_alert(msg)
                                            server_self._send_text_to_esp32(msg)
                                            server_self._trigger_navigation_directly(saved["destination"], saved.get("waypoints", []))
                                        else:
                                            server_self.trigger_voice_alert("Không tìm thấy hành trình cũ.")
                                        return
                                    elif any(x in text_lower for x in ["không", "hủy", "bỏ", "no"]):
                                        server_self.status["pending_resume"] = False
                                        server_self._clear_journey_state()
                                        msg = "Đã hủy hành trình cũ. Hôm nay Ngài muốn đi đâu?"
                                        try:
                                            speech.say(msg, "vi-VN")
                                        except Exception:
                                            pass
                                        server_self.update_status(voice_reply=msg)
                                        server_self.trigger_voice_alert(msg)
                                        server_self._send_text_to_esp32(msg)
                                        return

                                is_nav_command = False
                                
                                # 2. Xử lý câu lệnh điều hướng đi đường
                                for keyword in ["đi đến", "đến", "tới", "chỉ đường tới", "chỉ đường đến", "navigate to"]:
                                    if keyword in text_lower:
                                        destination = text_lower.split(keyword, 1)[1].strip()
                                        if destination:
                                            server_self._trigger_routes_search(destination, [])
                                            is_nav_command = True
                                            break
                                
                                # 3. Trò chuyện và hỏi đáp cùng Gemini AI
                                if not is_nav_command:
                                    gemini_key = server_self.status.get("gemini_api_key", "")
                                    reply = server_self.query_gemini(text, gemini_key)
                                    if reply.strip().startswith("NAV:"):
                                        destination = reply.replace("NAV:", "").strip()
                                        server_self._trigger_routes_search(destination, [])
                                    else:
                                        # Phát câu trả lời của AI vào tai nghe nón bảo hiểm Bluetooth (nếu có Pythonista)
                                        try:
                                            speech.say(reply, "vi-VN")
                                        except Exception:
                                            pass
                                        
                                        # Cập nhật voice_reply lên status để Safari Dashboard phát âm thanh TTS
                                        server_self.update_status(voice_reply=reply)
                                        
                                        # Đồng bộ chữ & phát âm thanh sinh ra lên loa xe máy qua Cloud Polling
                                        server_self.trigger_voice_alert(reply)
                                        
                                        # Đẩy chữ phản hồi của AI hiển thị lên màn hình ESP32 local
                                        server_self._send_text_to_esp32(reply)
                            except Exception as e:
                                print("[Voice Engine] Lỗi xử lý âm thanh:", e)
                                
                        threading.Thread(target=process_audio, daemon=True).start()
                        self.send_json({"status": "ok"})
                        return

                # Đọc dữ liệu body JSON cho các endpoint khác
                body = self.rfile.read(content_len)
                try:
                    data = json.loads(body) if body else {}
                except Exception:
                    data = {}
                    
                # Cấu hình lại IP ESP32 nếu gửi từ Web UI
                esp_ip = data.get('esp32_ip')
                if esp_ip:
                    server_self.esp32_ip = esp_ip

                if self.path == '/api/set-gemini-key':
                    gemini_key = data.get('gemini_api_key', '')
                    server_self.status["gemini_api_key"] = gemini_key
                    print("[WebServer] Đã cấu hình khóa Gemini API thành công.")
                    self.send_json({"status": "ok"})

                elif self.path == '/api/boot':
                    print("[WebServer] 🚀 Thiết bị ESP32 thông báo đã khởi động!")
                    saved = server_self._load_journey_state()
                    if saved and saved.get("destination"):
                        msg = "Xin chào Ngài Tequila, hôm nay Ngài muốn đi đâu. À, tôi thấy Ngài có một hành trình chưa hoàn thành. Ngài có muốn tiếp tục quãng đường cũ không?"
                        server_self.status["pending_resume"] = True
                    else:
                        msg = "Xin chào Ngài Tequila, hôm nay Ngài muốn đi đâu?"
                        server_self.status["pending_resume"] = False
                    
                    server_self.update_status(voice_reply=msg)
                    server_self.trigger_voice_alert(msg)
                    self.send_json({"status": "ok", "pending_resume": server_self.status["pending_resume"]})

                elif self.path == '/api/navigate':
                    destination = data.get('destination', '')
                    waypoints_text = data.get('waypoints', [])
                    if destination:
                        server_self._trigger_routes_search(destination, waypoints_text)
                    self.send_json({"status": "ok"})

                elif self.path == '/api/get-routes':
                    # Tính 3 tuyến đường và gửi ESP32 + Web UI hiển thị để user chọn
                    destination = data.get('destination', '')
                    waypoints_text = data.get('waypoints', [])
                    if not destination:
                        self.send_json({"status": "error", "message": "Thiếu điểm đến"})
                        return

                    def calc_routes():
                        try:
                            pos = server_self.gps.get_current() if server_self.gps else (10.7769, 106.7009)
                            wp_coords = []
                            for wp in waypoints_text:
                                c = server_self.nav_engine.geocode(wp)
                                if c: wp_coords.append(c)
                            routes = server_self.nav_engine.get_route_alternatives(
                                pos[0], pos[1], destination, wp_coords or None
                            )
                            if routes:
                                # Lưu vào status để Web UI polling lấy
                                server_self.update_status(
                                    pending_routes=routes,
                                    selecting_route=True,
                                    is_navigating=False,
                                )
                                # Gửi ESP32 hiển thị màn hình chọn tuyến
                                esp_payload = {
                                    "routes": [
                                        {
                                            "index": rt["index"],
                                            "label": rt["label"],
                                            "dist_km": rt["total_distance_km"],
                                            "eta_min": rt["total_duration_min"],
                                            "summary": rt["summary"][:20],
                                            "polyline": [[p[0], p[1]] for p in rt["polyline"][:30]],
                                        }
                                        for rt in routes
                                    ]
                                }
                                server_self.device_state["show_routes"] = esp_payload
                                # Gửi trực tiếp ESP32 nếu local
                                def send_routes_bg():
                                    try:
                                        url = f"http://{server_self.esp32_ip}/show-routes"
                                        requests.post(url, json=esp_payload, timeout=2)
                                    except Exception:
                                        pass
                                threading.Thread(target=send_routes_bg, daemon=True).start()
                                print(f"[WebServer] Gửi {len(routes)} tuyến đường lên ESP32.")
                            else:
                                server_self.update_status(
                                    pending_routes=[],
                                    selecting_route=False,
                                    voice_reply="Không tìm thấy tuyến đường. Vui lòng thử lại.",
                                )
                        except Exception as e:
                            print("[WebServer] Lỗi tính tuyến đường:", e)

                    threading.Thread(target=calc_routes, daemon=True).start()
                    self.send_json({"status": "calculating"})

                # ── FindMy: Form-based setup (khong can JS, redirect sau khi xong) ──
                elif self.path == '/api/setup-findmy-form':
                    import urllib.parse
                    body_str = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
                    params = urllib.parse.parse_qs(body_str)
                    apple_id = params.get('apple_id', [''])[0].strip()
                    password = params.get('password', [''])[0]
                    if not apple_id or not password:
                        # Quay lai trang setup voi thong bao loi
                        msg = '<div class="msg msg-err">Vui long nhap Apple ID va mat khau!</div>'
                        page = FINDMY_SETUP_PAGE.replace('{MSG}', msg)
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(page.encode('utf-8'))
                        return
                    # Goi setup trong background
                    import threading
                    result_holder = [None]
                    def do_auth():
                        result_holder[0] = server_self.findmy_reader.setup_apple_auth(apple_id, password)
                        if result_holder[0] and result_holder[0].get('status') == 'ok':
                            server_self.findmy_reader.start_background_polling()
                    t = threading.Thread(target=do_auth, daemon=True)
                    t.start()
                    t.join(timeout=45)  # Cho toi da 45 giay
                    result = result_holder[0] or {'status': 'error', 'message': 'Timeout - thu lai'}
                    if result.get('status') == '2fa_required':
                        # Hien trang nhap 2FA
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(FINDMY_2FA_PAGE.encode('utf-8'))
                    elif result.get('status') == 'ok':
                        msg = '<div class="msg msg-ok">&#9989; Dang nhap thanh cong! Server dang doc GPS tu Apple Find My.</div>'
                        page = FINDMY_SETUP_PAGE.replace('{MSG}', msg)
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(page.encode('utf-8'))
                    else:
                        err = result.get('message', result.get('error', str(result)))
                        msg = f'<div class="msg msg-err">Loi: {err}</div>'
                        page = FINDMY_SETUP_PAGE.replace('{MSG}', msg)
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/html; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(page.encode('utf-8'))

                # ── FindMy: Form 2FA submit ──
                elif self.path == '/api/setup-findmy-2fa':
                    import urllib.parse
                    body_str = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else body
                    params = urllib.parse.parse_qs(body_str)
                    code = params.get('code', [''])[0].strip()
                    result = server_self.findmy_reader.submit_2fa(code)
                    if result.get('status') == 'ok':
                        server_self.findmy_reader.start_background_polling()
                        msg = '<div class="msg msg-ok">&#9989; Xac nhan 2FA thanh cong! Find My dang hoat dong.</div>'
                    else:
                        err = result.get('error', str(result))
                        msg = f'<div class="msg msg-err">Ma 2FA sai: {err}</div>'
                    page = FINDMY_SETUP_PAGE.replace('{MSG}', msg)
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(page.encode('utf-8'))

                # ── FindMy: Dang nhap Apple ID (JSON API) ──
                elif self.path == '/api/setup-findmy':
                    apple_id = data.get('apple_id', '')
                    password = data.get('password', '')
                    if not apple_id or not password:
                        self.send_json({"status": "error", "message": "Thieu apple_id hoac password"})
                        return
                    import threading
                    def do_auth():
                        result = server_self.findmy_reader.setup_apple_auth(apple_id, password)
                        if result.get("status") == "ok":
                            server_self.findmy_reader.start_background_polling()
                        print("[FindMy Setup]", result)
                    threading.Thread(target=do_auth, daemon=True).start()
                    self.send_json({"status": "ok", "message": "Dang xu ly xac thuc Apple ID..."})

                # ── FindMy: Nhap ma 2FA ──
                elif self.path == '/api/findmy-2fa':
                    code = data.get('code', '').strip()
                    if not code:
                        self.send_json({"status": "error", "message": "Thieu ma 2FA"})
                        return
                    result = server_self.findmy_reader.submit_2fa(code)
                    if result.get("status") == "ok":
                        server_self.findmy_reader.start_background_polling()
                    self.send_json(result)

                elif self.path == '/api/select-route':
                    # User chọn tuyến đường (index 0/1/2) → bắt đầu dẫn đường
                    route_idx = data.get('route_index', 0)
                    pending = server_self.status.get("pending_routes", [])
                    if not pending or route_idx >= len(pending):
                        self.send_json({"status": "error", "message": "Không có tuyến đường"})
                        return

                    selected = pending[route_idx]
                    def start_selected():
                        try:
                            # Nạp steps vào nav engine
                            server_self.nav_engine.current_route_steps = selected.get("steps", [])
                            server_self.nav_engine.current_step_index = 0
                            server_self.nav_engine.blinker_announced = False

                            # Lưu lại hành trình chưa hoàn thành đề phòng tắt nguồn/reset đột ngột
                            server_self._save_journey_state(
                                server_self.status.get("destination_text", "Điểm đến"),
                                server_self.status.get("waypoints_text", [])
                            )

                            poly_full = selected.get("full_polyline", selected.get("polyline", []))
                            server_self.update_status(
                                is_navigating=True,
                                selecting_route=False,
                                pending_routes=[],
                                current_instruction=f"Bắt đầu — {selected.get('label', 'Tuyến đường')}",
                                eta_min=selected.get("total_duration_min", 0),
                                dist_remain_km=selected.get("total_distance_km", 0),
                                route_polyline=poly_full,
                            )

                            pos = server_self.gps.get_current() if server_self.gps else (10.7769, 106.7009)
                            cam_payload = []
                            if server_self.cam_engine:
                                cams = server_self.cam_engine.get_nearby_cameras(pos[0], pos[1])
                                cam_payload = [{"lat": c["lat"], "lon": c["lon"], "type": c["type"]}
                                               for c in cams]

                            update_payload = {
                                "lat": pos[0], "lon": pos[1],
                                "heading": pos[2] if len(pos) > 2 else 0,
                                "speed": server_self.gps.get_speed_kmh() if server_self.gps else 0,
                                "route": [[p[0], p[1]] for p in selected.get("polyline", [])[:30]],
                                "cameras": cam_payload,
                            }
                            server_self.device_state["update"] = update_payload
                            server_self.device_state["show_routes"] = None

                            def send_bg():
                                try:
                                    requests.post(f"http://{server_self.esp32_ip}/update",
                                                  json=update_payload, timeout=2)
                                except Exception:
                                    pass
                            threading.Thread(target=send_bg, daemon=True).start()
                            label = selected.get("label", "tuyến đường")
                            msg = (f"Bắt đầu dẫn đường theo {label}. "
                                   f"{selected.get('total_distance_km', 0)} km, "
                                   f"khoảng {selected.get('total_duration_min', 0)} phút.")
                            server_self.trigger_voice_alert(msg)
                            server_self.update_status(voice_reply=msg)
                            print(f"[WebServer] ✅ Bắt đầu dẫn đường tuyến {route_idx}: {label}")
                        except Exception as e:
                            print("[WebServer] Lỗi bắt đầu tuyến đường đã chọn:", e)

                    threading.Thread(target=start_selected, daemon=True).start()
                    self.send_json({"status": "ok"})

                elif self.path == '/api/optimize':

                    waypoints_text = data.get('waypoints', [])
                    destination = data.get('destination', '')
                    
                    pos = server_self.gps.get_current() if server_self.gps else (10.7769, 106.7009)
                    start = (pos[0], pos[1], "Vị trí hiện tại")
                    
                    wp_coords = []
                    for wp in waypoints_text:
                        c = server_self.nav_engine.geocode(wp)
                        if c: wp_coords.append(c)
                    
                    dest_coords = server_self.nav_engine.geocode(destination) if destination else None
                    
                    if dest_coords and wp_coords:
                        optimized = server_self.nav_engine.optimize_waypoints_locally(start, wp_coords, dest_coords)
                        order = ["Hiện tại"] + [w[2] for w in optimized] + [dest_coords[2]]
                    else:
                        order = ["Hiện tại"] + waypoints_text + [destination]
                        
                    self.send_json({"status": "ok", "optimized_order": order})
                    
                elif self.path == '/api/stop':
                    server_self._clear_journey_state()
                    server_self.update_status(is_navigating=False)
                    server_self.device_state["stop"] = True
                    def do_stop():
                        try:
                            url = f"http://{server_self.esp32_ip}/stop"
                            requests.post(url, json={}, timeout=2.0)
                        except Exception:
                            pass
                    threading.Thread(target=do_stop, daemon=True).start()
                    self.send_json({"status": "ok"})
                    
                elif self.path == '/api/update-gps':
                    # Định vị gửi từ trình duyệt điện thoại Safari (tiện lợi khi chạy Cloud)
                    # Auto-fix decimal bi mat khi iOS Shortcuts dung kieu "So" (Number)
                    def _fix_coord(v, is_lat=True):
                        if v is None: return None
                        try: v = float(str(v).replace(',', '.'))
                        except: return None
                        if is_lat and v > 90:   # VN lat 2 chu so
                            s = str(int(v)); v = float(s[:2] + '.' + s[2:])
                        elif not is_lat and v > 180:  # VN lon 3 chu so
                            s = str(int(v)); v = float(s[:3] + '.' + s[3:])
                        return v
                    lat = _fix_coord(data.get("lat"), is_lat=True)
                    lon = _fix_coord(data.get("lon"), is_lat=False)
                    speed = data.get("speed", 0)
                    heading = data.get("heading", 0)
                    if lat and lon:
                        server_self.update_status(gps_lat=lat, gps_lon=lon, speed_kmh=speed)
                        if server_self.gps:
                            # Cập nhật toạ độ thủ công vào GPSTracker
                            server_self.gps._manual_loc = (lat, lon, heading, 5.0)
                            server_self.gps._manual_speed = speed
                    self.send_json({"status": "ok"})
                    
                else:
                    self.send_response(404)
                    self.end_headers()
                    
            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                
        return Handler
        
    def _trigger_navigation_directly(self, destination, waypoints_text):
        """Tiến hành tính toán lộ trình trực tiếp và đẩy bản đồ lên màn hình xe."""
        server_self = self
        def start_nav():
            try:
                pos = server_self.gps.get_current() if server_self.gps else (10.7769, 106.7009)
                dest_coords = server_self.nav_engine.geocode(destination)
                if not dest_coords:
                    return

                wp_coords = []
                for wp in waypoints_text:
                    c = server_self.nav_engine.geocode(wp)
                    if c: wp_coords.append(c)

                result = server_self.nav_engine.get_route(
                    pos[0], pos[1], dest_coords, wp_coords
                )
                
                if result.get("status") == "OK":
                    server_self.update_status(
                        is_navigating=True,
                        current_instruction="Bắt đầu dẫn đường...",
                        eta_min=result.get("total_duration_min", 0),
                        dist_remain_km=result.get("total_distance_km", 0),
                        route_polyline=result.get("full_polyline", [])
                    )
                    
                    poly = result.get("polyline", [])
                    route_list = [[p[0], p[1]] for p in poly]
                    
                    cameras_payload = []
                    if server_self.cam_engine:
                        cams = server_self.cam_engine.get_nearby_cameras(pos[0], pos[1])
                        cameras_payload = [{"lat": c["lat"], "lon": c["lon"], "type": c["type"]} for c in cams]

                    payload = {
                        "lat": pos[0],
                        "lon": pos[1],
                        "heading": pos[2],
                        "speed": server_self.gps.get_speed_kmh() if server_self.gps else 0,
                        "route": route_list,
                        "cameras": cameras_payload
                    }
                    
                    # Lưu dữ liệu vào Cloud State để ESP32 Polling
                    server_self.device_state["update"] = payload
                    
                    # Gửi trực tiếp local ngầm
                    url = f"http://{server_self.esp32_ip}/update"
                    print(f"[WebServer] Đẩy bản đồ sang ESP32: {url}...")
                    def send_bg():
                        try:
                            requests.post(url, json=payload, timeout=1.5)
                        except Exception:
                            pass
                    threading.Thread(target=send_bg, daemon=True).start()
            except Exception as e:
                print("[WebServer] Lỗi tính toán lộ trình:", e)
        threading.Thread(target=start_nav, daemon=True).start()

    def start(self):
        """Khởi chạy web server trên background thread."""
        if not HAS_SERVER:
            print("[WebServer] Thư viện http.server không khả dụng")
            return
        handler = self._handle_request(None)
        socketserver.TCPServer.allow_reuse_address = True
        self._server = socketserver.TCPServer(("0.0.0.0", self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"[WebServer] ✅ Mobile Web UI đang chạy tại: http://localhost:{self.port}")
        print(f"[WebServer] Mở Safari trên iPhone 14 Pro để bắt đầu điều khiển!")
        
    def stop(self):
        if self._server:
            self._server.shutdown()
