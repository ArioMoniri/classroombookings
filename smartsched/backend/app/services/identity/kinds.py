"""The identity provider kinds and their setup presets (wave 3b W3-IDP; the "add provider" gallery and the guided
setup of docs/design/v3/integrations.md).

Each kind says which values the administrator pastes in (``fields``), what SmartSched generates for the provider's
console (``console``: redirect URI, entity id, ACS URL, scopes, logout URL; built by
:func:`app.services.identity.wizard.console_values`) and the steps in Turkish and English. Presets refine a kind
(``oidc``: Okta, Keycloak, Auth0, Authentik, ADFS; ``saml``: Shibboleth, YETKİM, ADFS) with placeholders and claim
names. Nothing here is a secret; nothing here talks to the network.
"""

from __future__ import annotations

import re
from typing import Any

ENTRA, GOOGLE, OIDC, SAML, LDAP = "entra", "google_workspace", "oidc", "saml", "ldap"
#: the kinds stored in ``sso_providers`` (LDAP keeps its settings group and is listed alongside)
KINDS = (ENTRA, GOOGLE, OIDC, SAML)

#: slugs that collide with fixed routes under ``/auth/sso``
RESERVED_SLUGS = frozenset(
    {"admin", "invites", "exchange", "providers", "me", "local", "test-done", "ldap", "password", "kinds"}
)
SLUG_RX = re.compile(r"^[a-z][a-z0-9-]{1,39}$")

#: badge text of the gallery cards (plain text, no logo assets)
BADGES = {ENTRA: "MS", GOOGLE: "G", OIDC: "OIDC", SAML: "SAML", LDAP: "LDAP"}

DEFAULT_LABELS: dict[str, dict[str, str]] = {
    ENTRA: {"tr": "Microsoft 365", "en": "Microsoft 365"},
    GOOGLE: {"tr": "Google Workspace", "en": "Google Workspace"},
    OIDC: {"tr": "Kurum girişi (OIDC)", "en": "Institution sign-in (OIDC)"},
    SAML: {"tr": "Kurum girişi (SAML)", "en": "Institution sign-in (SAML)"},
    LDAP: {"tr": "LDAP / Active Directory", "en": "LDAP / Active Directory"},
}

DESCRIPTIONS: dict[str, dict[str, str]] = {
    ENTRA: {
        "tr": "Kurumun Microsoft Entra ID dizini (tek kiracı, sabitlenmiş tenant).",
        "en": "The institution's Microsoft Entra ID directory (single tenant, pinned).",
    },
    GOOGLE: {
        "tr": "Kurumun Google Workspace alanı (barındırılan alan adı sabitlenir).",
        "en": "The institution's Google Workspace domain (the hosted domain is pinned).",
    },
    OIDC: {
        "tr": "Keşif adresi olan her OpenID Connect sağlayıcısı: Okta, Keycloak, Auth0, Authentik, ADFS.",
        "en": "Any OpenID Connect issuer with discovery: Okta, Keycloak, Auth0, Authentik, ADFS.",
    },
    SAML: {
        "tr": "SAML 2.0 kimlik sağlayıcısı: Shibboleth, eduGAIN, YETKİM federasyonu, ADFS.",
        "en": "A SAML 2.0 identity provider: Shibboleth, eduGAIN, the YETKİM federation, ADFS.",
    },
    LDAP: {
        "tr": "Kurumun dizin sunucusu; parola formuyla giriş (ayrı LDAP ayarları).",
        "en": "The institution's directory server; sign-in with the password form (separate LDAP settings).",
    },
}

