# HTTP Query Forwarder Plugin for Flow Launcher

This plugin allows you to forward your search queries from Flow Launcher to a custom HTTP/S server and display the results returned by that server.

## Features

- Forwards queries to a configurable HTTP/S endpoint.
- Displays rich results from the server, including titles, subtitles, icons.
- Supports custom actions (opening URLs, running shell commands, etc.) defined by the server.
- Supports context menus defined by the server.
- Server address, port, path, query parameter, and request timeout are configurable.
- Optional: Use a single custom URL template to fully control the request URL format.

## Installation

1.  **Download**: Go to the [Releases page](https://github.com/your-repo/Flow.Launcher.Plugin.HttpForwarder/releases) of this plugin's GitHub repository and download the latest `.zip` file.
2.  **Locate Plugins Directory**:
    - Open Flow Launcher.
    - Type `flow launcher userdata` and press Enter. This will open the UserData folder.
    - Navigate into the `Plugins` subfolder.
3.  **Install Plugin**:
    - Extract the downloaded `.zip` file. You should get a folder (e.g., `HttpQueryForwarder-v1.0.0`).
    - Copy this entire folder into Flow Launcher's `Plugins` directory (from step 2).
4.  **Restart Flow Launcher**: Close and reopen Flow Launcher to load the new plugin.
5.  **Configure**:
    - Configuration is managed via an external YAML file created at:
      `[User Documents]\httpflow\settings.yaml`.
    - If the file or folder doesn't exist, the plugin will create it on first run with defaults.
    - Default Action Keyword: `fwd`

## Configuration

The plugin will create or use `[Documents]\httpflow\settings.yaml`. You can configure either the classic fields or provide a full URL template.

Classic fields:

```yaml
server_address: "http://127.0.0.1"
server_port: "8080"
server_path: "/"
query_param_name: "q"
url_encode_query: true
request_timeout: 5
```

Custom URL Template (optional):

- Set `custom_url_template` to override the URL construction. It supports:
  - `{query}`: raw user query
  - `{encoded_query}`: URL-encoded user query
  - `{query_param_name}`: the name of the query parameter
- If neither `{query}` nor `{encoded_query}` is present in the template, the plugin appends the query using `query_param_name` and respects `url_encode_query`.
- If no scheme is provided (e.g., `localhost:8080/search`), `http://` is assumed.

Examples:

```yaml
# 1) Explicit encoded placeholder
custom_url_template: "http://localhost:8080/search?q={encoded_query}&lang=en"

# 2) Let the plugin append ?{query_param_name}=... (uses url_encode_query)
custom_url_template: "https://api.example.com/search"

# 3) Use raw query
custom_url_template: "https://example.com/echo?text={query}"
```

If `custom_url_template` is empty or omitted, the plugin uses the classic fields.

## Server API

Your HTTP server should:

- Listen for GET requests.
- Accept a query parameter (default `q`) containing the user's input (e.g., `http://localhost:8080/?q=search%20term`), unless your custom template defines a different pattern.
- Respond with a JSON array. Each object in the array represents a result item.

**Example Server Response JSON:**

```json
[
  {
    "Title": "Open Flow Launcher Docs",
    "SubTitle": "Official documentation website",
    "IcoPath": "https://flowlauncher.com/public/favicon.ico",
    "Score": 10,
    "JsonRPCAction": {
      "method": "open_url",
      "parameters": ["https://flowlauncher.com/docs"]
    },
    "ContextMenuItems": [
      {
        "Title": "Copy URL",
        "SubTitle": "Copies the documentation URL to clipboard",
        "JsonRPCAction": {
          "method": "copy_to_clipboard",
          "parameters": ["https://flowlauncher.com/docs"]
        }
      }
    ]
  },
  {
    "Title": "Echo User Query",
    "SubTitle": "This was your query: the_actual_query_string",
    "IcoPath": "Images\\icon.png"
  }
]
```

See the `main.py` file for supported `JsonRPCAction` methods and their parameters:

- `open_url`: `[url: string]`
- `shell_run`: `[command: string]`
- `copy_to_clipboard`: `[text_to_copy: string]`
- `change_query`: `[new_query_string: string, requery: string ("true" or "false")]`
- `flow_show_msg`: `[title: string, sub_title: string, ico_path (optional): string]`

The `IcoPath` can be a full URL or a relative path (e.g., `Images/custom_icon.png`) to an icon within the plugin's `Images` folder.

## Development & Building

This plugin is developed in Python.

- Dependencies are listed in `requirements.txt`.
- GitHub Actions are configured in `.github/workflows/release.yml` to automatically build and package the plugin into a distributable zip file.

To build locally (for testing):

1. Ensure Python 3.7+ and pip are installed.
2. Create a virtual environment (optional but recommended).
3. Install dependencies into a `lib` folder: `pip install -r requirements.txt -t ./lib`
4. Your plugin folder (containing `main.py`, `plugin.json`, `Images/`, `lib/`, `SettingsTemplate.yaml`) can then be copied to Flow Launcher's plugin directory.
