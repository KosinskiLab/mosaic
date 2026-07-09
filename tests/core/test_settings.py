import pytest
from unittest.mock import Mock, patch
from dataclasses import dataclass

from mosaic.settings import SettingsProperty, SettingsCategory


class TestSettingsProperty:
    """Test suite for SettingsProperty descriptor."""

    def test_init(self):
        """Test SettingsProperty initialization."""
        prop = SettingsProperty("test_key", "default_value", str)

        assert prop.key == "test_key"
        assert prop.default == "default_value"
        assert prop.value_type == str
        assert prop._value is None
        assert prop._loaded is False

    def test_get_loads_from_qsettings(self):
        """Test getting value loads from QSettings."""
        prop = SettingsProperty("test_key", "default", str)

        mock_obj = Mock()
        mock_qsettings = Mock()
        mock_obj._qsettings = mock_qsettings

        mock_qsettings.contains.return_value = True
        mock_qsettings.value.return_value = "loaded_value"

        result = prop.__get__(mock_obj)

        assert result == "loaded_value"
        assert prop._loaded is True
        mock_qsettings.value.assert_called_once_with("test_key", type=str)

    def test_get_uses_default_when_not_in_qsettings(self):
        """Test getting value uses default when key not in QSettings."""
        prop = SettingsProperty("test_key", "default", str)

        mock_obj = Mock()
        mock_qsettings = Mock()
        mock_obj._qsettings = mock_qsettings

        mock_qsettings.contains.return_value = False

        result = prop.__get__(mock_obj)

        assert result == "default"
        assert prop._loaded is True

    def test_set_saves_to_qsettings(self):
        """Test setting value saves to QSettings."""
        prop = SettingsProperty("test_key", "default", str)

        mock_obj = Mock()
        mock_qsettings = Mock()
        mock_obj._qsettings = mock_qsettings

        prop.__set__(mock_obj, "new_value")

        assert prop._value == "new_value"
        assert prop._loaded is True
        mock_qsettings.setValue.assert_called_once_with("test_key", "new_value")

    def test_tuple_type_handling(self):
        """Test handling of tuple types in QSettings."""
        from typing import Tuple

        prop = SettingsProperty("test_key", (1, 2, 3), Tuple[int, int, int])

        mock_obj = Mock()
        mock_qsettings = Mock()
        mock_obj._qsettings = mock_qsettings

        mock_qsettings.contains.return_value = True
        mock_qsettings.value.return_value = [1, 2, 3]

        with patch("mosaic.settings.get_origin") as mock_get_origin:
            mock_get_origin.return_value = tuple

            result = prop.__get__(mock_obj)

            assert result == (1, 2, 3)


class TestSettingsCategory:
    """Test suite for SettingsCategory class."""

    def test_init_creates_properties(self):
        """Test SettingsCategory creates properties from dataclass."""

        @dataclass
        class TestSettings:
            test_field: str = "default"
            test_number: int = 42

        with patch("mosaic.settings.QSettings") as mock_qsettings_class:
            category = SettingsCategory("test_category", TestSettings)

            assert hasattr(category.__class__, "test_field")
            assert hasattr(category.__class__, "test_number")
            assert "test_field" in category._fields
            assert "test_number" in category._fields

    def test_get_settings(self):
        """Test getting all settings as dictionary."""

        @dataclass
        class TestSettings:
            field1: str = "value1"
            field2: int = 123

        with patch("mosaic.settings.QSettings"):
            category = SettingsCategory("test", TestSettings)

            # Mock the property getters
            with patch.object(category.__class__, "field1", "mocked1"):
                with patch.object(category.__class__, "field2", 456):
                    settings = category.get_settings()

                    expected_fields = {"field1", "field2"}
                    assert set(settings.keys()) == expected_fields
