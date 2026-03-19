# door-clock-display

사무실 문 앞 디스플레이를 위한 파티클 기반 디지털 시계입니다.
시스템 폰트를 캔버스에 렌더링한 뒤 픽셀을 샘플링하여, 파티클이 시간 텍스트 형태로 자연스럽게 모입니다.
Additive blending으로 파티클이 겹치는 곳에서 자연스러운 글로우가 생깁니다.
배경에는 서로 연결선이 이어지는 인터랙티브 파티클 네트워크가 떠다니며,
드래그하면 파티클이 과감하게 밀려나고 글로우 궤적이 남습니다.

## 실행 방법

의존성 설치 없이 정적 파일 서버만 있으면 실행됩니다.

### 방법 1) Python

```bash
cd door-clock-display
python3 -m http.server 4173
```

브라우저에서 `http://localhost:4173` 접속

### 방법 2) Node (npx)

```bash
cd door-clock-display
npx serve -l 4173
```

브라우저에서 `http://localhost:4173` 접속

## 키보드 단축키

- `F`: 전체화면 토글

## 인터랙션

### 드래그 (터치 / 마우스)

- 화면을 드래그하면 배경 파티클과 시계 파티클이 밀려남
- 드래그 궤적을 따라 글로우 트레일이 남고, 시간이 지나면 자연 소멸
- 터치스크린에서는 손가락으로 쓸어넘기는 제스처 그대로 동작

### 탭 / 클릭

- 탭(클릭) 1회: 파티클이 흩어진 뒤 짧은 끌림 펄스
- 더블탭(더블클릭): 파티클이 흩어진 뒤 짧은 밀림 펄스
- 우클릭(데스크톱): 밀림 펄스 즉시 발생
- 모든 액션은 순간형이며, 곧바로 시계 형태로 재집결

## 커스터마이징

`config.json`에서 대부분 조정할 수 있습니다.

### 시간

- `time.use24Hour`: 24시간제 여부

### 색상

- `palette.background`: 배경색
- `palette.core`: 숫자 파티클 색상
- `palette.ambient`: 배경 파티클 색상

### 레이아웃

- `layout.textWidthRatio`: 텍스트 영역 폭 비율 (0~1)
- `layout.textHeightRatio`: 텍스트 영역 높이 비율 (0~1)
- `layout.fontFamily`: 렌더링에 사용할 폰트
- `layout.fontWeight`: 폰트 두께

### 모션

- `motion.particleCount`: 전체 파티클 수 (권장 600~1200)
- `motion.ambientRatio`: 배경 파티클 비율 (0~1)
- `motion.approach`: 목표 수렴 속도 (0.05~0.3, 높을수록 빠름)
- `motion.scatterDecay`: 흩어짐 속도 감쇠 (0~1, 낮을수록 빨리 멈춤)
- `motion.jitter`: 정착 후 미세 흔들림 강도
- `motion.wanderSpeed`: 배경 파티클 떠다니는 속도

### 렌더링

- `render.sizeMin` / `render.sizeMax`: 파티클 크기 범위
- `render.coreScale`: 숫자 파티클 렌더 배율
- `render.coreAlpha`: 숫자 파티클 밝기
- `render.glowScale`: 글로우 반경 배율
- `render.glowAlpha`: 글로우 밝기
- `render.ambientScale`: 배경 파티클 크기 배율
- `render.ambientAlpha`: 배경 파티클 밝기
- `render.dprCap`: 픽셀 비율 상한 (저사양 권장 1)
- `render.fps`: FPS 상한 (저사양 권장 24~30)

### 배경 파티클

- `background.count`: 배경 파티클 수 (권장 150~300)
- `background.sizeMin` / `background.sizeMax`: 배경 파티클 크기 범위
- `background.speed`: 떠다니는 속도
- `background.alpha`: 파티클 밝기
- `background.glowAlpha` / `background.glowScale`: 글로우 강도와 크기
- `background.linkDist`: 연결선이 그려지는 최대 거리
- `background.linkAlpha`: 연결선 밝기
- `background.linkWidth`: 연결선 두께

### 드래그

- `drag.force`: 드래그 시 파티클 밀어내는 힘
- `drag.radius`: 드래그 영향 반경
- `drag.clockForceRatio`: 시계 파티클에 대한 힘 비율 (0~1)
- `drag.trailFadeMs`: 궤적 소멸 시간 (ms)
- `drag.trailWidth`: 궤적 선 두께
- `drag.trailGlow`: 궤적 글로우 크기
- `drag.trailColor`: 궤적 색상

### 탭/클릭 인터랙션

- `interaction.radius`: 클릭 영향 반경
- `interaction.burstForce`: 클릭 시 흩어짐 강도
- `interaction.pulseDuration`: 클릭 효과 지속 시간 (ms)
- `interaction.pulseForce`: 끌림/밀림 강도
- `interaction.dblClickWindow`: 더블클릭 판정 시간 (ms)

## 장시간 디스플레이 운영 팁

- 렉이 있으면 `particleCount`와 `background.count`를 먼저 낮추세요 (`900 → 600`, `220 → 120`)
- `fps`를 `24`로 낮추면 발열/전력 사용이 크게 줄어듭니다
- 브라우저 자동 절전/화면 끄기 설정을 비활성화해야 안정적으로 상시 노출됩니다
- 가능하면 크롬 계열 브라우저를 전체화면(F11) + 앱 모드로 고정해 사용하세요
