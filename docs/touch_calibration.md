# Touch Calibration and Screen Rotation for 2.8" IPS TFT

This document explains how to set up display rotation and calibrate capacitive touch coordinates (using GT911 or FT6336 ICs) so they align with the rendering space in MicroPython.

---

## 1. Setting Screen Rotation

A 2.8" display panel typically has a native portrait resolution of $240 \times 320$. For motorcycle navigation, you can use portrait mode or rotate it $90^\circ$ or $270^\circ$ into landscape mode ($320 \times 240$ or $480 \times 320$).

In the MicroPython driver (e.g., ST7789 or ILI9341), rotation is set during initialization:

```python
import st7789

# Init display with 270-degree rotation (Landscape)
display = st7789.ST7789(
    spi, 
    width=320, 
    height=240, 
    rotation=st7789.ROTATION_270 # 0, 90, 180, or 270
)
```

---

## 2. Touch Coordinate Mapping (Calibration)

Capacitive touch controllers report raw ADC coordinate locations (e.g., $0$ to $4095$ or physical bounds like $0$ to $800$). These raw values must be scaled and mapped to screen pixel space.

### The Mapping Logic
If your display is rotated or the touch sensor is mounted upside down, touch registers may be inverted or swapped.

Use the following mapping equations in your touch driver read loop:

```python
# Raw read from GT911/FT6336 via I2C
raw_x, raw_y = touch_sensor.read_raw()

# 1. Scale raw input to display limits
# Assuming raw touch range is 0-800 for X and 0-480 for Y:
scaled_x = int((raw_x / 800.0) * DISPLAY_WIDTH)
scaled_y = int((raw_y / 480.0) * DISPLAY_HEIGHT)

# 2. Swap Axes (if screen is rotated landscape but touch is native portrait)
if ROTATED:
    scaled_x, scaled_y = scaled_y, scaled_x

# 3. Invert Axes (if coordinate directions are flipped)
if INVERT_X:
    scaled_x = DISPLAY_WIDTH - scaled_x
if INVERT_Y:
    scaled_y = DISPLAY_HEIGHT - scaled_y
```

---

## 3. Registering Touch Driver with LVGL

LVGL requires an input device (indev) driver to capture touch coordinates. Register your MicroPython touch callback as follows:

```python
import lvgl as lv

def touch_read_callback(indev_drv, data):
    if touch_sensor.is_touched():
        raw_x, raw_y = touch_sensor.read_raw()
        
        # Apply calibration offsets
        x, y = map_and_calibrate(raw_x, raw_y)
        
        data.point.x = x
        data.point.y = y
        data.state = lv.INDEV_STATE.PRESSED
    else:
        data.state = lv.INDEV_STATE.RELEASED
    return False

# Register indev driver
indev_drv = lv.indev_drv_t()
indev_drv.init()
indev_drv.type = lv.INDEV_TYPE.POINTER
indev_drv.read_cb = touch_read_callback
indev_drv.register()
```

---

## 4. Visual Touch Calibration Script

To verify that your touch alignment is accurate, upload this small test script to the ESP32. It draws a small blue circle at the location of your finger:

```python
# Save as scratch/touch_test.py
import lvgl as lv
import time

lv.init()
# [Insert display & touch drivers initialization code here]

# Create screen and a target marker
scr = lv.obj()
lv.scr_load(scr)

marker = lv.obj(scr)
marker.set_size(20, 20)
marker.set_style_bg_color(lv.color_make(0, 168, 255), 0)
marker.set_style_radius(lv.RADIUS_CIRCLE, 0)
marker.align(lv.ALIGN.CENTER, 0, 0)

label = lv.label(scr)
label.align(lv.ALIGN.TOP_MID, 0, 20)
label.set_text("Cham vao man hinh de test...")

def touch_timer_cb(timer):
    # Retrieve current active touch pointer point
    indev = lv.indev_get_next(None)
    if indev:
        point = lv.point_t()
        indev.get_point(point)
        state = indev.get_state()
        if state == lv.INDEV_STATE.PRESSED:
            # Move marker directly under finger
            marker.move_to(point.x - 10, point.y - 10)
            label.set_text(f"Touch X: {point.x}, Y: {point.y}")

# Poll touch state every 30ms using LVGL timer
test_timer = lv.timer_create(touch_timer_cb, 30, None)

while True:
    lv.tick_inc(5)
    lv.task_handler()
    time.sleep_ms(5)
```
- If the blue marker moves in the **opposite direction** of your finger, toggle the inversion flags (`INVERT_X` or `INVERT_Y`) in your calibration equations.
- If it moves **perpendicular** to your finger, swap the X and Y coordinates.