#: preset -> what it changes. ``issuer_hint``: placeholder of the issuer field; ``groups_claim`` / ``roles_claim``:
#: claim names read for the role mapping; ``scopes``: extra scopes after ``openid profile email``.
OIDC_PRESETS: dict[str, dict[str, Any]] = {
    "okta": {
        "label": "Okta",
        "issuer_hint": "https://uni.okta.com/oauth2/default",
        "groups_claim": "groups",
        "scopes": ["groups"],
        "steps": {
            "tr": [
                "Okta Admin › Applications › Create App Integration › OIDC - Web Application.",
                "Sign-in redirect URI alanına aşağıdaki yönlendirme adresini yapıştırın.",
                "Grant type: Authorization Code (PKCE açık). Groups claim filtresi: Matches regex .*",
                "Client ID ve Client secret değerlerini buraya yapıştırın; issuer: yetkilendirme sunucusunun adresi.",
            ],
            "en": [
                "Okta Admin › Applications › Create App Integration › OIDC - Web Application.",
                "Paste the redirect URI below into Sign-in redirect URIs.",
                "Grant type: Authorization Code (PKCE on). Groups claim filter: Matches regex .*",
                "Paste the Client ID and Client secret here; issuer: the authorization server's URL.",
            ],
        },
    },
    "keycloak": {
        "label": "Keycloak",
        "issuer_hint": "https://sso.uni.edu.tr/realms/uni",
        "groups_claim": "groups",
        "scopes": [],
        "steps": {
            "tr": [
                "Keycloak › Clients › Create client: OpenID Connect, Client authentication açık.",
                "Valid redirect URIs alanına aşağıdaki yönlendirme adresini yapıştırın.",
                "Gruplar için: Client scopes › Mappers › Group Membership (Token Claim Name: groups, Full group "
                "path kapalı).",
                "Credentials sekmesindeki Client secret'ı buraya yapıştırın; issuer: realm adresi.",
            ],
            "en": [
                "Keycloak › Clients › Create client: OpenID Connect, Client authentication on.",
                "Paste the redirect URI below into Valid redirect URIs.",
                "For groups: Client scopes › Mappers › Group Membership (Token Claim Name: groups, Full group path "
                "off).",
                "Paste the Client secret from the Credentials tab here; issuer: the realm URL.",
            ],
        },
    },
    "auth0": {
        "label": "Auth0",
        "issuer_hint": "https://uni.eu.auth0.com/",
        "groups_claim": "https://smartsched/groups",
        "scopes": [],
        "steps": {
            "tr": [
                "Auth0 › Applications › Create Application › Regular Web Application.",
                "Allowed Callback URLs alanına aşağıdaki yönlendirme adresini yapıştırın.",
                "Gruplar için bir Action ile ad alanlı bir claim ekleyin (ör. https://smartsched/groups).",
                "Domain'i issuer olarak (sonundaki / ile), Client ID ve Client Secret'ı buraya yapıştırın.",
            ],
            "en": [
                "Auth0 › Applications › Create Application › Regular Web Application.",
                "Paste the redirect URI below into Allowed Callback URLs.",
                "For groups, add a namespaced claim with an Action (e.g. https://smartsched/groups).",
                "Paste the Domain as the issuer (with the trailing /), the Client ID and the Client Secret here.",
            ],
        },
    },
    "authentik": {
        "label": "Authentik",
        "issuer_hint": "https://auth.uni.edu.tr/application/o/smartsched/",
        "groups_claim": "groups",
        "scopes": [],
        "steps": {
            "tr": [
                "Authentik › Applications › Providers › Create › OAuth2/OpenID Provider (Confidential).",
                "Redirect URIs alanına aşağıdaki yönlendirme adresini yapıştırın.",
                "Uygulamayı oluşturup sağlayıcıya bağlayın; OpenID Configuration Issuer adresini buraya yapıştırın.",
            ],
            "en": [
                "Authentik › Applications › Providers › Create › OAuth2/OpenID Provider (Confidential).",
                "Paste the redirect URI below into Redirect URIs.",
                "Create the application, attach the provider and paste its OpenID Configuration Issuer here.",
            ],
        },
    },
    "adfs": {
        "label": "ADFS",
        "issuer_hint": "https://adfs.uni.edu.tr/adfs",
        "groups_claim": "group",
        "roles_claim": "role",
        "scopes": ["allatclaims"],
        "steps": {
            "tr": [
                "AD FS Yönetimi › Application Groups › Server application accessing a web API.",
                "Redirect URI alanına aşağıdaki yönlendirme adresini yapıştırın; paylaşılan bir gizli anahtar "
                "oluşturun.",
                "Issuance Transform Rules: e-posta (email) ve gruplar (group) talepleri.",
                "ADFS e-posta doğrulaması göndermez: 'E-postaya güven' seçeneğini yalnızca kurum dizini için açın.",
            ],
            "en": [
                "AD FS Management › Application Groups › Server application accessing a web API.",
                "Paste the redirect URI below into Redirect URI; generate a shared secret.",
                "Issuance Transform Rules: the email and group claims.",
                "ADFS sends no e-mail verification flag: turn on 'Trust the e-mail' for the institution directory "
                "only.",
            ],
        },
    },
    "generic": {
        "label": "OpenID Connect",
        "issuer_hint": "https://idp.uni.edu.tr",
        "groups_claim": "groups",
        "scopes": [],
        "steps": {
            "tr": [
                "Sağlayıcıda gizli anahtarlı (confidential) bir web istemcisi oluşturun: Authorization Code + PKCE.",
                "Yönlendirme adresini aşağıdan kopyalayın; kapsamlar: openid profile email.",
                "Issuer, Client ID ve Client secret değerlerini buraya yapıştırın.",
            ],
            "en": [
                "Create a confidential web client at the provider: Authorization Code + PKCE.",
                "Copy the redirect URI below; scopes: openid profile email.",
                "Paste the issuer, the Client ID and the Client secret here.",
            ],
        },
    },
}

