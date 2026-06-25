"""Tests for scripts/clean_weaviate.py"""
import pytest
import json
import tempfile
import sys
from unittest.mock import MagicMock, patch, call
from pathlib import Path
from io import StringIO


@pytest.fixture
def mock_weaviate_setup():
    """Mock Weaviate client and collection for tests."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.collections.get.return_value = mock_collection
    mock_client.collections.delete = MagicMock()
    return mock_client, mock_collection


def test_list_prints_incidents(mock_weaviate_setup, capsys):
    """Should print incident UUIDs and titles when listing."""
    mock_client, mock_collection = mock_weaviate_setup

    # Mock fetch_objects returning 2 objects
    mock_obj1 = MagicMock()
    mock_obj1.uuid = "uuid-1234-5678"
    mock_obj1.properties = {"title": "Database pool exhaustion", "fix": "Increased pool size"}

    mock_obj2 = MagicMock()
    mock_obj2.uuid = "uuid-abcd-efgh"
    mock_obj2.properties = {"title": "Memory leak in auth service", "fix": "Added LRU cache"}

    mock_response = MagicMock()
    mock_response.objects = [mock_obj1, mock_obj2]
    mock_collection.query.fetch_objects.return_value = mock_response

    with patch("scripts.clean_weaviate.get_client", return_value=mock_client):
        with patch("scripts.clean_weaviate.close_client"):
            with patch("sys.argv", ["clean_weaviate.py", "--list"]):
                from scripts.clean_weaviate import main
                main()

    captured = capsys.readouterr()
    assert "uuid-1234-5678" in captured.out
    assert "uuid-abcd-efgh" in captured.out
    assert "Database pool exhaustion" in captured.out
    assert "Memory leak in auth service" in captured.out


def test_list_warns_at_limit(mock_weaviate_setup, capsys):
    """Should print warning when exactly 1000 objects returned (at limit)."""
    mock_client, mock_collection = mock_weaviate_setup

    # Mock fetch_objects returning exactly 1000 objects
    mock_objects = []
    for i in range(1000):
        obj = MagicMock()
        obj.uuid = f"uuid-{i}"
        obj.properties = {"title": f"Incident {i}", "fix": f"Fix {i}"}
        mock_objects.append(obj)

    mock_response = MagicMock()
    mock_response.objects = mock_objects
    mock_collection.query.fetch_objects.return_value = mock_response

    with patch("scripts.clean_weaviate.get_client", return_value=mock_client):
        with patch("scripts.clean_weaviate.close_client"):
            with patch("sys.argv", ["clean_weaviate.py", "--list"]):
                from scripts.clean_weaviate import main
                main()

    captured = capsys.readouterr()
    assert "Warning: result count equals limit (1000)" in captured.out
    assert "there may be more entries" in captured.out


def test_delete_calls_delete_by_id(mock_weaviate_setup):
    """Should call collection.data.delete_by_id for each UUID provided."""
    mock_client, mock_collection = mock_weaviate_setup

    with patch("scripts.clean_weaviate.get_client", return_value=mock_client):
        with patch("scripts.clean_weaviate.close_client"):
            with patch("sys.argv", ["clean_weaviate.py", "--delete", "uuid-1", "uuid-2"]):
                from scripts.clean_weaviate import main
                main()

    assert mock_collection.data.delete_by_id.call_count == 2
    mock_collection.data.delete_by_id.assert_any_call("uuid-1")
    mock_collection.data.delete_by_id.assert_any_call("uuid-2")


def test_delete_prints_success(mock_weaviate_setup, capsys):
    """Should print success message for each deleted UUID."""
    mock_client, mock_collection = mock_weaviate_setup

    with patch("scripts.clean_weaviate.get_client", return_value=mock_client):
        with patch("scripts.clean_weaviate.close_client"):
            with patch("sys.argv", ["clean_weaviate.py", "--delete", "uuid-abc"]):
                from scripts.clean_weaviate import main
                main()

    captured = capsys.readouterr()
    assert "Deleted: uuid-abc" in captured.out


def test_delete_prints_error_on_exception(mock_weaviate_setup, capsys):
    """Should print error message when delete_by_id raises exception."""
    mock_client, mock_collection = mock_weaviate_setup

    # Make delete_by_id raise an exception
    mock_collection.data.delete_by_id.side_effect = Exception("Object not found")

    with patch("scripts.clean_weaviate.get_client", return_value=mock_client):
        with patch("scripts.clean_weaviate.close_client"):
            with patch("sys.argv", ["clean_weaviate.py", "--delete", "uuid-missing"]):
                from scripts.clean_weaviate import main
                main()

    captured = capsys.readouterr()
    assert "Error deleting uuid-missing" in captured.out


def test_wipe_and_reseed_requires_gemini_key(mock_weaviate_setup):
    """Should exit with code 1 when GEMINI_API_KEY is not set."""
    with patch("scripts.clean_weaviate.get_client"):
        with patch("scripts.clean_weaviate.close_client"):
            with patch.dict("os.environ", {}, clear=True):
                # Clear GEMINI_API_KEY
                with patch("scripts.clean_weaviate.dotenv_values", return_value={}):
                    with patch("sys.argv", ["clean_weaviate.py", "--wipe-and-reseed"]):
                        with patch("builtins.input", return_value="yes"):
                            from scripts.clean_weaviate import main
                            with pytest.raises(SystemExit) as exc_info:
                                main()

                            assert exc_info.value.code == 1


def test_wipe_and_reseed_aborts_without_confirmation(capsys):
    """Should abort and print message when user doesn't confirm."""
    with patch("scripts.clean_weaviate.get_client"):
        with patch("scripts.clean_weaviate.close_client"):
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                with patch("scripts.clean_weaviate.dotenv_values", return_value={}):
                    with patch("sys.argv", ["clean_weaviate.py", "--wipe-and-reseed"]):
                        with patch("builtins.input", return_value="no"):
                            from scripts.clean_weaviate import main
                            with pytest.raises(SystemExit) as exc_info:
                                main()

                            assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "Aborted" in captured.out


