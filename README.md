# HTTP Query Forwarder Plugin for Flow Launcher

This plugin allows you to forward your search queries from Flow Launcher to a custom HTTP/S server and display the results returned by that server.

## Features

- Forwards queries to a configurable HTTP/S endpoint.
- Displays rich results from the server, including titles, subtitles, icons.
- Supports custom actions (opening URLs, running shell commands, etc.) defined by the server.
- Supports context menus defined by the server.
- Server address, port, path, query parameter, and request timeout are configurable in Flow Launcher settings.

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
    - Open Flow Launcher settings (type `settings` or right-click Flow icon > Settings).
    - Go to the "Plugins" tab.
    - Find "HTTP Query Forwarder" in the list and click its icon or title to open its settings.
    - Configure the "HTTP Server Address", "Port", "Path", "Query Parameter Name", and "Request Timeout" according to your server setup.
    - Default Action Keyword: `fwd`

## Server API

Your HTTP server should:

- Listen for GET requests.
- Accept a query parameter (default `q`) containing the user's input (e.g., `http://localhost:8080/?q=search%20term`).
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
- GitHub Actions are configured in `.github/workflows/release.yml` to automatically build and package the plugin into a distributable zip file on pushes to the `main` branch.

To build locally (for testing):

1. Ensure Python 3.7+ and pip are installed.
2. Create a virtual environment (optional but recommended).
3. Install dependencies into a `lib` folder: `pip install -r requirements.txt -t ./lib`
4. Your plugin folder (containing `main.py`, `plugin.json`, `Images/`, `lib/`, `SettingsTemplate.yaml`) can then be copied to Flow Launcher's plugin directory.
