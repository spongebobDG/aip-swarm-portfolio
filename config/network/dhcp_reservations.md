# AIP Fleet Network — DHCP Reservations

Wi-Fi AP: **SSID `AIP_FLEET`**, WPA2-PSK, dual-band (2.4 GHz must be enabled — ESP32-S3 is 2.4 GHz only).
Subnet: **192.168.0.0/24**. Gateway: 192.168.0.1.
DHCP 풀: 192.168.0.100~200 (고정 장치는 .2~.99 범위의 static IP 사용).

| IP | Hostname | MAC | Device | Notes |
|---|---|---|---|---|
| 192.168.0.1 | `gw` | — | Wi-Fi router (IPTime AX3000Q) | DHCP server + DNS forwarder |
| 192.168.0.9 | `central` | TBD | Central PC (Ubuntu 22.04) | FastDDS DS + µROS Agent + Foxglove Bridge |
| 192.168.0.3 | `main_agv` | d8:3a:dd:f0:00:1b | Main AGV (RPi4B) | ROS2 Humble, wlan0 고정 IP |
| 192.168.0.11 | `aip2` | TBD | Scout-1 (RPi4B, TB3 Burger) | ROS2 Humble |
| 192.168.0.12 | `aip3` | TBD | Scout-2 (RPi4B, 자작 차량) | ROS2 Humble |
| 192.168.0.20 | `op_laptop_1` | TBD | Operator laptop | Foxglove Studio client |

## /etc/hosts common block (Linux nodes)

```
192.168.0.9    central
192.168.0.3   main_agv
192.168.0.11   aip2
192.168.0.12   aip3
```

## Router firewall (recommended)

- DHCP 풀을 192.168.0.100~200으로 제한해 .2~.99는 DHCP 자동 할당 불가.
- Allow inbound `udp/8888` (µROS Agent) and `tcp/8765` (Foxglove Bridge) only from the AIP subnet.
- Allow `udp/11811` (FastDDS DS) within the subnet.
