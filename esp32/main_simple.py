# main_simple.py v9 - Fix marker, streaming, local HTTP fast
# - Server ve GPS marker tai dung vi tri (gps_lat/gps_lon param)
# - ESP32 KHONG ve dot rieng (tranh double marker)
# - Pre-cache adjacent tiles: lan 2 pan den vung do rat nhanh
import network, ssl, socket, json, time, machine, gc, math, config
from ili9341_simple import ILI9341
from lvgl_map_2_8 import MAP_Y, MAP_H, SCREEN_W, STATUS_H, HUD_H, C_WHITE

print("=== NAV v9 ===")

spi = machine.SPI(1, baudrate=40000000,
    sck=machine.Pin(config.TFT_CLK), mosi=machine.Pin(config.TFT_MOSI),
    miso=machine.Pin(config.TFT_MISO))
d = ILI9341(spi, cs_pin=config.TFT_CS, dc_pin=config.TFT_DC,
            rst_pin=-1, bl_pin=config.TFT_BL,
            width=config.DISPLAY_WIDTH, height=config.DISPLAY_HEIGHT)
d.fill(d.rgb(0,15,40))

C_FOLLOW = d.rgb(20,120,20); C_PAN = d.rgb(50,50,150)
C_WARN = d.rgb(180,80,0); C_HUD = d.rgb(8,8,18)

def draw_status(mode, zoom, lat, loading=False):
    c = C_FOLLOW if mode=='follow' else (C_WARN if loading else C_PAN)
    d.fill_rect(0,0,SCREEN_W,STATUS_H,c)
    label = "N" if mode=='follow' else "P"
    d.text(label, 2, 10, C_WHITE, c)
    d.fill_rect(14,2,22,STATUS_H-4,d.rgb(50,50,50))
    d.text("Z+",15,10,C_WHITE,d.rgb(50,50,50))
    d.fill_rect(38,2,22,STATUS_H-4,d.rgb(50,50,50))
    d.text("Z-",39,10,C_WHITE,d.rgb(50,50,50))
    info = "TAI..." if loading else "Z{} {:.4f}".format(zoom,lat)
    d.text(info[:16], 64, 10, C_WHITE, c)

def draw_hud(instr="", speed=0, eta=None, dist_km=None):
    d.fill_rect(0,MAP_Y+MAP_H,SCREEN_W,HUD_H,C_HUD)
    d.text((instr[:18] if instr else "San sang"),4,MAP_Y+MAP_H+4,C_WHITE,C_HUD)
    sp = "{}km/h".format(int(speed)) if speed else "--"
    et = "{}p".format(int(eta)) if eta else ""
    ds = "{:.1f}km".format(dist_km) if dist_km else ""
    d.text("{} {} {}".format(sp,ds,et)[:20],4,MAP_Y+MAP_H+18,d.rgb(200,200,80),C_HUD)

# ── Touch XPT2046 ──
class XPT2046:
    X_MIN,X_MAX = 300,3900; Y_MIN,Y_MAX = 200,3800
    def __init__(self,spi,cs,irq):
        self.spi=spi
        self.cs=machine.Pin(cs,machine.Pin.OUT); self.cs.value(1)
        self.irq=machine.Pin(irq,machine.Pin.IN)
    def _rd(self,cmd,n=5):
        v=[]
        for _ in range(n):
            self.cs.value(0); self.spi.write(bytes([cmd]))
            r=self.spi.read(2); self.cs.value(1)
            v.append(((r[0]<<8)|r[1])>>3)
        v.sort(); return sum(v[1:-1])//(n-2)
    def pressed(self): return not self.irq.value()
    def pos(self):
        if not self.pressed(): return None
        rx=self._rd(0xD0); ry=self._rd(0x90)
        sx = (ry-self.Y_MIN)*SCREEN_W//(self.Y_MAX-self.Y_MIN)
        sy = (rx-self.X_MIN)*320//(self.X_MAX-self.X_MIN)
        return (max(0,min(SCREEN_W-1,sx)), max(0,min(319,sy)))

try:
    tspi=machine.SPI(2,baudrate=2000000,
        sck=machine.Pin(config.TOUCH_CLK),mosi=machine.Pin(config.TOUCH_MOSI),
        miso=machine.Pin(config.TOUCH_MISO))
    touch=XPT2046(tspi,config.TOUCH_CS,config.TOUCH_IRQ)
    TOUCH_OK=True; print("[Touch] OK")
except Exception as e:
    TOUCH_OK=False; touch=None; print("[Touch] Loi:",e)

# ── WiFi ──
draw_status('follow',17,0); d.text("WiFi...",64,10,C_WHITE,C_FOLLOW)
wlan=network.WLAN(network.STA_IF); wlan.active(True)
wlan.connect(config.WIFI_SSID,config.WIFI_PASSWORD)
for _ in range(100):
    if wlan.isconnected(): break
    time.sleep_ms(300)
