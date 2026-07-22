---
name: Future-proof communication stack selection
description: When choosing comm/network/middleware stacks, factor in hardware upgrade path, not just today's cheapest option
type: feedback
---

통신 스택·미들웨어를 추천할 때는 현재의 비용 제약만 보지 말고 **하드웨어 업그레이드 시나리오(예: ESP32 → Pi4/Jetson)** 에서 비파괴적으로 전환 가능한지 확인한 뒤 추천할 것.

**Why:** AIP 프로젝트에서 현재 예산상 ESP32-S3 Scout를 쓰지만 이후 동급/고성능 차량 제작 가능성이 있음. 사용자가 이 확장성을 명시적으로 요구함(2026-04-20 대화).
**How to apply:** 통신/미들웨어/메시지 포맷 결정 시 (1) 상위 추상(ROS2 토픽·서비스·TF) 유지 가능성, (2) RMW/브릿지만 교체하는 식의 스왑 가능성, (3) 네임스페이스·QoS·보안 레이어(SROS2 등) 수용 가능성을 같이 설명. 지금 가장 싸고 빠른 옵션만 내지 말 것.
