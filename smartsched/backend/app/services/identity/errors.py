"""Connection check rows and provider error translation for the guided setup (design v3 integrations.md §5.4):
each row says what was checked in Turkish and English; a provider's raw error (``AADSTS50011``,
``redirect_uri_mismatch``, a SAML audience mismatch …) becomes cause + fix + the setup step to return to, with the
raw text kept for IT under "Ayrıntı"."""

from __future__ import annotations

import re
from typing import Any

#: check key -> (ok TR, ok EN, failed TR, failed EN); ``{name}`` placeholders come from the call
CHECKS: dict[str, tuple[str, str, str, str]] = {
    "discovery": (
        "Keşif belgesi alındı ({url}).",
        "Discovery document fetched ({url}).",
        "Yayıncı adresinde keşif belgesi yok ya da okunamadı. Adresi yetkilendirme sunucusunun kökü olarak girin.",
        "No readable discovery document at the issuer. Enter the authorization server's root URL.",
    ),
    "issuer": (
        "Yayıncı eşleşiyor.",
        "The issuer matches.",
        "Yayıncı (issuer) adresi eksik.",
        "The issuer URL is missing.",
    ),
    "tenant": (
        "Kiracı doğru: {tenant}.",
        "Tenant is {tenant}.",
        "Kiracı doğrulanamadı.",
        "The tenant could not be checked.",
    ),
    "metadata": (
        "Meta veri okundu: {entity}.",
        "Metadata read: {entity}.",
        "IdP meta verisi okunamadı. Adresi ya da XML'i ve federasyon meta verisiyse IdP varlık kimliğini kontrol edin.",
        "The IdP metadata could not be read. Check the URL or XML and, for federation metadata, the IdP entity id.",
    ),
    "certificate": (
        "İmza sertifikası geçerli ({date} tarihine kadar).",
        "The signing certificate is valid (until {date}).",
        "IdP imza sertifikasının süresi dolmuş. IdP meta verisini yeniden alın.",
        "The IdP signing certificate has expired. Fetch the IdP metadata again.",
    ),
    "metadata_signature": (
        "Meta veri imzası federasyon sertifikasıyla doğrulandı ({subject}).",
        "The metadata signature was verified with the federation certificate ({subject}).",
        "Meta veri imzası federasyon sertifikasıyla doğrulanamadı.",
        "The metadata signature could not be verified with the federation certificate.",
    ),
    "library": (
        "SAML kütüphanesi yüklü.",
        "The SAML library is installed.",
        "Kütüphane gerekli: sunucuda signxml yüklü değil (pip install signxml).",
        "Library required: signxml is not installed on the server (pip install signxml).",
    ),
}

#: (check key, reason) -> (failed TR, failed EN): one plain sentence per refusal (RF-12)
REASONS: dict[tuple[str, str], tuple[str, str]] = {
    ("metadata_signature", "unsigned"): (
        "Meta veri imzalı değil. Federasyon sertifikası girildiği için imzasız meta veri kabul edilmez: "
        "federasyonun imzalı meta veri adresini kullanın.",
        "The metadata is not signed. With a federation certificate set, unsigned metadata is refused: use the "
        "federation's signed metadata URL.",
    ),
    ("metadata_signature", "invalid"): (
        "Meta veri imzası girilen federasyon sertifikasıyla doğrulanamadı: belge değiştirilmiş ya da sertifika "
        "yanlış. Sertifikayı federasyonun sitesinden yeniden alın.",
        "The metadata signature could not be verified with the federation certificate: the document was changed "
        "or the certificate is wrong. Fetch the certificate from the federation's site again.",
    ),
    ("metadata_signature", "expired"): (
        "Meta verinin geçerlilik süresi (validUntil) dolmuş. Federasyonun güncel meta verisini alın.",
        "The metadata has expired (validUntil). Fetch the federation's current metadata.",
    ),
}