#: SAML attribute names (OID form, as eduGAIN / YETKİM release them; friendly names are accepted too)
ATTR_MAIL = "urn:oid:0.9.2342.19200300.100.1.3"
ATTR_DISPLAY_NAME = "urn:oid:2.16.840.1.113730.3.1.241"
ATTR_EPPN = "urn:oid:1.3.6.1.4.1.5923.1.1.1.6"
ATTR_ENTITLEMENT = "urn:oid:1.3.6.1.4.1.5923.1.1.1.7"
ATTR_AFFILIATION = "urn:oid:1.3.6.1.4.1.5923.1.1.1.9"

SAML_PRESETS: dict[str, dict[str, Any]] = {
    "shibboleth": {
        "label": "Shibboleth IdP",
        "metadata_hint": "https://idp.uni.edu.tr/idp/shibboleth",
        "email_attribute": ATTR_MAIL,
        "name_attribute": ATTR_DISPLAY_NAME,
        "groups_attribute": ATTR_ENTITLEMENT,
    },
    "yetkim": {
        "label": "YETKİM federasyonu (eduGAIN)",
        "metadata_hint": "https://yetkim.org.tr/metadata/yetkim-metadata.xml",
        "email_attribute": ATTR_MAIL,
        "name_attribute": ATTR_DISPLAY_NAME,
        "groups_attribute": ATTR_AFFILIATION,
    },
    "adfs": {
        "label": "ADFS (SAML)",
        "metadata_hint": "https://adfs.uni.edu.tr/FederationMetadata/2007-06/FederationMetadata.xml",
        "email_attribute": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "name_attribute": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        "groups_attribute": "http://schemas.microsoft.com/ws/2008/06/identity/claims/role",
    },
    "generic": {
        "label": "SAML 2.0",
        "metadata_hint": "https://idp.uni.edu.tr/metadata",
        "email_attribute": ATTR_MAIL,
        "name_attribute": ATTR_DISPLAY_NAME,
        "groups_attribute": ATTR_ENTITLEMENT,
    },
}

#: fields the administrator pastes in, per kind (``secret``: write-only; ``required``: needed before enabling)
FIELDS: dict[str, list[dict[str, Any]]] = {
    ENTRA: [
        {"key": "tenant_id", "required": True, "secret": False},
        {"key": "client_id", "required": True, "secret": False},
        {"key": "client_secret", "required": True, "secret": True},
        {"key": "domain_hint", "required": False, "secret": False},
    ],
    GOOGLE: [
        {"key": "client_id", "required": True, "secret": False},
        {"key": "client_secret", "required": True, "secret": True},
        {"key": "hosted_domains", "required": True, "secret": False},
    ],
    OIDC: [
        {"key": "issuer", "required": True, "secret": False},
        {"key": "client_id", "required": True, "secret": False},
        {"key": "client_secret", "required": True, "secret": True},
        {"key": "groups_claim", "required": False, "secret": False},
        {"key": "roles_claim", "required": False, "secret": False},
        {"key": "trust_email", "required": False, "secret": False},
    ],
    SAML: [
        {"key": "metadata_url", "required": False, "secret": False},
        {"key": "metadata_xml", "required": False, "secret": False},
        {"key": "idp_entity_id", "required": False, "secret": False},
        {"key": "email_attribute", "required": False, "secret": False},
        {"key": "name_attribute", "required": False, "secret": False},
        {"key": "groups_attribute", "required": False, "secret": False},
    ],
}

