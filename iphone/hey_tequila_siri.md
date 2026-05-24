# 🎙️ Hướng Dẫn Kích Hoạt Siri "Hey Tequila" & Cấu Hình WYN Chạy Nền

Tài liệu này hướng dẫn bạn thiết lập **2 tính năng rảnh tay cao cấp nhất** cho chiếc **iPhone 14 Pro** để tối ưu hóa trải nghiệm lái xe máy với **Tequila Navigator**:
1. Ra lệnh tìm đường bằng giọng nói tiếng Việt chuẩn Siri qua câu lệnh: **"Hey Siri, Hey Tequila"** (hoặc gõ mặt lưng điện thoại).
2. Tích hợp chạy đè (Overlay Mode) ứng dụng cảnh báo giao thông **WYN** song song với bản đồ HUD.

---

## 1. Hướng Dẫn Cấu Hình Siri Shortcut "Hey Tequila"

Bằng cách tạo một Shortcut trên iOS, bạn có thể tận dụng bộ nhận diện giọng nói AI và chống ồn cao cấp của iPhone 14 Pro để nhập điểm đến bằng giọng nói hoàn toàn rảnh tay khi đang đi trên đường.

### Các bước thiết lập trên iPhone 14 Pro:
1. Mở ứng dụng **Phím Tắt (Shortcuts)** có sẵn trên iPhone của bạn.
2. Nhấn nút **`+`** ở góc trên cùng bên phải để tạo Phím Tắt mới.
3. Đổi tên phím tắt (nhấp vào tên ở trên cùng) thành: **`Hey Tequila`** (hoặc `Hey Tequila Dẫn Đường`).
4. Thêm các Action (Tác vụ) theo đúng thứ tự sau:

#### 🔹 Tác vụ 1: Phát câu hỏi bằng giọng nói Siri
* Tìm kiếm từ khóa: **Speak Text (Đọc văn bản)**.
* Nhấp vào Text và nhập: `"Bạn muốn đi đâu?"`.
* Nhấn nút mũi tên xanh bên cạnh tác vụ, chọn:
  * **Language (Ngôn ngữ)**: `Vietnamese (Vietnam)`
  * **Voice (Giọng nói)**: `Linh` hoặc `Siri` (chọn giọng bạn thích nhất).

#### 🔹 Tác vụ 2: Ghi âm giọng nói địa điểm của bạn
* Tìm kiếm từ khóa: **Dictate Text (Đọc chính tả văn bản)**.
* Thiết lập cấu hình:
  * **Language**: `Vietnamese (Vietnam)`
  * **Stop listening (Dừng nghe)**: `After pause (Sau khi tạm dừng)` (để Siri tự nhận biết khi bạn nói xong).

#### 🔹 Tác vụ 3: Đẩy điểm đến sang Web Server Python của xe máy
* Tìm kiếm từ khóa: **Get Contents of URL (Lấy nội dung của URL)**.
* Nhập địa chỉ URL của Pythonista Web Server chạy trên iPhone:
  * `http://localhost:8080/api/navigate`
* Nhấp vào **Method (Phương thức)**, đổi từ `GET` thành **`POST`**.
* Nhấp vào **Request Body (Thân yêu cầu)**, chọn **`JSON`**.
* Nhấn **Add new field (Thêm trường mới)**:
  * Chọn kiểu: **`Text`**
  * Key: **`destination`**
  * Value: Nhấp chọn biến **`Dictated Text`** (kết quả ghi âm ở Tác vụ 2).
* Nhấn **Thêm trường mới** lần 2:
  * Chọn kiểu: **`Text`**
  * Key: **`esp32_ip`**
  * Value: `172.20.10.2` (hoặc IP thực tế hiển thị trên ESP32 của bạn).

#### 🔹 Tác vụ 4: Phản hồi hoàn thành
* Tìm kiếm từ khóa: **Speak Text (Đọc văn bản)**.
* Nhập: `"Đang tìm đường đi tối ưu tốt nhất. Bản đồ hành trình đã hiển thị trên mặt xe!"`

---

