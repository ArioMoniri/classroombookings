/**
 * Room admin helpers (T-R1-34, R1-M-20). The backend stores canonical codes ("T101", `normalize.parse_room_codes`)
 * and shows them with a space ("T 101", `display_room_code`); the admin list, the edit sheet and the pickers read
 * this one spelling so a room never appears under two names.
 */

/** "T101" → "T 101", "AZ01" → "A z01" (a ground-floor code), anything else unchanged. */
export function roomCodeLabel(code: string | null | undefined): string {
  const c = (code ?? "").trim();
  if (c.length < 2 || !/^[A-Za-z][0-9Zz]/.test(c) || c.includes(" ")) return c;
  let rest = c.slice(1);
  if (rest[0] === "Z") rest = `z${rest.slice(1)}`;
  return `${c[0]} ${rest}`;
}

/** "T 101 · Test dersliği", or the code alone when the room has no other name. */
export function roomTitle(room: { code: string; display_name?: string | null }): string {
  const code = roomCodeLabel(room.code);
  const name = (room.display_name ?? "").trim();
  return name && name !== code && name !== room.code ? `${code} · ${name}` : code;
}
