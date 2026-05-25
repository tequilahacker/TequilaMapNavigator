# iphone/findmy_reader.py
# Doc vi tri thiet bi Tequila Map tu Apple Find My Network
# Su dung thu vien findmy.py (malmeloo/FindMy.py)
#
# FLOW:
#   1. Server gen EC P-224 key pair 1 lan → luu private key
#   2. ESP32 phat BLE beacon voi public key → iPhone pickup → Apple server
#   3. Server query Apple Find My voi private key → giai ma → lay GPS
#
# SETUP (chi can lam 1 lan):
#   1. Goi GET /api/gen-findmy-key → lay public_key_hex
#   2. Cap nhat FINDMY_PUBLIC_KEY trong esp32/config.py
#   3. Goi POST /api/setup-findmy voi Apple ID va password
#   4. Server tu dong doc GPS tu Find My moi 30 giay

import os
import json
import time
import threading
import base64

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption
    )
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import findmy
    from findmy import KeyPair
    from findmy.reports import RemoteAnisetteProvider
    HAS_FINDMY = True
except ImportError:
    HAS_FINDMY = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# File luu trang thai xac thuc Apple (1 lan duy nhat)
AUTH_FILE  = "findmy_auth.json"
KEY_FILE   = "findmy_key.json"
ANISETTE_URL = "https://ani.f1sh.me/"  # Public anisette server (mien phi)


