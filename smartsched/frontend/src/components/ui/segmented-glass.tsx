"use client"
// Deprecated alias (design-system overhaul 2026-10-15): SegmentedGlass is now SegmentedControl
// (components/ui/segmented-control.tsx). The beUI Tabs implementation it wrapped was deleted; the label
// clip-path morph and the layoutId thumb are replaced by one CSS thumb that cannot rest outside its track.
// Kept only so screens owned by other agents compile until they import SegmentedControl directly.
export { SegmentedControl as SegmentedGlass, type SegmentedOption } from "@/components/ui/segmented-control"
