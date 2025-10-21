#!/usr/bin/env python3
"""
shopify_client.py
Central GraphQL helper for the newCollectionUpsert app.
Reads SHOP_URL, SHOPIFY_ACCESS_TOKEN, API_VERSION from .env
and exposes a `ShopifyClient` class.
"""

import os, time, json, requests, re
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
        if data.get('extensions', {}).get('cost', {}).get('throttleStatus', {}).get('currentlyAvailable', 0) < 1000:
            time.sleep(2)
        return data

    def get_products_by_tag(self, tag: str) -> list:
        # ... (This function is correct and remains unchanged) ...
        print(f"Fetching all products tagged with '{tag}' from Shopify...")
        products = []
        query = """
        query getProductsByTag($query: String!, $cursor: String) {
          products(first: 250, after: $cursor, query: $query) {
            edges {
              cursor
              node {
                id
                handle
                tags
              }
            }
            pageInfo {
              hasNextPage
            }
          }
        }
        """
        hasNextPage = True
        cursor = None
        variables = {"query": f"tag:'{tag}'"}
        while hasNextPage:
            if cursor:
                variables["cursor"] = cursor
            response = self.graphql(query, variables)
            data = response.get("data", {}).get("products", {})
            for edge in data.get("edges", []):
                products.append(edge.get("node", {}))
                cursor = edge.get("cursor")
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
        print(f"Found {len(products)} products with the tag.")
        return products
    
    def get_all_smart_collection_titles(self) -> set:
        """
        Fetches all smart collection titles from Shopify.
        Returns a set of titles for quick lookup.
        """
        print("Fetching all existing smart collection titles...")
        titles = set()
        query = """
        query getSmartCollections($cursor: String) {
          collections(first: 250, after: $cursor, query: "collection_type:smart") {
            edges {
              cursor
              node {
                title
              }
            }
            pageInfo {
              hasNextPage
            }
          }
        }
        """
        hasNextPage = True
        cursor = None
        variables = {}
        
        while hasNextPage:
            if cursor:
                variables["cursor"] = cursor
            
            response = self.graphql(query, variables)
            
            if 'errors' in response:
                print("❌ GraphQL API returned errors:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break
            
            data = response.get("data", {}).get("collections", {})
            if data is None:
                print("⚠️  Warning: The 'collections' key was not found. This may be a permission issue.")
                break

            for edge in data.get("edges", []):
                node = edge.get("node", {})
                if node and "title" in node:
                    titles.add(node["title"])
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(titles)} existing smart collections.")
        return titles
    
    def get_products_for_qa(self, tag: str) -> list:
        """
        Fetches all products for a given capsule tag with all data needed for QA.
        """
        print(f"Fetching all products tagged with '{tag}' for QA...")
        products = []
        query = """
        query getProductsForQA($query: String!, $cursor: String) {
          products(first: 100, after: $cursor, query: $query) {
            edges {
              cursor
              node {
                id
                handle
                tags
                bodyHtml
                images(first: 1) {
                  edges { node { id } }
                }
                swatch_metafield: metafield(namespace: "altuzarra", key: "swatch_image") {
                  value
                }
                details_metafield: metafield(namespace: "altuzarra", key: "details") {
                  value
                }
                look_image_metafield: metafield(namespace: "altuzarra", key: "look_image") {
                  value
                }
              }
            }
            pageInfo {
              hasNextPage
            }
          }
        }
        """
        hasNextPage = True
        cursor = None
        variables = {"query": f"tag:'{tag}'"}
        
        while hasNextPage:
            if cursor:
                variables["cursor"] = cursor
            
            response = self.graphql(query, variables)
            
            if 'errors' in response:
                print("❌ GraphQL API returned errors:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break
            
            data = response.get("data", {}).get("products", {})
            if data is None:
                print("⚠️  Warning: The 'products' key was not found. This may be a permission issue.")
                break

            for edge in data.get("edges", []):
                products.append(edge.get("node", {}))
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(products)} products for QA.")
        return products

    def get_staged_uploads_map(self) -> dict:
        """
        Fetches all files from Shopify and returns a map of {filename: gid}.
        The filename key is standardized to use underscores instead of spaces.
        """
        print("Fetching existing staged files from Shopify to prevent duplicates...")
        files_map = {}
        paginated_query = """
        query($cursor: String) {
          files(first: 250, after: $cursor) {
            edges {
              cursor
              node {
                id
                ... on GenericFile {
                  url
                }
                ... on MediaImage {
                  originalSource {
                    url
                  }
                }
              }
            }
            pageInfo {
              hasNextPage
            }
          }
        }
        """
        hasNextPage = True
        cursor = None
        while hasNextPage:
            response = self.graphql(paginated_query, {"cursor": cursor})
            
            # --- DEBUGGING: Print the raw response from Shopify ---
            print("\n--- Raw GraphQL Response for Files ---")
            print(json.dumps(response, indent=2))
            print("-------------------------------------\n")
            
            # Check for top-level errors in the GraphQL response
            if 'errors' in response:
                print("❌ GraphQL API returned errors:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                # If there are errors, we likely won't have data, so stop.
                break

            files = response.get("data", {}).get("files", {})
            if files is None:
                print("⚠️  Warning: The 'files' key was not found in the API response data. This may indicate a permission issue (e.g., missing 'read_files' scope).")
                break

            for edge in files.get("edges", []):
                node = edge.get("node", {})
                
                file_url = None
                
                # Check for GenericFile url
                if "url" in node and node["url"]:
                    file_url = node["url"]
                
                # Check for MediaImage url
                elif "originalSource" in node and node["originalSource"] and "url" in node["originalSource"]:
                    file_url = node["originalSource"]["url"]

                if file_url:
                    # 1. Get filename from URL, strip query params
                    filename_from_url = file_url.split('/')[-1].split('?')[0]
                    
                    # 2. Separate name and extension
                    try:
                        name_part, extension = filename_from_url.rsplit('.', 1)
                    except ValueError:
                        # No extension or invalid format, skip
                        continue
                    
                    # 3. Regex to find and remove Shopify's UUID token
                    #    Matches _[8hex]-[4hex]-[4hex]-[4hex]-[12hex] at the end of the name
                    token_regex = r'_[a-fA-F0-9]{8}-([a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$'
                    
                    # Remove the token from the name part if it exists
                    name_part_clean = re.sub(token_regex, '', name_part)
                    
                    # 4. Re-assemble the clean filename
                    clean_filename = f"{name_part_clean}.{extension}"
                    
                    # 5. Standardize (for spaces, etc.) and add to map
                    #    Use the "clean" name as the map key
                    standardized_filename = re.sub(r'\s+', '_', clean_filename)
                    files_map[standardized_filename] = node["id"]

                cursor = edge.get("cursor")
            hasNextPage = files.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(files_map)} existing files in Shopify Content > Files.")
        return files_map

    # ------------------------------------------------------------------
    def upload_file(self, resource_url: str, alt: str) -> str:
        # ... (This function is correct and remains unchanged) ...
        mutation = """
        mutation fileCreate($files: [FileCreateInput!]!) {
          fileCreate(files: $files) {
            files { id }
            userErrors { field message }
          }
        }
        """
        variables = {"files": {"alt": alt, "contentType": "IMAGE_JPEG", "originalSource": resource_url}}
        resp = self.graphql(mutation, variables)
        return resp["data"]["fileCreate"]["files"][0]["id"]
        
    def wait_for_file_ready(self, file_gid: str, timeout: int = 30) -> str:
        # ... (This function is correct and remains unchanged) ...
        print(f"Simulating wait for file {file_gid} to be ready...")
        time.sleep(2)
        return f"https://cdn.shopify.com/s/files/1/0148/9561/2004/files/SIMULATED_URL.jpg"

    def set_product_metafield(self, product_gid: str, key: str, value_gid: str, namespace: str = "altuzarra", field_type: str = "file_reference"):
        # ... (This function is correct and remains unchanged) ...
        mutation = """
        mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            metafields { key namespace type value }
            userErrors { field message }
          }
        }"""
        variables = {"metafields": [{"ownerId": product_gid, "namespace": namespace, "key": key, "type": field_type, "value": value_gid}]}
        return self.graphql(mutation, variables)

    def create_smart_collection(self, title: str, tag: str) -> dict:
        # ... (This function is correct and remains unchanged) ...
        mutation = """
        mutation collectionCreate($input: CollectionInput!) {
          collectionCreate(input: $input) {
            collection { id handle title }
            userErrors { field message }
          }
        }"""
        variables = {"input": {"title": title, "handle": title.lower().replace(" ", "-"), "ruleSet": {"appliedDisjunctively": False, "rules": [{"column": "TAG", "relation": "EQUALS", "condition": tag}]}, "sortOrder": "BEST_SELLING"}}
        return self.graphql(mutation, variables)