// SmartSched touch hit areas (docs/design/tokens.md §A.5, docs/testing/flows/MOBILE.md M-02). Original work.
// On `pointer: coarse` an invisible ::after grows the tap target to at least 44 × 44 CSS px around the element's
// centre (Apple HIG). An axis that is already ≥ 44 px gets no extension (min(0px, 50% − 22px) = 0), so large
// controls are untouched; fine pointers never see the pseudo-element. The element must be positioned (relative or
// absolute) so the ::after is laid out against it. Overlaps with neighbours resolve in DOM order (the later,
// positioned sibling paints on top and takes the tap), the same as every Button.
// Each class is a complete literal so Tailwind's source scan picks it up.

/** Grows the hit area to 44 × 44 on touch, on both axes. */
export const coarseHitArea =
  "pointer-coarse:after:absolute pointer-coarse:after:content-[''] pointer-coarse:after:top-[min(0px,calc(50%-22px))] pointer-coarse:after:bottom-[min(0px,calc(50%-22px))] pointer-coarse:after:left-[min(0px,calc(50%-22px))] pointer-coarse:after:right-[min(0px,calc(50%-22px))]"

/**
 * 16 px text on touch screens so focusing a text field or select does not zoom the page (iOS; MOBILE.md M-03).
 * Mobile audit B/A (2026-10-17): every coarse pointer, not only below md, so a 768 px touch tablet gets 16 px too.
 */
export const coarsePhoneText = "pointer-coarse:text-base"
