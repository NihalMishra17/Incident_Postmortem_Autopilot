"""Weaviate client and schema management for incident embedding storage."""
import weaviate
from weaviate.classes.config import Configure, Property, DataType, VectorDistances


def get_client(host='localhost', port=8080):
    """Returns a connected Weaviate client."""
    return weaviate.connect_to_local(host=host, port=port)


def init_schema(client):
    """Creates PastIncident collection with schema for incident metadata and embeddings."""
    if client.collections.exists("PastIncident"):
        print("PastIncident collection already exists, skipping creation")
        return

    client.collections.create(
        name="PastIncident",
        properties=[
            Property(name="title", data_type=DataType.TEXT),
            Property(name="root_cause", data_type=DataType.TEXT),
            Property(name="fix", data_type=DataType.TEXT),
            Property(name="service", data_type=DataType.TEXT),
        ],
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
            # Expects vectors from gemini-embedding-001; dimension inferred on first insert
        ),
    )
    print("PastIncident collection created")


def close_client(client):
    client.close()


if __name__ == "__main__":
    client = get_client()
    init_schema(client)
    print("Weaviate schema initialized successfully")
    close_client(client)
