"""U-web-settings-37: the prod-like TLS edge (Caddy) and the exact nginx routes of the web image.

File-level and config-level checks: nginx.conf, compose.yaml, the Caddyfile and the CI workflow are parsed as files.
What only a running stack proves (redirect, HSTS on the wire, the 404 matrix through the edge, the log line) is
checked in the `e2e` CI job.
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / "apps" / "web" / "nginx.conf"
DOCKERFILE = ROOT / "apps" / "web" / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"
CADDYFILE = ROOT / "deploy" / "prod-like" / "Caddyfile"
CERTS = ROOT / "deploy" / "prod-like" / "certs.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
PLAYWRIGHT = ROOT / "apps" / "web" / "playwright.config.ts"
HOST = "mail-assistant.localhost"
PAGES = ("/", "/login", "/settings")
NOT_FOUND = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/healthz",
    "/readyz",
    "/metrics",
    "/api/docs",
    "/api/openapi.json",
    "/api/readyz",
    "/auth/anything-unknown",
    "/anything",
    "/index.html",
    "/settings/",
    "/login/extra",
)


def without_comments(text: str) -> str:
    return "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in text.splitlines())


def nginx_text() -> str:
    return without_comments(NGINX.read_text(encoding="utf-8"))


def locations() -> dict[tuple[bool, str], str]:
    """The location blocks as {(exact, path): body}; the config has no nested blocks inside a location."""
    found = re.findall(r"location\s+(=\s+)?(\S+)\s*\{([^}]*)\}", nginx_text())
    return {(bool(exact), path): body for exact, path, body in found}


def resolve(path: str) -> str:
    """Pick the location like nginx does (an exact match, else the longest prefix) and say what it does."""
    table = locations()
    body = table.get((True, path))
    if body is None:
        prefixes = [p for (exact, p) in table if not exact and path.startswith(p)]
        body = table[(False, max(prefixes, key=len))]
    if "return 404" in body:
        return "404"
    page = re.search(r"rewrite\s+\^\s+(/index\.html)\s+break;", body)
    if page is not None:
        return f"serve {page.group(1)}"
    served = re.search(r"try_files\s+(\S+)\s+=404", body)
    return "unknown" if served is None else f"serve {served.group(1)}"


def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def caddy() -> str:
    return without_comments(CADDYFILE.read_text(encoding="utf-8"))


def e2e_steps(key: str) -> str:
    job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["e2e"]
    return "\n".join(str(step.get(key, "")) for step in job["steps"])


# --- nginx: exact routes (criteria 3, 4, 5) ---


def test_given_the_web_config_when_read_then_it_has_no_proxy_pass() -> None:
    assert "proxy_pass" not in nginx_text()
    assert "resolver" not in nginx_text()


def test_given_the_web_config_when_read_then_only_the_exact_pages_and_assets_have_a_location() -> None:
    assert set(locations()) == {(True, "/"), (True, "/login"), (True, "/settings"), (False, "/assets/"), (False, "/")}


@pytest.mark.parametrize("path", PAGES)
def test_given_a_page_route_when_resolved_then_the_index_page_is_served(path: str) -> None:
    assert resolve(path) == "serve /index.html"


def test_given_an_asset_path_when_resolved_then_it_is_served_from_disk() -> None:
    assert resolve("/assets/index-abc123.js") == "serve $uri"


@pytest.mark.parametrize("path", NOT_FOUND)
def test_given_any_other_path_when_resolved_then_the_answer_is_404(path: str) -> None:
    assert resolve(path) == "404"


@pytest.mark.parametrize("key", [(True, "/"), (True, "/login"), (True, "/settings")])
def test_given_a_page_location_when_read_then_it_carries_the_csp_nosniff_and_no_cache(key: tuple[bool, str]) -> None:
    body = locations()[key]

    assert "Content-Security-Policy" in body
    assert "default-src 'self'" in body
    assert 'X-Content-Type-Options "nosniff"' in body
    assert 'Cache-Control "no-cache"' in body


@pytest.mark.parametrize("key", [(True, "/"), (True, "/login"), (True, "/settings")])
def test_given_a_page_location_when_read_then_the_index_is_served_by_a_rewrite_in_place(key: tuple[bool, str]) -> None:
    body = locations()[key]

    assert "rewrite ^ /index.html break;" in body
    assert "try_files" not in body  # try_files may re-enter location matching and hit the 404


def test_given_the_assets_location_when_read_then_it_is_immutable_with_nosniff() -> None:
    body = locations()[(False, "/assets/")]

    assert "max-age=31536000, immutable" in body
    assert 'X-Content-Type-Options "nosniff"' in body


def test_given_the_fallback_location_when_read_then_it_inherits_the_server_headers() -> None:
    body = locations()[(False, "/")]

    assert "add_header" not in body  # a location with its own add_header drops the server-level ones
    assert "Content-Security-Policy" in nginx_text()
    assert "nosniff" in nginx_text()


def test_given_the_web_config_when_read_then_hsts_is_left_to_the_edge() -> None:
    assert "Strict-Transport-Security" not in nginx_text()


def test_given_the_web_image_when_read_then_it_still_runs_non_root_with_a_healthcheck_on_the_index() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert "USER 101" in text
    assert "EXPOSE 8080" in text
    assert re.search(r"HEALTHCHECK .*http://127\.0\.0\.1:8080/", text)


# --- Caddy edge (criteria 2, 4, 6) ---


def test_given_the_caddyfile_when_read_then_plain_http_redirects_to_https_permanently() -> None:
    assert re.search(r"http://[^\s{]*\s*\{[^}]*redir\s+https://" + re.escape(HOST) + r"\S*\{uri\}\s+permanent", caddy())


def test_given_the_caddyfile_when_read_then_hsts_is_one_year_without_include_subdomains_or_preload() -> None:
    text = caddy()

    assert re.search(r'Strict-Transport-Security\s+"max-age=31536000"', text)
    assert "includeSubDomains" not in text
    assert "preload" not in text.lower()


def test_given_the_caddyfile_when_read_then_tls_comes_from_the_internal_ca_files_with_tls12_minimum() -> None:
    text = caddy()

    assert re.search(r"tls\s+/certs/server\.crt\s+/certs/server\.key", text)
    assert re.search(r"protocols\s+tls1\.2\s+tls1\.3", text)
    assert HOST in text


def test_given_the_caddyfile_when_read_then_api_and_auth_go_to_api_and_the_rest_to_web() -> None:
    text = caddy()

    assert re.search(r"handle\s+/api/\*\s*\{\s*reverse_proxy\s+api:8000", text)
    assert re.search(r"handle\s+/auth/\*\s*\{\s*reverse_proxy\s+api:8000", text)
    assert re.search(r"handle\s*\{\s*reverse_proxy\s+web:8080", text)
    assert "docs" not in text
    assert "metrics" not in text


def test_given_the_caddyfile_when_read_then_the_access_log_drops_the_query_string_and_headers() -> None:
    text = caddy()

    assert re.search(r"log\s*\{", text)
    assert re.search(r'request>uri\s+regexp\s+\S*\\\?\S*\s+""', text)
    assert re.search(r"request>headers\s+delete", text)


def test_given_the_caddyfile_when_read_then_it_has_no_insecure_verification_and_admin_is_off() -> None:
    text = caddy()

    assert "insecure_skip_verify" not in text
    assert re.search(r"admin\s+off", text)


def test_given_the_certs_script_when_read_then_it_makes_a_ca_and_a_leaf_for_the_host_outside_git() -> None:
    text = CERTS.read_text(encoding="utf-8")

    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert HOST in text
    assert "ca.crt" in text
    assert "server.crt" in text
    assert "server.key" in text
    assert "BEGIN" not in text  # no key material in the script itself
    assert "deploy/prod-like/certs/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


# --- compose (criteria 1, 7, 8) ---


def test_given_the_prod_like_profile_when_read_then_the_edge_service_exists_with_the_fixed_host_name() -> None:
    edge = compose()["services"]["edge"]

    assert edge["profiles"] == ["prod-like"]
    assert HOST in edge["networks"]["default"]["aliases"]
    assert edge["depends_on"]["api"]["condition"] == "service_healthy"
    assert edge["depends_on"]["web"]["condition"] == "service_healthy"
    assert edge["healthcheck"]["test"][0] == "CMD"


def test_given_the_edge_service_when_read_then_it_mounts_only_its_config_and_certs_read_only_as_non_root() -> None:
    edge = compose()["services"]["edge"]

    assert edge["volumes"] == [
        "./deploy/prod-like/Caddyfile:/etc/caddy/Caddyfile:ro",
        "./deploy/prod-like/certs:/certs:ro",
    ]
    assert int(str(edge["user"]).split(":")[0]) >= 10000
    assert edge["ports"]


@pytest.mark.parametrize("name", ["api", "web", "edge"])
def test_given_the_prod_like_services_when_read_then_each_is_hardened_and_binds_to_loopback(name: str) -> None:
    service = compose()["services"][name]

    assert service["read_only"] is True
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["cap_drop"] == ["ALL"]
    # The official caddy image sets file capabilities on the binary (cap_net_bind_service). With the bounding set
    # emptied by cap_drop ALL the kernel refuses to exec it (EPERM). The edge gets that one capability back; its
    # ports are unprivileged and no-new-privileges stops the process from gaining it.
    assert service.get("cap_add", []) == (["NET_BIND_SERVICE"] if name == "edge" else [])
    assert "privileged" not in service
    assert all(str(port).startswith("127.0.0.1:") for port in service.get("ports", []))


def test_given_the_compose_file_when_read_then_there_is_no_literal_secret() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    assert not re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text)
    assert not re.search(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:(?!\$\{)[^@\s]+@", text)
    literal = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"(PASSWORD|SECRET|TOKEN|KEY)\w*\s*:", line)
        and "${" not in line
        and not re.search(r":\s+/certs/\S+$", line)  # the path of a key file is not a secret
    ]
    assert literal == []


# --- CI and Playwright (criterion 1) ---


def test_given_the_e2e_job_when_read_then_it_makes_the_certs_trusts_the_ca_and_runs_through_the_edge() -> None:
    steps = e2e_steps("run") + e2e_steps("env")

    assert "deploy/prod-like/certs.sh" in steps
    assert "certutil" in steps  # the browser trusts the internal CA through its NSS store
    assert f"https://{HOST}:8443" in steps
    assert "E2E_BASE_URL" in steps
    assert steps.index("certs.sh") < steps.index("up -d --build --wait")


def test_given_the_e2e_job_when_read_then_it_checks_the_edge_with_curl() -> None:
    steps = e2e_steps("run")

    assert "Strict-Transport-Security" in steps
    assert "--cacert" in steps
    assert "/openapi.json" in steps
    assert "/auth/anything-unknown" in steps
    assert "logs" in steps
    assert "edge" in steps  # the log line has the path only
    # compose only knows services of an active profile, so every compose call of the job names it
    calls = re.findall(r"docker compose (?!--profile prod-like)(?!up|run)(\w+)", steps)
    assert calls == []


def test_given_the_playwright_config_when_read_then_the_base_url_is_the_edge_and_certificates_stay_verified() -> None:
    text = PLAYWRIGHT.read_text(encoding="utf-8")

    assert f"https://{HOST}:8443" in text
    assert "ignoreHTTPSErrors" not in text
