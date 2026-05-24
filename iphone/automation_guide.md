# iOS (iPhone 14 Pro) Automation & Setup Guide

This guide details how to configure the iOS Apple Shortcut, Google Maps API key, and Pythonista 3 background BLE wrapper to achieve a fully automated motorcycle navigator experience.

---

## 1. Setting up Google Maps Directions API

To query motorcycle paths from Google Maps, you require an API Key with the Directions API enabled:

1. Visit the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (e.g., `MotorcycleNavigator`).
3. Navigate to **APIs & Services > Library** and enable **Directions API**.
4. Go to **APIs & Services > Credentials**, click **Create Credentials**, and choose **API Key**.
5. Copy the key and replace `YOUR_GOOGLE_MAPS_API_KEY` inside your iOS Shortcut action or Script parameters.

---

## 2. Importing the iOS Apple Shortcut

Since iOS Shortcuts are binary files, they are represented in text format in [shortcuts_wyn.json](./shortcuts_wyn.json). To recreate this shortcut on your iPhone:

1. Open the **Shortcuts app** on your iPhone 14 Pro.
2. Tap the `+` button in the top right to create a new Shortcut.
3. Name it: `VMN_Compact_Motorcycle_Navigator`.
4. Recreate the blocks as documented in the JSON:
   - **Speak Text**: "Bạn muốn đi đâu?" (Language: Vietnamese).
   - **Dictate Text**: Input language `vi-VN`.
   - **Get Current Location**: Set to `Best` accuracy.
   - **Get Contents of URL**:
     - Insert URL: `https://maps.googleapis.com/maps/api/directions/json?origin=Current+Location&destination=[Dictated Text]&mode=two_wheeler&key=YOUR_API_KEY`
   - **Get File**: Select from `iCloud Drive/Shortcuts/` -> `camera_phat_nguoi.csv`.
   - **Open App**: Launch Pythonista 3 to start the background BLE link.

---

## 3. Running the Pythonista 3 BLE Assistant

Pythonista 3 is an iOS Python IDE that provides direct access to native iOS frameworks: Bluetooth (`cb`), Location/GPS (`location`), and Text-to-Speech (`speech`).

### Steps:
1. Install **Pythonista 3** from the iOS App Store.
2. Copy [ble_helper_ios.py](./ble_helper_ios.py) into the Pythonista local workspace directory.
3. In iOS Settings:
   - Navigate to **Privacy > Location Services** -> **Pythonista** -> Set to **Always**.
   - Navigate to **General > Background App Refresh** -> Enable for **Pythonista**.
4. Run the script in Pythonista. It will scan, connect to **VMN-Compact**, and run the navigation update loop in the background while your phone is locked or in your pocket.

---

## 4. Automation: Auto-Run on BLE Connect

You can configure iOS to launch your navigator script automatically when the ESP32 powers on:

1. In the **Shortcuts app**, tap the **Automation** tab at the bottom.
2. Tap **Create Personal Automation** (or the `+` button).
3. Select **Bluetooth**.
4. Under **Device**, select **VMN-Compact**.
5. Check **Run Immediately** (so it connects without prompting you to click).
6. Set the Action to **Run Pythonista Script** and select `ble_helper_ios.py`.

---

## 5. CSV Speed Camera Updates

The navigator compares your active coordinates to [camera_phat_nguoi.csv](../data/camera_phat_nguoi.csv) in real-time.

### How to update the camera data:
1. Save your camera locations in CSV format with columns: `latitude`, `longitude`, `camera_type` (either `speed` or `red_light`), `description`, and `speed_limit`.
2. Move the CSV file to the `Shortcuts` folder inside **iCloud Drive** on your iPhone.
3. The Apple Shortcut or Pythonista script will automatically reload this data at startup to calculate distance limits.
