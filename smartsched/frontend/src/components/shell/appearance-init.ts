// Server-safe (no "use client"): layout.tsx is a server component, and a constant exported from a
// "use client" module reaches it as a client reference, not a string. These keys and the motion /
// transparency part mirror `components/ui/appearance-preferences.tsx` (appearanceInitScript) exactly.
export const APPEARANCE_KEY_PREFIX = "smartsched.appearance.";
export const APPEARANCE_LAST_USER_KEY = "smartsched.appearance.lastUser";
export const ACCENT_PRESETS = ["blue", "indigo", "teal", "graphite", "orange"] as const;

/** Inline in <head> before paint: the last signed-in user's motion, transparency and accent preferences. */
export const appearanceHeadScript = `(function(){try{var u=localStorage.getItem(${JSON.stringify(APPEARANCE_LAST_USER_KEY)})||"anon";var p=JSON.parse(localStorage.getItem(${JSON.stringify(APPEARANCE_KEY_PREFIX)}+u)||"{}");var r=document.documentElement;if(p.motion==="reduced")r.dataset.motion="reduced";if(p.transparency==="reduced")r.dataset.transparency="reduced";var a=p.accent;if(a&&a!=="blue"&&${JSON.stringify(ACCENT_PRESETS)}.indexOf(a)>-1)r.dataset.accent=a;}catch(e){}})();`;
