/*
 * SmartSched Web Push service worker (Profile › Bağlı kanallar › "Bu cihaza bildirim gönder").
 *
 * Registered only by that action, with the narrow scope "/push-sw/" where no page lives: it controls no page,
 * caches nothing and has no fetch handler. It only turns a push into a notification and opens its link.
 * Payload (backend app/services/channels, RFC 8291 encrypted): { title, body, url, tag }.
 */
/* eslint-disable no-restricted-globals */
"use strict";

function sameOriginUrl(value) {
  try {
    const url = new URL(typeof value === "string" && value ? value : "/", self.location.origin);
    return url.origin === self.location.origin ? url.href : new URL("/", self.location.origin).href;
  } catch (_e) {
    return new URL("/", self.location.origin).href;
  }
}

function text(value, max) {
  return typeof value === "string" ? value.slice(0, max) : "";
}

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("push", (event) => {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (_e) {
      data = { body: event.data.text() };
    }
  }
  const title = text(data.title, 120) || "SmartSched";
  const tag = text(data.tag, 64);
  const options = {
    body: text(data.body, 400),
    data: { url: sameOriginUrl(data.url) },
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-48.png",
    lang: self.navigator && self.navigator.language ? self.navigator.language : "tr",
  };
  if (tag) {
    options.tag = tag;
    options.renotify = true;
  }
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = sameOriginUrl(event.notification.data && event.notification.data.url);
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of windows) {
        if (client.url === target && "focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
      return undefined;
    })(),
  );
});

/* The browser rotated the subscription: hand the new one to SmartSched (the session cookie goes along). */
self.addEventListener("pushsubscriptionchange", (event) => {
  const next = event.newSubscription;
  if (!next) return;
  event.waitUntil(
    fetch("/api/v1/me/channels/webpush", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ subscription: next.toJSON(), label: null }),
    }).catch(() => undefined),
  );
});
