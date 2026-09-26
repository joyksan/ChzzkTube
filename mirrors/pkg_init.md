"""ChzzkTube 패키지 메타데이터."""
from chzzktube.core.config import APP_NAME, APP_VERSION

__title__ = APP_NAME
__version__ = APP_VERSION.lstrip("v")

__all__ = ["APP_NAME", "APP_VERSION", "__title__", "__version__"]
