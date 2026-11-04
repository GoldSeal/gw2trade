import hashlib
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)

DEFAULT_CACHE_DIR = Path("icon_cache")


class IconCacheManager(QObject):
    """Manages asynchronous fetching, in-memory caching, and disk persistence

    for item icons.
    """

    icon_loaded = pyqtSignal(int, QPixmap)  # (item_id, pixmap)

    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)

        self._memory_cache: dict[str, QPixmap] = {}
        # Maps active network replies to (item_id, disk_path, url_str)
        self._pending_replies: dict[QNetworkReply, tuple[int, Path, str]] = {}
        # Tracks URLs currently downloading to prevent duplicate in-flight requests
        self._in_flight_urls: set[str] = set()

        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.finished.connect(self._on_reply_finished)

    def _get_disk_path(self, url: str) -> Path:
        """Derives a deterministic filename using an MD5 hash of the URL."""
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{url_hash}.png"

    def get_cached_pixmap(self, url: str) -> Optional[QPixmap]:
        """Returns the QPixmap if already present in memory or disk, else None."""
        if not url:
            return None

        # 1. Memory Cache
        if url in self._memory_cache:
            return self._memory_cache[url]

        # 2. Disk Cache
        disk_path = self._get_disk_path(url)
        if disk_path.exists():
            pixmap = QPixmap(str(disk_path))
            if not pixmap.isNull():
                self._memory_cache[url] = pixmap
                return pixmap

        return None

    def get_cached_icon(self, url: str) -> Optional[QIcon]:
        """Convenience method returning a QIcon if cached, else None."""
        pixmap = self.get_cached_pixmap(url)
        return QIcon(pixmap) if pixmap else None

    def load_icon(self, item_id: int, url: str) -> Optional[QPixmap]:
        """Attempts to retrieve the icon immediately.

        If not cached, initiates an asynchronous network request and emits
        `icon_loaded` upon completion.
        """
        if not url:
            return None

        pixmap = self.get_cached_pixmap(url)
        if pixmap:
            return pixmap

        # Already fetching this exact asset
        if url in self._in_flight_urls:
            return None

        # 3. Asynchronous Network Download
        disk_path = self._get_disk_path(url)
        reply = self._network_manager.get(QNetworkRequest(QUrl(url)))
        self._pending_replies[reply] = (item_id, disk_path, url)
        self._in_flight_urls.add(url)
        return None

    def _on_reply_finished(self, reply: QNetworkReply):
        entry = self._pending_replies.pop(reply, None)
        if not entry:
            reply.deleteLater()
            return

        item_id, disk_path, url_str = entry
        self._in_flight_urls.discard(url_str)

        if reply.error() == QNetworkReply.NetworkError.NoError:
            raw_bytes = reply.readAll().data()

            # Save to disk cache
            try:
                disk_path.write_bytes(raw_bytes)
            except OSError:
                pass

            # Populate memory cache
            pixmap = QPixmap()
            pixmap.loadFromData(raw_bytes)
            if not pixmap.isNull():
                self._memory_cache[url_str] = pixmap
                self.icon_loaded.emit(item_id, pixmap)

        reply.deleteLater()
