export interface DropTarget {
  roomId: number;
  day: number;
  startPeriod: number;
  endPeriod: number;
  ok: boolean;
  reasons: string[];
  conflictIds: string[];
}