if not wlan.isconnected():
    d.fill(d.rgb(80,0,0)); d.text("NO WIFI",10,160,C_WHITE,d.rgb(80,0,0))
    while True: time.sleep(1)
print("[WiFi]",wlan.ifconfig()[0])

CLOUD = "tequilamap.onrender.com"
LOCAL_IP = "172.20.10.3"; LOCAL_PORT = 8080
MAP_W = SCREEN_W; MAP_H2 = MAP_H

# ── fetch_status: cloud HTTPS (co GPS thuc tu iPhone) ──
def fetch_status():
    gc.collect()
    try:
        s=socket.socket(); s.settimeout(10)
        s.connect((CLOUD,443))
        ss=ssl.wrap_socket(s,server_hostname=CLOUD)
        ss.write(b'GET /api/status HTTP/1.1\r\nHost: tequilamap.onrender.com\r\nConnection: close\r\n\r\n')
        resp=b''
        while True:
            c=ss.read(1024)
            if not c: break
            resp+=c
            if len(resp)>8000: break
        ss.close()
        i=resp.find(b'{'); j=resp.rfind(b'}')
        if i>=0 and j>i: return json.loads(resp[i:j+1])
    except Exception as e: print("[Status]",e)
    return None

def _stream_map_body(sock, is_ssl=False):
    """Stream HTTP response body truc tiep vao SPI. Tra ve so bytes da ghi."""
    read = sock.read if is_ssl else sock.recv
    # Doc header
    hdr = b''
    while b'\r\n\r\n' not in hdr:
        c = read(256)
        if not c: break
        hdr += c
    first_line = hdr[:hdr.find(b'\r\n')]
    if b' 200 ' not in first_line:
        print("[Map] HTTP:", first_line[:30]); return 0
    body_start = hdr[hdr.find(b'\r\n\r\n')+4:]
    # Stream thang vao display SPI
    d.set_window(0, MAP_Y, MAP_W-1, MAP_Y+MAP_H2-1)
    d.dc.value(1); d.cs.value(0)
    total = 0
    if body_start:
        d.spi.write(body_start); total += len(body_start)
    while True:
        c = read(512)
        if not c: break
        d.spi.write(c); total += len(c)
    d.cs.value(1)
    return total

def fetch_map_local(path):
    gc.collect()
    try:
        s=socket.socket(); s.settimeout(20)
        s.connect((LOCAL_IP,LOCAL_PORT))
        req='GET {} HTTP/1.1\r\nHost: {}:{}\r\nConnection: close\r\n\r\n'.format(path,LOCAL_IP,LOCAL_PORT)
        s.send(req.encode()); total=_stream_map_body(s,is_ssl=False)
        s.close(); return total
    except Exception as e: print("[Local]",e); return 0

def fetch_map_cloud(path):
    gc.collect()
    try:
        s=socket.socket(); s.settimeout(30)
        s.connect((CLOUD,443))
        ss=ssl.wrap_socket(s,server_hostname=CLOUD)
        req='GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n'.format(path,CLOUD)
        ss.write(req.encode()); total=_stream_map_body(ss,is_ssl=True)
        ss.close(); return total
    except Exception as e: print("[Cloud]",e); return 0

def fetch_map(map_lat, map_lon, zoom, gps_lat, gps_lon):
    """
    Fetch map tu server va stream truc tiep vao SPI (KHONG buffer RAM).
    - Server se ve GPS marker tai gps_lat/gps_lon (dung vi tri, k phai center map khi pan)
    - Pre-cache server da lam truoc vung ke can -> lan 2 pan den nhanh hon
    """
    path='/api/map-image?lat={:.6f}&lon={:.6f}&zoom={}&format=rgb565&gps_lat={:.6f}&gps_lon={:.6f}'.format(
        map_lat, map_lon, zoom, gps_lat, gps_lon)
    t0 = time.ticks_ms()
    total = fetch_map_local(path)
    src = 'local'
    MIN_OK = MAP_W * MAP_H2 * 2 * 0.9  # 90% of expected
    if total < MIN_OK:
        print("[Map] local {}B < min, thu cloud...".format(total))
        total = fetch_map_cloud(path); src = 'cloud'
    ms = time.ticks_diff(time.ticks_ms(), t0)
    ok = total >= MIN_OK
    print("[Map] {}B {}ms {} {}".format(total, ms, src, "OK" if ok else "THIEU"))
    return ok

def dist_m(la1,lo1,la2,lo2):
    return math.sqrt(((la2-la1)*111000)**2+((lo2-lo1)*111000*0.982)**2)

def px_to_deg(dx, dy, lat, zoom):
    ppd = 256.0*(1<<zoom)/360.0
    return (dy/ppd), (-dx/(ppd*math.cos(lat*0.01745)))

