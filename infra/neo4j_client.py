"""Neo4j driver initialization and service dependency graph seeding."""
import os
from neo4j import GraphDatabase


def get_driver():
    """Returns a Neo4j driver authenticated with environment variables."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    user = os.environ.get('NEO4J_USER', 'neo4j')
    password = os.environ.get('NEO4J_PASSWORD', 'neo4jpassword')
    return GraphDatabase.driver(uri, auth=(user, password))


def seed_service_graph(driver):
    """Creates service nodes and DEPENDS_ON/CALLS relationships in Neo4j."""
    with driver.session() as session:
        session.run("""
            MERGE (api:Service {name: 'api-gateway'})
            MERGE (auth:Service {name: 'auth-service'})
            MERGE (user:Service {name: 'user-service'})
            MERGE (order:Service {name: 'order-service'})
            MERGE (payment:Service {name: 'payment-service'})
            MERGE (notification:Service {name: 'notification-service'})
            MERGE (inventory:Service {name: 'inventory-service'})
            MERGE (analytics:Service {name: 'analytics-service'})
            MERGE (logging:Service {name: 'logging-service'})
            MERGE (cache:Service {name: 'cache-service'})

            MERGE (api)-[:DEPENDS_ON]->(auth)
            MERGE (api)-[:DEPENDS_ON]->(order)
            MERGE (api)-[:DEPENDS_ON]->(cache)
            MERGE (order)-[:DEPENDS_ON]->(payment)
            MERGE (order)-[:DEPENDS_ON]->(inventory)
            MERGE (order)-[:DEPENDS_ON]->(notification)
            MERGE (payment)-[:DEPENDS_ON]->(auth)

            MERGE (api)-[:CALLS]->(logging)
            MERGE (analytics)-[:CALLS]->(user)
            MERGE (analytics)-[:CALLS]->(inventory)
            MERGE (auth)-[:CALLS]->(cache)
        """)
    print("Service graph seeded successfully")


def verify_graph(driver):
    """Counts and prints service nodes and relationships in the graph."""
    with driver.session() as session:
        node_count = session.run("MATCH (n:Service) RETURN count(n) as count").single()['count']
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()['count']
        print(f"Graph verification: {node_count} nodes, {rel_count} relationships")


if __name__ == "__main__":
    driver = get_driver()
    seed_service_graph(driver)
    verify_graph(driver)
    driver.close()
