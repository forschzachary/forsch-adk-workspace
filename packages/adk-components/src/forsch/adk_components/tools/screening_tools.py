"""ADK tool functions for ScreeningRoom — movie search, details, recommendations, watchlist, and tracking.

All tools are read-only against TMDB API (placeholder until API key is provided).
Watchlist and watched tracking use a local JSONL store.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ── config ──────────────────────────────────────────────────────────────────

def _tmdb_api_key() -> str:
    return os.environ.get("TMDB_API_KEY", "PLACEHOLDER_TMDB_API_KEY")

def _tmdb_base_url() -> str:
    return "https://api.themoviedb.org/3"

def _store_path() -> Path:
    ws = Path(os.environ.get("FORSCH_ADK_WORKSPACE", "/workspace"))
    return ws / "data" / "screening_store.jsonl"

def _load_store() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def _append_store(entry: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")

# ── search ──────────────────────────────────────────────────────────────────

def search_movies(
    query: str = "",
    year: int = 0,
    genre: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search for movies by title, year, and genre.

    Args:
        query: Movie title or keyword search.
        year: Release year filter.
        genre: Genre name filter (e.g. 'action', 'comedy', 'horror').
        limit: Max results to return.
    """
    # PLACEHOLDER: implement TMDB API call
    # GET /search/movie?query={query}&year={year}&api_key={key}
    return [{"status": "placeholder", "query": query, "year": year, "genre": genre, "limit": limit}]


def get_movie_details(movie_id: int) -> dict[str, Any]:
    """Get full movie details including synopsis, cast, ratings, runtime, and release info.

    Args:
        movie_id: TMDB movie ID.
    """
    # PLACEHOLDER: implement TMDB API call
    # GET /movie/{id}?api_key={key}&append_to_response=credits
    return {"status": "placeholder", "movie_id": movie_id}


def get_similar_movies(movie_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Get movies similar to a given film (recommendations).

    Args:
        movie_id: TMDB movie ID to base recommendations on.
        limit: Max results to return.
    """
    # PLACEHOLDER: implement TMDB API call
    # GET /movie/{id}/similar?api_key={key}
    return [{"status": "placeholder", "movie_id": movie_id, "limit": limit}]

# ── watchlist ───────────────────────────────────────────────────────────────

def add_to_watchlist(
    movie_id: int,
    title: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Add a movie to your watchlist.

    Args:
        movie_id: TMDB movie ID.
        title: Movie title (optional, for readability).
        notes: Why you want to watch it (optional).
    """
    entry = {
        "type": "watchlist",
        "movie_id": movie_id,
        "title": title,
        "notes": notes,
    }
    _append_store(entry)
    return {"status": "added", "movie_id": movie_id, "title": title}


def get_watchlist() -> list[dict[str, Any]]:
    """Get your current watchlist."""
    store = _load_store()
    return [e for e in store if e.get("type") == "watchlist"]

# ── watched tracking ────────────────────────────────────────────────────────

def log_watched(
    movie_id: int,
    title: str = "",
    rating: int = 0,
    notes: str = "",
) -> dict[str, Any]:
    """Log that you watched a movie, with optional rating and notes.

    Args:
        movie_id: TMDB movie ID.
        title: Movie title (optional).
        rating: Your rating 1-5 (optional).
        notes: What you thought (optional).
    """
    entry = {
        "type": "watched",
        "movie_id": movie_id,
        "title": title,
        "rating": rating,
        "notes": notes,
    }
    _append_store(entry)
    return {"status": "logged", "movie_id": movie_id, "title": title}


def get_watched() -> list[dict[str, Any]]:
    """Get your watch history."""
    store = _load_store()
    return [e for e in store if e.get("type") == "watched"]
