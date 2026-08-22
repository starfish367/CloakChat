# CloakChat

CloakChat là ứng dụng chat P2P ẩn danh hai người qua mạng Tor. Phiên bản hiện tại là CLI, sử dụng một file Python duy nhất và ưu tiên khả năng chạy trên **PC Linux** तथा **Android thông qua Termux**. Mã hóa đầu-cuối dùng X25519, HKDF-SHA256 và AES-256-GCM; địa chỉ Host là ephemeral onion service nên không được lưu cố định sau khi thoát.

> **Tình trạng nền tảng:** `CloakChat.py` là bản CLI cho Linux/Android Termux. `cloakchat_gui.py` là bản giao diện cửa sổ Kivy cho Windows, Linux và Android. Chế độ LAN E2EE hoạt động trên cả ba nền tảng; APK Android hiện ưu tiên LAN vì Tor trong APK cần tích hợp binary/service Android riêng.

## Tính năng chính

File `cloakchat_gui.py` cung cấp giao diện cửa sổ dùng chung cho Windows, Linux và Android. Core mạng/mật mã vẫn nằm trong `CloakChat.py`, vì vậy GUI và CLI dùng chung X25519, Safety Number và AES-256-GCM. GUI có nút tạo QR invite, chia sẻ invite qua Android Sharesheet/Bluetooth và danh bạ cục bộ.

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
| QR invite | Payload có version/checksum; không chứa private key hoặc session key |
| Bluetooth | Android Sharesheet cho phép chọn Bluetooth để gửi invite; desktop có fallback QR |
| Danh bạ | Lưu cục bộ tên + invite trong app data, không đồng bộ máy chủ |
| Vanity onion | Wrapper `tools/vanity_onion.py` gọi `mkp224o` để tạo prefix dễ nhớ |
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

### QR, Bluetooth và danh bạ

Sau khi Host có địa chỉ, nút `QR` tạo ảnh QR chứa invite có checksum. Invite chỉ chứa transport và địa chỉ kết nối, không chứa private key hoặc session key. Trên Android, nút `Bluetooth` mở Android Sharesheet; người dùng có thể chọn Bluetooth để chuyển invite. Trên desktop, hãy dùng QR hoặc sao chép invite.

Nút `Danh bạ` lưu tên và invite trong thư mục dữ liệu cục bộ của ứng dụng. Danh bạ không được đồng bộ lên máy chủ. Khi nạp một invite từ danh bạ, GUI tự chọn lại transport LAN/Tor.

### Vanity onion

Vanity onion không rút ngắn địa chỉ v3; nó chỉ tạo prefix dễ nhớ. Cài `mkp224o` từ nguồn đáng tin cậy rồi chạy:

```bash
python3 tools/vanity_onion.py cloakchat -o ~/cloakchat-vanity
```

Private key được tạo trong thư mục output và phải được bảo vệ. Prefix càng dài càng tốn thời gian/tài nguyên, đồng thời không thay thế Safety Number.

## Kiểm tra cục bộ

```bash
python -m py_compile CloakChat.py
python -m unittest discover -s tests -v
```

## Giao diện cửa sổ trên Linux/Windows

Cài dependency GUI và chạy:

```bash
python3 -m pip install -r requirements-gui.txt
python3 cloakchat_gui.py
```

Trên Linux/Armbian, build executable bằng:

```bash
bash linux/build-gui.sh
./dist/CloakChatGUI
```

Tor cần được cài hệ thống nếu chọn `Tor / Onion`:

```bash
sudo apt install tor
```

Trên Windows, đặt `tor.exe` tại `tor_bin/tor.exe`, sau đó chạy PowerShell:

```powershell
py -m pip install -r requirements-gui.txt
py -m PyInstaller --clean --noconfirm CloakChatGUI.spec
```

File tạo ra là `dist/CloakChatGUI.exe`. PyInstaller phải chạy trên đúng hệ điều hành và kiến trúc đích.

## Giao diện Android bằng Buildozer

Build APK trên máy Linux:

```bash
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev cmake
bash android/build-apk.sh
```

APK debug sẽ nằm trong `bin/`. Trên Android, chọn `LAN trực tiếp` để chat E2EE không cần Tor. Tor trong APK cần tích hợp Orbot hoặc binary Tor Android riêng; không dùng binary Tor Linux/Windows trong APK.

## Build tự động bằng GitHub Actions

Workflow `.github/workflows/build.yml` được chạy khi push vào `main`, khi push tag dạng `v*`, hoặc khi bấm **Run workflow** trong tab **Actions**. Workflow tạo ba artifact: `CloakChat-linux-x86_64`, `CloakChat-windows-x64` và `CloakChat-android-debug`. Khi chạy từ tag phiên bản, job cuối sẽ gom các artifact và tạo GitHub Release tự động.

Để chạy build thủ công, vào repository trên GitHub, mở **Actions → Build CloakChat → Run workflow**. Để tạo Release mới sau khi workflow đã được thêm:

```bash
git tag -a v1.2.0 -m "CloakChat v1.2.0"
git push origin v1.2.0
```

Binary Linux do runner GitHub tạo là `x86_64`. Armbian ARM cần build riêng trên chính Armbian hoặc dùng runner ARM tương ứng; không đổi tên binary x86_64 thành ARM được.

## Đóng gói CLI Windows bằng PyInstaller

Đặt `tor.exe` tại `tor_bin/tor.exe`, sau đó:

```powershell
pyinstaller --onefile --console --add-binary "tor_bin/tor.exe;tor_bin" CloakChat.py
```

## Mô hình tin cậy và giới hạn

Safety Number chỉ có tác dụng chống MitM khi được đối chiếu qua kênh ngoài băng có tính xác thực. Tor ẩn tuyến mạng nhưng không thay thế xác thực danh tính. Ứng dụng không lưu lịch sử chat, tuy nhiên hệ điều hành, terminal, crash dump hoặc công cụ bên ngoài vẫn có thể tạo dữ liệu riêng.

Đây là phần mềm liên lạc bảo mật cần được kiểm thử và audit độc lập trước khi dùng cho dữ liệu nhạy cảm cao. Chế độ LAN không ẩn địa chỉ IP khỏi mạng nội bộ; nó chỉ tắt Tor, còn E2EE vẫn hoạt động. Không chạy `tor.exe` hoặc binary Tor không rõ nguồn gốc.

## Giấy phép

Xem [LICENSE](LICENSE).
