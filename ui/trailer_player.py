import requests
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from api.store_api import get_trailer_url

DEFAULT_TRAILER_VOLUME = 15
MAX_WIDGET_HEIGHT = 16777215

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
        self.setMinimumHeight(180)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mousePressEvent(event)


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

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.video_widget = ClickableVideoWidget(self)

        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        self.video_widget.setVisible(False)

        self.trailer_button = QPushButton("Watch Trailer")
        self.trailer_button.setEnabled(False)

        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(88)
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
        self._set_compact_mode()

    def _create_layout(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self.video_widget, 1)

        controls = QHBoxLayout()
        controls.addWidget(self.trailer_button)
        controls.addWidget(self.time_label)
        controls.addStretch()
        controls.addWidget(self.volume_label)
        controls.addWidget(self.volume_slider)
        controls.addWidget(self.volume_value_label)

        layout.addLayout(controls)

    def _connect_signals(self):
        self.trailer_button.clicked.connect(self.toggle_trailer)
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
        self.trailer_button.setEnabled(app_id is not None)

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
        if self.app_id is None:
            return

        app_id = self.app_id
        trailer_url = _TRAILER_URL_CACHE.get(app_id)

        if trailer_url:
            self._start_playback(app_id, trailer_url)
            return

        if app_id in _NO_TRAILER_CACHE:
            QMessageBox.information(
                self,
                "Trailer",
                "No Steam trailer is available for this game.",
            )
            return

        self._loading_app_id = app_id
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

        self.video_widget.setVisible(False)
        self.video_widget.setToolTip("Click the video to pause or resume.")

        self.time_label.setText("0:00 / 0:00")
        self.time_label.setVisible(False)

        self._loading_app_id = None

        self.trailer_button.setText("Watch Trailer")
        self.trailer_button.setEnabled(self.app_id is not None)

        self._set_compact_mode()

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
        self.trailer_button.setText("Watch Trailer")
        self.trailer_button.setEnabled(True)

        if error_message:
            QMessageBox.warning(
                self,
                "Trailer",
                f"Could not retrieve the Steam trailer:\n{error_message}",
            )
            return

        if not trailer_url:
            QMessageBox.information(
                self,
                "Trailer",
                "No Steam trailer is available for this game.",
            )
            return

        if not self.isVisible():
            return

        self._start_playback(app_id, trailer_url)

    def _start_playback(self, app_id, trailer_url):
        if app_id != self.app_id:
            return

        self._set_video_mode()
        self.video_widget.setVisible(True)
        self.time_label.setVisible(True)

        self.media_player.setSource(QUrl(trailer_url))
        self.media_player.play()

        self.video_widget.setToolTip("Click the video to pause.")
        self.trailer_button.setText("Stop Trailer")
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

    def _set_compact_mode(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setMaximumHeight(110)

    def _set_video_mode(self):
        self.setMaximumHeight(MAX_WIDGET_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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
            self.trailer_button.setText("Watch Trailer")
            self.trailer_button.setEnabled(self.app_id is not None)

        self.pause()
        super().hideEvent(event)
