"""2D 도면 입력의 오류 경계."""


class DrawingError(Exception):
    """도면 분석·프로파일 계층의 기반 예외."""


class UnsupportedImageError(DrawingError):
    """지원하지 않거나 디코딩할 수 없는 이미지."""


class ImageTooLargeError(DrawingError):
    """파일 또는 디코딩한 픽셀 수가 상한을 넘었다."""


class ProfileDetectionError(DrawingError):
    """유효한 외곽 프로파일 후보를 찾지 못했다."""


class ProfileInvalidError(DrawingError):
    """확정 프로파일의 토폴로지나 치수가 유효하지 않다."""
