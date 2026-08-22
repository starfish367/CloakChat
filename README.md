# CloakChat

CloakChat là ứng dụng chat P2P ẩn danh hai người qua mạng Tor. Phiên bản hiện tại là CLI, sử dụng một file Python duy nhất và ưu tiên khả năng chạy trên **PC Linux** तथा **Android thông qua Termux**. Mã hóa đầu-cuối dùng X25519, HKDF-SHA256 và AES-256-GCM; địa chỉ Host là ephemeral onion service nên không được lưu cố định sau khi thoát.

> **Tình trạng nền tảng:** Linux chạy trực tiếp bằng Python. Android chạy bằng Termux với Python và Tor được cài trong môi trường Termux. Đây chưa phải APK native có giao diện Android riêng; mục tiêu của bản đầu tiên là cung cấp một client CLI có thể chạy thật trên Android và PC Linux.

## Tính năng chính

| Thành phần | Triển khai |
|---|---|
| Tor transport | Tor daemon tạm thời, SOCKS5 `127.0.0.1:9050`, ControlPort `127.0.0.1:9051`, CookieAuthentication |
| Host | Tạo ephemeral onion service v3 và lắng nghe TCP localhost |
| Join | Kết nối `.onion` qua SOCKS5 với DNS remote (`rdns=True`) |
| E2EE | X25519, HKDF-SHA256 với `cloakchat_v1`, AES-256-GCM nonce 12 byte |
| TCP protocol | Frame length 4 byte big-endian để chống dồn/trộn packet |
| MitM verification | Safety Number 30 chữ số, chia thành 6 nhóm 5 chữ số |
| Runtime | Main thread nhập liệu, receiver thread nhận và giải mã |
| Cleanup | `atexit`, SIGINT/SIGTERM, đóng socket, dừng Tor và xóa DataDirectory tạm |

## Cài đặt trên PC Linux

Cần Python 3.9 trở lên và một bản Tor đáng tin cậy từ kho phân phối. Trước hết clone repository rồi chuyển vào đúng thư mục dự án:

```bash
git clone https://github.com/starfish367/CloakChat.git
cd CloakChat
sudo apt update
sudo apt install -y tor python3 python3-venv python3-pip
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python CloakChat.py
```

Lỗi `Could not open requirements file` hoặc `can't open file CloakChat.py` xảy ra khi chạy các lệnh cài đặt từ thư mục home thay vì thư mục `CloakChat`. Nếu đã clone trước đó, chỉ cần chạy `cd ~/CloakChat` rồi tiếp tục từ bước tạo virtual environment.

CloakChat tự tìm `tor` trong `PATH`. Có thể chỉ rõ đường dẫn bằng biến môi trường:

```bash
CLOAKCHAT_TOR_EXECUTABLE=/usr/bin/tor python3 CloakChat.py
```

## Cài đặt trên Android bằng Termux

Cài Termux từ nguồn đáng tin cậy, mở Termux và chạy:

```bash
pkg update -y
pkg install -y python tor git
pip install -r requirements.txt
```

Clone repository và chạy:

```bash
git clone https://github.com/starfish367/CloakChat.git
cd CloakChat
bash android/install-termux.sh
python CloakChat.py
```

Nếu Termux không tìm thấy Tor, kiểm tra:

```bash
which tor
CLOAKCHAT_TOR_EXECUTABLE="$(which tor)" python CloakChat.py
```

Android có thể hạn chế tiến trình nền. Vì vậy nên giữ Termux ở trạng thái hoạt động trong suốt phiên chat và cấp quyền mạng khi hệ điều hành yêu cầu.

## Cách sử dụng

Chọn `Host` để tạo địa chỉ `.onion`, sau đó gửi địa chỉ này cho người còn lại qua một kênh phù hợp. Người kia chọn `Join` và nhập địa chỉ `.onion`.

Sau handshake, cả hai phía sẽ hiển thị cùng một **Safety Number**. Hai người phải đối chiếu số này qua một kênh tin cậy bên ngoài và chỉ nhập `y` khi số trùng khớp. Nếu một phía nhập khác `y`, kết nối sẽ bị từ chối.

Trong màn hình chat, nhập tin nhắn rồi nhấn Enter. Nhập `exit` để đóng phiên, dừng Tor và xóa dữ liệu tạm.

## Kiểm tra cục bộ

```bash
python -m py_compile CloakChat.py
python -m unittest discover -s tests -v
```

## Đóng gói Windows bằng PyInstaller

Đặt `tor.exe` tại `tor_bin/tor.exe`, sau đó:

```powershell
pyinstaller --onefile --console --add-binary "tor_bin/tor.exe;tor_bin" CloakChat.py
```

## Mô hình tin cậy và giới hạn

Safety Number chỉ có tác dụng chống MitM khi được đối chiếu qua kênh ngoài băng có tính xác thực. Tor ẩn tuyến mạng nhưng không thay thế xác thực danh tính. Ứng dụng không lưu lịch sử chat, tuy nhiên hệ điều hành, terminal, crash dump hoặc công cụ bên ngoài vẫn có thể tạo dữ liệu riêng.

Đây là phần mềm liên lạc bảo mật cần được kiểm thử và audit độc lập trước khi dùng cho dữ liệu nhạy cảm cao. Không chạy `tor.exe` hoặc binary Tor không rõ nguồn gốc.

## Giấy phép

Xem [LICENSE](LICENSE).
