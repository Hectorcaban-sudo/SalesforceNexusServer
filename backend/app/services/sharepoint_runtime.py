"""SharePoint runtime used by the walker/worker. Adapters stay in sharepoint.py."""
from ..sharepoint import run_sharepoint_file, run_sharepoint_list

__all__ = ["run_sharepoint_file", "run_sharepoint_list"]
