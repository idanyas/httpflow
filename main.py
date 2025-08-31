# -*- coding: utf-8 -*-

import sys
import os
from pathlib import Path
import logging # Moved up for global logger
import json # Moved up for global logger

# --- Global sys.argv logging ---
_GLOBAL_PLUGIN_LOG_DIR = Path(__file__).resolve().parent
_GLOBAL_ARGV_LOG_FILE = _GLOBAL_PLUGIN_LOG_DIR / "plugin_argv_dump.log"
_global_argv_logger = logging.getLogger("HttpQueryForwarderGlobalArgvLogger")

if not _global_argv_logger.handlers:
    try:
        _GLOBAL_PLUGIN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        _g_handler = logging.FileHandler(_GLOBAL_ARGV_LOG_FILE, encoding='utf-8', mode='a')
        _g_formatter = logging.Formatter('%(asctime)s - PID:%(process)d - %(levelname)s - %(message)s')
        _g_handler.setFormatter(_g_formatter)
        _global_argv_logger.addHandler(_g_handler)
        _global_argv_logger.setLevel(logging.DEBUG)
        _global_argv_logger.info(f"--- Python script started. PID: {os.getpid()} ---")
        _global_argv_logger.info(f"sys.executable: {sys.executable}")
        _sys_version_cleaned = sys.version.replace('\n', ' ')
        _global_argv_logger.info(f"sys.version: {_sys_version_cleaned}")
        _global_argv_logger.info(f"sys.argv at script start (raw): {sys.argv}") 
        _global_argv_logger.info(f"sys.argv at script start (json_dumped): {json.dumps(sys.argv)}") 
        _global_argv_logger.info(f"Working directory (os.getcwd()): {os.getcwd()}")
    except Exception as e:
        print(f"CRITICAL: Failed to set up global argv logger to '{_GLOBAL_ARGV_LOG_FILE}': {e}", file=sys.stderr)
        print(f"sys.argv at script start: {sys.argv}", file=sys.stderr)
# --- End Global sys.argv logging ---


# --- BEGIN SYS.PATH MODIFICATION ---
plugindir_path = Path(__file__).resolve().parent
libdir = plugindir_path / 'lib'
sys.path.insert(0, str(plugindir_path))
if libdir.is_dir():
    sys.path.insert(0, str(libdir))
# --- END SYS.PATH MODIFICATION ---

import webbrowser
import requests
from urllib.parse import quote_plus, urlunsplit, urlsplit, urlencode, parse_qsl
import traceback 
from typing import List, Dict, Any, Optional, Union
import yaml 

from flowlauncher import FlowLauncher, FlowLauncherAPI # Ensure FlowLauncherAPI is imported

LOG_FILENAME = "plugin_httpforwarder_errors.log"
PLUGIN_JSON_FILE = "plugin.json"
EXTERNAL_SETTINGS_SUBDIR = "httpflow" 
EXTERNAL_SETTINGS_FILENAME = "settings.yaml"