STEPS: dict[str, dict[str, list[str]]] = {
    ENTRA: {
        "tr": [
            "Microsoft Entra yönetim merkezi › Uygulama kayıtları › Yeni kayıt: 'Yalnızca bu kuruluş dizini'.",
            "Yeniden yönlendirme URI'si (Web) olarak aşağıdaki adresi yapıştırın.",
            "Sertifikalar ve gizli diziler › Yeni istemci gizli anahtarı; değeri hemen kopyalayın.",
            "Dizin (tenant) kimliği, Uygulama (istemci) kimliği ve gizli anahtarı buraya yapıştırın.",
        ],
        "en": [
            "Microsoft Entra admin center › App registrations › New registration: 'This organisational directory "
            "only'.",
            "Paste the address below as the Redirect URI (Web).",
            "Certificates & secrets › New client secret; copy the value at once.",
            "Paste the directory (tenant) id, the application (client) id and the secret here.",
        ],
    },
    GOOGLE: {
        "tr": [
            "Google Cloud Console › API'ler ve Hizmetler › OAuth izin ekranı: Kullanıcı türü 'Dahili'.",
            "Kimlik bilgileri › OAuth istemci kimliği oluştur › Web uygulaması.",
            "Yetkili JavaScript kaynağı ve yetkili yönlendirme URI'si olarak aşağıdaki değerleri yapıştırın.",
            "İstemci kimliği, istemci gizli anahtarı ve kurumun alan adını (uni.edu.tr) buraya yapıştırın.",
        ],
        "en": [
            "Google Cloud Console › APIs & Services › OAuth consent screen: user type 'Internal'.",
            "Credentials › Create OAuth client ID › Web application.",
            "Paste the values below as the authorised JavaScript origin and the authorised redirect URI.",
            "Paste the client id, the client secret and the institution's domain (uni.edu.tr) here.",
        ],
    },
    SAML: {
        "tr": [
            "IdP yöneticisine SmartSched'in SP meta veri adresini verin (ya da varlık kimliği ve ACS adresini).",
            "Öznitelikler: mail, displayName, eduPersonPrincipalName; isteğe bağlı eduPersonEntitlement.",
            "NameID biçimi: persistent. Onaylamalar (assertion) imzalı olmalı; şifreleme kapalı.",
            "IdP meta veri adresini (ya da XML'ini) buraya yapıştırın; federasyon meta verisiyse IdP varlık "
            "kimliğini de girin.",
        ],
        "en": [
            "Give the IdP administrator SmartSched's SP metadata URL (or the entity id and the ACS URL).",
            "Attributes: mail, displayName, eduPersonPrincipalName; optionally eduPersonEntitlement.",
            "NameID format: persistent. Assertions must be signed; encryption off.",
            "Paste the IdP metadata URL (or its XML) here; for federation metadata also give the IdP entity id.",
        ],
    },
}


def default_label(kind: str, locale: str = "tr") -> str:
    return DEFAULT_LABELS.get(kind, DEFAULT_LABELS[OIDC]).get(locale, DEFAULT_LABELS[OIDC]["tr"])


def presets_for(kind: str) -> dict[str, dict[str, Any]]:
    if kind == OIDC:
        return OIDC_PRESETS
    if kind == SAML:
        return SAML_PRESETS
    return {}


def steps_for(kind: str, preset: str | None) -> dict[str, list[str]]:
    if kind == OIDC:
        return OIDC_PRESETS.get(preset or "generic", OIDC_PRESETS["generic"])["steps"]
    return STEPS.get(kind, {"tr": [], "en": []})


def catalog(*, saml_available: bool) -> list[dict[str, Any]]:
    """The "add provider" gallery: one card per kind (LDAP last, managed in its own settings)."""
    out: list[dict[str, Any]] = []
    for kind in (*KINDS, LDAP):
        presets = [{"key": key, "label": p["label"]} for key, p in presets_for(kind).items()]
        out.append(
            {
                "kind": kind,
                "badge": BADGES[kind],
                "label": DEFAULT_LABELS[kind],
                "description": DESCRIPTIONS[kind],
                "presets": presets,
                "fields": FIELDS.get(kind, []),
                "available": saml_available if kind == SAML else True,
                #: SAML without the optional library: the card says "kütüphane gerekli"
                "library_required": kind == SAML and not saml_available,
            }
        )
    return out
