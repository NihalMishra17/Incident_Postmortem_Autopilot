import pytest
import os
from unittest.mock import patch, MagicMock, call
from infra.neo4j_client import get_driver, seed_service_graph, verify_graph


class TestGetDriver:
    """Test Neo4j driver initialization."""

    @patch('infra.neo4j_client.GraphDatabase.driver')
    def test_get_driver_default_env_vars(self, mock_driver_class):
        """Test driver creation with default environment variables."""
        mock_driver_instance = MagicMock()
        mock_driver_class.return_value = mock_driver_instance

        with patch.dict(os.environ, {}, clear=True):
            result = get_driver()

            mock_driver_class.assert_called_once_with(
                'bolt://localhost:7687',
                auth=('neo4j', 'neo4jpassword')
            )
            assert result == mock_driver_instance

    @patch('infra.neo4j_client.GraphDatabase.driver')
    def test_get_driver_custom_env_vars(self, mock_driver_class):
        """Test driver creation with custom environment variables."""
        mock_driver_instance = MagicMock()
        mock_driver_class.return_value = mock_driver_instance

        env_vars = {
            'NEO4J_URI': 'bolt://neo4j-prod:7687',
            'NEO4J_USER': 'admin',
            'NEO4J_PASSWORD': 'secretpassword'
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_driver()

            mock_driver_class.assert_called_once_with(
                'bolt://neo4j-prod:7687',
                auth=('admin', 'secretpassword')
            )
            assert result == mock_driver_instance

    @patch('infra.neo4j_client.GraphDatabase.driver')
    def test_get_driver_partial_env_vars(self, mock_driver_class):
        """Test driver creation with only some environment variables set."""
        mock_driver_instance = MagicMock()
        mock_driver_class.return_value = mock_driver_instance

        env_vars = {
            'NEO4J_URI': 'bolt://custom:7687'
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_driver()

            mock_driver_class.assert_called_once_with(
                'bolt://custom:7687',
                auth=('neo4j', 'neo4jpassword')
            )

    @patch('infra.neo4j_client.GraphDatabase.driver')
    def test_get_driver_neo4j_plus_uri(self, mock_driver_class):
        """Test driver creation with neo4j+s:// URI scheme."""
        mock_driver_instance = MagicMock()
        mock_driver_class.return_value = mock_driver_instance

        env_vars = {
            'NEO4J_URI': 'neo4j+s://aura.instance.io:7687',
            'NEO4J_USER': 'neo4j',
            'NEO4J_PASSWORD': 'cloud-password'
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_driver()

            mock_driver_class.assert_called_once_with(
                'neo4j+s://aura.instance.io:7687',
                auth=('neo4j', 'cloud-password')
            )


class TestSeedServiceGraph:
    """Test service graph seeding."""

    @patch('builtins.print')
    def test_seed_service_graph_creates_all_nodes(self, mock_print, mock_neo4j_driver):
        """Test that all 10 service nodes are created."""
        session = mock_neo4j_driver.session().__enter__()

        seed_service_graph(mock_neo4j_driver)

        session.run.assert_called_once()
        cypher_query = session.run.call_args[0][0]

        # Verify all service nodes are in the query
        expected_services = [
            'api-gateway', 'auth-service', 'user-service', 'order-service',
            'payment-service', 'notification-service', 'inventory-service',
            'analytics-service', 'logging-service', 'cache-service'
        ]

        for service in expected_services:
            assert service in cypher_query

        mock_print.assert_called_with("Service graph seeded successfully")

    @patch('builtins.print')
    def test_seed_service_graph_creates_depends_on_relationships(self, mock_print, mock_neo4j_driver):
        """Test that DEPENDS_ON relationships are created."""
        session = mock_neo4j_driver.session().__enter__()

        seed_service_graph(mock_neo4j_driver)

        cypher_query = session.run.call_args[0][0]

        # Verify key DEPENDS_ON relationships
        assert 'DEPENDS_ON' in cypher_query
        assert '(api)-[:DEPENDS_ON]->(auth)' in cypher_query
        assert '(order)-[:DEPENDS_ON]->(payment)' in cypher_query
        assert '(payment)-[:DEPENDS_ON]->(auth)' in cypher_query

    @patch('builtins.print')
    def test_seed_service_graph_creates_calls_relationships(self, mock_print, mock_neo4j_driver):
        """Test that CALLS relationships are created."""
        session = mock_neo4j_driver.session().__enter__()

        seed_service_graph(mock_neo4j_driver)

        cypher_query = session.run.call_args[0][0]

        # Verify CALLS relationships
        assert 'CALLS' in cypher_query
        assert '(api)-[:CALLS]->(logging)' in cypher_query
        assert '(analytics)-[:CALLS]->(user)' in cypher_query
        assert '(auth)-[:CALLS]->(cache)' in cypher_query

    @patch('builtins.print')
    def test_seed_service_graph_uses_merge(self, mock_print, mock_neo4j_driver):
        """Test that MERGE is used for idempotent operations."""
        session = mock_neo4j_driver.session().__enter__()

        seed_service_graph(mock_neo4j_driver)

        cypher_query = session.run.call_args[0][0]

        # Verify MERGE is used instead of CREATE
        assert 'MERGE' in cypher_query
        assert 'CREATE' not in cypher_query

    @patch('builtins.print')
    def test_seed_service_graph_is_idempotent(self, mock_print, mock_neo4j_driver):
        """Test that seed_service_graph can be called multiple times."""
        session = mock_neo4j_driver.session().__enter__()

        seed_service_graph(mock_neo4j_driver)
        seed_service_graph(mock_neo4j_driver)
        seed_service_graph(mock_neo4j_driver)

        assert session.run.call_count == 3
        assert mock_print.call_count == 3

    @patch('builtins.print')
    def test_seed_service_graph_uses_session_context(self, mock_print, mock_neo4j_driver):
        """Test that session context manager is used properly."""
        seed_service_graph(mock_neo4j_driver)

        mock_neo4j_driver.session.assert_called_once()
        session = mock_neo4j_driver.session().__enter__()
        session.run.assert_called_once()

    @patch('builtins.print')
    def test_seed_service_graph_node_labels(self, mock_print, mock_neo4j_driver):
        """Test that nodes have Service label."""
        session = mock_neo4j_driver.session().__enter__()

        seed_service_graph(mock_neo4j_driver)

        cypher_query = session.run.call_args[0][0]

        # Count Service label occurrences (should be 10 for 10 services)
        assert cypher_query.count(':Service') == 10


class TestVerifyGraph:
    """Test graph verification."""

    @patch('builtins.print')
    def test_verify_graph_counts_nodes_and_relationships(self, mock_print, mock_neo4j_driver):
        """Test that verify_graph queries node and relationship counts."""
        session = mock_neo4j_driver.session().__enter__()

        # Mock query results
        node_result = MagicMock()
        node_result.single.return_value = {'count': 10}

        rel_result = MagicMock()
        rel_result.single.return_value = {'count': 11}

        session.run.side_effect = [node_result, rel_result]

        verify_graph(mock_neo4j_driver)

        assert session.run.call_count == 2

        # Verify node count query
        node_query = session.run.call_args_list[0][0][0]
        assert 'MATCH (n:Service)' in node_query
        assert 'count(n)' in node_query

        # Verify relationship count query
        rel_query = session.run.call_args_list[1][0][0]
        assert 'MATCH ()-[r]->()' in rel_query
        assert 'count(r)' in rel_query

        mock_print.assert_called_with("Graph verification: 10 nodes, 11 relationships")

    @patch('builtins.print')
    def test_verify_graph_empty_graph(self, mock_print, mock_neo4j_driver):
        """Test verify_graph with empty graph."""
        session = mock_neo4j_driver.session().__enter__()

        node_result = MagicMock()
        node_result.single.return_value = {'count': 0}

        rel_result = MagicMock()
        rel_result.single.return_value = {'count': 0}

        session.run.side_effect = [node_result, rel_result]

        verify_graph(mock_neo4j_driver)

        mock_print.assert_called_with("Graph verification: 0 nodes, 0 relationships")

    @patch('builtins.print')
    def test_verify_graph_large_counts(self, mock_print, mock_neo4j_driver):
        """Test verify_graph with large node/relationship counts."""
        session = mock_neo4j_driver.session().__enter__()

        node_result = MagicMock()
        node_result.single.return_value = {'count': 1000}

        rel_result = MagicMock()
        rel_result.single.return_value = {'count': 5000}

        session.run.side_effect = [node_result, rel_result]

        verify_graph(mock_neo4j_driver)

        mock_print.assert_called_with("Graph verification: 1000 nodes, 5000 relationships")


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch('infra.neo4j_client.GraphDatabase.driver')
    def test_get_driver_with_empty_password(self, mock_driver_class):
        """Test driver creation with empty password."""
        mock_driver_instance = MagicMock()
        mock_driver_class.return_value = mock_driver_instance

        env_vars = {
            'NEO4J_PASSWORD': ''
        }

        with patch.dict(os.environ, env_vars, clear=True):
            result = get_driver()

            mock_driver_class.assert_called_once_with(
                'bolt://localhost:7687',
                auth=('neo4j', '')
            )

    @patch('builtins.print')
    def test_seed_service_graph_session_exception(self, mock_print, mock_neo4j_driver):
        """Test that exceptions from session.run are propagated."""
        session = mock_neo4j_driver.session().__enter__()
        session.run.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception, match="Database connection failed"):
            seed_service_graph(mock_neo4j_driver)

    @patch('builtins.print')
    def test_verify_graph_handles_none_results(self, mock_print, mock_neo4j_driver):
        """Test verify_graph when single() returns unexpected structure."""
        session = mock_neo4j_driver.session().__enter__()

        node_result = MagicMock()
        node_result.single.return_value = {'count': 5}

        rel_result = MagicMock()
        rel_result.single.return_value = {'count': 8}

        session.run.side_effect = [node_result, rel_result]

        verify_graph(mock_neo4j_driver)

        assert session.run.call_count == 2


class TestIntegrationScenario:
    """Test realistic usage scenarios."""

    @patch('builtins.print')
    def test_full_graph_setup_workflow(self, mock_print, mock_neo4j_driver):
        """Test complete workflow: seed and verify graph."""
        session = mock_neo4j_driver.session().__enter__()

        # Setup verify_graph mock responses
        node_result = MagicMock()
        node_result.single.return_value = {'count': 10}
        rel_result = MagicMock()
        rel_result.single.return_value = {'count': 11}

        # First call is seed, next two are verify
        session.run.side_effect = [
            MagicMock(),  # seed_service_graph
            node_result,  # verify_graph nodes
            rel_result    # verify_graph relationships
        ]

        seed_service_graph(mock_neo4j_driver)
        verify_graph(mock_neo4j_driver)

        assert session.run.call_count == 3
        assert mock_print.call_count == 2
