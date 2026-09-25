from unittest.mock import patch

import pytest

from mosaic.dialogs.update import UpdateDialog, newer_version, release_exists


def _payload(*versions, info_version=None, yanked=(), files=True):
    """Minimal shape of the PyPI JSON payload the checker reads."""
    releases = {}
    for version in versions:
        if not files:
            releases[version] = []
            continue
        releases[version] = [{"yanked": version in yanked}]
    return {
        "info": {"version": info_version or (versions[-1] if versions else "")},
        "releases": releases,
    }


class TestNewerVersion:
    def test_picks_highest_release_above_current(self):
        payload = _payload("1.4.0", "1.5.2", "1.6.0")
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_release_order_in_payload_is_irrelevant(self):
        payload = _payload("1.6.0", "1.10.0", "1.9.0")
        assert newer_version(payload, "1.5.2") == "1.10.0"

    def test_returns_none_when_current_is_latest(self):
        assert newer_version(_payload("1.4.0", "1.6.0"), "1.6.0") is None

    def test_returns_none_when_current_is_ahead(self):
        assert newer_version(_payload("1.4.0", "1.6.0"), "1.7.0.dev0") is None

    def test_skips_prereleases(self):
        payload = _payload("1.6.0", "1.7.0rc1", "1.7.0b2")
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_skips_dev_releases(self):
        payload = _payload("1.6.0", "1.7.0.dev3")
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_skips_fully_yanked_releases(self):
        payload = _payload("1.6.0", "1.7.0", yanked=("1.7.0",))
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_keeps_partially_yanked_releases(self):
        payload = {
            "info": {"version": "1.7.0"},
            "releases": {"1.7.0": [{"yanked": True}, {"yanked": False}]},
        }
        assert newer_version(payload, "1.5.2") == "1.7.0"

    def test_skips_releases_without_files(self):
        payload = _payload("1.6.0", "1.7.0")
        payload["releases"]["1.7.0"] = []
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_ignores_unparsable_version_strings(self):
        payload = _payload("1.6.0", "not-a-version")
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_falls_back_to_info_version_without_releases(self):
        payload = {"info": {"version": "1.6.0"}}
        assert newer_version(payload, "1.5.2") == "1.6.0"

    def test_returns_none_for_unparsable_current_version(self):
        assert newer_version(_payload("1.6.0"), "not-a-version") is None

    def test_returns_none_for_empty_payload(self):
        assert newer_version({}, "1.5.2") is None


class TestReleaseExists:
    def test_true_when_tag_endpoint_resolves(self):
        with patch(
            "mosaic.dialogs.update._fetch_json", return_value={"tag_name": "v1.6.0"}
        ):
            assert release_exists("1.6.0") is True

    def test_false_when_tag_endpoint_is_missing(self):
        with patch("mosaic.dialogs.update._fetch_json", return_value=None):
            assert release_exists("1.6.0") is False


@pytest.fixture
def dialog(qapp):
    dialogs = []

    def build(current="1.5.2", latest="1.6.0", has_changelog=True):
        widget = UpdateDialog(current, latest, has_changelog=has_changelog)
        dialogs.append(widget)
        return widget

    yield build
    for widget in dialogs:
        widget.deleteLater()


class TestUpdateDialog:
    def test_changelog_enabled_when_release_exists(self, dialog):
        assert dialog(has_changelog=True).changelog_button.isEnabled()

    def test_changelog_disabled_without_release(self, dialog):
        widget = dialog(has_changelog=False)
        assert not widget.changelog_button.isEnabled()
        assert widget.changelog_button.toolTip()

    def test_state_is_announced_in_the_window_title(self, dialog):
        widget = dialog()
        assert widget.windowTitle() == "Update available"
        widget._apply_state("installing")
        assert widget.windowTitle() == "Installing update"
        widget._on_install_finished(True, "")
        assert widget.windowTitle() == "Update installed"

    def test_failure_detail_replaces_the_body_text(self, dialog):
        widget = dialog()
        widget._on_install_finished(False, "ERROR: no matching distribution")
        assert widget.windowTitle() == "Update failed"
        assert widget.subline.text() == "ERROR: no matching distribution"

    def test_shows_both_versions(self, dialog):
        widget = dialog(current="1.5.2", latest="1.6.0")
        assert widget.installed_label.text() == "1.5.2"
        assert widget.available_label.text() == "1.6.0"

    def test_changelog_opens_github_release_page(self, dialog):
        widget = dialog(latest="1.6.0")
        with patch("mosaic.dialogs.update.QDesktopServices.openUrl") as open_url:
            widget.changelog_button.click()
        assert open_url.call_count == 1
        assert open_url.call_args[0][0].toString().endswith("/releases/tag/v1.6.0")

    def test_cancel_closes_without_recording_state(self, dialog):
        from mosaic.settings import Settings

        widget = dialog()
        widget.cancel_button.click()
        assert not widget.isVisible()
        assert not hasattr(Settings.ui, "skipped_version")

    def test_install_switches_to_progress_state(self, dialog):
        widget = dialog()
        with patch.object(widget, "_start_install"):
            widget.install_button.click()
        assert widget.state == "installing"
        assert widget.install_button is None

    def test_failed_install_surfaces_the_manual_command(self, dialog):
        widget = dialog()
        widget._on_install_finished(False, "no network")
        assert widget.state == "failed"
        assert "pip install -U mosaic-gui" in widget.command_label.text()

    def test_successful_install_offers_restart(self, dialog):
        widget = dialog()
        widget._on_install_finished(True, "")
        assert widget.state == "success"
        assert widget.restart_button.isEnabled()
