import inspect

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

import ui.recommendations_tab as recommendations_module
from ui.gui import MainWindow
from ui.maintenance_tab import MaintenanceTab
from ui.recommendations_tab import RecommendationsTab


@pytest.fixture
def maintenance_tab(qapp):
    tab = MaintenanceTab(
        steam_id="0",
        api_key_configured=True,
        appearance="System",
    )

    yield tab

    tab.close()
    tab.deleteLater()
    qapp.processEvents()


@pytest.fixture
def recommendations_tab(qapp, monkeypatch):
    monkeypatch.setattr(
        recommendations_module,
        "load_recommendation_state",
        lambda: None,
    )
    monkeypatch.setattr(
        recommendations_module,
        "load_saved_recommendations",
        list,
    )

    tab = RecommendationsTab([])

    yield tab

    tab.close()
    tab.deleteLater()
    qapp.processEvents()


def test_maintenance_uses_refresh_workflow_not_old_next_five_buttons(maintenance_tab):
    assert not hasattr(maintenance_tab, "hltb_button")
    assert not hasattr(maintenance_tab, "metadata_button")
    assert not hasattr(maintenance_tab, "achievement_button")

    assert maintenance_tab.hltb_refresh_button.text() == "Refresh Oldest"
    assert maintenance_tab.metadata_refresh_button.text() == "Refresh Oldest"
    assert maintenance_tab.achievement_refresh_button.text() == "Refresh Changed"


@pytest.mark.parametrize(
    ("control", "value", "expected"),
    [
        ("hltb", "10", 10),
        ("hltb", "25", 25),
        ("hltb", "All", None),
        ("metadata", "25", 25),
        ("metadata", "100", 100),
        ("metadata", "250", 250),
        ("metadata", "All", None),
    ],
)
def test_maintenance_refresh_limits(maintenance_tab, control, value, expected):
    if control == "hltb":
        maintenance_tab.hltb_refresh_count.setCurrentText(value)
        assert maintenance_tab.hltb_refresh_limit() == expected
    else:
        maintenance_tab.metadata_refresh_count.setCurrentText(value)
        assert maintenance_tab.metadata_refresh_limit() == expected


def test_maintenance_busy_state_toggles_actions(maintenance_tab):
    maintenance_tab.set_review_available(True)
    maintenance_tab.set_busy(True)

    disabled = [
        maintenance_tab.update_all_button,
        maintenance_tab.library_button,
        maintenance_tab.steam_classification_button,
        maintenance_tab.hltb_refresh_button,
        maintenance_tab.hltb_refresh_count,
        maintenance_tab.metadata_refresh_button,
        maintenance_tab.metadata_refresh_count,
        maintenance_tab.achievement_refresh_button,
        maintenance_tab.hltb_review_button,
    ]

    assert all(not widget.isEnabled() for widget in disabled)
    assert maintenance_tab.cancel_updates_button.isEnabled()

    maintenance_tab.set_busy(False)

    assert all(widget.isEnabled() for widget in disabled)
    assert not maintenance_tab.cancel_updates_button.isEnabled()


def test_failure_button_tracks_failure_availability(maintenance_tab):
    maintenance_tab.set_failures([])

    assert maintenance_tab.view_failures_button.isHidden()
    assert not maintenance_tab.view_failures_button.isEnabled()

    maintenance_tab.set_failures(["one", "two"])

    assert not maintenance_tab.view_failures_button.isHidden()
    assert maintenance_tab.view_failures_button.isEnabled()
    assert maintenance_tab.view_failures_button.text() == "View Failures (2)"


def test_main_window_bindings_do_not_reference_removed_buttons():
    source = inspect.getsource(MainWindow._bind_tabs)

    assert ".hltb_button" not in source
    assert ".metadata_button" not in source
    assert ".achievement_button" not in source


@pytest.mark.parametrize(
    ("panel_name", "content_name"),
    [
        ("for_you_left_panel", "for_you_left_content"),
        ("similar_left_panel", "similar_left_content"),
    ],
)
def test_recommendation_media_panels_are_vertical_scroll_areas(
    recommendations_tab,
    panel_name,
    content_name,
):
    panel = getattr(recommendations_tab, panel_name)
    content = getattr(recommendations_tab, content_name)

    assert isinstance(panel, QScrollArea)
    assert panel.widget() is content
    assert panel.widgetResizable()
    assert panel.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert panel.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_recommendation_scroll_content_keeps_media_and_actions(recommendations_tab):
    assert (
        recommendations_tab.for_you_image.parent()
        is recommendations_tab.for_you_left_content
    )
    assert (
        recommendations_tab.for_you_trailer_player.parent()
        is recommendations_tab.for_you_left_content
    )
    assert recommendations_tab.for_you_previous_button is not None
    assert recommendations_tab.for_you_next_button is not None

    assert (
        recommendations_tab.similar_image.parent()
        is recommendations_tab.similar_left_content
    )
    assert (
        recommendations_tab.similar_trailer_player.parent()
        is recommendations_tab.similar_left_content
    )
    assert recommendations_tab.similar_steam_button is not None


@pytest.mark.parametrize(
    ("panel_name", "page_name"),
    [
        ("for_you_left_panel", "for_you_page"),
        ("similar_left_panel", "similar_page"),
    ],
)
def test_recommendation_panels_scroll_when_height_is_small(
    qapp,
    recommendations_tab,
    panel_name,
    page_name,
):
    recommendations_tab.resize(1100, 520)
    recommendations_tab.show()
    recommendations_tab.mode_tabs.setCurrentWidget(
        getattr(recommendations_tab, page_name)
    )
    qapp.processEvents()

    panel = getattr(recommendations_tab, panel_name)
    original_minimum = panel.minimumHeight()
    original_maximum = panel.maximumHeight()

    panel.setFixedHeight(170)
    qapp.processEvents()

    assert panel.verticalScrollBar().maximum() > 0

    panel.setMinimumHeight(original_minimum)
    panel.setMaximumHeight(original_maximum)
