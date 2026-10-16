/**
 * Browser push for Profile › Bağlı kanallar. The service worker (`/push-sw.js`) is registered only when the person
 * presses "Bu cihaza bildirim gönder", with the narrow scope `/push-sw/` (no page lives there, so it never controls
 * the app). iPhone / iPad (iOS 16.4+) support push only for a site added to the Home Screen.
 */
import type { PushSubscriptionJson } from "@/lib/api/channels";

export const PUSH_SW_URL = "/push-sw.js";
export const PUSH_SW_SCOPE = "/push-sw/";

export type PushSupport = "ok" | "unsupported" | "ios-install" | "denied";

export function pushSupport(): PushSupport {
  if (typeof window === "undefined") return "unsupported";
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return ios && !standalone ? "ios-install" : "unsupported";
  if (ios && !standalone) return "ios-install";
  if (Notification.permission === "denied") return "denied";
  return "ok";
}

/** VAPID public key (base64url) → the bytes `applicationServerKey` wants. */
export function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const pad = "=".repeat((4 - (value.length % 4)) % 4);
  const raw = atob((value + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export class PushError extends Error {
  constructor(readonly reason: "denied" | "unsupported" | "failed") {
    super(reason);
  }
}

/** Ask for permission, register the worker and subscribe this browser (the JSON the backend stores). */
export async function subscribeThisBrowser(vapidPublicKey: string): Promise<PushSubscriptionJson> {
  if (pushSupport() === "unsupported") throw new PushError("unsupported");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new PushError("denied");
  try {
    const reg = await navigator.serviceWorker.register(PUSH_SW_URL, { scope: PUSH_SW_SCOPE });
    const ready = reg.active ? reg : await waitActive(reg);
    const key = base64UrlToBytes(vapidPublicKey);
    let sub = await ready.pushManager.getSubscription();
    if (sub) {
      // a subscription made with another (rotated) VAPID key cannot be reused
      const current = sub.options.applicationServerKey ? new Uint8Array(sub.options.applicationServerKey) : null;
      if (!current || current.length !== key.length || current.some((b, i) => b !== key[i])) {
        await sub.unsubscribe();
        sub = null;
      }
    }
    sub ??= await ready.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string }; expirationTime?: number | null };
    if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) throw new PushError("failed");
    return { endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth }, expirationTime: json.expirationTime ?? null };
  } catch (e) {
    if (e instanceof PushError) throw e;
    throw new PushError("failed");
  }
}

function waitActive(reg: ServiceWorkerRegistration): Promise<ServiceWorkerRegistration> {
  return new Promise((resolve) => {
    const sw = reg.installing ?? reg.waiting;
    if (!sw) return resolve(reg);
    sw.addEventListener("statechange", () => {
      if (sw.state === "activated") resolve(reg);
    });
  });
}

/** A short device label for the linked list ("Chrome · Android"). */
export function deviceLabel(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad|iPod/.test(ua) ? "iOS" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  return os ? `${browser} · ${os}` : browser;
}
