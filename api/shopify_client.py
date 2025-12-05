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

    # ... (get_products_by_tag, get_all_smart_collection_titles can remain as-is) ...

    def get_products_by_tag(self, tag: str) -> list:
        """
        Fetches all products tagged with 'tag' from Shopify.
        This function is used by other scripts, so we keep its prints.
        """
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
    
    def get_all_smart_collections(self) -> list:
        """
        Fetches all smart collections from Shopify.
        Returns a list of collection dictionaries (e.g., [{'id': ..., 'title': ...}]).
        """
        print("Fetching all smart collection objects (ID, Title, Handle)...")
        collections = []
        query = """
        query getSmartCollections($cursor: String) {
          collections(first: 250, after: $cursor, query: "collection_type:smart") {
            edges {
              cursor
              node {
                id
                title
                handle
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
                if node and "id" in node and "title" in node:
                    collections.append(node) # Append the whole node dictionary
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(collections)} existing smart collections.")
        return collections
    
    def delete_smart_collection(self, collection_gid: str) -> dict:
        """
        Deletes a collection given its GID.
        """
        mutation = """
        mutation collectionDelete($input: CollectionDeleteInput!) {
          collectionDelete(input: $input) {
            deletedCollectionId
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {"input": {"id": collection_gid}}
        response = self.graphql(mutation, variables)
        
        # Check for errors
        data = response.get("data", {}).get("collectionDelete", {})
        user_errors = data.get("userErrors", [])
        if user_errors:
            # Raise an error so the calling script can catch it
            raise RuntimeError(f"Failed to delete {collection_gid}: {user_errors[0]['message']}")
        
        return data
    
    def get_all_smart_collections_with_publication_status(self, store_pub_id: str, pos_pub_id: str) -> list:
        """
        Fetches all ACTIVE smart collections, checking publication status
        against *specific* channel IDs.
        Returns a list of collection dictionaries.
        """
        print("Fetching all ACTIVE smart collection objects (ID, Title, Handle, specific Publications)...")
        collections = []
        # Query is parameterized with the publication IDs AND status:active
        query = """
        query getSmartCollections($cursor: String, $storePubId: ID!, $posPubId: ID!) {
          collections(first: 100, after: $cursor, query: "collection_type:smart AND status:active") {
            edges {
              cursor
              node {
                id
                title
                handle
                isPublishedOnStore: publishedOnPublication(publicationId: $storePubId)
                isPublishedOnPOS: publishedOnPublication(publicationId: $posPubId)
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
        # Add the IDs to the variables
        variables = {"storePubId": store_pub_id, "posPubId": pos_pub_id}
        
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
                if node and "id" in node and "title" in node:
                    # 'status' field is no longer here, which is correct
                    collections.append(node) # Append the node dictionary
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(collections)} existing active smart collections with publication data.")
        return collections

    def get_publication_ids(self, names: list) -> dict:
        """
        Fetches all publications and returns a dict mapping names to GIDs
        for the names specified in the list.
        """
        print(f"Fetching Publication IDs for: {', '.join(names)}...")
        publication_map = {}
        target_names = {name.lower() for name in names}
        
        query = """
        query getPublications($cursor: String) {
          publications(first: 25, after: $cursor) {
            edges {
              cursor
              node {
                id
                name
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
                print("❌ GraphQL API returned errors fetching publications:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break

            data = response.get("data", {}).get("publications", {})
            if data is None:
                print("⚠️  Warning: The 'publications' key was not found. (Missing 'read_publications' scope?)")
                break
                
            for edge in data.get("edges", []):
                node = edge.get("node", {})
                if node and node.get("name", "").lower() in target_names:
                    publication_map[node["name"]] = node["id"]
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
            # Stop if we've found all we need
            if all(name in publication_map for name in names):
                hasNextPage = False

        return publication_map

    def publish_collection(self, collection_gid: str, publication_inputs: list, store_pub_id: str, pos_pub_id: str):
        """
        Publishes a collection to a list of publications using the
        ADDITIVE 'publishablePublish' mutation and verifies the result.
        
        publication_inputs is the list of {publicationId: "gid"} to ADD.
        """
        
        mutation = """
        mutation publishablePublish($id: ID!, $input: [PublicationInput!]!, $storePubId: ID!, $posPubId: ID!) {
          publishablePublish(id: $id, input: $input) {
            publishable {
              ... on Collection {
                id
                # Re-check the status *after* the mutation
                isPublishedOnStore: publishedOnPublication(publicationId: $storePubId)
                isPublishedOnPOS: publishedOnPublication(publicationId: $posPubId)
              }
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {
            "id": collection_gid,
            "input": publication_inputs, # This is the list of channels to ADD
            "storePubId": store_pub_id,    # Pass in the IDs for re-checking
            "posPubId": pos_pub_id
        }
        
        response = self.graphql(mutation, variables)
        
        # Check for userErrors first
        data = response.get("data", {}).get("publishablePublish", {})
        user_errors = data.get("userErrors", [])
        if user_errors:
            raise RuntimeError(f"Failed to publish {collection_gid}: {user_errors[0]['message']}")
            
        # --- NEW SUCCESS CHECK ---
        # If no userErrors, check that the 'publishable' object was
        # actually returned and that the new statuses are true.
        publishable_data = data.get("publishable")
        if not publishable_data:
            raise RuntimeError(f"API call succeeded but returned no publishable object for {collection_gid}. (This is a silent failure, check API scopes for 'write_publications'.)")

        # Check which channels we *tried* to publish to
        channels_we_tried_to_publish = [p["publicationId"] for p in publication_inputs]

        # Check Online Store status
        if store_pub_id in channels_we_tried_to_publish and not publishable_data.get("isPublishedOnStore"):
            raise RuntimeError(f"API reported success but collection is NOT published to Online Store.")
            
        # Check POS status
        if pos_pub_id in channels_we_tried_to_publish and not publishable_data.get("isPublishedOnPOS"):
            raise RuntimeError(f"API reported success but collection is NOT published to Point of Sale.")
        # --- END NEW SUCCESS CHECK ---

        return data
    
    # ------------------------------------------------------------------
    # --- get_products_for_qa (Used by qa_tracker) ---
    # ------------------------------------------------------------------
    
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

    # ------------------------------------------------------------------
    # --- get_staged_uploads_map (Used by pre_upload & upserter) ---
    # ------------------------------------------------------------------
    
    def get_staged_uploads_map(self, verbose: bool = False) -> dict:
        """
        Fetches all files from Shopify and returns a map of {filename: gid}.
        The filename key is standardized to use underscores instead of spaces.
        """
        if verbose:
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
            
            if verbose:
                print("\n--- Raw GraphQL Response for Files ---")
                print(json.dumps(response, indent=2))
                print("-------------------------------------\n")
            
            if 'errors' in response:
                print("❌ GraphQL API returned errors:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break

            files = response.get("data", {}).get("files", {})
            if files is None:
                print("⚠️  Warning: The 'files' key was not found in the API response data. (Missing 'read_files' scope?)")
                break

            for edge in files.get("edges", []):
                node = edge.get("node", {})
                
                file_url = None
                
                if "url" in node and node["url"]:
                    file_url = node["url"]
                elif "originalSource" in node and node["originalSource"] and "url" in node["originalSource"]:
                    file_url = node["originalSource"]["url"]

                if file_url:
                    filename_from_url = file_url.split('/')[-1].split('?')[0]
                    
                    try:
                        name_part, extension = filename_from_url.rsplit('.', 1)
                    except ValueError:
                        continue
                    
                    token_regex = r'_[a-fA-F0-9]{8}-([a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$'
                    name_part_clean = re.sub(token_regex, '', name_part)
                    clean_filename = f"{name_part_clean}.{extension}"
                    fixed_filename = clean_filename.replace('_20', ' ')
                    standardized_filename = re.sub(r'\s+', '_', fixed_filename)
                    files_map[standardized_filename] = node["id"]

                cursor = edge.get("cursor")
            hasNextPage = files.get("pageInfo", {}).get("hasNextPage", False)
            
        if verbose:
            print(f"Found {len(files_map)} existing files in Shopify Content > Files.")
        return files_map

    def get_staged_uploads_map_with_urls(self) -> dict:
        """
        Fetches all files from Shopify and returns a map of {standardized_filename: cdn_url}.
        Used by pre_upload_images.py.
        """
        print("Fetching existing staged files with CDN URLs from Shopify...")
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
                  image {           # <-- ADD THIS BLOCK
                    url
                  }                 # <-- ADD THIS BLOCK
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
            
            if 'errors' in response:
                print("❌ GraphQL API returned errors:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break

            files = response.get("data", {}).get("files", {})
            if files is None:
                print("⚠️  Warning: The 'files' key was not found. (Missing 'read_files' scope?)")
                break

            for edge in files.get("edges", []):
                node = edge.get("node", {})
                
                file_url = None
                
                # 1. Try to get the canonical MediaImage URL
                if "image" in node and node.get("image") and node["image"].get("url"):
                    file_url = node["image"]["url"]
                
                # 2. Fallback to GenericFile URL
                elif "url" in node and node.get("url"):
                    file_url = node["url"]
                
                # 3. Fallback to originalSource (old behavior, wrong URL)
                elif "originalSource" in node and node.get("originalSource") and node["originalSource"].get("url"):
                    file_url = node["originalSource"]["url"]

                if file_url:
                    filename_from_url = file_url.split('/')[-1].split('?')[0]
                    
                    try:
                        name_part, extension = filename_from_url.rsplit('.', 1)
                    except ValueError:
                        continue
                    
                    token_regex = r'_[a-fA-F0-9]{8}-([a-fA-F0-9]{4}-){3}[a-fA-F0-9]{12}$'
                    name_part_clean = re.sub(token_regex, '', name_part)
                    clean_filename = f"{name_part_clean}.{extension}"
                    
                    fixed_filename = clean_filename.replace('_20', ' ')
                    standardized_filename = re.sub(r'\s+', '_', fixed_filename)
                    files_map[standardized_filename] = file_url.split('?')[0]

                cursor = edge.get("cursor")
            hasNextPage = files.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(files_map)} existing files with CDN URLs.")
        return files_map

    # ------------------------------------------------------------------
    # --- File Upload & Metafield Functions (Used by pre_upload & writer) ---
    # ------------------------------------------------------------------

    def upload_file(self, resource_url: str, alt: str) -> str:
        # ... (This function can remain as-is) ...
        mutation = """
        mutation fileCreate($files: [FileCreateInput!]!) {
          fileCreate(files: $files) {
            files { 
              id
              fileStatus
            }
            userErrors { field message }
          }
        }
        """
        variables = {"files": {"alt": alt, "contentType": "IMAGE", "originalSource": resource_url}}
        resp = self.graphql(mutation, variables)
        
        if 'errors' in resp:
            error_message = resp['errors'][0]['message']
            raise RuntimeError(f"GraphQL API Error: {error_message}")

        user_errors = resp.get("data", {}).get("fileCreate", {}).get("userErrors", [])
        if user_errors:
            raise RuntimeError(f"Error creating file: {user_errors[0]['message']}")
            
        file_data = resp["data"]["fileCreate"]["files"][0]
        
        if file_data["fileStatus"] == "READY":
            return file_data["id"]
        
        return file_data["id"]
        
    def wait_for_file_ready(self, file_gid: str, timeout: int = 60) -> str:
        # ... (This function can remain as-is) ...
        print(f"  > Waiting for file {file_gid} to be 'READY'...")
        start_time = time.time()
        
        query = """
        query checkFileStatus($id: ID!) {
          node(id: $id) {
            ... on File {
              fileStatus
              ... on MediaImage {
                image {
                  url
                }
                originalSource { url }
              }
              ... on GenericFile {
                url
              }
            }
          }
        }
        """
        variables = {"id": file_gid}
        
        while time.time() - start_time < timeout:
            resp = self.graphql(query, variables)
            node = resp.get("data", {}).get("node", {})
            
            if not node:
                raise RuntimeError(f"Could not find file {file_gid} during polling.")

            status = node.get("fileStatus")
            
            if status == "READY":
                cdn_url = None
                
                # 1. Try to get the canonical MediaImage URL (e.g., cdn.shopify.com/...)
                if "image" in node and node["image"] and "url" in node["image"]:
                    cdn_url = node["image"]["url"]
                
                # 2. Fallback to GenericFile URL (for non-image files)
                elif "url" in node and node["url"]:
                    cdn_url = node["url"]
                
                # 3. Fallback to originalSource (old behavior, wrong URL)
                elif "originalSource" in node and node["originalSource"] and "url" in node["originalSource"]:
                    cdn_url = node["originalSource"]["url"]
                    print(f"  > ⚠️  File is 'READY' but using originalSource URL.")

                if cdn_url:
                    print(f"  > File is 'READY'.")
                    # Strip query params like ?v=... from the final URL
                    return cdn_url.split('?')[0]
                else:
                    raise RuntimeError(f"File {file_gid} is READY but no URL was found.")

            elif status == "FAILED":
                raise RuntimeError(f"File processing FAILED for {file_gid}.")
            
            time.sleep(2)
        
        raise TimeoutError(f"Timed out waiting for file {file_gid} to become ready.")

    def set_product_metafield(self, product_gid: str, key: str, value_gid: str, namespace: str = "altuzarra", field_type: str = "file_reference"):
        # ... (This function can remain as-is) ...
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
        # ... (This function can remain as-is) ...
        mutation = """
        mutation collectionCreate($input: CollectionInput!) {
          collectionCreate(input: $input) {
            collection { id handle title }
            userErrors { field message }
          }
        }"""
        variables = {"input": {"title": title, "handle": title.lower().replace(" ", "-"), "ruleSet": {"appliedDisjunctively": False, "rules": [{"column": "TAG", "relation": "EQUALS", "condition": tag}]}, "sortOrder": "BEST_SELLING"}}
        return self.graphql(mutation, variables)
    
    # ------------------------------------------------------------------
    # --- Size Guide Functions (Used by other scripts) ---
    # ------------------------------------------------------------------

    def get_size_guide_pages_map(self) -> dict:
        # ... (This function can remain as-is) ...
        print("Fetching all pages from Shopify to find 'Size Guides'...")
        page_map = {}
        query = """
        query getPages($cursor: String) {
          pages(first: 250, after: $cursor) {
            edges {
              cursor
              node {
                id
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
                print("❌ GraphQL API returned errors fetching pages:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break
            
            data = response.get("data", {}).get("pages", {})
            if data is None:
                print("⚠️  Warning: The 'pages' key was not found. (Missing 'read_online_store_pages' scope?)")
                break

            for edge in data.get("edges", []):
                node = edge.get("node", {})
                
                if node and node["title"].startswith("Size Guide"):
                    base_title = node["title"].replace("Size Guide", "").strip()
                    product_type = base_title.split(' - ')[0].strip() 
                    
                    if product_type:
                        page_map[product_type] = node["id"]
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(page_map)} size guide pages and mapped them to product types.")
        return page_map
    
    def get_products_with_type(self, tag: str) -> list:
        # ... (This function can remain as-is) ...
        print(f"Fetching all products and types for capsule '{tag}'...")
        products = []
        query = """
        query getProductsWithType($query: String!, $cursor: String) {
          products(first: 250, after: $cursor, query: $query) {
            edges {
              cursor
              node {
                id
                handle
                productType
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
                print("❌ GraphQL API returned errors fetching products:")
                for error in response['errors']:
                    print(f"  - {error.get('message')}")
                break
            
            data = response.get("data", {}).get("products", {})
            if data is None:
                print("⚠️  Warning: The 'products' key was not found.")
                break

            for edge in data.get("edges", []):
                products.append(edge.get("node", {}))
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        print(f"Found {len(products)} products in capsule '{tag}'.")
        return products

    # ------------------------------------------------------------------
    # --- NEW FUNCTIONS FOR PRODUCT UPSERTER ---
    # ------------------------------------------------------------------
    
    def get_products_for_upsert(self, tag: str, verbose: bool = False) -> dict:
        """
        Fetches all products for a given tag and returns a map of
        {handle: {'gid': '...', 'media_gids': [...]}}.
        """
        if verbose:
            print(f"Fetching product GIDs, handles, and media for tag '{tag}'...")
        product_map = {}
        query = """
        query getProductsForUpsert($query: String!, $cursor: String) {
          products(first: 100, after: $cursor, query: $query) {
            edges {
              cursor
              node {
                id
                handle
                media(first: 50) {
                  edges {
                    node {
                      id
                    }
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
        variables = {"query": f"tag:'{tag}'"}
        
        while hasNextPage:
            if cursor:
                variables["cursor"] = cursor
            
            response = self.graphql(query, variables)
            data = response.get("data", {}).get("products", {})
            
            for edge in data.get("edges", []):
                node = edge.get("node", {})
                if node.get("handle") and node.get("id"):
                    
                    # Extract the list of media GIDs
                    media_gids = [
                        media_edge['node']['id'] 
                        for media_edge in node.get('media', {}).get('edges', [])
                    ]
                    
                    product_map[node["handle"]] = {
                        "gid": node["id"],
                        "media_gids": media_gids
                    }
                cursor = edge.get("cursor")
            
            hasNextPage = data.get("pageInfo", {}).get("hasNextPage", False)
            
        if verbose:
            print(f"Found {len(product_map)} products.")
        return product_map

    def delete_product_media(self, product_gid: str, media_gids: list, dry_run: bool = False, verbose: bool = False):
        """
        Deletes all specified media from a product using the
        productDeleteMedia mutation.
        """
        mutation = """
        mutation productDeleteMedia($productId: ID!, $mediaIds: [ID!]!) {
          productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
            deletedMediaIds
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {"productId": product_gid, "mediaIds": media_gids}

        if dry_run:
            print(f"  > [DRY RUN] Would delete {len(media_gids)} existing media items.")
            if verbose:
                print(json.dumps(variables, indent=4))
            return
            
        response = self.graphql(mutation, variables)
        
        if 'errors' in response:
            raise RuntimeError(f"GraphQL Error: {response['errors']}")
            
        delete_data = response.get("data", {}).get("productDeleteMedia", {})
        
        if delete_data.get("userErrors"):
            errors = delete_data["userErrors"]
            error_msgs = [f"({e['field']}: {e['message']})" for e in errors]
            raise RuntimeError(f"Media Delete Error: {', '.join(error_msgs)}")
        
        if verbose:
            print(f"  > 🖼️  Deleted {len(delete_data.get('deletedMediaIds', []))} old media items.")
    
    def create_product_media(self, product_gid: str, file_gids: list, dry_run: bool = False, verbose: bool = False):
        """
        Creates new media (images) on a product from a list of
        File GIDs (e.g., "gid://shopify/File/123...").
        """
        
        # Convert File GIDs into the 'CreateMediaInput' format
        media_input_list = [
            {"mediaContentType": "IMAGE", "originalSource": gid}
            for gid in file_gids
        ]
        
        mutation = """
        mutation productCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
          productCreateMedia(productId: $productId, media: $media) {
            media {
              id
              status
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {"productId": product_gid, "media": media_input_list}

        if dry_run:
            print(f"  > [DRY RUN] Would create {len(media_input_list)} new media items from File GIDs.")
            if verbose:
                print(json.dumps(variables, indent=4))
            return
            
        response = self.graphql(mutation, variables)
        
        if 'errors' in response:
            raise RuntimeError(f"GraphQL Error: {response['errors']}")
            
        create_data = response.get("data", {}).get("productCreateMedia", {})
        
        if create_data.get("userErrors"):
            errors = create_data["userErrors"]
            error_msgs = [f"({e['field']}: {e['message']})" for e in errors]
            if "originalSource" in error_msgs[0] and ("processing failed" in error_msgs[0] or "File is invalid" in error_msgs[0]):
                raise RuntimeError(f"Media Create Error: Shopify failed to process the File GID. {error_msgs[0]}")
            raise RuntimeError(f"Media Create Error: {', '.join(error_msgs)}")

        # --- START POLLING LOGIC ---
        created_media_info = create_data.get('media', [])
        if not created_media_info:
            print("  > ⚠️ Warning: productCreateMedia returned no media items.")
            return # Nothing to poll

        media_ids_to_poll = [m['id'] for m in created_media_info if m.get('id')]

        if not media_ids_to_poll:
                print("  > ⚠️ Warning: productCreateMedia returned media items without IDs.")
                return

        if verbose:
                print(f"  > Polling status for {len(media_ids_to_poll)} new media items...")

        start_time = time.time()
        timeout = 120 # 2 minutes
        pending_ids = set(media_ids_to_poll)
        failed_ids = set()
        ready_ids = set()

        poll_query = """
        query checkMediaStatus($ids: [ID!]!) {
            nodes(ids: $ids) {
            ... on MediaImage {
                id
                status
            }
            }
        }
        """
        
        while pending_ids and (time.time() - start_time < timeout):
            time.sleep(3) # Wait between polls
            try:
                poll_resp = self.graphql(poll_query, {"ids": list(pending_ids)})
                nodes = poll_resp.get("data", {}).get("nodes", [])

                if not nodes:
                        if verbose: print("  > Polling: No node data returned yet...")
                        continue

                for node in nodes:
                    if not node or 'id' not in node or 'status' not in node:
                            continue

                    media_id = node['id']
                    status = node['status']
                    
                    if media_id not in pending_ids:
                        continue 

                    if status == 'READY':
                        ready_ids.add(media_id)
                        pending_ids.remove(media_id)
                    elif status == 'FAILED':
                        failed_ids.add(media_id)
                        pending_ids.remove(media_id)
                        if verbose: print(f"    - {media_id} -> FAILED")
                    elif status == 'PROCESSING' or status == 'UPLOADING':
                        pass # Still waiting
                    else:
                        print(f"    - {media_id} -> UNEXPECTED STATUS: {status}")
                        failed_ids.add(media_id)
                        pending_ids.remove(media_id)

            except Exception as poll_e:
                print(f"  > ❌ Error during media status polling: {poll_e}")
                break 

        # --- REPORTING ---
        if pending_ids: # Timed out
                print(f"  > ⚠️ Timeout: {len(pending_ids)} media items did not become READY or FAILED within {timeout}s.")
                failed_ids.update(pending_ids)

        if failed_ids:
                raise RuntimeError(f"Media Create Failed: {len(failed_ids)} media item(s) failed processing. Failed IDs: {', '.join(failed_ids)}")
        
        if verbose or not failed_ids:
                print(f"  > 🖼️  Successfully processed {len(ready_ids)} new media items.")
        # --- END POLLING LOGIC ---

    def update_product(self, product_input: dict, dry_run: bool = False, verbose: bool = False):
        """
        Performs a productUpdate mutation.
        The input_payload must be a dict containing the product 'id'
        and any fields to update (e.g., 'tags').
        """
        mutation = """
        mutation productUpdate($input: ProductInput!) {
          productUpdate(input: $input) {
            product {
              id
              handle
              tags
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        variables = {"input": product_input}

        if dry_run:
            print("  > [DRY RUN] Would execute productUpdate.")
            if verbose:
                print(json.dumps(variables, indent=4))
            return
            
        response = self.graphql(mutation, variables)
        
        if 'errors' in response:
            raise RuntimeError(f"GraphQL Error: {response['errors']}")
            
        update_data = response.get("data", {}).get("productUpdate", {})
        
        if update_data.get("userErrors"):
            errors = update_data["userErrors"]
            error_msgs = [f"({e['field']}: {e['message']})" for e in errors]
            raise RuntimeError(f"Product Update Error: {', '.join(error_msgs)}")
        
        if verbose:
            print("  > productUpdate mutation successful.")


    def set_string_metafield(self, owner_gid: str, namespace: str, key: str, value: str, dry_run: bool = False, verbose: bool = False):
        """
        Sets a 'string' type metafield on any object (e.g., Product).
        """
        mutation = """
        mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            metafields {
              id
              key
              namespace
              value
            }
            userErrors {
              field
              message
            }
          }
        }
        """
        metafield_input = {
            "ownerId": owner_gid,
            "namespace": namespace,
            "key": key,
            "type": "string", # Hardcoded to 'string' for this function
            "value": value
        }
        variables = {"metafields": [metafield_input]}
        
        if dry_run:
            print("  > [DRY RUN] Would execute metafieldsSet for string.")
            if verbose:
                print(json.dumps(variables, indent=4))
            return

        response = self.graphql(mutation, variables)

        if 'errors' in response:
            raise RuntimeError(f"GraphQL Error: {response['errors']}")
            
        set_data = response.get("data", {}).get("metafieldsSet", {})
        
        if set_data.get("userErrors"):
            errors = set_data["userErrors"]
            error_msgs = [f"({e['field']}: {e['message']})" for e in errors]
            raise RuntimeError(f"Metafield Set Error: {', '.join(error_msgs)}")

        if verbose:
            print("  > metafieldsSet (string) mutation successful.")