import json
import sqlite3
import time
from pathlib import Path

import requests


class OpenAlexCache:
    def __init__(
        self,
        cache_path: str = "cache/openalex_cache.db",
        timeout: int = 10,
        max_retries: int = 3,
    ):
        self.cache_path = Path(cache_path)

        # Create parent directory
        self.cache_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.timeout = timeout
        self.max_retries = max_retries

        self.conn = sqlite3.connect(
            str(self.cache_path),
            timeout=30,
        )

        self._create_table()

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS doi_metadata (
                doi TEXT PRIMARY KEY,
                metadata TEXT,
                success INTEGER NOT NULL,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        self.conn.commit()

    @staticmethod
    def _normalize_doi(doi: str) -> str:
        doi = doi.strip()

        prefixes = (
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
        )

        for prefix in prefixes:
            if doi.lower().startswith(prefix):
                doi = doi[len(prefix):]
                break

        return doi.strip().lower()

    def _get_cached(self, doi: str):
        row = self.conn.execute(
            """
            SELECT metadata, success, error
            FROM doi_metadata
            WHERE doi = ?
            """,
            (doi,),
        ).fetchone()

        if row is None:
            return None

        metadata, success, error = row

        return {
            "success": bool(success),
            "metadata": json.loads(metadata) if metadata else None,
            "error": error,
            "cached": True,
        }

    def _save(
        self,
        doi: str,
        metadata: dict | None,
        success: bool,
        error: str | None,
    ):
        now = time.time()

        self.conn.execute(
            """
            INSERT INTO doi_metadata (
                doi,
                metadata,
                success,
                error,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(doi)
            DO UPDATE SET
                metadata = excluded.metadata,
                success = excluded.success,
                error = excluded.error,
                updated_at = excluded.updated_at
            """,
            (
                doi,
                json.dumps(metadata) if metadata else None,
                int(success),
                error,
                now,
                now,
            ),
        )

        self.conn.commit()

    def get(self, doi: str) -> dict:
        """
        Get metadata for a DOI.

        Returns cached metadata if available.
        Otherwise queries OpenAlex and caches the result.
        """

        doi = self._normalize_doi(doi)

        if not doi:
            return {
                "success": False,
                "metadata": None,
                "error": "empty_doi",
                "cached": False,
            }

        # ---------------------------------------------------------
        # Check cache first
        # ---------------------------------------------------------
        cached = self._get_cached(doi)

        if cached is not None:
            return cached

        # ---------------------------------------------------------
        # Query OpenAlex
        # ---------------------------------------------------------
        url = (
            "https://api.openalex.org/works/"
            f"https://doi.org/{doi}"
        )

        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    timeout=self.timeout,
                )

                # Success
                if response.status_code == 200:
                    metadata = response.json()

                    self._save(
                        doi=doi,
                        metadata=metadata,
                        success=True,
                        error=None,
                    )

                    return {
                        "success": True,
                        "metadata": metadata,
                        "error": None,
                        "cached": False,
                    }

                # DOI not found
                if response.status_code == 404:
                    self._save(
                        doi=doi,
                        metadata=None,
                        success=False,
                        error="not_found",
                    )

                    return {
                        "success": False,
                        "metadata": None,
                        "error": "not_found",
                        "cached": False,
                    }

                # Temporary errors
                if response.status_code in (
                    429,
                    500,
                    502,
                    503,
                    504,
                ):
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue

                    error = f"http_{response.status_code}"

                    return {
                        "success": False,
                        "metadata": None,
                        "error": error,
                        "cached": False,
                    }

                # Other HTTP errors
                error = f"http_{response.status_code}"

                self._save(
                    doi=doi,
                    metadata=None,
                    success=False,
                    error=error,
                )

                return {
                    "success": False,
                    "metadata": None,
                    "error": error,
                    "cached": False,
                }

            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue

                return {
                    "success": False,
                    "metadata": None,
                    "error": "timeout",
                    "cached": False,
                }

            except requests.exceptions.ConnectionError:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue

                return {
                    "success": False,
                    "metadata": None,
                    "error": "connection_error",
                    "cached": False,
                }

            except requests.exceptions.RequestException as e:
                return {
                    "success": False,
                    "metadata": None,
                    "error": f"request_error: {e}",
                    "cached": False,
                }

            except ValueError:
                return {
                    "success": False,
                    "metadata": None,
                    "error": "invalid_json",
                    "cached": False,
                }

        return {
            "success": False,
            "metadata": None,
            "error": "max_retries_exceeded",
            "cached": False,
        }

    def close(self):
        self.conn.close()