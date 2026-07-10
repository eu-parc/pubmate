"""Download nanopublication TriG files from query API results."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import rdflib
from rdflib.namespace import RDF

NP = rdflib.Namespace("http://www.nanopub.org/nschema#")


@dataclass(frozen=True)
class DownloadedNanopub:
    artifact_code: str
    np_uri: str
    path: pathlib.Path


def endpoint_url_with_params(endpoint_url: str, query_params: Sequence[str] = ()) -> str:
    """Return ``endpoint_url`` with additional ``key=value`` query parameters."""
    if not query_params:
        return endpoint_url

    parsed = urllib.parse.urlsplit(endpoint_url)
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    for param in query_params:
        if "=" not in param:
            raise ValueError(f"Expected query parameter as key=value, got: {param}")
        key, value = param.split("=", 1)
        if not key:
            raise ValueError(f"Expected non-empty query parameter key in: {param}")
        params.append((key, value))

    query = urllib.parse.urlencode(params)
    return urllib.parse.urlunsplit(parsed._replace(query=query))


def fetch_url(url: str, *, accept: str, timeout: int, retries: int) -> bytes:
    """Fetch a URL with retry/backoff and an Accept header."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"Accept": accept})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (TimeoutError, urllib.error.URLError) as error:
            last_error = error
            if attempt == retries:
                break
            time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}") from last_error


def nanopub_uris_from_query(
    query_url: str,
    *,
    np_column: str = "np",
    timeout: int,
    retries: int,
) -> list[str]:
    """Fetch a SPARQL JSON endpoint result and extract nanopublication URIs."""
    payload = fetch_url(
        query_url,
        accept="application/sparql-results+json",
        timeout=timeout,
        retries=retries,
    )
    data = json.loads(payload)
    bindings = data.get("results", {}).get("bindings", [])
    uris = {
        row[np_column]["value"]
        for row in bindings
        if row.get(np_column, {}).get("type") == "uri" and row[np_column].get("value")
    }
    if not uris:
        raise RuntimeError(f"The query returned no nanopublication URIs in the '{np_column}' column.")
    return sorted(uris)


def artifact_code(np_uri: str) -> str:
    """Extract the trusty artifact code from a nanopublication URI."""
    code = np_uri.rstrip("/").rsplit("/", 1)[-1]
    if not code.startswith("RA"):
        raise ValueError(f"Unexpected nanopublication URI without RA artifact code: {np_uri}")
    return code


def ensure_nanopublication_trig(content: bytes, *, source_url: str) -> None:
    """Raise if ``content`` does not parse as a nanopublication TriG document."""
    dataset = rdflib.Dataset()
    try:
        dataset.parse(data=content.decode("utf-8"), format="trig")
    except Exception as error:  # rdflib raises several parser-specific errors.
        raise RuntimeError(f"Downloaded content is not valid TriG: {source_url}") from error

    if not any((None, RDF.type, NP.Nanopublication) in graph for graph in dataset.graphs()):
        raise RuntimeError(f"Downloaded content does not look like a nanopublication: {source_url}")


def download_nanopubs(
    np_uris: Iterable[str],
    *,
    output_dir: pathlib.Path,
    timeout: int,
    retries: int,
    validate: bool = True,
) -> list[DownloadedNanopub]:
    """Download each nanopublication URI as ``<artifact-code>.trig``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[DownloadedNanopub] = []
    for np_uri in np_uris:
        code = artifact_code(np_uri)
        trig_url = f"{np_uri}.trig"
        content = fetch_url(trig_url, accept="application/trig", timeout=timeout, retries=retries)
        if validate:
            ensure_nanopublication_trig(content, source_url=trig_url)
        path = output_dir / f"{code}.trig"
        path.write_bytes(content)
        downloaded.append(DownloadedNanopub(code, np_uri, path))
    return downloaded


def sync_nanopubs(
    np_uris: Iterable[str],
    *,
    output_dir: pathlib.Path,
    timeout: int,
    retries: int,
    validate: bool = True,
) -> list[DownloadedNanopub]:
    """Replace ``output_dir``'s ``*.trig`` files with the downloaded set atomically."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pubmate-nanopub-download-") as temp_dir:
        staging_dir = pathlib.Path(temp_dir)
        staged = download_nanopubs(
            np_uris,
            output_dir=staging_dir,
            timeout=timeout,
            retries=retries,
            validate=validate,
        )
        for path in output_dir.glob("*.trig"):
            path.unlink()
        downloaded: list[DownloadedNanopub] = []
        for item in staged:
            dest = output_dir / item.path.name
            shutil.copy2(item.path, dest)
            downloaded.append(DownloadedNanopub(item.artifact_code, item.np_uri, dest))
    return downloaded


def write_manifest(path: pathlib.Path, rows: Sequence[DownloadedNanopub]) -> None:
    """Write a TSV manifest of downloaded nanopublications."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("artifact_code\tnp_uri\tpath\n")
        for row in rows:
            handle.write(f"{row.artifact_code}\t{row.np_uri}\t{row.path}\n")
