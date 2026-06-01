import pytest
from unittest.mock import patch, MagicMock
from weaviate.classes.config import Property, DataType
from infra.weaviate_client import get_client, init_schema, close_client


class TestGetClient:
    """Test Weaviate client initialization."""

    @patch('infra.weaviate_client.weaviate.connect_to_local')
    def test_get_client_default_params(self, mock_connect):
        """Test client creation with default host and port."""
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        result = get_client()

        mock_connect.assert_called_once_with(host='localhost', port=8080)
        assert result == mock_client

    @patch('infra.weaviate_client.weaviate.connect_to_local')
    def test_get_client_custom_params(self, mock_connect):
        """Test client creation with custom host and port."""
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        result = get_client(host='weaviate-prod', port=8081)

        mock_connect.assert_called_once_with(host='weaviate-prod', port=8081)
        assert result == mock_client

    @patch('infra.weaviate_client.weaviate.connect_to_local')
    def test_get_client_numeric_port(self, mock_connect):
        """Test client creation with integer port."""
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        result = get_client(host='127.0.0.1', port=9999)

        mock_connect.assert_called_once_with(host='127.0.0.1', port=9999)


class TestInitSchema:
    """Test Weaviate schema initialization."""

    @patch('builtins.print')
    def test_init_schema_creates_collection_when_not_exists(self, mock_print, mock_weaviate_client):
        """Test schema creation when collection does not exist."""
        mock_weaviate_client.collections.exists.return_value = False

        init_schema(mock_weaviate_client)

        mock_weaviate_client.collections.exists.assert_called_once_with("PastIncident")
        mock_weaviate_client.collections.create.assert_called_once()

        # Verify create was called with correct collection name
        call_args = mock_weaviate_client.collections.create.call_args
        assert call_args[1]['name'] == "PastIncident"

        # Verify properties
        properties = call_args[1]['properties']
        assert len(properties) == 5

        property_names = [prop.name for prop in properties]
        assert 'title' in property_names
        assert 'root_cause' in property_names
        assert 'fix' in property_names
        assert 'service' in property_names
        assert 'embedding' in property_names

        mock_print.assert_called_with("PastIncident collection created")

    @patch('builtins.print')
    def test_init_schema_skips_when_exists(self, mock_print, mock_weaviate_client):
        """Test schema initialization when collection already exists."""
        mock_weaviate_client.collections.exists.return_value = True

        init_schema(mock_weaviate_client)

        mock_weaviate_client.collections.exists.assert_called_once_with("PastIncident")
        mock_weaviate_client.collections.create.assert_not_called()
        mock_print.assert_called_with("PastIncident collection already exists, skipping creation")

    @patch('builtins.print')
    def test_init_schema_is_idempotent(self, mock_print, mock_weaviate_client):
        """Test that init_schema can be called multiple times safely."""
        mock_weaviate_client.collections.exists.return_value = True

        init_schema(mock_weaviate_client)
        init_schema(mock_weaviate_client)
        init_schema(mock_weaviate_client)

        assert mock_weaviate_client.collections.exists.call_count == 3
        mock_weaviate_client.collections.create.assert_not_called()

    def test_init_schema_property_types(self, mock_weaviate_client):
        """Test that schema properties have correct data types."""
        mock_weaviate_client.collections.exists.return_value = False

        init_schema(mock_weaviate_client)

        call_args = mock_weaviate_client.collections.create.call_args
        properties = call_args[1]['properties']

        # Create a mapping for easier testing - use dataType (camelCase) not data_type
        prop_map = {prop.name: prop.dataType for prop in properties}

        assert prop_map['title'] == DataType.TEXT
        assert prop_map['root_cause'] == DataType.TEXT
        assert prop_map['fix'] == DataType.TEXT
        assert prop_map['service'] == DataType.TEXT
        assert prop_map['embedding'] == DataType.NUMBER_ARRAY

    def test_init_schema_all_required_properties_present(self, mock_weaviate_client):
        """Test that all required properties for PastIncident are created."""
        mock_weaviate_client.collections.exists.return_value = False

        init_schema(mock_weaviate_client)

        call_args = mock_weaviate_client.collections.create.call_args
        properties = call_args[1]['properties']
        property_names = {prop.name for prop in properties}

        required_properties = {'title', 'root_cause', 'fix', 'service', 'embedding'}
        assert property_names == required_properties


class TestCloseClient:
    """Test Weaviate client cleanup."""

    def test_close_client(self, mock_weaviate_client):
        """Test that close_client calls client.close()."""
        close_client(mock_weaviate_client)

        mock_weaviate_client.close.assert_called_once()

    def test_close_client_multiple_calls(self, mock_weaviate_client):
        """Test that close_client can be called multiple times."""
        close_client(mock_weaviate_client)
        close_client(mock_weaviate_client)

        assert mock_weaviate_client.close.call_count == 2


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch('infra.weaviate_client.weaviate.connect_to_local')
    def test_get_client_with_empty_host(self, mock_connect):
        """Test client creation with empty host string."""
        mock_client = MagicMock()
        mock_connect.return_value = mock_client

        result = get_client(host='', port=8080)

        mock_connect.assert_called_once_with(host='', port=8080)

    def test_init_schema_exception_handling(self, mock_weaviate_client):
        """Test that init_schema handles collection existence check properly."""
        mock_weaviate_client.collections.exists.return_value = False
        mock_weaviate_client.collections.create.side_effect = Exception("Connection failed")

        with pytest.raises(Exception, match="Connection failed"):
            init_schema(mock_weaviate_client)

    @patch('builtins.print')
    def test_init_schema_verifies_collection_name(self, mock_print, mock_weaviate_client):
        """Test that init_schema checks for exact collection name."""
        mock_weaviate_client.collections.exists.return_value = False

        init_schema(mock_weaviate_client)

        # Verify exact collection name (case-sensitive)
        mock_weaviate_client.collections.exists.assert_called_with("PastIncident")
