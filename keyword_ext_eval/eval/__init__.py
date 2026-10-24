"""키워드 추출 API 스키마 키워드 커버리지 평가 도구 (README.md 참고)."""

import warnings

# .venv의 Python 3.9(LibreSSL)에서 urllib3 v2가 import마다 내는 경고 - 로컬 HTTP 호출엔 영향 없음
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
