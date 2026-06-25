#!/usr/bin/env python3
"""Clean and manage Weaviate PastIncident collection."""
import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import dotenv_values
from google import genai
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from infra.weaviate_client import get_client, init_schema, close_client


_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "past_incidents.json"


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception(lambda e: isinstance(e, ClientError) and e.code == 429),
    reraise=True,
)
def _embed_text(genai_client, text: str) -> list[float]:
    """Embed text using Gemini with exponential backoff retry on rate limits."""
    result = genai_client.models.embed_content(
        model="models/gemini-embedding-001", contents=text
    )
    return result.embeddings[0].values


def main():
    """Parse CLI args and execute --list, --delete, or --wipe-and-reseed on PastIncident collection."""
    env_vars = dotenv_values()
    for k, v in env_vars.items():
        if k not in os.environ or not os.environ[k]:
            os.environ[k] = v

    parser = argparse.ArgumentParser(description="Manage Weaviate PastIncident collection")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all incidents in Weaviate")
    group.add_argument("--delete", nargs="+", metavar="UUID", help="Delete incidents by UUID")
    group.add_argument("--wipe-and-reseed", action="store_true", help="Wipe all data and reseed from JSON")

    args = parser.parse_args()

    if args.list:
        client = None
        try:
            client = get_client()
            collection = client.collections.get("PastIncident")
            response = collection.query.fetch_objects(limit=1000)
            objects = response.objects
            print(f"{'UUID':<40}  {'Title':<50}  Fix")
            print("-" * 180)
            for obj in objects:
                uuid = str(obj.uuid)
                title = obj.properties.get("title", "")[:50]
                fix = obj.properties.get("fix", "")[:80]
                print(f"{uuid:<40}  {title:<50}  {fix}")
            if len(objects) == 1000:
                print("Warning: result count equals limit (1000); there may be more entries")
        finally:
            if client:
                close_client(client)

    elif args.delete:
        client = None
        try:
            client = get_client()
            collection = client.collections.get("PastIncident")
            for uuid in args.delete:
                try:
                    collection.data.delete_by_id(uuid)
                    print(f"Deleted: {uuid}")
                except Exception as e:
                    print(f"Error deleting {uuid}: {e}")
        finally:
            if client:
                close_client(client)

    elif args.wipe_and_reseed:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable is required")
            sys.exit(1)

        confirmation = input("This will DELETE all PastIncident data and reseed. Type 'yes' to confirm: ")
        if confirmation != "yes":
            print("Aborted.")
            sys.exit(0)

        try:
            with open(_JSON_PATH) as f:
                incidents = json.load(f)
        except FileNotFoundError:
            print(f"Error: {_JSON_PATH} not found")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: {_JSON_PATH} is not valid JSON: {e}")
            sys.exit(1)

        required_fields = {"title", "root_cause", "fix", "service"}
        for entry in incidents:
            missing = required_fields - set(entry.keys())
            if missing:
                print(f"Error: past_incidents.json entry missing fields: {missing}")
                sys.exit(1)

        client = None
        try:
            client = get_client()
            try:
                client.collections.delete("PastIncident")
                print("Deleted PastIncident collection")
            except Exception as e:
                print(f"Warning during deletion: {e}")

            init_schema(client)
            genai.configure(api_key=os.environ["GEMINI_API_KEY"])
            genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

            collection = client.collections.get("PastIncident")
            for incident in incidents:
                text = f"{incident['title']}. {incident['root_cause']}. {incident['fix']}"
                vector = _embed_text(genai_client, text)
                collection.data.insert(properties=incident, vector=vector)

            print(f"Reseeded {len(incidents)} incidents.")
        finally:
            if client:
                close_client(client)


if __name__ == "__main__":
    main()
