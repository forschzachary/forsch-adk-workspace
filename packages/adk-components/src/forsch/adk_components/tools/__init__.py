"""Shared tools for ADK agents."""

from . import household, stability_tools, screening_tools
from .authsome_client import AuthsomeHTTPClient, AuthsomeHTTPError
from .crm_tools import get_crm_health_snapshot, list_recent_crm_leads
from .email_groceries import (
    add_grocery_email_sender,
    is_grocery_email_sender_allowed,
    list_grocery_email_senders,
    log_grocery_email_receipt,
    remove_grocery_email_sender,
)
from .frappe_client import FrappeClient
from .graph_tools import get_factory_status, get_graph_overview, manage_cluster
from .household import add_reminder, get_grocery_log, log_groceries
from .stability_tools import check_service_health, get_git_state, get_workspace_inventory
from .stability_tools import validate_agent_imports
from .ops_tools import execute_bash_command, read_host_file, write_host_file
from .wow_tools import (
    get_boss_loot,
    get_dungeon_bosses,
    get_item_details,
    get_player,
    register_player,
    search_items,
    search_npcs,
    search_quests,
)
from .screening_tools import (
    add_to_watchlist,
    get_movie_details,
    get_similar_movies,
    get_watched,
    get_watchlist,
    log_watched,
    search_movies,
)
from .reference_tools import read_reference, search_reference

__all__ = [
    "AuthsomeHTTPClient",
    "AuthsomeHTTPError",
    "read_reference",
    "search_reference",
    "FrappeClient",
    "add_grocery_email_sender",
    "add_reminder",
    "check_service_health",
    "get_boss_loot",
    "get_dungeon_bosses",
    "get_factory_status",
    "get_git_state",
    "get_grocery_log",
    "get_graph_overview",
    "get_item_details",
    "get_player",
    "get_workspace_inventory",
    "get_crm_health_snapshot",
    "graph_tools",
    "household",
    "is_grocery_email_sender_allowed",
    "list_grocery_email_senders",
    "list_recent_crm_leads",
    "log_groceries",
    "log_grocery_email_receipt",
    "manage_cluster",
    "register_player",
    "remove_grocery_email_sender",
    "search_items",
    "search_npcs",
    "search_quests",
    "stability_tools",
    "validate_agent_imports",
    "execute_bash_command",
    "read_host_file",
    "write_host_file",
    "add_to_watchlist",
    "get_movie_details",
    "get_similar_movies",
    "get_watched",
    "get_watchlist",
    "log_watched",
    "search_movies",
    "screening_tools",
]
