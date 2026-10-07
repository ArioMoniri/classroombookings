"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Density = "comfortable" | "compact";

interface UiState {
  sidebarCollapsed: boolean;
  drawerOpen: boolean;
  paletteOpen: boolean;
  shortcutsOpen: boolean;
  termId: number | null;
  density: Density;
  /** cross-component contract (generate-and-chat.md §7.6) */
  highlightAssignmentIds: number[];
  changedAssignmentIds: number[];
  selectedAssignmentId: number | null;
  toggleSidebar: () => void;
  setSidebarCollapsed: (v: boolean) => void;
  setDrawerOpen: (v: boolean) => void;
  setPaletteOpen: (v: boolean) => void;
  setShortcutsOpen: (v: boolean) => void;
  setTermId: (id: number | null) => void;
  setDensity: (d: Density) => void;
  setHighlightAssignmentIds: (ids: number[]) => void;
  setChangedAssignmentIds: (ids: number[]) => void;
  setSelectedAssignmentId: (id: number | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      drawerOpen: false,
      paletteOpen: false,
      shortcutsOpen: false,
      termId: null,
      density: "comfortable",
      highlightAssignmentIds: [],
      changedAssignmentIds: [],
      selectedAssignmentId: null,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      setDrawerOpen: (v) => set({ drawerOpen: v }),
      setPaletteOpen: (v) => set({ paletteOpen: v }),
      setShortcutsOpen: (v) => set({ shortcutsOpen: v }),
      setTermId: (id) => set({ termId: id }),
      setDensity: (d) => set({ density: d }),
      setHighlightAssignmentIds: (ids) => set({ highlightAssignmentIds: ids }),
      setChangedAssignmentIds: (ids) => set({ changedAssignmentIds: ids }),
      setSelectedAssignmentId: (id) => set({ selectedAssignmentId: id }),
    }),
    {
      name: "smartsched.ui",
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed, termId: s.termId, density: s.density }),
    },
  ),
);
