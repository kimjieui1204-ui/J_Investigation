# jieui-fundamentals

한 달에 한 번 SEC 공시에서 재무 지표를 긁어 `fundamentals.json` 으로 저장합니다.
JIEUI OS 의 관심기업 스크리너가 이 파일을 읽습니다.

## 왜 GitHub 인가

Apps Script 에서 SEC 를 직접 부르면 이렇게 나옵니다.

```
403  SEC.gov | Request Rate Threshold Exceeded
```

인증 문제가 아닙니다. 구글이 전 세계 Apps Script 사용자에게 **같은 IP 를 나눠 주는데**,
SEC 의 초당 10회 제한이 그 IP 단위로 걸립니다. 우리가 첫 요청을 보내기도 전에 이미
한도가 차 있습니다. 연락처를 넣어도, 천천히 불러도 소용이 없습니다.

GitHub Actions 러너는 자기 IP 를 씁니다. 그래서 **긁는 일만** 여기로 옮기고,
결과 JSON 을 저장소에 올려둡니다. Apps Script 는 `raw.githubusercontent.com` 에서
그 파일 하나만 읽으면 됩니다. 거긴 막히지 않습니다.

## 설치

### 1. 저장소를 만듭니다

이름은 아무거나. **공개(Public)로 만드세요** — 비공개면 `raw.githubusercontent.com`
주소로 읽을 수 없습니다. 이 저장소에는 공개 재무 데이터만 들어가고 비밀은 없습니다.

올릴 파일 두 개:

```
sec_fundamentals.py
.github/workflows/sec-fundamentals.yml
```

### 2. 시크릿을 하나 넣습니다

저장소 → Settings → Secrets and variables → Actions → New repository secret

| 이름 | 값 |
|---|---|
| `SEC_CONTACT` | `JIEUI OS kimjieui1204@gmail.com` |

SEC 가 요구하는 연락처입니다. 비밀은 아니지만 저장소에 이메일이 그대로 남지 않게
시크릿으로 둡니다.

### 3. 한 번 손으로 돌립니다

Actions 탭 → "SEC 펀더멘털 수집" → Run workflow

5~15분 걸립니다. 끝나면 저장소 루트에 `fundamentals.json` 이 생깁니다.
로그 끝에 `저장 fundamentals.json · NNNN종목 · NNNKB` 가 보이면 성공입니다.

500종목 미만이면 워크플로가 일부러 실패합니다. 반쪽짜리 파일을 조용히 커밋하느니
실패하는 편이 낫습니다.

### 4. 주소를 Apps Script 에 넣습니다

`fundamentals.json` 을 GitHub 에서 열고 **Raw** 버튼을 누르면 이런 주소가 나옵니다.

```
https://raw.githubusercontent.com/<계정>/<저장소>/main/fundamentals.json
```

Apps Script → 프로젝트 설정 → 스크립트 속성

| 이름 | 값 |
|---|---|
| `FUND_JSON_URL` | 위 주소 |

### 5. `screenerRefreshFundamentals()` 를 돌립니다

이제 SEC 를 부르지 않고 이 JSON 만 읽습니다. **몇 초면 끝납니다.**
로그에 `GitHub JSON 에서 읽음 · 생성 … · 내 명부 NN/NN건 정상` 이 나오면 됩니다.

그다음 `screenerScore()` → 끝.

## 이후

매월 3일 새벽 5시(한국 시간)에 자동으로 돌고, 값이 바뀌면 커밋됩니다.
Apps Script 쪽은 아무것도 안 해도 됩니다 — 다음 갱신 때 새 파일을 읽습니다.

워크플로가 실패하면 GitHub 이 메일을 보냅니다. Gmail 분류 규칙이 그 메일을
`40_System/운영` 으로 보내고 별표를 답니다.

## 파일 형식

```json
{
  "generated": "2026-08-19 20:04:11 UTC",
  "years": [2025, 2024, 2023, 2022],
  "count": 4183,
  "data": {
    "AAPL": {
      "roe": 1.52, "fcf": 108800000000, "fcfPos": 3,
      "fcfm": 0.27, "epsCagr": 0.09, "revCagr": 0.05,
      "debt": 4.12, "epsVol": 0.08,
      "years": "2022·2023·2024", "reason": ""
    }
  }
}
```

- 키는 SEC 표기 티커입니다. 점이 아니라 하이픈입니다 (`BRK-B`).
- 못 구한 값은 `null` 이고 `reason` 에 왜인지 적힙니다. **0 으로 채우지 않습니다** —
  0 과 '모른다' 는 다릅니다.
- 품질(ROE)과 성장(EPS 성장률)을 둘 다 못 구한 종목은 아예 넣지 않습니다.

## 계산 규칙

`sec_fundamentals.py` 의 `derive()` 와 Apps Script 의 `scrDerive()` 는
**같은 규칙을 두 번 적어놓은 것**입니다. 한쪽만 고치면 두 결과가 조용히 갈라집니다.
`cross_check.py` 가 열 가지 경우(자본잠식, 연도 어긋남, capex 부호 반대, 빈 자료 등)로
두 구현을 대조합니다. 고칠 일이 있으면 그것부터 돌리세요.

| 지표 | 계산 |
|---|---|
| ROE | 같은 해의 순이익 ÷ 자기자본, 최근 3년 평균 (자기자본이 양수인 해만) |
| FCF | 영업현금흐름 − \|설비투자\|, 가장 최근 값. capex 가 없으면 결측 |
| FCF 마진 | FCF ÷ 매출, 3년 평균 |
| EPS·매출 성장률 | 3년 CAGR. **시작이 적자면 결측**(의미가 없어서), 끝이 적자면 −1 |
| 부채비율 | 부채 ÷ 자기자본, 가장 최근 |
| 이익 변동성 | EPS 표준편차 ÷ \|평균\| |
