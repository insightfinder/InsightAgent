# Confluence Space Exporter

This project is a Python script that fetches all pages from a specific Confluence space and saves them as JSON files. Each page's content and metadata are exported for further processing or backup purposes.

## Features

- Fetches all pages from a Confluence space using the REST API v2.
- Saves page content in JSON format.
- Utilizes configurable settings for Confluence URL, space key, and user authentication.
- Supports limiting the number of pages to fetch.
- Automatically creates a save directory if it does not exist.

## Requirements

This project uses Python and the following external libraries:
- `requests`: For performing HTTP requests to the Confluence REST API.
- `pyyaml`: For reading and parsing the configuration file.

Install all dependencies from the `requirements.txt` file:
```bash
pip install -r requirements.txt
```

## Configuration

The script uses a `config.yaml` file for configuration. Below is the format of the file and the available settings:

```yaml
confluence_url: "https://example.atlassian.net" # URL for the Confluence instance
space_key: "ExampleSpace"                      # Key of the Confluence space to export
username: "user@example.com"                   # Your Confluence account username
api_token: "your_api_token"                    # API token for Confluence
save_directory: "output"                       # (Optional) Directory to save JSON files. Defaults to 'confluence_pages_v2'.
page_limit: 25                                 # (Optional) Number of pages to fetch per request. Defaults to 25.
```

### Generating an API Token

To generate an API token for your account:
1. Go to your Confluence account settings.
2. Navigate to **API tokens** and create a new token.
3. Use the generated token in the `config.yaml` file.

### Example Configuration

```yaml
confluence_url: "https://insightfinders.atlassian.net"
space_key: "InsightFin"
username: "maoyu@insightfinder.com"
api_token: "your_api_token"
save_directory: "output"
page_limit: 25
```

## Usage

1. Clone the repository:
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```

2. Set up the `config.yaml` file with your Confluence settings.

3. Run the script using:
   ```bash
   python main.py
   ```

4. JSON files representing each Confluence page are saved in the specified output directory (default: `confluence_pages_v2`).

## Functions Overview

The script includes the following core functions:

- `fetch_all_pages_in_space_v2`: Fetches basic information (ID, title, etc.) of all pages in the Confluence space.
- `fetch_page_content_v2`: Fetches the detailed content of a specific Confluence page.
- `slugify_title`: Converts page titles into filename-safe strings.
- `save_page_to_json`: Saves page data as a JSON file.

## File Structure

The project contains the following files:

- `main.py`: The main script to run the Confluence page exporter.
- `config.yaml`: Configuration file for the exporter.
- `requirements.txt`: List of required Python libraries.

## Notes

- Ensure that your Confluence account has permission to access the specified space and pages.
- Set a reasonable `page_limit` value to avoid overloading the Confluence API.

## License

This project is licensed under the MIT License. Feel free to use, modify, and distribute it as needed.