# ── State ──
gps_lat = getattr(config,'DEFAULT_LAT',10.8541)
gps_lon = getattr(config,'DEFAULT_LON',106.7878)
map_lat = gps_lat; map_lon = gps_lon
zoom = 17; mode = 'follow'
pan_ts = 0; need_remap = True
is_nav = False; instr = ""; speed = 0; eta = None; dist_km = None
t_down = False; t_sx=t_sy=t_lx=t_ly = 0; t_dx = t_dy = 0
last_gps_ms = time.ticks_ms() - 15000
GPS_NAV_MS = 5000; GPS_IDLE_MS = 30000; PAN_BACK_MS = 20000

draw_status(mode,zoom,gps_lat); draw_hud()
d.fill_rect(0,0,SCREEN_W,STATUS_H,C_WARN)
d.text("GPS cloud...",4,10,C_WHITE,C_WARN)
data = fetch_status()
if data:
    g=data.get('gps_lat') or 0; h=data.get('gps_lon') or 0
    if g and h:
        gps_lat,gps_lon = g,h; print("[GPS]",gps_lat,gps_lon)
    is_nav=bool(data.get('is_navigating')); instr=data.get('current_instruction','') or ''
    speed=data.get('speed_kmh') or 0; eta=data.get('eta_min'); dist_km=data.get('dist_remain_km')
map_lat,map_lon = gps_lat,gps_lon
draw_status(mode,zoom,gps_lat); draw_hud(instr,speed,eta,dist_km)
print("[OK] v9, GPS={:.5f},{:.5f}".format(gps_lat,gps_lon))

# ── Main loop ──
while True:
    now = time.ticks_ms()

    # Tu dong quay lai follow sau PAN_BACK_MS
    if mode=='pan' and pan_ts and time.ticks_diff(now,pan_ts) >= PAN_BACK_MS:
        mode='follow'; map_lat,map_lon=gps_lat,gps_lon; need_remap=True
        print("[Auto] Follow")

    # Poll touch 80 lan x 50ms = 4 giay
    for _ in range(80):
        if TOUCH_OK:
            pos = touch.pos()
            if pos:
                tx,ty = pos; t_lx,t_ly = tx,ty
                if not t_down:
                    t_sx,t_sy = tx,ty; t_dx=t_dy=0; t_down=True
                else:
                    ddx=tx-t_sx; ddy=ty-t_sy
                    if abs(ddx)>2 or abs(ddy)>2:
                        t_dx+=ddx; t_dy+=ddy; t_sx,t_sy=tx,ty
            else:
                if t_down:
                    # Nha tay: xu ly touch
                    if t_ly < STATUS_H+8:
                        # Status bar: zoom buttons
                        if 14<=t_lx<=36: zoom=min(19,zoom+1); need_remap=True; print("[Z+]",zoom)
                        elif 38<=t_lx<=60: zoom=max(10,zoom-1); need_remap=True; print("[Z-]",zoom)
                    elif abs(t_dx)>8 or abs(t_dy)>8:
                        # Swipe: pan map
                        dlat,dlon = px_to_deg(t_dx,t_dy,map_lat,zoom)
                        map_lat = max(-85,min(85,map_lat+dlat))
                        map_lon = ((map_lon+dlon+180)%360)-180
                        mode='pan'; pan_ts=time.ticks_ms(); need_remap=True
                        draw_status(mode,zoom,gps_lat,loading=True)
                        print("[Pan] ({:.4f},{:.4f}) dx={} dy={}".format(map_lat,map_lon,int(t_dx),int(t_dy)))
                    t_down=False; t_dx=t_dy=0
        if need_remap: break
        time.sleep_ms(50)

    # GPS update
    gps_int = GPS_NAV_MS if is_nav else GPS_IDLE_MS
    if time.ticks_diff(time.ticks_ms(),last_gps_ms) >= gps_int and not need_remap:
        last_gps_ms = time.ticks_ms()
        data = fetch_status()
        if data:
            g=data.get('gps_lat') or 0; h=data.get('gps_lon') or 0
            if g and h:
                mv = dist_m(gps_lat,gps_lon,g,h)
                if mv < 5000:
                    gps_lat,gps_lon = g,h
                    if mode=='follow' and mv >= 15:
                        map_lat,map_lon=gps_lat,gps_lon; need_remap=True
            is_nav=bool(data.get('is_navigating')); instr=data.get('current_instruction','') or ''
            speed=data.get('speed_kmh') or 0; eta=data.get('eta_min'); dist_km=data.get('dist_remain_km')
            draw_hud(instr,speed,eta,dist_km)

    # Fetch + display map
    if need_remap:
        need_remap = False
        draw_status(mode,zoom,gps_lat,loading=True)
        # Server se ve GPS marker tai gps_lat/gps_lon dung vi tri
        ok = fetch_map(map_lat,map_lon,zoom,gps_lat,gps_lon)
        last_gps_ms = time.ticks_ms()
        draw_status(mode,zoom,gps_lat)
        draw_hud(instr,speed,eta,dist_km)