class FindMyReader:
    """Doc vi tri thiet bi Tequila Map tu Apple Find My.
    
    Sau khi setup 1 lan, tu dong cap nhat GPS moi 30 giay
    ma khong can mo bat ky app nao tren iPhone.
    """

    def __init__(self, update_callback=None):
        """
        update_callback: fn(lat, lon, accuracy, timestamp) - goi moi khi co vi tri moi
        """
        self._callback = update_callback
        self._running = False
        self._thread = None
        self._last_lat = None
        self._last_lon = None
        self._last_seen = None
        self._key_pair = None
        self._is_setup = False
        self._poll_interval = 30  # giay

        # Kiem tra trang thai setup
        if os.path.exists(KEY_FILE) and os.path.exists(AUTH_FILE):
            self._is_setup = True
            print("[FindMy] Da setup truoc do. San sang doc GPS.")
        else:
            print("[FindMy] Chua setup. Goi /api/setup-findmy de bat dau.")

    # ─────────────────────────────────────────
    # BUOC 1: Tao key pair (1 lan)
    # ─────────────────────────────────────────
    def generate_key_pair(self):
        """Tao cap khoa EC P-224 moi cho thiet bi Tequila Map.
        
        Tra ve:
            dict: {
                'public_key_hex': str,    # Gui vao esp32/config.py
                'public_key_bytes': list, # 28 bytes cho ESP32
                'status': 'ok'
            }
        """
        if not HAS_CRYPTO:
            return {"error": "Thieu thu vien cryptography. Chay: pip install cryptography"}

        # Tao private key EC P-224
        private_key = ec.generate_private_key(ec.SECP224R1())
        public_key  = private_key.public_key()

        # Serialize
        priv_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        pub_compressed = public_key.public_bytes(Encoding.X962, PublicFormat.CompressedPoint)
        # pub_compressed = 29 bytes: [0x02/0x03] + 28 bytes

        pub_hex = pub_compressed.hex()
        pub_bytes_for_esp32 = list(pub_compressed[1:])  # Bo byte dau, lay 28 bytes

        # Luu private key
        key_data = {
            "private_key_pem": priv_pem.decode(),
            "public_key_hex": pub_hex,
            "created_at": time.time()
        }
        with open(KEY_FILE, "w") as f:
            json.dump(key_data, f, indent=2)

        print("[FindMy] Da tao key pair moi!")
        print("[FindMy] Public key (28 bytes cho ESP32):", pub_bytes_for_esp32)

        return {
            "status": "ok",
            "public_key_hex": pub_hex,
            "public_key_bytes": pub_bytes_for_esp32,
            "message": "Cap nhat FINDMY_PUBLIC_KEY trong esp32/config.py voi public_key_bytes nay"
        }

    # ─────────────────────────────────────────
    # BUOC 2: Dang nhap Apple ID (1 lan)
    # ─────────────────────────────────────────
    def setup_apple_auth(self, apple_id, password):
        """Xac thuc Apple ID va luu token.
        
        Chi can chay 1 lan. Token duoc luu va su dung lai.
        2FA: Neu Apple yeu cau 2FA, server tra ve yeu cau nhap ma.
        """
        if not HAS_FINDMY:
            return {
                "error": "Thieu thu vien findmy. Chay: pip install findmy",
                "install_cmd": "pip install findmy"
            }

        try:
            # Dung Anisette server public de xac thuc khong can Mac
            anisette = RemoteAnisetteProvider(ANISETTE_URL)

            # Tao account object
            acc = findmy.AppleAccount(anisette)

            # Dang nhap
            state = acc.login(apple_id, password)

            if state == findmy.LoginState.REQUIRE_2FA:
                # Luu account state de nhap 2FA sau
                auth_data = {
                    "apple_id": apple_id,
                    "state": "REQUIRE_2FA",
                    "account_data": acc.export()
                }
                with open(AUTH_FILE, "w") as f:
                    json.dump(auth_data, f)
                return {
                    "status": "2fa_required",
                    "message": "Apple yeu cau xac thuc 2 buoc. Goi POST /api/findmy-2fa voi {'code': 'XXXXXX'}"
                }

            elif state == findmy.LoginState.LOGGED_IN:
                auth_data = {
                    "apple_id": apple_id,
                    "state": "LOGGED_IN",
                    "account_data": acc.export()
                }
                with open(AUTH_FILE, "w") as f:
                    json.dump(auth_data, f)
                self._is_setup = True
                return {"status": "ok", "message": "Dang nhap Apple ID thanh cong!"}

            else:
                return {"error": f"Trang thai dang nhap: {state}"}

        except Exception as e:
            return {"error": str(e)}

    def submit_2fa(self, code):
        """Nhap ma 2FA sau khi Apple yeu cau."""
        if not HAS_FINDMY:
            return {"error": "Thieu thu vien findmy"}

        try:
            if not os.path.exists(AUTH_FILE):
                return {"error": "Chua bat dau dang nhap. Goi /api/setup-findmy truoc."}

            with open(AUTH_FILE) as f:
                auth_data = json.load(f)

            if auth_data.get("state") != "REQUIRE_2FA":
                return {"error": "Khong o trang thai cho 2FA"}

            anisette = RemoteAnisetteProvider(ANISETTE_URL)
            acc = findmy.AppleAccount(anisette)
            acc.restore(auth_data["account_data"])

            # Nhap ma 2FA
            state = acc.resolve_challenge(code.strip())

            if state == findmy.LoginState.LOGGED_IN:
                auth_data["state"] = "LOGGED_IN"
                auth_data["account_data"] = acc.export()
                with open(AUTH_FILE, "w") as f:
                    json.dump(auth_data, f)
                self._is_setup = True
                return {"status": "ok", "message": "Xac thuc 2FA thanh cong! He thong san sang."}
            else:
                return {"error": f"Ma 2FA sai hoac het han. State: {state}"}

        except Exception as e:
            return {"error": str(e)}

    # ─────────────────────────────────────────
    # DOC VI TRI TU FIND MY
    # ─────────────────────────────────────────
    def _load_account(self):
        """Tai Apple account tu file."""
        if not HAS_FINDMY:
            return None
        try:
            with open(AUTH_FILE) as f:
                auth_data = json.load(f)
            if auth_data.get("state") != "LOGGED_IN":
                return None
            anisette = RemoteAnisetteProvider(ANISETTE_URL)
            acc = findmy.AppleAccount(anisette)
            acc.restore(auth_data["account_data"])
            return acc
        except Exception as e:
            print("[FindMy] Loi tai account:", e)
            return None

    def _load_key_pair(self):
        """Tai private key tu file."""
        if not HAS_FINDMY or not HAS_CRYPTO:
            return None
        try:
            with open(KEY_FILE) as f:
                key_data = json.load(f)
            pem = key_data["private_key_pem"].encode()
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            private_key = load_pem_private_key(pem, password=None)
            # Tao KeyPair cho findmy.py
            kp = KeyPair.from_private_key(private_key)
            return kp
        except Exception as e:
            print("[FindMy] Loi tai key pair:", e)
            return None

    def fetch_location_once(self):
        """Doc vi tri hien tai tu Find My (1 lan).
        
        Tra ve: {'lat': float, 'lon': float, 'accuracy': float, 'timestamp': float}
        hoac None neu loi.
        """
        if not self._is_setup:
            print("[FindMy] Chua setup.")
            return None

        if not HAS_FINDMY:
            # Fallback: tra ve vi tri GPS tu iPhone qua /api/update-gps (browser)
            print("[FindMy] Khong co findmy library, dung GPS browser thay the.")
            return None

        try:
            acc = self._load_account()
            if not acc:
                return None

            kp = self._load_key_pair()
            if not kp:
                return None

            # Fetch reports tu Apple server
            end_time = time.time()
            start_time = end_time - 86400  # 24 gio qua

            reports = acc.fetch_reports(kp, date_from=start_time, date_to=end_time)
            if not reports:
                print("[FindMy] Chua co bao cao vi tri nao.")
                return None

            # Lay bao cao moi nhat
            latest = max(reports, key=lambda r: r.timestamp)
            loc = latest.location

            self._last_lat = loc.latitude
            self._last_lon = loc.longitude
            self._last_seen = latest.timestamp

            print(f"[FindMy] Vi tri: ({loc.latitude:.5f}, {loc.longitude:.5f}) "
                  f"luc {time.strftime('%H:%M:%S', time.localtime(latest.timestamp))}")

            return {
                "lat": loc.latitude,
                "lon": loc.longitude,
                "accuracy": getattr(loc, 'accuracy', 10.0),
                "timestamp": latest.timestamp,
                "source": "findmy"
            }

        except Exception as e:
            print("[FindMy] Loi doc vi tri:", e)
            return None

    def start_background_polling(self):
        """Bat dau doc GPS tu Find My ngam (background thread)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        print(f"[FindMy] Bat dau polling GPS moi {self._poll_interval}s.")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        """Vong lap polling chay ngam."""
        while self._running:
            try:
                loc = self.fetch_location_once()
                if loc and self._callback:
                    self._callback(
                        loc["lat"], loc["lon"],
                        loc.get("accuracy", 10),
                        loc.get("timestamp", time.time())
                    )
            except Exception as e:
                print("[FindMy] Poll loop error:", e)
            time.sleep(self._poll_interval)

    @property
    def last_location(self):
        """Vi tri cuoi cung doc duoc."""
        if self._last_lat:
            return {
                "lat": self._last_lat,
                "lon": self._last_lon,
                "last_seen": self._last_seen,
                "source": "findmy"
            }
        return None

    @property
    def is_setup(self):
        return self._is_setup
