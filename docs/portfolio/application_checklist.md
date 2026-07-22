# Application Checklist

> 목적: GitHub 제출 전과 면접 전 확인할 항목을 정리한다.

## GitHub 제출 전

- [ ] 현재 브랜치가 `codex/robot-sw-portfolio`인지 확인한다.
- [ ] README 첫 화면에서 프로젝트 목적, 데모, 내 역할, 한계가 보이는지 확인한다.
- [ ] 이미지/GIF/PDF 링크가 열리는지 확인한다.
- [ ] `docker/central/.env`, `firmware/scout/secrets.ini`, `firmware/scout_microros/secrets.ini`가 stage 되지 않는지 확인한다.
- [ ] `tmp/`, PDF 렌더링 PNG, demo frame 원본이 stage 되지 않는지 확인한다.
- [ ] 내부 IP, 비밀번호, 팀원 개인정보, 학교 내부 장비명이 공개 문서에 남아 있지 않은지 확인한다.
- [ ] "완전 자율주행", "상용 FMS", "군집 주행 완료" 같은 표현이 없는지 확인한다.

## 지원서 작성 전

- [ ] 본인이 실제로 맡은 일 5줄을 확정한다.
- [ ] 팀원이 맡은 일과 팀 전체 구현을 분리한다.
- [ ] 시연에서 실제 성공한 기능 목록을 확정한다.
- [ ] 실패하거나 불안정했던 기능 3개와 배운 점을 정리한다.
- [ ] GitHub README, 포트폴리오 PDF, 이력서의 표현이 서로 모순되지 않는지 확인한다.

## 면접 전 암기

- [ ] 30초 프로젝트 소개
- [ ] 1분 자기소개
- [ ] 3분 프로젝트 설명
- [ ] ROS2 Node/Topic/Service/Action 차이
- [ ] Nav2 planner/controller/localization 역할
- [ ] WebSocket을 쓴 이유
- [ ] E-Stop 명령 흐름
- [ ] Vision Pi/RGB/thermal 데이터 흐름
- [ ] 확인 필요 항목을 솔직하게 말하는 문장

## 면접에서 피할 말

- "제가 전체 로봇을 혼자 다 만들었습니다."
- "실차 군집 자율주행을 완성했습니다."
- "YOLO 화재 탐지가 검증됐습니다."
- "상용 수준 관제 시스템입니다."
- "AI가 만들어줘서 자세히는 모릅니다."

## 면접에서 좋은 마무리

이 프로젝트를 통해 ROS2 시스템에서는 기능 구현만큼 Topic 계약, namespace, 상태/제어 흐름, 검증 로그가 중요하다는 점을 배웠습니다. 아직 부족한 부분은 실차 end-to-end 검증과 성능 측정이지만, 확인된 것과 확인이 필요한 것을 분리해 개선해 나가겠습니다.
