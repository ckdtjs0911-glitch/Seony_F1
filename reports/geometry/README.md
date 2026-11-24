# 피트레인 참고 지도

피트 경로는 실제 차량의 location에서 추정한 주행 궤적이 아니라 공개 지도 자료다.
정합은 원래 서킷 외곽선과 세션 좌표를 같은 거리 간격으로 표본화한 뒤 회전·이동·배율을 맞춘다.
원래 비율은 유지하며 오차가 외곽선 대각선의 1.5%를 넘으면 해당 참고선을 표시하지 않는다.
출력은 근사 위치이며 정확한 입출구 판정에 사용하지 않는다.

- Las Vegas pit: https://www.openstreetmap.org/way/1223479152
- Interlagos pit: https://www.openstreetmap.org/way/33779109
- 취득: 2026-11-25 (한국 시간), OpenStreetMap API 0.6 bbox 조회. 원본 way geometry와 태그를 보존했다.
- Pit geometry: © OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright
- 데이터 라이선스 전문: https://opendatacommons.org/licenses/odbl/1-0/
- Circuit outlines: https://github.com/bacinger/f1-circuits, MIT. 원본 라이선스는 CIRCUIT-LICENSE.txt.

지도 데이터는 OpenStreetMap 출처와 ODbL 조건을 유지한다. 정합된 피트 좌표도 같은 출처로
각 세션의 pit_reference에 저장하고, 보고서에서 출처와 근사 정합임을 표시한다.
