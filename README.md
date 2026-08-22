# CloakChat

CloakChat là ứng dụng chat P2P ẩn danh hai người qua mạng Tor. Phiên bản hiện tại là CLI, sử dụng một file Python duy nhất và ưu tiên khả năng chạy trên **PC Linux** तथा **Android thông qua Termux**. Mã hóa đầu-cuối dùng X25519, HKDF-SHA256 và AES-256-GCM; địa chỉ Host là ephemeral onion service nên không được lưu cố định sau khi thoát.

> **Tình trạng nền tảng:** Linux chạy trực tiếp bằng Python. Android chạy bằng Termux với Python và Tor được cài trong môi trường Termux. Đây chưa phải APK native có giao diện Android riêng; mục tiêu của bản đầu tiên là cung cấp một client CLI có thể chạy thật trên Android và PC Linux.

## Tính năng chính

| Thành phần | Triển khai |
|---|---|
| Tor transport | Tor daemon tạm thời, SOCKS5 `127.0.0.1:9050`, ControlPort `127.0.0.1:9051`, CookieAuthentication |
| Host qua Tor | Tạo ephemeral onion service v3 và lắng nghe TCP localhost |
| Join qua Tor | Kết nối `.onion` qua SOCKS5 với DNS remote (`rdns=True`) |
| Host LAN | Lắng nghe IP nội bộ trực tiếp, không khởi động Tor |
| Join LAN | Kết nối `IP:cổng` trực tiếp, không dùng SOCKS5/Tor |
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

Cài Termux từ nguồn đáng tin cậy, mở Termux và clone repository. **Không dùng `sudo`, `apt` của Ubuntu hoặc `pip install --upgrade pip` trong Termux.** Termux dùng `pkg` để quản lý Python và các thư viện native.

```bash
pkg update -y
pkg upgrade -y
pkg install -y git

git clone https://github.com/starfish367/CloakChat.git ~/CloakChat
cd ~/CloakChat
bash android/install-termux.sh
python CloakChat.py
```

Script `android/install-termux.sh` sẽ cài `python`, `tor` và `python-cryptography` bằng `pkg`, sau đó chỉ cài `stem` và `PySocks` bằng pip. Cách này tránh lỗi `Rust not found`, lỗi build `maturin` và lỗi `Installing pip is forbidden` của Termux.

Nếu muốn chạy từng bước thủ công:

```bash
pkg install -y python tor python-cryptography
python -m pip install -r requirements-termux.txt
python CloakChat.py
```

Nếu Termux không tìm thấy Tor, kiểm tra:

```bash
which tor
CLOAKCHAT_TOR_EXECUTABLE="$(which tor)" python CloakChat.py
```

Nếu bạn đã chạy sai các lệnh trước đó và thấy `.venv/bin/activate` không tồn tại, không cần tạo virtual environment trong Termux; chỉ cần cài lại bằng script ở trên. Android có thể hạn chế tiến trình nền, vì vậy nên giữ Termux ở trạng thái hoạt động trong suốt phiên chat và cấp quyền mạng khi hệ điều hành yêu cầu.

## Cách sử dụng

Menu có hai nhóm kết nối. Lựa chọn `1` và `2` dùng Tor cho Host/Join `.onion`. Lựa chọn `3` là `Host LAN`, lựa chọn `4` là `Join LAN`; hai lựa chọn LAN **không khởi động Tor và không dùng SOCKS5**.

### Chế độ Tor

Chọn `Host` để tạo địa chỉ `.onion`, sau đó gửi địa chỉ này cho người còn lại qua một kênh phù hợp. Sau dòng `[+] Tor daemon đã sẵn sàng.`, chương trình sẽ hiện `[ * ] Tor đã chạy...` và chờ tối đa 180 giây để Tor bootstrap rồi công bố onion service. Đây là trạng thái bình thường; chỉ khi xuất hiện lỗi timeout hoặc thông báo Bootstrap thất bại thì phiên mới có vấn đề. Người kia chọn `Join` và nhập địa chỉ `.onion` sau khi địa chỉ được hiển thị.

### Chế độ LAN trực tiếp

Trên máy Host, chọn `3`. Chương trình sẽ hiện địa chỉ dạng `IP:cổng`, ví dụ `192.168.1.20:45678`. Gửi địa chỉ này cho peer, rồi trên máy peer chọn `4` và nhập đúng `IP:cổng`. Hai thiết bị phải cùng mạng nội bộ hoặc có đường định tuyến tới nhau; nếu Linux có firewall, cần cho phép cổng TCP được in trên màn hình.

Chế độ LAN chỉ thay đổi **lớp truyền tải**. Sau khi socket kết nối, cả hai phía vẫn chạy X25519, HKDF-SHA256, AES-256-GCM, framing TCP và Safety Number như chế độ Tor. Hai người vẫn phải đối chiếu Safety Number qua một kênh tin cậy bên ngoài.

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

Đây là phần mềm liên lạc bảo mật cần được kiểm thử và audit độc lập trước khi dùng cho dữ liệu nhạy cảm cao. Chế độ LAN không ẩn địa chỉ IP khỏi mạng nội bộ; nó chỉ tắt Tor, còn E2EE vẫn hoạt động. Không chạy `tor.exe` hoặc binary Tor không rõ nguồn gốc.

## Giấy phép

Xem [LICENSE](LICENSE).
