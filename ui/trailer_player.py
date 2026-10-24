import requests
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from api.store_api import get_trailer_url

DEFAULT_TRAILER_VOLUME = 15
MIN_PREVIEW_HEIGHT = 180
MAX_PREVIEW_HEIGHT = 360

_TRAILER_URL_CACHE = {}
_NO_TRAILER_CACHE = set()


class ClickableVideoWidget(QVideoWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click the video to pause or resume.")
        self.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mousePressEvent(event)


class ClickablePreviewFrame(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("trailerPreviewFrame")
        self.setStyleSheet(
            "#trailerPreviewFrame {"
            " background-color: #111111;"
            " border: 1px solid #3a3a3a;"
            " border-radius: 6px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setStyleSheet("color: #b8b8b8; font-size: 11pt;")

        layout.addStretch()
        layout.addWidget(self.label)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mousePressEvent(event)


class TrailerPreviewContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        policy = QSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumHeight(MIN_PREVIEW_HEIGHT)
        self.setMaximumHeight(MAX_PREVIEW_HEIGHT)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        target_height = int(max(width, 1) * 9 / 16)
        return max(
            MIN_PREVIEW_HEIGHT,
            min(target_height, MAX_PREVIEW_HEIGHT),
        )

    def sizeHint(self):
        width = max(self.width(), 480)
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):
        return QSize(220, MIN_PREVIEW_HEIGHT)


class TrailerLookupSignals(QObject):
    finished = Signal(int, object, object)


class TrailerLookupWorker(QRunnable):
    def __init__(self, app_id):
        super().__init__()

        self.app_id = app_id
        self.signals = TrailerLookupSignals()

    def run(self):
        try:
            trailer_url = get_trailer_url(self.app_id)
        except (requests.RequestException, OSError, ValueError) as error:
            self.signals.finished.emit(self.app_id, None, str(error))
            return

        self.signals.finished.emit(self.app_id, trailer_url, None)


class TrailerPlayer(QWidget):
    volume_changed = Signal(int)

    def __init__(self, parent=None, initial_volume=DEFAULT_TRAILER_VOLUME):
        super().__init__(parent)

        self.app_id = None
        self._loading_app_id = None
        self.thread_pool = QThreadPool.globalInstance()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.video_widget = ClickableVideoWidget(self)
        self.preview_frame = ClickablePreviewFrame(self)
        self.preview_container = TrailerPreviewContainer(self)

        self.preview_stack = QStackedLayout(self.preview_container)
        self.preview_stack.setContentsMargins(0, 0, 0, 0)
        self.preview_stack.addWidget(self.preview_frame)
        self.preview_stack.addWidget(self.video_widget)
        self.preview_stack.setCurrentWidget(self.preview_frame)

        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.trailer_button = QPushButton("Watch Trailer")
        self.trailer_button.setEnabled(False)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(72)
        self.time_label.setVisible(False)

        self.volume_label = QLabel("Volume:")

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setSingleStep(5)
        self.volume_slider.setPageStep(10)
        self.volume_slider.setMaximumWidth(160)

        initial_volume = max(0, min(int(initial_volume), 100))
        self.volume_slider.setValue(initial_volume)

        self.volume_value_label = QLabel(f"{initial_volume}%")
        self.volume_value_label.setMinimumWidth(36)

        self.audio_output.setVolume(initial_volume / 100.0)

        self._create_layout()
        self._connect_signals()
        self._update_idle_state()

    def _create_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self.preview_container)

        self.controls_widget = QWidget(self)
        self.controls_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        controls = QVBoxLayout(self.controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)

        playback_row = QHBoxLayout()
        playback_row.setContentsMargins(0, 0, 0, 0)
        playback_row.addWidget(self.trailer_button)
        playback_row.addWidget(self.time_label)
        playback_row.addStretch()

        volume_row = QHBoxLayout()
        volume_row.setContentsMargins(0, 0, 0, 0)
        volume_row.addWidget(self.volume_label)
        volume_row.addWidget(self.volume_slider, 1)
        volume_row.addWidget(self.volume_value_label)

        controls.addLayout(playback_row)
        controls.addLayout(volume_row)
        layout.addWidget(self.controls_widget)

    def _connect_signals(self):
        self.trailer_button.clicked.connect(self.toggle_trailer)
        self.preview_frame.clicked.connect(self.play_trailer)
        self.video_widget.clicked.connect(self.toggle_pause)
        self.volume_slider.valueChanged.connect(self._volume_changed)

        self.media_player.positionChanged.connect(self._position_changed)
        self.media_player.durationChanged.connect(self._duration_changed)
        self.media_player.errorOccurred.connect(self._handle_media_error)
        self.media_player.mediaStatusChanged.connect(self._media_status_changed)

    def set_game(self, app_id):
        if app_id == self.app_id:
            return

        self.stop()
        self.app_id = app_id
        self._loading_app_id = None
        self._update_idle_state()

    def clear_game(self):
        self.set_game(None)

    def toggle_trailer(self):
        if self.app_id is None or self._loading_app_id is not None:
            return

        if not self.media_player.source().isEmpty():
            self.stop()
            return

        self.play_trailer()

    def play_trailer(self):
        if self.app_id is None or self._loading_app_id is not None:
            return

        app_id = self.app_id
        trailer_url = _TRAILER_URL_CACHE.get(app_id)

        if trailer_url:
            self._start_playback(app_id, trailer_url)
            return

        if app_id in _NO_TRAILER_CACHE:
            self._update_idle_state()
            return

        self._loading_app_id = app_id
        self.preview_frame.label.setText("Loading Steam trailer…")
        self.trailer_button.setText("Loading...")
        self.trailer_button.setEnabled(False)

        worker = TrailerLookupWorker(app_id)
        worker.signals.finished.connect(self._trailer_lookup_finished)
        self.thread_pool.start(worker)

    def toggle_pause(self):
        if self.media_player.source().isEmpty():
            return

        state = self.media_player.playbackState()

        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
            return

        if state == QMediaPlayer.PlaybackState.PausedState:
            self.resume()

    def pause(self):
        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return

        self.media_player.pause()
        self.video_widget.setToolTip("Paused. Click the video to resume.")

    def resume(self):
        if self.media_player.source().isEmpty():
            return

        if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PausedState:
            return

        self.media_player.play()
        self.video_widget.setToolTip("Click the video to pause.")

    def stop(self):
        self.media_player.stop()
        self.media_player.setSource(QUrl())
        self.preview_stack.setCurrentWidget(self.preview_frame)
        self.video_widget.setToolTip("Click the video to pause or resume.")

        self.time_label.setText("0:00 / 0:00")
        self.time_label.setVisible(False)
        self._loading_app_id = None

        self._update_idle_state()

    def set_volume(self, volume):
        volume = max(0, min(int(volume), 100))
        self.volume_slider.setValue(volume)

    def volume(self):
        return self.volume_slider.value()

    def _volume_changed(self, volume):
        self.audio_output.setVolume(volume / 100.0)
        self.volume_value_label.setText(f"{volume}%")
        self.volume_changed.emit(volume)

    def _trailer_lookup_finished(self, app_id, trailer_url, error_message):
        if trailer_url:
            _TRAILER_URL_CACHE[app_id] = trailer_url
        elif error_message is None:
            _NO_TRAILER_CACHE.add(app_id)

        if app_id != self.app_id or self._loading_app_id != app_id:
            return

        self._loading_app_id = None

        if error_message:
            self._update_idle_state()

            QMessageBox.warning(
                self,
                "Trailer",
                f"Could not retrieve the Steam trailer:\n{error_message}",
            )
            return

        if not trailer_url:
            self._update_idle_state()
            return

        if not self.isVisible():
            self._update_idle_state()
            return

        self._start_playback(app_id, trailer_url)

    def _start_playback(self, app_id, trailer_url):
        if app_id != self.app_id:
            return

        self.preview_stack.setCurrentWidget(self.video_widget)
        self.time_label.setVisible(True)
        self.media_player.setSource(QUrl(trailer_url))
        self.media_player.play()

        self.video_widget.setToolTip("Click the video to pause.")
        self.trailer_button.setText("Stop Trailer")
        self.trailer_button.setEnabled(True)

    def _update_idle_state(self):
        self.preview_stack.setCurrentWidget(self.preview_frame)

        if self.app_id is None:
            self.preview_frame.label.setText(
                "Trailer Preview\nSelect a game to enable playback."
            )
            self.preview_frame.setCursor(Qt.CursorShape.ArrowCursor)
            self.trailer_button.setText("Watch Trailer")
            self.trailer_button.setEnabled(False)
            return

        if self.app_id in _NO_TRAILER_CACHE:
            self.preview_frame.label.setText(
                "No Steam trailer is available for this game."
            )
            self.preview_frame.setCursor(Qt.CursorShape.ArrowCursor)
            self.trailer_button.setText("No Trailer")
            self.trailer_button.setEnabled(False)
            return

        self.preview_frame.label.setText(
            "▶  Trailer Preview\nClick here or Watch Trailer to play."
        )
        self.preview_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.trailer_button.setText("Watch Trailer")
        self.trailer_button.setEnabled(True)

    def _position_changed(self, position):
        self._update_time_label(position, self.media_player.duration())

    def _duration_changed(self, duration):
        self._update_time_label(self.media_player.position(), duration)

    def _update_time_label(self, position, duration):
        self.time_label.setText(
            f"{self._format_time(position)} / {self._format_time(duration)}"
        )

    def _media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop()

    def _handle_media_error(self, error, error_string):
        if error == QMediaPlayer.Error.NoError:
            return

        message = error_string or "Unknown playback error."
        self.stop()

        QMessageBox.warning(
            self,
            "Video Playback",
            f"The trailer could not be played:\n{message}",
        )

    @staticmethod
    def _format_time(milliseconds):
        total_seconds = max(int(milliseconds // 1000), 0)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"

        return f"{minutes}:{seconds:02d}"

    def hideEvent(self, event):
        if self._loading_app_id is not None:
            self._loading_app_id = None
            self._update_idle_state()

        self.pause()
        super().hideEvent(event)
