/** Welcome guide per role (docs/design/v3/welcome-guide.md): the shell's mount points. */
// the provider and the page slot are imported lazily by the shell (components/shell/lazy-shell.tsx, F-CH-1)
export { ChecklistPill } from "./checklist/checklist-pill";
export { HelpMenuGroup, DrawerWelcomeRows, useWelcomeCommands } from "./help-menu";
export { NewBadge } from "./hints/new-badge";
export { TOUR_RUNNING_ATTR, tourAnchorFor } from "./tour/anchors";
