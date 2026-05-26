# esp32/config.py
# Cấu hình pin cho ESP32-2432S028 (Cheap Yellow Display - CYD)
# Board: ESP32-WROOM-32, ILI9341 2.8" 240×320, XPT2046 resistive touch

# ─── WiFi ───
# ⚠️ Điền tên hotspot iPhone và mật khẩu vào đây
# Tìm ở: Cài đặt iPhone → Personal Hotspot
WIFI_SSID     = "iPhone của Tequila"   # Sửa thành tên hotspot thật
WIFI_PASSWORD = "matkhaucuaban"        # Sửa thành mật khẩu thật
HTTP_PORT     = 80

# ─── CLOUD SERVER ───
USE_CLOUD_SERVER  = True
CLOUD_SERVER_HOST = "tequilamap.onrender.com"
CLOUD_SERVER_PORT = 443
CLOUD_SERVER_SSL  = True
CLOUD_POLL_MS     = 1500

# ─── OPENHAYSTACK / APPLE FIND MY ───
FINDMY_BLE_ENABLED = True
FINDMY_PUBLIC_KEY  = bytes([
    74, 65, 168, 22, 50, 46, 153, 59,
    47, 163, 85, 131, 229, 167, 229, 96,
    77, 12, 90, 17, 246, 165, 195, 50,
    215, 173, 253, 53
])

# ─── DISPLAY: ILI9341 SPI ───
# ESP32-2432S028 (CYD) pinout
DISPLAY_WIDTH    = 240
DISPLAY_HEIGHT   = 320
DISPLAY_ROTATION = 0      # Portrait dọc
MAP_AREA_HEIGHT  = 252    # 320 - 28 (statusbar) - 40 (HUD)
HUD_HEIGHT       = 40
STATUS_BAR_H     = 28

TFT_MOSI = 13   # SPI MOSI
TFT_MISO = 12   # SPI MISO (ILI9341 không cần nhưng SPI bus cần)
TFT_CLK  = 14   # SPI CLK
TFT_CS   = 15   # Chip Select
TFT_DC   = 2    # Data/Command
TFT_RST  = 12   # Reset — CYD dùng chung với MISO, có thể là -1
TFT_BL   = 21   # Backlight (PWM)

# ─── TOUCH: XPT2046 Resistive (SPI riêng) ───
# ⚠️ CYD dùng XPT2046, KHÔNG phải FT6236 capacitive!
TOUCH_CLK  = 25   # SPI CLK riêng cho touch
TOUCH_MOSI = 32   # SPI MOSI
TOUCH_MISO = 39   # SPI MISO (GPIO39 = input only)
TOUCH_CS   = 33   # Chip Select
TOUCH_IRQ  = 36   # Interrupt (GPIO36 = input only)

# ─── I2C (cho các module phụ nếu cần) ───
I2C_SDA  = 21
I2C_SCL  = 22

# ─── I2S MICROPHONE - INMP441 (nối ngoài) ───
MIC_SCK  = 26   # GPIO26 - SCK
MIC_WS   = 27   # GPIO27 - WS (L/R)
MIC_SD   = 35   # GPIO35 - SD (data, input only)

# ─── I2S SPEAKER - MAX98357A (nối ngoài) ───
SPK_SCK  = 17   # GPIO17 - BCLK
SPK_WS   = 16   # GPIO16 - LRC
SPK_SD   = 18   # GPIO18 - DIN
SPK_GAIN = 19   # GPIO19 - Gain

# ─── POWER ───
BATTERY_ADC_PIN = 34   # ADC đo pin (input only, qua voltage divider)
ACC_PIN         = 34   # Dùng chung ADC34 cho ACC nếu không có pin riêng
                       # ⚠️ Nếu không có dây ACC từ xe, để mặc định True trong check_power_source()

# ─── BUTTONS ───
WAKE_BUTTON_PIN = 0    # GPIO0 = nút BOOT có sẵn trên board CYD

# ─── LED RGB (CYD có LED RGB tích hợp) ───
LED_RED   = 4    # GPIO4
LED_GREEN = 16   # GPIO16 (chia sẻ với SPK_WS nếu dùng loa)
LED_BLUE  = 17   # GPIO17

# ─── AUDIO ───
SAMPLE_RATE     = 16000
MIC_GAIN        = 32
VOICE_RECORD_MS = 5000

# ─── MAP DISPLAY ───
MAP_ROUTE_COLOR    = (0, 85, 255)
MAP_CAM_COLOR      = (255, 50, 50)
MAP_POS_COLOR      = (255, 0, 0)
MAP_BG_COLOR       = (15, 15, 25)
CAMERA_ALERT_DIST  = 50          # Cảnh báo camera khi cách <= 50m
MAP_UPDATE_SEC     = 3           # Fetch bản đồ mỗi 3 giây
