# 기여 가이드 — AIP Swarm Workspace

## 기본 규칙

**`main` 브랜치에 직접 push 하지 않는다.**
모든 변경은 feature 브랜치 → Pull Request → 리뷰 → Merge 순서로 진행한다.

---

## 브랜치 전략

```
main
 └─ feature/<이름>-<기능>    작업 브랜치 (개인)
 └─ fix/<이름>-<버그명>      버그 수정 브랜치
```

브랜치 이름 예시:
- `feature/kim-corner-patrol`
- `fix/lee-mppi-overshoot`
- `docs/park-setup-guide`

---

## 작업 절차

```bash
# 1. 최신 main 동기화
git checkout main
git pull origin main

# 2. 작업 브랜치 생성
git checkout -b feature/<이름>-<기능>

# 3. 작업 & 빌드 확인
aip_build   # 반드시 빌드 성공 확인 후 커밋

# 4. 커밋 (컨벤션 참고)
git add <변경파일>
git commit -m "feat: 기능 설명"

# 5. 원격 push
git push -u origin feature/<이름>-<기능>

# 6. GitHub에서 PR 생성 → Mark2AC 리뷰 요청
```

---

## 커밋 메시지 컨벤션

```
<type>: <한 줄 요약>

<상세 설명 (선택)>
```

| type | 사용 시점 |
|---|---|
| `feat` | 새 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변화 없는 코드 정리 |
| `config` | 파라미터·YAML·런치 파일 변경 |
| `docs` | 문서 수정 |
| `test` | 테스트 추가·수정 |

---

## PR 리뷰 기준

리뷰어(Mark2AC)가 Merge 전 확인하는 항목:

1. **빌드 성공** — CI (`colcon build`) 초록 확인
2. **장애물 충돌 없음** — 웨이포인트 변경 시 `inflation_radius=0.35m` 검증 스크립트 실행
3. **네임스페이스 규약** — 새 토픽은 `/<ns>/` 접두사 준수 (`main`, `scout_N`)
4. **시크릿 없음** — `secrets.ini`, `.env`, `keystore/` 포함 금지
5. **CLAUDE.md 규칙 준수** — 차량 자체 SW(`my_ros_env`) 수정 금지

---

## 환경 설정 (처음 클론 시)

```bash
git clone --recurse-submodules https://github.com/Mark2AC/aip-swarm-ws.git ~/aip_swarm_ws
bash ~/aip_swarm_ws/scripts/setup_ubuntu.sh
source ~/aip_swarm_ws/aip_env.sh
aip_build
```

자세한 내용: `docs/SETUP_UBUNTU.md`
