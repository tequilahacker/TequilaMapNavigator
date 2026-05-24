# Sample navigation test route and camera locations inside District 1, Ho Chi Minh City
# GPS Route: Notre Dame Cathedral (Nhà Thờ Đức Bà) -> Zoo (Thảo Cầm Viên)

# Current positions containing (latitude, longitude, heading)
simulated_positions = [
    (10.779785, 106.699017, 45),   # Starting at Cathedral corner
    (10.780185, 106.699517, 45),   # Moving onto Lê Duẩn
    (10.780585, 106.700117, 45),   # Approaching Speed Camera
    (10.781050, 106.701100, 45),   # Right next to Speed Camera! (Warning should trigger)
    (10.781485, 106.701817, 90),   # Heading right on Lê Duẩn
    (10.781885, 106.702517, 90),
    (10.782585, 106.703217, 30),   # Turning towards Nguyễn Bỉnh Khiêm
    (10.783185, 106.703717, 30),   # Approaching Red Light Camera
    (10.784100, 106.704200, 30),   # Right next to Red Light Camera!
    (10.784585, 106.704617, 90),   # Turning into Zoo entrance
    (10.785085, 106.705117, 90)    # Arrived
]

# Static route polyline [latitude, longitude]
simulated_route = [
    (10.779785, 106.699017),
    (10.780185, 106.699517),
    (10.780585, 106.700117),
    (10.781050, 106.701100),
    (10.781485, 106.701817),
    (10.781885, 106.702517),
    (10.782585, 106.703217),
    (10.783185, 106.703717),
    (10.784100, 106.704200),
    (10.784585, 106.704617),
    (10.785085, 106.705117)
]

# Near camera database [latitude, longitude, camera_type]
simulated_cameras = [
    (10.781050, 106.701100, "speed"),      # Speed Camera on Lê Duẩn
    (10.784100, 106.704200, "red_light")    # Red Light Camera on Nguyễn Bỉnh Khiêm
]

# Text warnings corresponding to simulator steps
simulated_nav_data = [
    ("Đi thẳng vào Lê Duẩn", 30, 200),
    ("Đi thẳng vào Lê Duẩn", 32, 150),
    ("Cảnh báo bắn tốc độ!", 25, 80),
    ("Cảnh báo bắn tốc độ!", 20, 20),
    ("Rẽ trái vào Nguyễn Bỉnh Khiêm", 38, 250),
    ("Rẽ trái vào Nguyễn Bỉnh Khiêm", 40, 180),
    ("Chú ý camera vượt đèn đỏ!", 32, 100),
    ("Chú ý camera vượt đèn đỏ!", 28, 40),
    ("Chú ý camera vượt đèn đỏ!", 15, 10),
    ("Đến Thảo Cầm Viên", 10, 30),
    ("Đã đến điểm hẹn", 0, 0)
]
