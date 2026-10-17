/**
 * After the inspector closes, focus returns to the chip of the class it showed, else to the week title (motion T4,
 * README §4.7: never to <body>). One helper for the close button and the Escape key (mobile-b phase 2: Escape at
 * 768 cleared the selection and dropped focus to <body>).
 */
export function focusClassChip(aid: number | undefined): void {
  requestAnimationFrame(() => {
    const chip = aid !== undefined ? document.querySelector<HTMLElement>(`[data-testid="calendar-event"][data-assignment-id="${aid}"]`) : null;
    (chip ?? document.getElementById("calendar-title"))?.focus();
  });
}
