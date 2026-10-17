/**
 * Test-only doubles for the voice tests (imported by *.test.tsx only; never by product code): a MediaRecorder that
 * hands out one chunk on stop, a getUserMedia that resolves or rejects, a controllable clock, and the
 * Permissions-Policy switch. `installMedia()` puts them on `window` / `navigator` and returns the handles.
 */
import { vi } from "vitest";

export class FakeRecorder {
  static instances: FakeRecorder[] = [];
  static isTypeSupported = (m: string) => m.startsWith("audio/webm");
  state: "inactive" | "recording" = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(
    public stream: unknown,
    opts?: { mimeType?: string },
  ) {
    this.mimeType = opts?.mimeType ?? "";
    FakeRecorder.instances.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["opus-bytes-".repeat(20)], { type: "audio/webm" }) });
    this.onstop?.();
  }
}

export function installMedia({ reject, policy = true }: { reject?: string; policy?: boolean } = {}) {
  FakeRecorder.instances = [];
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] };
  const getUserMedia = vi.fn(() => (reject ? Promise.reject(Object.assign(new Error(reject), { name: reject })) : Promise.resolve(stream)));
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  (window as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeRecorder;
  (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeRecorder;
  Object.defineProperty(document, "featurePolicy", { value: { allowsFeature: (f: string) => (f === "microphone" ? policy : true) }, configurable: true });
  let now = 1_000_000;
  const clock = vi.spyOn(Date, "now").mockImplementation(() => now);
  return {
    getUserMedia,
    track,
    advance: (ms: number) => {
      now += ms;
    },
    restore: () => clock.mockRestore(),
    recorder: () => FakeRecorder.instances[FakeRecorder.instances.length - 1],
  };
}
