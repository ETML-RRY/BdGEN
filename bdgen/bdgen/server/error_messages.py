"""Translate provider/API exceptions into short, French, user-facing messages.

The worker catch-all in :mod:`bdgen.server.jobs` used to surface raw exceptions
like ``APIStatusError: {'type': 'error', 'error': {...}, 'request_id': '...'}``
straight to the UI. This module turns those into a one-line explanation that
the end user can actually act on (retry, fix a key, reduce payload, etc.).
The raw exception is still kept in the worker's traceback for diagnostics.
"""
from __future__ import annotations

from typing import Any


# Anthropic and OpenAI both expose a typed ``error.type`` field on their HTTP
# error bodies. The keys below cover both conventions (Anthropic uses
# ``_error`` suffixes, OpenAI uses bare names).
_FRIENDLY_BY_TYPE: dict[str, str] = {
    "overloaded_error": (
        "Le service d'IA est temporairement surchargé. "
        "Réessayez dans quelques minutes."
    ),
    "rate_limit_error": (
        "Quota d'appels atteint chez le fournisseur d'IA. "
        "Patientez quelques minutes avant de relancer."
    ),
    "rate_limit_exceeded": (
        "Quota d'appels atteint chez le fournisseur d'IA. "
        "Patientez quelques minutes avant de relancer."
    ),
    "authentication_error": (
        "Clé API invalide ou expirée. "
        "Vérifiez les secrets configurés pour ce fournisseur."
    ),
    "invalid_api_key": (
        "Clé API invalide ou expirée. "
        "Vérifiez les secrets configurés pour ce fournisseur."
    ),
    "permission_error": (
        "La clé API ne dispose pas des droits requis pour cette opération."
    ),
    "not_found_error": (
        "Modèle ou ressource introuvable côté fournisseur. "
        "Vérifiez le nom du modèle dans les options de génération."
    ),
    "request_too_large": (
        "Requête trop volumineuse pour le modèle. "
        "Réduisez la taille du scénario ou des références envoyées."
    ),
    "context_length_exceeded": (
        "Le contenu envoyé dépasse la fenêtre de contexte du modèle. "
        "Réduisez la taille du scénario ou des références envoyées."
    ),
    "invalid_request_error": (
        "Requête refusée par le fournisseur d'IA."
    ),
    "billing_error": (
        "Problème de facturation côté fournisseur "
        "(crédit épuisé ou abonnement requis)."
    ),
    "insufficient_quota": (
        "Crédit épuisé sur le compte du fournisseur d'IA."
    ),
    "api_error": (
        "Erreur interne côté fournisseur d'IA. Réessayez dans quelques minutes."
    ),
    "timeout": (
        "Le fournisseur d'IA n'a pas répondu à temps. Réessayez."
    ),
}

# HTTP status fallback when no typed error is available (e.g. the SDK raised
# a transport error before parsing a JSON body).
_FRIENDLY_BY_STATUS: dict[int, str] = {
    401: _FRIENDLY_BY_TYPE["authentication_error"],
    403: _FRIENDLY_BY_TYPE["permission_error"],
    404: _FRIENDLY_BY_TYPE["not_found_error"],
    408: _FRIENDLY_BY_TYPE["timeout"],
    413: _FRIENDLY_BY_TYPE["request_too_large"],
    429: _FRIENDLY_BY_TYPE["rate_limit_error"],
    500: _FRIENDLY_BY_TYPE["api_error"],
    502: "Le fournisseur d'IA est momentanément indisponible. Réessayez.",
    503: "Le fournisseur d'IA est momentanément indisponible. Réessayez.",
    504: _FRIENDLY_BY_TYPE["timeout"],
    529: _FRIENDLY_BY_TYPE["overloaded_error"],
}

_PROVIDER_LABEL_BY_MODULE: dict[str, str] = {
    "anthropic": "Claude (Anthropic)",
    "openai": "OpenAI",
    "fal_client": "fal.ai",
    "httpx": "réseau",
}

# Error types where the provider's English ``message`` adds real information
# (the offending field, size, or resource name). For other typed errors the
# message is usually a generic restatement of the type — we suppress it.
_INFORMATIVE_DETAIL_TYPES: frozenset[str] = frozenset({
    "invalid_request_error",
    "request_too_large",
    "context_length_exceeded",
    "not_found_error",
    "billing_error",
    "permission_error",
})


def _extract_body(exc: BaseException) -> dict[str, Any] | None:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        return body
    # Some SDKs expose the parsed payload under .response.json() — we don't
    # call it here because it may not be a JSON response. The .body attribute
    # is the documented surface for both Anthropic and OpenAI.
    return None


def _extract_error_dict(body: dict[str, Any] | None) -> dict[str, Any] | None:
    if not body:
        return None
    err = body.get("error")
    if isinstance(err, dict):
        return err
    return None


def _provider_label(exc: BaseException) -> str | None:
    module = (exc.__class__.__module__ or "").split(".")[0]
    return _PROVIDER_LABEL_BY_MODULE.get(module)


def format_user_error(exc: BaseException) -> str:
    """Return a short, French, user-facing message for ``exc``.

    The function never raises: any failure to parse the exception falls back
    to the legacy ``"ClassName: str(exc)"`` representation so the user still
    sees something deterministic.
    """
    try:
        body = _extract_body(exc)
        err = _extract_error_dict(body)
        err_type = err.get("type") if err else None
        err_message = err.get("message") if err else None
        status = getattr(exc, "status_code", None)
        request_id = getattr(exc, "request_id", None)
        if not request_id and isinstance(body, dict):
            request_id = body.get("request_id")

        friendly: str | None = None
        matched_by_type = False
        if isinstance(err_type, str):
            friendly = _FRIENDLY_BY_TYPE.get(err_type)
            matched_by_type = friendly is not None
        if friendly is None and isinstance(status, int):
            friendly = _FRIENDLY_BY_STATUS.get(status)

        if friendly is None:
            return f"{type(exc).__name__}: {exc}"

        parts: list[str] = []
        provider = _provider_label(exc)
        if provider:
            parts.append(f"[{provider}]")
        parts.append(friendly)
        # Suppress the provider's English ``message`` when it's redundant
        # (e.g. "Overloaded" on top of an overloaded_error). Keep it when the
        # type carries actionable specifics (which field was invalid, which
        # model wasn't found, etc.) or when only the status code matched.
        keep_detail = (not matched_by_type) or (
            isinstance(err_type, str) and err_type in _INFORMATIVE_DETAIL_TYPES
        )
        if keep_detail and isinstance(err_message, str):
            normalized = err_message.strip()
            if normalized and normalized.lower() not in friendly.lower():
                parts.append(f"(détail : {normalized})")
        if isinstance(request_id, str) and request_id:
            parts.append(f"[req {request_id}]")
        return " ".join(parts)
    except Exception:
        return f"{type(exc).__name__}: {exc}"