class HttpQueryForwarder(FlowLauncher):
    settings: Dict[str, Any] 
    logger: logging.Logger 
    icon: str 
    plugindir: str
    
    _fallback_logger: Optional[logging.Logger]
    resolved_default_icon_path: str

    def __init__(self):
        self._fallback_logger = None 
        self._ensure_fallback_logger_initialized() 
        
        self.logger.info(f"--- Starting {self.__class__.__name__} __init__ (PID: {os.getpid()}) ---")

        self.settings = {} 
        self.plugindir = str(Path(__file__).resolve().parent) 
        self.icon = self._get_default_ico_from_plugin_json_early(self.plugindir)
        self.resolved_default_icon_path = "" 

        self.logger.info(f"[INIT_PHASE_1] Pre-super values: icon='{self.icon}', plugindir='{self.plugindir}'")
        
        self.logger.info(f"sys.argv as seen by plugin's __init__ before super(): {json.dumps(sys.argv)}")
        if len(sys.argv) > 1:
            potential_json_arg1 = sys.argv[1].strip()
            is_argv1_json_like = potential_json_arg1.startswith("{") and potential_json_arg1.endswith("}")
            if is_argv1_json_like:
                self.logger.info("sys.argv[1] appears to be JSON-like. Proceeding with standard super() call.")
            else:
                self.logger.warning("sys.argv[1] does NOT appear to be JSON-like. This might cause issues with super().__init__().")
        else:
             self.logger.warning(f"sys.argv has {len(sys.argv)} element(s). This will likely cause issues if base class expects JSON in sys.argv[1].")

        try:
            super().__init__()
            self.logger.info(f"[INIT_PHASE_2] super().__init__() completed.")
            _global_argv_logger.info(f"[CLASS_INIT] super().__init__() completed for HttpQueryForwarder instance.") 

            # Check if the base class (from the flowlauncher library) set an 'api' or 'public_api' attribute.
            # This specific library version, as shown in the problem description's first project,
            # does NOT set self.api. It uses static/classmethods on FlowLauncherAPI.
            # The logging below is for observation.
            api_from_super = getattr(self, 'api', 'NOT_SET_BY_SUPER')
            public_api_from_super = getattr(self, 'public_api', 'NOT_SET_BY_SUPER')
            self.logger.info(f"  Post-super self.api: {api_from_super} (type: {type(api_from_super)})")
            self.logger.info(f"  Post-super self.public_api: {public_api_from_super} (type: {type(public_api_from_super)})")

        except Exception as e: 
            self.logger.exception("[INIT_PHASE_2] CRITICAL: Exception during super().__init__().")
            _global_argv_logger.exception("[CLASS_INIT] CRITICAL: Exception during super().__init__().")
            
        logger_from_super = getattr(self, 'logger', None)
        if isinstance(logger_from_super, logging.Logger) and logger_from_super is not self._fallback_logger:
            self.logger.info("[INIT_PHASE_3] Logger finalized: Using logger provided or reconfigured by FlowLauncher base.")
        else:
            self.logger.info("[INIT_PHASE_3] Logger finalized: Using plugin's fallback logger (super() did not provide a different, valid logger).")

        final_icon_str = getattr(self, 'icon', self.icon) 
        final_plugindir_str = getattr(self, 'plugindir', self.plugindir) 
        self.resolved_default_icon_path = self._resolve_icon_path_static(final_icon_str, final_plugindir_str, self.logger)
        
        self.logger.info(f"[INIT_PHASE_4] Resolved plugin default icon path: '{self.resolved_default_icon_path}' (from icon='{final_icon_str}', plugindir='{final_plugindir_str}')")
        self.logger.info(f"--- {self.__class__.__name__} __init__ finished ---")
        _global_argv_logger.info(f"[CLASS_INIT] HttpQueryForwarder __init__ finished. Resolved default icon: '{self.resolved_default_icon_path}'")

    def _get_settings_from_file(self) -> Dict[str, Any]:
        logger_to_use = self.logger 

        documents_path = self._get_user_documents_path(logger_to_use)
        settings_dir = documents_path / EXTERNAL_SETTINGS_SUBDIR
        settings_file_path = settings_dir / EXTERNAL_SETTINGS_FILENAME
        
        logger_to_use.debug(f"[_get_settings_from_file] Attempting to load external settings from: {settings_file_path}")

        default_settings_map = {
            "server_address": "http://127.0.0.1", 
            "server_port": "8080",
            "server_path": "/",
            "query_param_name": "q",
            "url_encode_query": True, 
            "request_timeout": 5,
            "custom_url_template": ""  # New: optional override for full URL construction
        }
        
        effective_settings = default_settings_map.copy()
        logger_to_use.debug(f"[_get_settings_from_file] Initialized effective_settings with defaults: {effective_settings}")

        if settings_file_path.exists() and settings_file_path.is_file():
            logger_to_use.info(f"[_get_settings_from_file] Settings file found at {settings_file_path}. Reading content.")
            raw_content = ""
            try:
                with open(settings_file_path, 'r', encoding='utf-8') as f:
                    raw_content = f.read()
                logger_to_use.debug(f"[_get_settings_from_file] Raw content of '{settings_file_path}':\n---\n{raw_content}\n---")
                
                loaded_yaml_settings = yaml.safe_load(raw_content)
                
                if isinstance(loaded_yaml_settings, dict):
                    logger_to_use.info("[_get_settings_from_file] YAML content parsed successfully as a dictionary.")
                    for key, default_value in default_settings_map.items():
                        if key in loaded_yaml_settings:
                            yaml_value = loaded_yaml_settings[key]
                            expected_type = type(default_value)
                            
                            if key == "request_timeout": 
                                try:
                                    effective_settings[key] = int(yaml_value)
                                    if effective_settings[key] <= 0: 
                                        logger_to_use.warning(f"[_get_settings_from_file] '{key}' in YAML ('{yaml_value}') is not positive. Using default: {default_value}")
                                        effective_settings[key] = default_value
                                except ValueError:
                                    logger_to_use.warning(f"[_get_settings_from_file] Invalid value for '{key}' in YAML (value: '{yaml_value}', expected int-convertible). Using default: {default_value}")
                                    effective_settings[key] = default_value
                            elif key == "url_encode_query": 
                                if isinstance(yaml_value, bool):
                                    effective_settings[key] = yaml_value
                                elif isinstance(yaml_value, str): 
                                    str_val = yaml_value.lower()
                                    if str_val == 'true': effective_settings[key] = True
                                    elif str_val == 'false': effective_settings[key] = False
                                    else:
                                        logger_to_use.warning(f"[_get_settings_from_file] Invalid string for boolean '{key}' in YAML (value: '{yaml_value}'). Using default: {default_value}")
                                        effective_settings[key] = default_value
                                else: 
                                    logger_to_use.warning(f"[_get_settings_from_file] Invalid type for boolean '{key}' in YAML (value: '{yaml_value}', type: {type(yaml_value)}). Using default: {default_value}")
                                    effective_settings[key] = default_value
                            elif isinstance(yaml_value, expected_type): 
                                effective_settings[key] = yaml_value
                            else: 
                                logger_to_use.warning(f"[_get_settings_from_file] Type mismatch for '{key}' in YAML (value: '{yaml_value}', type: {type(yaml_value)}, expected: {expected_type}). Using default: {default_value}")
                                effective_settings[key] = default_value
                        else: 
                            logger_to_use.debug(f"[_get_settings_from_file] Key '{key}' not found in YAML, using default: {default_value}")
                    logger_to_use.info(f"[_get_settings_from_file] Successfully loaded and merged settings from {settings_file_path}.")
                else:
                    logger_to_use.error(f"[_get_settings_from_file] Content of {settings_file_path} is not a YAML dictionary (actual type: {type(loaded_yaml_settings)}). Using default settings map.")
            except yaml.YAMLError as ye:
                logger_to_use.error(f"[_get_settings_from_file] Error parsing YAML from {settings_file_path}: {ye}. Raw content was:\n{raw_content[:500]}\nUsing default settings map.")
            except Exception as e:
                logger_to_use.error(f"[_get_settings_from_file] Failed to read/parse {settings_file_path}: {e}. Using default settings map.", exc_info=True)
        else:
            logger_to_use.warning(f"[_get_settings_from_file] Settings file NOT found at: {settings_file_path}. Attempting to create it with defaults.")
            try:
                settings_dir.mkdir(parents=True, exist_ok=True)
                with open(settings_file_path, 'w', encoding='utf-8') as f:
                    yaml.dump(default_settings_map, f, sort_keys=False, indent=2, default_flow_style=False)
                logger_to_use.info(f"[_get_settings_from_file] Created default settings file at: {settings_file_path}. Using these defaults.")
            except Exception as e:
                logger_to_use.error(f"[_get_settings_from_file] Failed to create default settings file at {settings_file_path}: {e}. Using IN-MEMORY hardcoded defaults for this session.", exc_info=True)
        
        logger_to_use.debug(f"[_get_settings_from_file] Returning effective settings: {effective_settings}")
        return effective_settings

    def _get_user_documents_path(self, logger_instance: logging.Logger) -> Path:
        home_documents_path = Path.home() / "Documents"
        logger_instance.debug(f"[_get_user_documents_path] Checking primary path: {home_documents_path}")
        if home_documents_path.is_dir():
            logger_instance.info(f"[_get_user_documents_path] Using User Documents Path (from Path.home()): {home_documents_path}")
            return home_documents_path

        logger_instance.warning(f"[_get_user_documents_path] Primary path '{home_documents_path}' is not a valid directory. Trying Windows CSIDL_PERSONAL as fallback.")
        
        if os.name == 'nt':
            try:
                import ctypes
                from ctypes.wintypes import MAX_PATH 
                CSIDL_PERSONAL = 5
                path_buf = ctypes.create_unicode_buffer(MAX_PATH)
                if hasattr(ctypes.windll.shell32, 'SHGetFolderPathW'):
                     result = ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, 0, path_buf)
                     if result == 0: 
                        windows_docs_path = Path(path_buf.value)
                        logger_instance.info(f"[_get_user_documents_path] Using User Documents Path (from CSIDL_PERSONAL): {windows_docs_path}")
                        return windows_docs_path
                     else:
                        logger_instance.error(f"[_get_user_documents_path] SHGetFolderPathW failed with HRESULT: {result}.")
                else:
                     logger_instance.error("[_get_user_documents_path] ctypes.windll.shell32.SHGetFolderPathW not found.")
            except Exception as e:
                logger_instance.error(f"[_get_user_documents_path] Failed CSIDL_PERSONAL lookup ({type(e).__name__}: {e}).")
        
        logger_instance.warning(f"[_get_user_documents_path] All methods failed. Using '{home_documents_path}' as final fallback.")
        return home_documents_path

    def _get_default_ico_from_plugin_json_early(self, current_plugindir: str) -> str:
        try:
            plugin_json_path = Path(current_plugindir) / PLUGIN_JSON_FILE
            if plugin_json_path.exists():
                with open(plugin_json_path, 'r', encoding='utf-8') as f: data = json.load(f)
                return data.get("IcoPath", "")
            return ""
        except: return "" 

    def _ensure_fallback_logger_initialized(self):
        if self._fallback_logger and getattr(self._fallback_logger, '_is_this_fallback_logger_custom_attr', False):
            if not (hasattr(self, 'logger') and isinstance(getattr(self, 'logger', None), logging.Logger)):
                self.logger = self._fallback_logger 
            return

        current_plugin_dir_for_log = Path(__file__).resolve().parent
        logger_name = f"FlowLauncher.Plugins.{current_plugin_dir_for_log.name}.{self.__class__.__name__}.Fallback"
        fb_logger = logging.getLogger(logger_name)
        
        if not fb_logger.handlers: 
            log_file_path = current_plugin_dir_for_log / LOG_FILENAME
            try:
                log_file_path.parent.mkdir(parents=True, exist_ok=True)
                handler = logging.FileHandler(log_file_path, encoding='utf-8', mode='a') 
                formatter = logging.Formatter('%(asctime)s - PID:%(process)d - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s')
                handler.setFormatter(formatter)
                fb_logger.addHandler(handler)
                fb_logger.propagate = False 
                fb_logger.setLevel(logging.DEBUG) 
                setattr(fb_logger, '_is_this_fallback_logger_custom_attr', True)
            except Exception as e:
                print(f"CRITICAL: Failed to initialize fallback file logger '{log_file_path}' for {logger_name}: {e}\n{traceback.format_exc()}", file=sys.stderr)
        
        self._fallback_logger = fb_logger
        self.logger = self._fallback_logger 

    @staticmethod
    def _resolve_icon_path_static(icon_path_str: Optional[str], plugin_dir_str: str, logger_instance: logging.Logger) -> str:
        if not icon_path_str: return ""
        normalized_path_str = icon_path_str.replace("\\", "/")
        if normalized_path_str.startswith(("http://", "https://")): return normalized_path_str
        if os.path.isabs(normalized_path_str):
            abs_path_obj = Path(normalized_path_str)
            if abs_path_obj.exists() and abs_path_obj.is_file(): return str(abs_path_obj.resolve()).replace("\\", "/")
            logger_instance.debug(f"Absolute icon path ('{normalized_path_str}') not found or not a file.")
            return "" 
        if not plugin_dir_str:
            logger_instance.warning(f"Cannot resolve relative icon '{normalized_path_str}': plugin_dir_str is empty.")
            return ""
        try:
            prospective_path = Path(plugin_dir_str) / normalized_path_str
            resolved_abs_path = prospective_path.resolve()
            
            if resolved_abs_path.exists() and resolved_abs_path.is_file(): 
                return str(resolved_abs_path).replace("\\", "/")
            
            logger_instance.debug(
                f"Relative icon not found. Original: '{icon_path_str}', PluginDir: '{plugin_dir_str}', "
                f"Normalized: '{normalized_path_str}', Prospective: '{prospective_path}', Resolved: '{resolved_abs_path}' "
                f"(Resolved.exists: {resolved_abs_path.exists()}, Resolved.is_file: {resolved_abs_path.is_file()}). "
                f"Also checking Prospective.exists: {prospective_path.exists()}, Prospective.is_file: {prospective_path.is_file()}."
            )
            return ""
        except Exception as e: 
            logger_instance.error(f"Error resolving icon '{normalized_path_str}' rel to '{plugin_dir_str}': {e}", exc_info=False) 
            return ""

    def query(self, param: str = "") -> List[dict]:
        _global_argv_logger.info(f"[QUERY_METHOD_ENTRY] query('{param}') called.")
        effective_settings = self._get_settings_from_file()
        logger_to_use = self.logger 
        final_resolved_default_icon = self.resolved_default_icon_path
        current_plugindir = getattr(self, 'plugindir', str(Path(__file__).resolve().parent)) 

        logger_to_use.debug(f"Querying with param: '{param}'. Effective settings for this call: {effective_settings}")

        server_addr = str(effective_settings.get("server_address", "http://localhost"))
        server_port_str = str(effective_settings.get("server_port", "8080"))
        raw_server_path = str(effective_settings.get("server_path", "/"))
        server_path = ("/" + raw_server_path.lstrip("/")) if not raw_server_path.startswith("/") else raw_server_path
        if server_path == "//": server_path = "/"
        
        query_param_name = str(effective_settings.get("query_param_name", "q"))
        url_encode_setting = effective_settings.get("url_encode_query", True)

        if isinstance(url_encode_setting, str):
            url_encode = url_encode_setting.lower() == 'true'
        else:
            url_encode = bool(url_encode_setting)

        timeout_val = effective_settings.get("request_timeout", 5)
        try:
            timeout = int(timeout_val) 
            if timeout <= 0: 
                logger_to_use.warning(f"Request timeout from settings ('{timeout_val}') is not positive. Defaulting to 5s.")
                timeout = 5
        except ValueError:
            logger_to_use.warning(f"Invalid request_timeout value '{timeout_val}' from settings. Defaulting to 5s.")
            timeout = 5
        
        current_url_for_error_reporting: str = "URL not constructed"
        results: List[dict] = [] 
        response_obj_for_logging = None 

        try:
            # Check if a custom URL template should be used
            custom_url_template = str(effective_settings.get("custom_url_template", "") or "").strip()

            if custom_url_template:
                logger_to_use.info("Using custom URL template from settings.")
                # Prepare substitution values
                encoded_for_placeholder = quote_plus(param)
                replaced_url = (
                    custom_url_template
                    .replace("{encoded_query}", encoded_for_placeholder)
                    .replace("{query}", param)
                    .replace("{query_param_name}", query_param_name)
                )

                # Ensure scheme; if missing, default to http
                if not urlsplit(replaced_url).scheme:
                    replaced_url = "http://" + replaced_url
                    logger_to_use.debug(f"No scheme detected in template. Defaulting to http -> '{replaced_url}'")

                parsed = urlsplit(replaced_url)

                # If neither {query} nor {encoded_query} were used, append the query param using the configured name
                if ("{encoded_query}" not in custom_url_template) and ("{query}" not in custom_url_template):
                    query_to_send = quote_plus(param) if url_encode else param
                    existing_qs = list(parse_qsl(parsed.query, keep_blank_values=True))
                    existing_qs.append((query_param_name, query_to_send))
                    new_query = urlencode(existing_qs, doseq=True)
                    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
                else:
                    # Placeholders already handled; use as-is
                    url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))

                current_url_for_error_reporting = url
                logger_to_use.info(f"Requesting URL (custom template): {url}")

            else:
                # Legacy path: build URL from server_address/port/path/query_param_name
                effective_server_addr = server_addr
                if not urlsplit(effective_server_addr).scheme and effective_server_addr:
                    effective_server_addr = "http://" + effective_server_addr
                
                parsed_addr = urlsplit(effective_server_addr)
                scheme = parsed_addr.scheme or "http"
                netloc_host = parsed_addr.hostname
                if not netloc_host: raise ValueError(f"Invalid server_address '{server_addr}': no hostname.")

                final_netloc = f"{netloc_host}:{parsed_addr.port}" if parsed_addr.port else (f"{netloc_host}:{server_port_str}" if server_port_str else netloc_host)
                query_to_send = quote_plus(param) if url_encode else param
                query_params_str = f"{query_param_name}={query_to_send}"
                url = urlunsplit((scheme, final_netloc, server_path, query_params_str, ''))
                current_url_for_error_reporting = url
                logger_to_use.info(f"Requesting URL: {url} (derived from settings: {effective_settings})")

            response_obj_for_logging = requests.get(url, timeout=timeout)
            response_obj_for_logging.raise_for_status() 
            server_response_data = response_obj_for_logging.json()

            if not isinstance(server_response_data, list):
                raise ValueError(f"Server response from {url} is not a JSON list.")

            for item_data in server_response_data: 
                if not (isinstance(item_data, dict) and item_data.get("Title")): continue
                item_specific_icon = self._resolve_icon_path_static(item_data.get("IcoPath"), current_plugindir, logger_to_use)
                result_entry: Dict[str, Any] = {
                    "Title": item_data["Title"],
                    "SubTitle": item_data.get("SubTitle", ""),
                    "IcoPath": item_specific_icon or final_resolved_default_icon,
                    "Score": int(item_data.get("Score", 0)),
                }
                if item_data.get("AutoCompleteText"): result_entry["AutoCompleteText"] = item_data["AutoCompleteText"]
                
                plugin_context_data: Any = item_data.get("ContextData")
                if item_data.get("ContextMenuItems") and isinstance(item_data["ContextMenuItems"], list):
                    plugin_context_data = {"original_data": item_data.get("ContextData"), "defined_menu_items": item_data["ContextMenuItems"]}
                if plugin_context_data is not None: result_entry["ContextData"] = plugin_context_data
                
                json_rpc = item_data.get("JsonRPCAction")
                if isinstance(json_rpc, dict):
                    method, params = json_rpc.get("method"), json_rpc.get("parameters", [])
                    if method and hasattr(self, method) and callable(getattr(self, method)):
                        result_entry["JsonRPCAction"] = {"method": method, "parameters": params if isinstance(params, list) else ([params] if params is not None else [])}
                    else: logger_to_use.warning(f"Invalid JsonRPCAction method ('{method}') or not callable.")
                results.append(result_entry)

        except requests.exceptions.Timeout:
            logger_to_use.error(f"Request timed out: {current_url_for_error_reporting}.", exc_info=True)
            results = [{"Title": "Error: Request Timed Out", "SubTitle": f"Server at {current_url_for_error_reporting} timed out.", "IcoPath": final_resolved_default_icon}]
        except requests.exceptions.RequestException as e:
            logger_to_use.error(f"Network Request Failed: {current_url_for_error_reporting}. Error: {e}", exc_info=True)
            results = [{"Title": "Error: Network Request Failed", "SubTitle": f"Could not connect to '{current_url_for_error_reporting}'. {type(e).__name__}", "IcoPath": final_resolved_default_icon}]
        except (json.JSONDecodeError, ValueError) as e: 
            response_text = response_obj_for_logging.text[:500] if response_obj_for_logging else "N/A (response object not available)"
            logger_to_use.error(f"Data Error (JSON or Value): {current_url_for_error_reporting}. Response (first 500 chars): '{response_text}'. Error: {e}", exc_info=True)
            results = [{"Title": f"Error: {type(e).__name__}", "SubTitle": str(e), "IcoPath": final_resolved_default_icon}]
        except Exception:
            logger_to_use.exception(f"Unexpected error in query: {current_url_for_error_reporting}.")
            results = [{"Title": "Error: Plugin Error", "SubTitle": "Unexpected. Check logs.", "IcoPath": final_resolved_default_icon}]
        
        if not results and param.strip(): 
            results.append({"Title": "No results", "SubTitle": f"Query '{param}' from server.", "IcoPath": final_resolved_default_icon})
        elif not results and not param.strip():
             settings_file_info = f"Config: ...\\Documents\\{EXTERNAL_SETTINGS_SUBDIR}\\{EXTERNAL_SETTINGS_FILENAME}"
             results.append({"Title": "HTTP Query Forwarder Ready", "SubTitle": f"Enter query. {settings_file_info}", "IcoPath": final_resolved_default_icon})
        
        _global_argv_logger.info(f"[QUERY_METHOD_EXIT] query('{param}') returning {len(results)} results.")
        return results

    def context_menu(self, data: Any) -> List[dict]:
        _global_argv_logger.info(f"[CONTEXT_MENU_ENTRY] context_menu called with data type: {type(data)}.")
        menu_results: List[dict] = []
        logger_to_use = self.logger
        final_resolved_default_icon = self.resolved_default_icon_path
        current_plugindir = getattr(self, 'plugindir', str(Path(__file__).resolve().parent))

        if isinstance(data, dict) and "defined_menu_items" in data:
            for item_def in data.get("defined_menu_items", []):
                if not (isinstance(item_def, dict) and item_def.get("Title")): continue
                item_icon = self._resolve_icon_path_static(item_def.get("IcoPath"), current_plugindir, logger_to_use)
                ctx_result: Dict[str, Any] = {
                    "Title": item_def["Title"], "SubTitle": item_def.get("SubTitle", ""),
                    "IcoPath": item_icon or final_resolved_default_icon
                }
                json_rpc = item_def.get("JsonRPCAction")
                if isinstance(json_rpc, dict):
                    method, params = json_rpc.get("method"), json_rpc.get("parameters", [])
                    if method and hasattr(self, method) and callable(getattr(self, method)):
                         ctx_result["JsonRPCAction"] = {"method": method, "parameters": params if isinstance(params, list) else ([params] if params is not None else [])}
                    else: logger_to_use.warning(f"Invalid context JsonRPCAction method ('{method}').")
                menu_results.append(ctx_result)
        
        if not menu_results: 
            default_context_title = "No context actions defined by server"
            if isinstance(data, dict) and "original_data" in data: 
                 default_context_title = "No specific context actions (original data present)"

            menu_results.append({"Title": default_context_title, "IcoPath": final_resolved_default_icon})
        
        _global_argv_logger.info(f"[CONTEXT_MENU_EXIT] context_menu returning {len(menu_results)} results.")
        return menu_results

    def open_url(self, url: str):
        _global_argv_logger.info(f"[ACTION_open_url_ENTRY] open_url('{url}') called.")
        self.logger.info(f"Opening URL: {url}")
        try: 
            webbrowser.open(url)
            self.logger.debug(f"webbrowser.open({url}) called.")
        except Exception as e:
            self.logger.error(f"Failed to open URL '{url}': {e}", exc_info=True)
            _global_argv_logger.error(f"[ACTION_open_url_ERROR] Failed to open URL '{url}': {e}", exc_info=True)
            # Use direct print for JSON-RPC as FlowLauncherAPI.show_msg might be the source of the problem
            payload = {
                "method": "Flow.Launcher.ShowMsg",
                "parameters": ["Error Opening URL", f"Could not open: {url}. Error: {type(e).__name__}", self.resolved_default_icon_path]
            }
            print(json.dumps(payload))
        _global_argv_logger.info(f"[ACTION_open_url_EXIT] open_url('{url}') finished.")

    def shell_run(self, command: Union[str, List[str]]):
        cmd_str = command[0] if isinstance(command, list) and command else str(command)
        _global_argv_logger.info(f"[ACTION_shell_run_ENTRY] shell_run('{cmd_str}') called.")
        
        self.logger.info(f"Preparing to execute shell_run for command: '{cmd_str}'")
        self.logger.debug(f"Parameter cmd_str: '{cmd_str}' (type: {type(cmd_str)})")
        
        try:
            self.logger.info(f"Constructing JSON-RPC payload for Flow.Launcher.ShellRun with command: '{cmd_str}'")
            payload = {
                "method": "Flow.Launcher.ShellRun",
                "parameters": [cmd_str]
            }
            print(json.dumps(payload))
            self.logger.info(f"Successfully printed JSON-RPC call for Flow.Launcher.ShellRun.")
            _global_argv_logger.info(f"[ACTION_shell_run_SUCCESS] Printed JSON-RPC for Flow.Launcher.ShellRun with command: '{cmd_str}'.")
        except Exception as e:
            self.logger.error(f"Exception during constructing/printing JSON for Flow.Launcher.ShellRun command '{cmd_str}': {e}", exc_info=True)
            _global_argv_logger.error(f"[ACTION_shell_run_EXCEPTION] Exception during JSON construction/print for Flow.Launcher.ShellRun('{cmd_str}'): {e}", exc_info=True)
            # Fallback to FlowLauncherAPI if direct print fails, though less likely.
            # This is primarily for logging the attempt. If print itself fails, this won't run effectively.
            FlowLauncherAPI.show_msg("Shell Command Error", f"Plugin failed to request shell_run. Error: {type(e).__name__}. Check logs.", self.resolved_default_icon_path)
        _global_argv_logger.info(f"[ACTION_shell_run_EXIT] shell_run('{cmd_str}') finished.")


    def copy_to_clipboard(self, text: Any, directCopy: Union[str, bool] = False, showDefaultNotification: Union[str, bool] = True):
        text_to_copy = str(text)
        _global_argv_logger.info(f"[ACTION_copy_to_clipboard_ENTRY] copy_to_clipboard called with text (len {len(text_to_copy)}), directCopy='{directCopy}', showDefaultNotification='{showDefaultNotification}'.")
        
        self.logger.info(f"Preparing to copy to clipboard. Text (first 30 chars): '{text_to_copy[:30]}...'")
        self.logger.debug(f"Parameter text_to_copy: '{text_to_copy}' (type: {type(text_to_copy)})")
        
        try:
            # Convert string bools from parameters if they are strings
            should_direct_copy = str(directCopy).lower() == 'true' if isinstance(directCopy, str) else bool(directCopy)
            should_show_notification = str(showDefaultNotification).lower() == 'true' if isinstance(showDefaultNotification, str) else bool(showDefaultNotification)

            self.logger.debug(f"Parameter should_direct_copy: {should_direct_copy} (type: {type(should_direct_copy)}) (original directCopy param: '{directCopy}', type: {type(directCopy)})")
            self.logger.debug(f"Parameter should_show_notification: {should_show_notification} (type: {type(should_show_notification)}) (original showDefaultNotification param: '{showDefaultNotification}', type: {type(showDefaultNotification)})")

            payload = {
                "method": "Flow.Launcher.CopyToClipboard",
                "parameters": [text_to_copy, should_direct_copy, should_show_notification]
            }
            print(json.dumps(payload))
            self.logger.info(f"Successfully printed JSON-RPC call for Flow.Launcher.CopyToClipboard.")
            _global_argv_logger.info(f"[ACTION_copy_to_clipboard_SUCCESS] Printed JSON-RPC for Flow.Launcher.CopyToClipboard.")

        except Exception as e:
            self.logger.error(f"Failed copy_to_clipboard: {e}", exc_info=True)
            _global_argv_logger.error(f"[ACTION_copy_to_clipboard_EXCEPTION] Exception: {e}", exc_info=True)
            # Use FlowLauncherAPI for error reporting, as it's less likely to be the source of error here.
            FlowLauncherAPI.show_msg("Clipboard Error", f"Plugin failed to request copy. Error: {type(e).__name__}", self.resolved_default_icon_path)
        _global_argv_logger.info(f"[ACTION_copy_to_clipboard_EXIT] copy_to_clipboard finished.")


    def change_query(self, new_query: str, requery: Union[str, bool] = "false"):
        query_str = str(new_query)
        _global_argv_logger.info(f"[ACTION_change_query_ENTRY] change_query('{query_str}', requery='{requery}') called.")
        
        try:
            should_requery = str(requery).lower() == 'true' if isinstance(requery, str) else bool(requery)
            self.logger.info(f"Preparing to change query. New query: '{query_str}', Requery: {should_requery}")
            self.logger.debug(f"Parameter query_str: '{query_str}' (type: {type(query_str)})")
            self.logger.debug(f"Parameter should_requery: {should_requery} (type: {type(should_requery)}) (original requery param: '{requery}', type: {type(requery)})")
            
            self.logger.info(f"Calling FlowLauncherAPI.change_query with Query='{query_str}', Requery={should_requery}")
            FlowLauncherAPI.change_query(query_str, requery=should_requery) # This seems to work, so keep using FlowLauncherAPI
            self.logger.info(f"Successfully completed call to FlowLauncherAPI.change_query.")
            _global_argv_logger.info(f"[ACTION_change_query_SUCCESS] FlowLauncherAPI.change_query('{query_str}', requery={should_requery}) completed.")
        except Exception as e: 
            self.logger.error(f"Failed change_query to '{query_str}': {e}", exc_info=True)
            _global_argv_logger.error(f"[ACTION_change_query_EXCEPTION] Exception: {e}", exc_info=True)
            # Use direct print for JSON-RPC as FlowLauncherAPI.show_msg might be the source of the problem
            payload = {
                "method": "Flow.Launcher.ShowMsg",
                "parameters": ["Change Query Error", f"Failed to change query. Error: {type(e).__name__}", self.resolved_default_icon_path]
            }
            print(json.dumps(payload))
        _global_argv_logger.info(f"[ACTION_change_query_EXIT] change_query('{query_str}') finished.")

    def flow_show_msg(self, title: str, sub_title: str, ico_path_param: Optional[str] = None):
        title_str, sub_title_str = str(title), str(sub_title)
        _global_argv_logger.info(f"[ACTION_flow_show_msg_ENTRY] flow_show_msg(title='{title_str}', sub_title='{sub_title_str}', ico='{ico_path_param}') called.")
        
        try:
            icon_to_use = self._resolve_icon_path_static(ico_path_param, self.plugindir, self.logger) or self.resolved_default_icon_path
            self.logger.info(f"Preparing to show message. Title='{title_str}', SubTitle='{sub_title_str}', Icon='{icon_to_use}'")
            self.logger.debug(f"Parameter title_str: '{title_str}' (type: {type(title_str)})")
            self.logger.debug(f"Parameter sub_title_str: '{sub_title_str}' (type: {type(sub_title_str)})")
            self.logger.debug(f"Parameter icon_to_use: '{icon_to_use}' (type: {type(icon_to_use)}) (original ico_path_param: '{ico_path_param}')")

            self.logger.info(f"Constructing JSON-RPC payload for Flow.Launcher.ShowMsg with Title='{title_str}', SubTitle='{sub_title_str}', Icon='{icon_to_use}'")
            payload = {
                "method": "Flow.Launcher.ShowMsg",
                "parameters": [title_str, sub_title_str, icon_to_use]
            }
            print(json.dumps(payload))
            self.logger.info(f"Successfully printed JSON-RPC call for Flow.Launcher.ShowMsg.")
            _global_argv_logger.info(f"[ACTION_flow_show_msg_SUCCESS] Printed JSON-RPC for Flow.Launcher.ShowMsg.")
        except Exception as e: 
            self.logger.error(f"Failed flow_show_msg. Title='{title_str}': {e}", exc_info=True)
            _global_argv_logger.error(f"[ACTION_flow_show_msg_EXCEPTION] Exception: {e}", exc_info=True)
            self.logger.critical(f"Cannot display error message via show_msg as it might be the source of error. Original title: {title_str}")
        _global_argv_logger.info(f"[ACTION_flow_show_msg_EXIT] flow_show_msg finished.")

if __name__ == "__main__":
    _global_argv_logger.info(f"[MAIN_BLOCK_ENTRY] __name__ == '__main__' block entered.")
    try:
        plugin_instance = HttpQueryForwarder()
        _global_argv_logger.info(f"[MAIN_BLOCK_SUCCESS] HttpQueryForwarder instance created successfully.")
    except Exception: 
        _global_argv_logger.exception("[MAIN_BLOCK_EXCEPTION] CRITICAL: Exception during HttpQueryForwarder instantiation in __main__ block.")
        emergency_log_path = Path(__file__).resolve().parent / "EMERGENCY_PLUGIN_INSTANTIATION_ERROR.log"
        error_details = traceback.format_exc() 
        import datetime
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(emergency_log_path, "a", encoding="utf-8") as f:
            f.write(f"--- {timestamp} ---\n{error_details}\n")
        raise