import json
import sqlite3
import time
from pathlib import Path

import requests


class OpenAlexCache:
    def __init__(
        self,
        cache_path: str = "cache/new_openalex_cache.db",
        timeout: int = 3,
        max_retries: int = 3,
    ):
        self.cache_path = Path(cache_path)

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

        # Reuse one session for both APIs.
        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "ReferenceFormatter/1.0 "
                "(mailto:your-email@example.com)"
            )
        })

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS doi_metadata (
                doi TEXT PRIMARY KEY,
                metadata TEXT,
                success INTEGER NOT NULL,
                error TEXT,
                source TEXT,
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
            "doi:"
        )

        for prefix in prefixes:
            if doi.lower().startswith(prefix):
                doi = doi[len(prefix):]
                break

        return doi.strip().lower()

    def _get_cached(self, doi: str):
        row = self.conn.execute(
            """
            SELECT metadata, success, error, source
            FROM doi_metadata
            WHERE doi = ?
            """,
            (doi,),
        ).fetchone()

        if row is None:
            return None

        metadata, success, error, source = row

        return {
            "success": bool(success),
            "metadata": json.loads(metadata) if metadata else None,
            "error": error,
            "source": source,
            "cached": True,
        }

    def _save(
        self,
        doi: str,
        metadata: dict | None,
        success: bool,
        error: str | None,
        source: str | None
    ):
        now = time.time()

        self.conn.execute(
            """
            INSERT INTO doi_metadata (
                doi,
                metadata,
                success,
                error,
                source,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doi)
            DO UPDATE SET
                metadata = excluded.metadata,
                success = excluded.success,
                error = excluded.error,
                source = excluded.source,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                doi,
                json.dumps(metadata) if metadata else None,
                int(success),
                error,
                source,
                now,
                now,
            ),
        )

        self.conn.commit()

    def _query_api(
        self,
        url: str,
        source: str,
    ) -> dict:
        """
        Query an API with retries.

        Returns:
            {
                "success": bool,
                "metadata": dict | None,
                "error": str | None,
            }
        """

        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    try:
                        metadata = response.json()
                    except ValueError:
                        last_error = f"{source}_invalid_json"
                        break

                    if not isinstance(metadata, dict):
                        last_error = f"{source}_invalid_json"
                        break

                    # Crossref returns its work metadata under "message".
                    if source == "crossref":
                        metadata = metadata.get("message")

                        if not isinstance(metadata, dict):
                            last_error = "crossref_invalid_response"
                            break

                    return {
                        "success": True,
                        "metadata": metadata,
                        "error": None,
                        "source": source
                    }

                if response.status_code == 404:
                    return {
                        "success": False,
                        "metadata": None,
                        "error": f"{source}_not_found",
                        "source": None
                    }

                if response.status_code in (
                    429,
                    500,
                    502,
                    503,
                    504,
                ):
                    last_error = f"{source}_http_{response.status_code}"

                    if attempt < self.max_retries - 1:
                        # Respect Retry-After when available.
                        retry_after = response.headers.get("Retry-After")

                        try:
                            delay = float(retry_after)
                        except (TypeError, ValueError):
                            delay = 2 ** attempt

                        time.sleep(min(delay, 30))
                        continue

                    break

                last_error = f"{source}_http_{response.status_code}"
                break

            except requests.exceptions.Timeout:
                last_error = f"{source}_timeout"

            except requests.exceptions.ConnectionError:
                last_error = f"{source}_connection_error"

            except requests.exceptions.RequestException:
                last_error = f"{source}_request_error"

            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        return {
            "success": False,
            "metadata": None,
            "error": last_error or f"{source}_failed",
            "source": None
        }

    def get(self, doi: str) -> dict:
        """
        Get metadata for a DOI.

        Lookup order:
            1. SQLite cache
            2. OpenAlex
            3. Crossref fallback

        The existing response structure and database schema
        remain unchanged.
        """

        doi = self._normalize_doi(doi)

        if not doi:
            return {
                "success": False,
                "metadata": None,
                "error": "empty_doi",
                "source": None,
                "cached": False,
            }

        # ---------------------------------------------------------
        # 1. Check cache
        # ---------------------------------------------------------
        cached = self._get_cached(doi)

        if cached is not None:
            # print(f'cached meta: {json.dumps(cached)}')
            return cached

        # ---------------------------------------------------------
        # 2. Query OpenAlex
        # ---------------------------------------------------------
        openalex_url = (
            "https://api.openalex.org/works/"
            f"https://doi.org/{doi}"
        )
        print(f'OpenAlexAPI query with doi: {doi}')
        result = self._query_api(
            url=openalex_url,
            source="openalex",
        )
        print(result["success"])
        if result["success"]:
            self._save(
                doi=doi,
                metadata=result["metadata"],
                success=True,
                error=None,
                source= "openalex"
            )

            return {
                "success": True,
                "metadata": result["metadata"],
                "error": None,
                "cached": False,
                "source": "openalex"
            }

        openalex_error = result["error"]

        # ---------------------------------------------------------
        # 3. Fallback to Crossref
        # ---------------------------------------------------------
        crossref_url = (
            "https://api.crossref.org/works/"
            f"{requests.utils.quote(doi, safe='/')}"
        )
        print(f'CrossRefAPI query with doi: {doi}')

        result = self._query_api(
            url=crossref_url,
            source="crossref",
        )
        print(result["success"])
        if result["success"]:
            # print(json.dumps(result["metadata"]))
            self._save(
                doi=doi,
                metadata=result["metadata"],
                success=True,
                error=None,
                source="crossref",
            )

            return {
                "success": True,
                "metadata": result["metadata"],
                "error": None,
                "cached": False,
                "source": "crossref"
            }

        crossref_error = result["error"]

        # ---------------------------------------------------------
        # 4. Both APIs failed
        # ---------------------------------------------------------
        error = (
            f"openalex: {openalex_error}; "
            f"crossref: {crossref_error}"
        )

        # Cache permanent not-found responses only.
        # Avoid caching transient API/network failures so that
        # subsequent calls can retry.
        if (
            openalex_error == "openalex_not_found"
            and crossref_error == "crossref_not_found"
        ):
            self._save(
                doi=doi,
                metadata=None,
                success=False,
                error="not_found",
                source= None,
            )

        return {
            "success": False,
            "metadata": None,
            "error": error,
            "source": None,
            "cached": False,
        }

    def close(self):
        self.session.close()
        self.conn.close()