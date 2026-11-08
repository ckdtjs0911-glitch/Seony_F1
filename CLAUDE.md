# Seony_F1 작업 규칙

## 내용 작성 워크플로: Claude Code(초안) → Codex(검토) → Claude Code(최종)

### 적용 범위

- **적용:** 대화 중 Claude Code가 직접 작성하거나 수정하는 경기·랩 분석, 보고서 문구,
  보고서 템플릿 문구(예: `tools/weekend_report.py`의 선수별 한 줄 평 생성 문장), 저장소 문서
  (`reports/AUTOMATION.md`, `README.md` 등).
- **제외:** 단순 오탈자 수정, 질문에 대한 짧은 답변, 검토 결과 전달, `tools/weekend_report.py`를
  그대로 실행해 자동 생성되는 보고서.

### 1. 초안 (Claude Code)

- 근거를 내용에 맞게 정한다.
  - 경기 분석: OpenF1 데이터(`reports/weekend-*/data/*.json` 또는 API 응답)
  - 개발·운영 문서: 관련 코드와 설정(`tools/`, `.github/workflows/` 등)
- 초안은 파일로 저장한다. 저장소에 남길 내용은 해당 위치에, 채팅 답변용은 스크래치 파일에 둔다.

### 2. 검토 (Codex)

Codex에는 검토만 맡긴다. `--write`를 주지 않고, 요청문에 "파일 수정 금지"를 명시한다.

```bash
COMPANION=$(find ~/.claude/plugins -path '*codex/scripts/codex-companion.mjs' | head -n 1)
```
```bash
node "$COMPANION" task "검토만 하고 파일은 수정하지 마. 초안: <초안 경로>. 근거: <데이터·코드 경로>. 수치·랩 번호·선수명·팀명이 근거와 일치하는지, 근거 없는 해석이나 원인 단정이 있는지, 구조·가독성·맞춤법을 확인해서 한국어로 번호 목록으로 알려줘."
```

코드 변경이 함께 있으면 아래 명령으로 코드 검토도 받는다.

```bash
node "$COMPANION" review --scope working-tree
```

### 3. 최종 (Claude Code)

- Codex 지적은 종류에 맞는 기준으로 하나씩 확인한 뒤 반영 여부를 정한다.
  - 수치·사실 지적 → 원본 데이터로 확인
  - 동작 설명 지적 → 코드·설정으로 확인
  - 문장·구조 지적 → 아래 "작성 기준"으로 판단
- 최종본과 함께 "Codex 지적 / 반영한 것 / 반영하지 않은 것과 이유"를 짧게 정리해 사용자에게 알린다.

Codex를 쓸 수 없으면(미설치, 미로그인 등) 사용자에게 알리고, 검토 단계를 건너뛰었다고 명시한다.

## 작성 기준

- 수치·선수명·팀명·출처는 데이터 그대로 쓴다. 데이터에 없는 원인(트래픽, 감속, 사고 등)은 단정하지 않는다.
- 타이어, 주행 시점, 연료처럼 조건이 다른 비교는 그 한계를 함께 적는다.
- 사용자에게 답할 때는 한국어로 쓴다.

## 참고

- 자동 보고서 생성: `tools/weekend_report.py`, `.github/workflows/weekend-report.yml` (`reports/AUTOMATION.md` 참고)
- GitHub Actions 보고서는 Python으로 자동 생성합니다. 자동 첨삭은 하지 않으며,
  인증이 설정되면 별도 작업에서 Claude CLI 일반 검토 후 rescue 문제 조사·수정안 작성을 실행합니다.
  반대 관점 검토는 실행하지 않습니다. 결과는 Actions artifact에 저장하고 보고서를 자동 수정하지 않습니다.
