/**
 * Passkey provider names from the authenticator's AAGUID (docs/design/v3/auth.md §6.4; AUX-07). A small subset of
 * the community list `passkeydeveloper/passkey-authenticator-aaguids` (MIT; components/ui/SOURCES.md): names only,
 * no vendor icons (the row shows a neutral key glyph; Simplicity). Unknown or all-zero AAGUIDs fall back to
 * "{browser} · {os}" from the user agent.
 */

const NAMES: Record<string, { tr: string; en: string }> = {
  "ea9b8d66-4d01-1d21-3ce4-b6b48cb575d4": { tr: "Google Parola Yöneticisi", en: "Google Password Manager" },
  "fbfc3007-154e-4ecc-8c0b-6e020557d7bd": { tr: "iCloud Anahtar Zinciri", en: "iCloud Keychain" },
  "dd4ec289-e01d-41c9-bb89-70fa845d4bf2": { tr: "iCloud Anahtar Zinciri", en: "iCloud Keychain" },
  "08987058-cadc-4b81-b6e1-30de50dcbe96": { tr: "Windows Hello", en: "Windows Hello" },
  "9ddd1817-af5a-4672-a2b9-3e3dd95000a9": { tr: "Windows Hello", en: "Windows Hello" },
  "6028b017-b1d4-4c02-b4b3-afcdafc96bb2": { tr: "Windows Hello", en: "Windows Hello" },
  "bada5566-a7aa-401f-bd96-45619a55120d": { tr: "1Password", en: "1Password" },
  "d548826e-79b4-db40-a3d8-11116f7e8349": { tr: "Bitwarden", en: "Bitwarden" },
  "531126d6-e717-415c-9320-3d9aa6981239": { tr: "Dashlane", en: "Dashlane" },
  "adce0002-35bc-c60a-648b-0b25f1f05503": { tr: "Chrome (Mac)", en: "Chrome on Mac" },
  "53414d53-554e-4700-0000-000000000000": { tr: "Samsung Pass", en: "Samsung Pass" },
  "50726f74-6f6e-5061-7373-50726f746f6e": { tr: "Proton Pass", en: "Proton Pass" },
  "fdb141b2-5d84-443e-8a35-4698c205a502": { tr: "KeePassXC", en: "KeePassXC" },
};

export function providerName(aaguid: string | null | undefined, locale: string): string | null {
  const hit = aaguid ? NAMES[aaguid.toLowerCase()] : undefined;
  return hit ? (locale === "tr" ? hit.tr : hit.en) : null;
}

/** "Chrome · macOS" from a user agent (the fallback name). */
export function deviceName(ua: string): string {
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\/|CriOS\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : null;
  const os = /iPhone|iPad|iPod/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X|Macintosh/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /CrOS/.test(ua) ? "ChromeOS" : /Linux/.test(ua) ? "Linux" : null;
  return [browser, os].filter(Boolean).join(" · ");
}

/** The name a new passkey gets: the provider, else "{browser} · {os}", else null (the server's default). */
export function defaultPasskeyName(aaguid: string | null | undefined, locale: string, ua: string = typeof navigator !== "undefined" ? navigator.userAgent : ""): string | null {
  return providerName(aaguid, locale) ?? (deviceName(ua) || null);
}
