# Orbot integration notes

Nguồn chính thức:

1. Orbot product page: https://orbot.app/
2. Guardian Project Orbot page: https://guardianproject.info/et/apps/org.torproject.android/
3. NetCipher OrbotHelper API: https://guardianproject.github.io/NetCipher/libnetcipher/index.html?info/guardianproject/netcipher/proxy/OrbotHelper.html

Orbot trên Android là ứng dụng proxy/VPN Tor; ứng dụng khác có thể dùng Tor nếu có cơ chế proxy. Guardian Project ghi nhận cổng SOCKS mặc định thường là 9050, nhưng người dùng có thể đổi sang 9051 hoặc AUTO, vì vậy CloakChat cần cho phép cấu hình cổng thay vì hardcode duy nhất.

Orbot có thể cho phép ứng dụng truy cập onion service và trang Orbot hiện tại cũng mô tả khả năng host onion service. Tuy nhiên, CloakChat tích hợp an toàn nhất ở tầng SOCKS5 cho Join; Host onion qua Orbot cần một API/control mechanism cụ thể và không nên tự giả định ControlPort có thể truy cập từ ứng dụng. Bản triển khai sẽ thêm transport Orbot SOCKS5 cho Join, kiểm tra proxy trước khi kết nối, không khởi động tor daemon nội bộ trên Android; Host Tor hiện tại vẫn giữ đường riêng và sẽ báo rõ nếu không có daemon/control support.
