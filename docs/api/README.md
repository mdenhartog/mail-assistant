# API guide

This guide explains what the generated [API reference](reference.md) cannot: how a caller is authenticated and authorised, what the category file routes expect and return, and the error format. The reference and `openapi.json` are generated from the code; do not edit them by hand (`node scripts/docs.mjs api`).

The API belongs to the web app of this project. It is meant for that app and for scripts of the one user who signs in; it is not a public integration API.

## Base URL and format

- Routes of the web app are under `/api`; the sign-in routes are under `/auth`; the probes are `/healthz` and `/readyz`.
- Requests and responses are JSON unless a route says otherwise. The category file routes send and receive YAML (`application/yaml`).
- Errors use RFC 9457 `application/problem+json`: an object with `type`, `title` and `status`. The text is a fixed sentence and never repeats a value that the caller sent. A refused category file adds `problems` (see below).

## Authentication and authorisation

There are no OAuth scopes or roles. The API has one kind of caller, the signed-in user of the single mailbox:

1. The caller signs in with `POST /auth/request-code` and `POST /auth/verify-code` (username plus a one-time code sent by e-mail). The response sets the session cookie `__Host-session`.
2. `GET /api/session` returns the masked address, the CSRF token and the expiry of the session. The token is only returned to a same-origin request.
3. Every route that changes state (`POST` and `PUT`) must also carry the header `X-CSRF-Token` with that token, an `Origin` header equal to the public origin of the app and no cross-site Fetch Metadata. A missing or wrong token or origin is always the same `403`.

A route without a live session answers `401`. A locked web sign-in also answers `401`.

The generated reference lists every operation as "Public (no authentication)" because the OpenAPI document declares no security scheme yet. That is a gap of the document, not of the code: only the two sign-in routes and the probes are public, and a test of the route inventory (`backend/tests/test_route_inventory.py`) fails when a route declares neither the session nor the public marker, or when a `POST` or `PUT` lacks the CSRF check.

Every route is also rate-limited (the limit is counted before the session is looked up); a flood answers `429` with `Retry-After`.

## Category routes

These routes keep the category list of the user. All of them need a live session; those that change state need the CSRF token and `Origin`. The list itself is read and saved with `GET` and `PUT /api/categories` (see the reference).

| Operation | Needs | Request | Success | Errors |
| --- | --- | --- | --- | --- |
| `POST /api/categories/upload` | session, CSRF token, `Origin` | The file as the body, `Content-Type: application/yaml` (or `text/yaml`, `text/plain`), at most 256 KiB of file (the route accepts 320 KiB of body) | `200` preview | `401`, `403`, `409`, `413`, `415`, `422` with `problems`, `429`, `500` |
| `POST /api/categories/upload/{preview_id}/confirm` | session of the upload, CSRF token, `Origin` | JSON `{"file_hash": "<64 hex characters>"}` | `200` the stored list | `401`, `403`, `409`, `415`, `422`, `429`, `500` |
| `POST /api/categories/restore-previous` | session, CSRF token, `Origin` | JSON `{"version": <the version the caller sees as current>}` | `200` the stored list | `401`, `403`, `409`, `415`, `422`, `429`, `500` |
| `GET /api/categories/export` | session | none | `200` `mail-categories.yaml` as an attachment | `401`, `409` (no list yet), `429` |
| `GET /api/categories/template?file=template` or `file=example` | session | `file`: `template` (default) or `example` | `200` the commented template or the worked example as an attachment | `401`, `422` (unknown `file`), `429` |

### Upload, preview and confirm

1. `POST /api/categories/upload` checks the file and stores only a preview, bound to the session, the hash of the file and the version of the list it was made against. The preview lives 15 minutes.
2. The `200` body has `preview_id`, `file_hash`, `base_version`, `expires_at`, the counts `added`, `changed` and `removed`, `removed_categories` (names) and `instructions_changed`. Nothing of the file is returned beyond those names.
3. `POST /api/categories/upload/{preview_id}/confirm` replaces the whole list as one new version when every binding still holds: the same session, the same file hash, a preview that has not expired or been used, and a list that has not changed since. Otherwise it answers `409` and stores nothing. A double submit makes one version.
4. `POST /api/categories/restore-previous` stores a new version equal to the one before the version the caller names; `409` when that is no longer the current version or there is no earlier version.

The file format is `schema: 1`; the field list is in the [user guide](../user-guide/label-structure.md#what-the-fields-mean) and the commented template is the file served by `GET /api/categories/template`.

A refused file answers `422` with `application/problem+json` and a `problems` array; every problem has `rule`, `line`, `field` and a fixed `message`, for example line 12, field `categories[0].senders[3]`. Nothing is stored.

Limits: at most 256 KiB of file; a session may store as many previews per hour as the hourly limit for list saves (10 by default), then `429` with `Retry-After`.

### Download headers

The export and the template are sent with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. The export file name is `mail-categories.yaml`.

## Other operations

The sign-in, settings, places, plan and probe routes are listed in the [reference](reference.md).

## Versioning

There is no version in the path. The contract is checked against the OpenAPI document in CI; a change to a route changes `openapi.json`, and the web app is built against it.