def test_wipe_and_reseed_invalid_json_exits(capsys):
    """Should exit with code 1 when JSON file is invalid."""
    # Create invalid JSON file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{invalid json}")
        temp_path = f.name

    try:
        with patch("scripts.clean_weaviate._JSON_PATH", Path(temp_path)):
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                with patch("scripts.clean_weaviate.dotenv_values", return_value={}):
                    with patch("sys.argv", ["clean_weaviate.py", "--wipe-and-reseed"]):
                        with patch("builtins.input", return_value="yes"):
                            from scripts.clean_weaviate import main
                            with pytest.raises(SystemExit) as exc_info:
                                main()

                            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "is not valid JSON" in captured.out
    finally:
        import os
        os.unlink(temp_path)


def test_wipe_and_reseed_missing_field_exits(capsys):
    """Should exit with code 1 when JSON entry is missing required field."""
    invalid_json = [
        {
            "title": "Test",
            "root_cause": "Cause",
            "fix": "Fix"
            # Missing "service" field
        }
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(invalid_json, f)
        temp_path = f.name

    try:
        with patch("scripts.clean_weaviate._JSON_PATH", Path(temp_path)):
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                with patch("scripts.clean_weaviate.dotenv_values", return_value={}):
                    with patch("sys.argv", ["clean_weaviate.py", "--wipe-and-reseed"]):
                        with patch("builtins.input", return_value="yes"):
                            from scripts.clean_weaviate import main
                            with pytest.raises(SystemExit) as exc_info:
                                main()

                            assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "missing fields" in captured.out
    finally:
        import os
        os.unlink(temp_path)


def test_wipe_and_reseed_success(mock_weaviate_setup, capsys):
    """Should delete collection, init schema, and insert all incidents."""
    mock_client, mock_collection = mock_weaviate_setup

    valid_json = [
        {
            "title": "Incident 1",
            "root_cause": "Root cause 1",
            "fix": "Fix 1",
            "service": "service-1"
        },
        {
            "title": "Incident 2",
            "root_cause": "Root cause 2",
            "fix": "Fix 2",
            "service": "service-2"
        }
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(valid_json, f)
        temp_path = f.name

    try:
        # Mock genai client and embed_text
        mock_genai_client = MagicMock()
        mock_embedding = MagicMock()
        mock_embedding.embeddings = [MagicMock(values=[0.5] * 768)]
        mock_genai_client.models.embed_content.return_value = mock_embedding

        with patch("scripts.clean_weaviate._JSON_PATH", Path(temp_path)):
            with patch("scripts.clean_weaviate.get_client", return_value=mock_client):
                with patch("scripts.clean_weaviate.close_client"):
                    with patch("scripts.clean_weaviate.init_schema") as mock_init_schema:
                        with patch("scripts.clean_weaviate.genai.configure", create=True):
                            with patch("scripts.clean_weaviate.genai.Client", return_value=mock_genai_client):
                                with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                                    with patch("scripts.clean_weaviate.dotenv_values", return_value={}):
                                        with patch("sys.argv", ["clean_weaviate.py", "--wipe-and-reseed"]):
                                            with patch("builtins.input", return_value="yes"):
                                                from scripts.clean_weaviate import main
                                                main()

        # Verify collections.delete was called
        mock_client.collections.delete.assert_called_once_with("PastIncident")

        # Verify init_schema was called
        mock_init_schema.assert_called_once_with(mock_client)

        # Verify insert was called twice (once for each incident)
        assert mock_collection.data.insert.call_count == 2

        captured = capsys.readouterr()
        assert "Deleted PastIncident collection" in captured.out
        assert "Reseeded 2 incidents" in captured.out
    finally:
        import os
        os.unlink(temp_path)
