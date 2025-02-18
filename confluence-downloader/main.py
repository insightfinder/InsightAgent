import os
import json
import requests
import re
import yaml

# Read configurations
with open("config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)
CONFLUENCE_URL = config["confluence_url"]
SPACE_KEY = config["space_key"]
USERNAME = config["username"]
API_TOKEN = config["api_token"]
SAVE_DIRECTORY = config.get("save_directory", "confluence_pages_v2")
PAGE_LIMIT = config.get("page_limit", 25)


def fetch_all_pages_in_space_v2(url, space_key, auth, limit=PAGE_LIMIT):
    """
    Fetch a list of page objects for a Confluence space using the v2 endpoint.
    Returns a list of dictionaries, each representing a page (including its ID and title).
    """
    pages = []
    # The initial endpoint URL with query params
    next_url = f"{url}/wiki/api/v2/pages?spaceKey={space_key}&limit={limit}"

    while next_url:
        response = requests.get(next_url, auth=auth)
        response.raise_for_status()
        data = response.json()

        # 'results' contains the list of pages for this request
        results = data.get("results", [])
        pages.extend(results)

        # If there's no "next" link in _links, it means we've reached the end
        links = data.get("_links", {})
        relative_next = links.get("next")
        if relative_next:
            # Build the full URL for the "next" link
            next_url = f"{url}{relative_next}"
        else:
            next_url = None

    return pages


def fetch_page_content_v2(url, page_id, auth):
    """
    Fetch the full page content (in storage format) for a given page ID using the v2 endpoint.
    """
    endpoint = f"{url}/wiki/api/v2/pages/{page_id}?body-format=storage"
    response = requests.get(endpoint, auth=auth)
    response.raise_for_status()
    page_data = response.json()

    # Filter out pages with empty 'body.storage.value'
    try :
        value_field = page_data["body"]["storage"]["value"]
        if value_field == "":
            return None
    except KeyError:
        return None

    return page_data



def slugify_title(title):
    """
    Convert the given title into a filename-safe format.
    Replaces spaces and special characters with hyphens, and keeps alphanumeric characters, dashes, and underscores.
    """
    # Replace non-alphanumeric characters with dashes
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title)
    # Remove leading/trailing hyphens
    return slug.strip("-")


def save_page_to_json(page_data, directory):
    """
    Save the page data to a JSON file, using the page title as the file name.
    """


    page_id = page_data.get("id")
    title = page_data.get("title", f"page_{page_id}")
    safe_title = slugify_title(title)
    file_name = f"{page_id}_{safe_title}.json"
    file_path = os.path.join(directory, file_name)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(page_data, f, indent=4, ensure_ascii=False)
    print(f"Saved page {page_id} to {file_path}")


def main():
    auth = (USERNAME, API_TOKEN)
    os.makedirs(SAVE_DIRECTORY, exist_ok=True)

    # 1. Fetch the basic info (ID, title, etc.) of all pages in the space
    pages_info = fetch_all_pages_in_space_v2(CONFLUENCE_URL, SPACE_KEY, auth)

    # 2. For each page, retrieve its expanded content and save as JSON
    for page in pages_info:
        page_id = page.get("id")
        if page_id:
            page_content = fetch_page_content_v2(CONFLUENCE_URL, page_id, auth)
            if page_content is None:
                continue
            save_page_to_json(page_content, SAVE_DIRECTORY)


if __name__ == "__main__":
    main()