## 2. Cách Sử Dụng Lệnh Giọng Nói Khi Lái Xe 🏍️

Sau khi cấu hình xong, bạn có thể ra lệnh bằng giọng nói theo 2 cách cực kỳ rảnh tay:

### Cách 1: Sử dụng giọng nói trực tiếp qua micro mũ bảo hiểm
1. Nói to: **"Hey Siri, Hey Tequila!"**
2. Siri trên iPhone 14 Pro sẽ tự động kích hoạt và hỏi: *"Bạn muốn đi đâu?"*
3. Bạn trả lời địa điểm: *"Nhà thờ Đức Bà"* hoặc *"Điểm dừng số 2 Vũng Tàu"*.
4. AI trên iPhone tự động tìm tuyến đường tối ưu nhất, đẩy hình vẽ lên màn hình ESP32 và bắt đầu đọc dẫn đường Turn-by-Turn vào tai nghe Bluetooth của bạn!

### Cách 2: Kích hoạt nhanh bằng cách gõ mặt lưng iPhone (Back Tap)
Nếu bạn không muốn nói "Hey Siri" giữa đường phố ồn ào:
1. Vào **Cài đặt (Settings) → Trợ năng (Accessibility) → Cảm ứng (Touch)**.
2. Cuộn xuống dưới cùng chọn **Chạm vào mặt sau (Back Tap)**.
3. Chọn **Chạm hai lần (Double Tap)** hoặc **Chạm ba lần (Triple Tap)**.
4. Cuộn xuống mục Phím tắt và chọn phím tắt: **`Hey Tequila`**.
* Bây giờ, bạn chỉ cần gõ nhẹ 2 cái vào lưng iPhone 14 Pro, Siri sẽ lập tức hỏi điểm đến!

---

## 3. Thiết Lập Ứng Dụng WYN Ở Chế Độ Chạy Đè (Overlay Mode)

Ứng dụng **WYN - Cảnh báo giao thông** (miễn phí trên App Store) có cơ sở dữ liệu cực kỳ khổng lồ với 6.000+ camera phạt nguội và 12.000+ biển báo giao thông Việt Nam. Chúng ta sẽ cấu hình để WYN chạy đè lên tất cả ứng dụng khác để tạo lớp **bảo vệ kép** song song với Tequila Navigator.

### Các bước thiết lập WYN Overlay trên iPhone 14 Pro:
1. Tải ứng dụng **WYN - Cảnh báo giao thông** từ App Store.
2. Mở ứng dụng WYN, nhấn vào biểu tượng **Cài đặt (⚙️)**.
3. Tìm mục **Chế độ chạy đè (Overlay / Chạy trên ứng dụng khác)** và kích hoạt **Bật**.
4. Cấp quyền **"Cho phép hiển thị trên các ứng dụng khác"** khi iOS hiển thị hộp thoại yêu cầu.
5. Trong mục cấu hình âm thanh của WYN:
   * Chọn đầu ra âm thanh là **Bluetooth Headset / HFP** để tiếng còi cảnh báo và giọng đọc biển báo của WYN luôn được ưu tiên phát thẳng vào tai nghe trong mũ bảo hiểm của bạn.

### Trải nghiệm thực tế khi di chuyển:
* Khi bạn khởi động xe, ESP32 sẽ hiển thị bản đồ dẫn đường HUD và đọc hướng nhắc rẽ, nhắc nhở bật xi-nhan.
* iPhone của bạn có thể khóa màn hình đút túi quần hoặc gắn trên giá đỡ. 
* Khi đi qua đoạn đường có camera phạt nguội hoặc biển báo tốc độ, **cả hai nguồn sẽ bảo vệ bạn**:
  1. Màn hình **ESP32** sẽ chớp nháy màu đỏ hiển thị hình ảnh camera tốc độ kèm khoảng cách mét giảm dần.
  2. Loa **WYN** chạy nền trên iPhone tự động phát âm thanh cảnh báo trực tiếp vào mũ bảo hiểm của bạn!
* **An toàn tuyệt đối, 100% rảnh tay, không bao giờ lo phạt nguội!**
