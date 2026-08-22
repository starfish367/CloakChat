# Nghiên cứu tính năng QR, Bluetooth và vanity onion

## Kết luận thiết kế

Kivy có thể đóng gói ứng dụng thành APK Android và truy cập Android API qua Pyjnius; Bluetooth Android vì vậy nên được triển khai như một adapter tùy nền tảng, không giả định API desktop giống Android. [1]

Địa chỉ onion v3 có độ dài thực 56 ký tự. Vanity address chỉ chọn một prefix dễ nhớ, không rút ngắn địa chỉ. Tor Project cảnh báo vanity prefix có thể tạo cảm giác nhận diện giả và làm tăng chi phí tính toán khi prefix dài. [2]

QR nên chứa invite có phiên bản và checksum, gồm transport, địa chỉ, cổng và tên hiển thị; QR không chứa private key hoặc session key. Danh bạ nên lưu ở phía client, với dữ liệu tối thiểu và quyền file hạn chế.

Bluetooth nên bắt đầu bằng chức năng chuyển invite/QR payload giữa hai thiết bị. Chat E2EE trực tiếp qua Bluetooth là một transport mới và cần adapter riêng cho Android/Linux; không nên giả vờ rằng socket TCP LAN có thể dùng trực tiếp trên mọi nền tảng Bluetooth.

## Sources

[1] Kivy, “Kivy on Android”: https://kivy.org/doc/stable/guide/android.html

[2] Tor Project, “Vanity Addresses”: https://community.torproject.org/onion-services/advanced/vanity-addresses/
