#!/usr/bin/env python3
"""
shopify_client.py
Central GraphQL helper for the newCollectionUpsert app.
Reads SHOP_URL, SHOPIFY_ACCESS_TOKEN, API_VERSION from .env
and exposes a `ShopifyClient` class.
"""

import os, time, json, requests
from dotenv import load_dotenv

load_dotenv()


class ShopifyClient:
    def __init__(self):
        self.shop_url = os.getenv("SHOP_URL", "").rstrip("/")
        self.token = os.getenv("SHOPIFY_ACCESS_TOKEN")
        self.api_version = os.getenv("API_VERSION", "2025-10")
        if not all([self.shop_url, self.token]):
            raise EnvironmentError("Missing SHOP_URL or SHOPIFY_ACCESS_TOKEN in .env")

        self.endpoint = f"{self.shop_url}/admin/api/{self.api_version}/graphql.json"
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.token,
        })

    # ------------------------------------------------------------------
    def graphql(self, query: str, variables: dict | None = None):
        """Perform a GraphQL POST with simple retry + throttle awareness."""
        payload = {"query": query, "variables": variables or {}}
        resp = self.session.post(self.endpoint, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"GraphQL HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {json.dumps(data['errors'], indent=2)}")

        cost = (
            data.get("extensions", {})
            .get("cost", {})
            .get("throttleStatus", {})
            .get("currentlyAvailable", 0)
        )
        if cost < 500:  # low throttle balance
            time.sleep(2)
        return data["data"]

    # ------------------------------------------------------------------
    def upload_file(self, source_url: str, alt_text: str) -> str:
        """Uploads an image to Shopify Files → returns MediaImage GID."""
        mutation = """
        mutation fileCreate($files: [FileCreateInput!]!) {
          fileCreate(files: $files) {
            files {
              id
              alt
              fileStatus
              preview { image { url } }
            }
            userErrors { field message }
          }
        }"""
        variables = {
            "files": [{
                "originalSource": source_url,
                "contentType": "IMAGE",
                "alt": alt_text
            }]
        }
        data = self.graphql(mutation, variables)
        node = data["fileCreate"]["files"][0]
        return node["id"]

    # ------------------------------------------------------------------
    def wait_for_file_ready(self, file_gid: str, timeout: int = 60) -> str:
        """Polls until fileStatus == READY → returns URL."""
        query = """
        query($id: ID!) {
          node(id: $id) {
            ... on MediaImage {
              fileStatus
              preview { image { url } }
            }
          }
        }"""
        for _ in range(timeout // 3):
            data = self.graphql(query, {"id": file_gid})
            node = data["node"]
            if node and node["fileStatus"] == "READY":
                return node["preview"]["image"]["url"]
            time.sleep(3)
        raise TimeoutError(f"File {file_gid} never reached READY status")

    # ------------------------------------------------------------------
    def set_product_metafield(self, product_gid: str, key: str,
                              value_gid: str, field_type: str = "file_reference",
                              namespace: str = "altuzarra"):
        """Attach a file_reference metafield to a product."""
        mutation = """
        mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            metafields { key namespace type value }
            userErrors { field message }
          }
        }"""
        variables = {
            "metafields": [{
                "ownerId": product_gid,
                "namespace": namespace,
                "key": key,
                "type": field_type,
                "value": value_gid
            }]
        }
        return self.graphql(mutation, variables)

    # ------------------------------------------------------------------
    def create_smart_collection(self, title: str, tag: str) -> dict:
        """Creates a smart collection for style_tag if it doesn't exist."""
        mutation = """
        mutation collectionCreate($input: CollectionInput!) {
          collectionCreate(input: $input) {
            collection { id handle title }
            userErrors { field message }
          }
        }"""
        variables = {
            "input": {
                "title": title,
                "handle": title.lower().replace(" ", "-"),
                "ruleSet": {
                    "appliedDisjunctively": False,
                    "rules": [{
                        "column": "TAG",
                        "relation": "EQUALS",
                        "condition": tag
                    }]
                },
                "sortOrder": "BEST_SELLING"
            }
        }
        return self.graphql(mutation, variables)