#: (pattern on the provider's raw error, TR cause + fix, EN, step to return to)
TRANSLATIONS: tuple[tuple[re.Pattern[str], str, str, int | None], ...] = tuple(
    (re.compile(p, re.I), tr, en, step)
    for p, tr, en, step in (
        (
            r"AADSTS50011|redirect_uri_mismatch",
            "Yönlendirme adresi sağlayıcıdaki kayıtla eşleşmiyor. 2. adımdaki adresi yönlendirme adresi "
            "olarak ekleyin.",
            "The redirect URI does not match the provider's registration. Add the address from step 2.",
            2,
        ),
        (
            r"AADSTS7000215|AADSTS7000222|invalid_client|unauthorized_client",
            "İstemci kimliği ya da gizli anahtar yanlış veya süresi dolmuş. Yeni bir gizli anahtar oluşturup 'Değer'i "
            "yapıştırın.",
            "The client id or secret is wrong or expired. Create a new secret and paste its Value.",
            3,
        ),
        (
            r"AADSTS700016|AADSTS90002",
            "Bu uygulama bu kiracıda bulunamadı. Kiracı kimliğini ve uygulama kimliğini kontrol edin.",
            "The application was not found in this tenant. Check the tenant and application ids.",
            3,
        ),
        (
            r"AADSTS65001|consent_required",
            "Kurum yöneticisinin uygulamaya izin vermesi gerekiyor (API izinleri › yönetici onayı ver).",
            "An administrator must grant consent (API permissions › Grant admin consent).",
            2,
        ),
        (
            r"org_internal|hd=",
            "Bu hesap kurumun alan adında değil. Kurum hesabınızla deneyin ya da alan adını düzeltin.",
            "This account is not in the institution's domain. Try your institution account or fix the domain.",
            1,
        ),
        (
            r"audience",
            "Hedef kitle (Audience) SmartSched'in varlık kimliği değil. IdP'de 2. adımdaki varlık kimliğini kullanın.",
            "The audience is not SmartSched's entity id. Use the entity id from step 2 at the IdP.",
            2,
        ),
        (
            r"no SP decryption key",
            "IdP onayı şifreli gönderiyor ama SmartSched'de SP çözme anahtarı yok. Sağlayıcıda SP anahtarı oluşturun ve "
            "SP meta verisini IdP'ye yeniden yükleyin.",
            "The IdP encrypts the assertion but SmartSched has no SP decryption key. Create an SP key for the provider "
            "and import the SP metadata at the IdP again.",
            2,
        ),
        (
            r"rsa-1_5",
            "IdP eski RSA 1.5 anahtar aktarımını kullanıyor. IdP'de RSA-OAEP'i seçin.",
            "The IdP uses the old RSA 1.5 key transport. Choose RSA-OAEP at the IdP.",
            None,
        ),
        (
            r"decrypt",
            "Şifreli onay SP anahtarıyla çözülemedi. IdP'nin SmartSched'in güncel SP meta verisini (şifreleme "
            "sertifikası) kullandığını kontrol edin.",
            "The encrypted assertion could not be decrypted with the SP key. Check that the IdP uses SmartSched's "
            "current SP metadata (encryption certificate).",
            2,
        ),
        (
            r"signature",
            "İmza doğrulanamadı. IdP meta verisini yeniden alın (sertifika değişmiş olabilir).",
            "The signature could not be verified. Fetch the IdP metadata again (the certificate may have changed).",
            3,
        ),
        (
            r"validity window|clock",
            "Sunucu saatleri arasında fark var. Sunucuların saatini (NTP) kontrol edin.",
            "The servers' clocks differ. Check the servers' time (NTP).",
            None,
        ),
        (
            r"iss=|issuer",
            "Belgedeki ya da tokendaki yayıncı girilen adresle aynı değil.",
            "The issuer in the document or token differs from the one entered.",
            3,
        ),
        (
            r"ConnectError|ConnectTimeout|ReadTimeout|unreachable|HTTP 5",
            "Sağlayıcıya ulaşılamadı. Sunucunun dışarıya çıkışı kapalı olabilir.",
            "The provider could not be reached. Outbound access may be blocked.",
            None,
        ),
        (
            r"SSL|certificate verify",
            "Sağlayıcının sertifikası doğrulanamadı. Kurum içi bir sertifika yetkilisi kullanılıyorsa BT'ye iletin.",
            "The provider's certificate could not be verified. Tell IT if an internal CA is used.",
            None,
        ),
        (
            r"denied|access_denied|no code",
            "Giriş penceresinde giriş tamamlanmadı ya da pencere kapatıldı. Yeniden deneyin.",
            "The sign-in was not completed or the window was closed. Try again.",
            4,
        ),
        (
            r"nonce|state",
            "Oturum doğrulaması tutmadı (süresi dolmuş ya da yeniden kullanılmış). Testi yeniden başlatın.",
            "The session check failed (expired or reused). Start the test again.",
            4,
        ),
    )
)


class _Safe(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def check(key: str, ok: bool, reason: str = "", **values: str) -> dict[str, Any]:
    ok_tr, ok_en, bad_tr, bad_en = CHECKS.get(key, (key, key, key, key))
    bad_tr, bad_en = REASONS.get((key, reason), (bad_tr, bad_en))
    v = _Safe({k: str(x) for k, x in values.items()})
    row: dict[str, Any] = {
        "key": key,
        "ok": ok,
        "tr": (ok_tr if ok else bad_tr).format_map(v),
        "en": (ok_en if ok else bad_en).format_map(v),
    }
    if not ok and reason:
        row["detail"] = reason[:200]
    return row


def translate(raw: str | None) -> dict[str, Any] | None:
    """cause + fix (TR/EN) and the step to return to, for a provider's raw error text; ``None`` when unknown."""
    if not raw:
        return None
    for rx, tr, en, step in TRANSLATIONS:
        if rx.search(raw):
            return {"tr": tr, "en": en, "step": step, "raw": raw[:200]}
    return None
