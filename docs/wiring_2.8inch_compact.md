# Wiring Guide for ESP32-S3 and 2.8" IPS TFT Compact Board

This document details the connections between the ESP32-S3 development board, the 2.8" SPI TFT Display (with GT911/FT6336 capacitive touch), the INMP441 I2S microphone, and the MAX98357 I2S speaker amplifier.

## 1. TFT Display and Capacitive Touch (SPI + I2C)

| Display/Touch Pin | ESP32-S3 Pin | Description |
| :--- | :--- | :--- |
| **VCC** | 3V3 / 5V | Display Power |
| **GND** | GND | Common Ground |
| **CS** | GPIO 15 | SPI Chip Select |
| **RST** | GPIO 4 | Display Reset |
| **DC/RS** | GPIO 2 | Data/Command Select |
| **MOSI/SDI** | GPIO 13 | SPI Master Out Slave In |
| **SCK** | GPIO 14 | SPI Clock |
| **LED/BL** | GPIO 21 | Backlight control (PWM compatible) |
| **MISO/SDO** | GPIO 12 | SPI Master In Slave Out (Optional) |
| **T_SDA** | GPIO 18 | I2C Data (Capacitive Touch) |
| **T_SCL** | GPIO 19 | I2C Clock (Capacitive Touch) |
| **T_INT** | GPIO 5 | Touch Interrupt |
| **T_RST** | GPIO 17 | Touch Reset |

---

## 2. Audio Input: INMP441 (I2S Microphone)

| INMP441 Pin | ESP32-S3 Pin | Description |
| :--- | :--- | :--- |
| **VDD** | 3.3V | Power Supply (Do NOT connect to 5V) |
| **GND** | GND | Ground |
| **L/R** | GND | Left/Right Channel Select (GND = Left Channel) |
| **WS** | GPIO 33 | Word Select (Left-Right Clock) |
| **SCK** | GPIO 32 | Serial Clock |
| **SD** | GPIO 34 | Serial Data Output |

---

## 3. Audio Output: MAX98357A (I2S Speaker Amplifier)

| MAX98357A Pin | ESP32-S3 Pin | Description |
| :--- | :--- | :--- |
| **Vin** | 5V / Vin | 5V Power for higher speaker output volume |
| **GND** | GND | Ground |
| **LRC/WS** | GPIO 25 | Word Select (Left-Right Clock) |
| **BCLK** | GPIO 26 | Bit Clock |
| **DIN** | GPIO 27 | Data Input |
| **GAIN** | Unconnected | Leave floating for default 9dB gain |
| **SD/MODE** | Unconnected | Default stereo mix / enabled |

---

## 4. Power & Battery Management

A standard 3.7V LiPo Battery (e.g., 800-1200mAh) is connected to a TP4056 charger board or directly to the ESP32-S3 board with battery charging capabilities.

- **Battery Voltage ADC Monitor**:
  - Connect Battery Positive (`BATT+`) via a voltage divider to **GPIO 35** of the ESP32-S3:
    - `BATT+` -> `100kΩ` -> [GPIO 35] -> `100kΩ` -> `GND`
    - This divides the maximum battery voltage (~4.2V) by 2, resulting in ~2.1V which is safe for the 3.3V ADC pin.

---

## 5. Voice Trigger Button Wiring

A physical tactile push button is required to trigger Vietnamese voice commands.
- **Onboard Option**: The built-in **BOOT button (GPIO 0)** on the ESP32-S3 development board is supported out-of-the-box.
- **External Option**: Connect a momentary push-button:
  - **Pin 1**: **GPIO 0** (configured with internal Pull-Up)
  - **Pin 2**: **GND**

---

## 6. How to Flash MicroPython with LVGL

To run this project, the ESP32-S3 must be flashed with a MicroPython firmware build that has been compiled with `lvgl` binding support.

### Step 1: Install flash tools
```bash
pip install esptool mpremote
```

### Step 2: Erase ESP32-S3 Flash
Connect the board to your computer, find the serial port (e.g., `/dev/cu.usbmodemX`), and run:
```bash
esptool.py --chip esp32s3 --port /dev/cu.usbmodem101 erase_flash
```

### Step 3: Flash LVGL-enabled MicroPython Firmware
Download an ESP32-S3 MicroPython binary with LVGL support (e.g. from LVGL MicroPython repository builds) and flash it:
```bash
esptool.py --chip esp32s3 --port /dev/cu.usbmodem101 --baud 460800 write_flash -z 0x0 firmware.bin
```

---

## 7. Running the First Test

After successful flashing, upload the project files to the ESP32:

### Step 1: Upload the script folder
Run this command from the project root directory:
```bash
# Upload all python files from esp32 folder to the device root
mpremote connect /dev/cu.usbmodem101 fs cp esp32/*.py :
```

### Step 2: Launch the App
Run the main app directly to view console logs:
```bash
mpremote connect /dev/cu.usbmodem101 run :main.py
```

### Step 3: Verify Actions
1. **Screen Display**: The TFT screen should light up and display:
   - "Đang kết nối iPhone..." in orange text.
   - Battery indicator (e.g., "100%") in green at the bottom right.
   - "Chờ dẫn đường..." at the bottom left.
2. **BLE Advertising**: Open the LightBlue or nRF Connect app on your iPhone. Scan for peripherals and locate **VMN-Compact**.
3. **Voice Record Command**: Press the physical BOOT button. The screen will display:
   - "ĐANG GHI ÂM: X%" progressing from 0% to 100% for 6 seconds.
   - On the terminal, you will see `[Voice] Starting Voice Record...` followed by raw data stream outputs.

