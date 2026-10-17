/** VO-06 recorder state machine against a mocked MediaRecorder + getUserMedia. */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installMedia } from "@/test/voice-media";
import { pickMime, rmsLevel, useVoiceRecorder } from "./use-voice-recorder";

let media: ReturnType<typeof installMedia>;
afterEach(() => {
  media?.restore();
  vi.useRealTimers();
});

function setup(max = 120) {
  const onClip = vi.fn();
  const onCap = vi.fn();
  const onError = vi.fn();
  const hook = renderHook(() => useVoiceRecorder({ maxSeconds: max, onClip, onCap, onError }));
  return { ...hook, onClip, onCap, onError };
}

describe("pickMime / rmsLevel", () => {
  it("prefers Opus in WebM, then Ogg, then MP4 (Safari)", () => {
    expect(pickMime((m) => m === "audio/webm;codecs=opus")).toBe("audio/webm;codecs=opus");
    expect(pickMime((m) => m === "audio/mp4")).toBe("audio/mp4");
    expect(pickMime(() => false)).toBeUndefined();
  });
  it("silence is 0, a loud frame is near 1", () => {
    expect(rmsLevel(new Uint8Array(64).fill(128))).toBe(0);
    expect(rmsLevel(Uint8Array.from({ length: 64 }, (_, i) => (i % 2 ? 0 : 255)))).toBeCloseTo(1, 1);
  });
});

describe("useVoiceRecorder", () => {
  it("idle → starting → recording → stop delivers one webm clip and releases the microphone", async () => {
    media = installMedia();
    const { result, onClip } = setup();
    expect(result.current.phase).toBe("idle");
    let p: Promise<void> | undefined;
    act(() => {
      p = result.current.start();
    });
    expect(result.current.phase).toBe("starting");
    await act(async () => {
      await p;
    });
    expect(result.current.phase).toBe("recording");
    expect(media.recorder()?.mimeType).toBe("audio/webm;codecs=opus");
    media.advance(3000);
    act(() => result.current.stop());
    expect(result.current.phase).toBe("idle");
    expect(onClip).toHaveBeenCalledTimes(1);
    const [blob, ms] = onClip.mock.calls[0]!;
    expect((blob as Blob).type).toBe("audio/webm");
    expect(ms).toBe(3000);
    expect(media.track.stop).toHaveBeenCalled();
  });

  it("cancel (Esc) drops the clip", async () => {
    media = installMedia();
    const { result, onClip } = setup();
    await act(async () => {
      await result.current.start();
    });
    media.advance(2000);
    act(() => result.current.cancel());
    expect(onClip).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("idle");
    expect(media.track.stop).toHaveBeenCalled();
  });

  it("a cancel while the browser prompt is open releases the stream when it arrives", async () => {
    media = installMedia();
    const { result, onClip } = setup();
    let p: Promise<void> | undefined;
    act(() => {
      p = result.current.start();
    });
    act(() => result.current.cancel());
    await act(async () => {
      await p;
    });
    expect(result.current.phase).toBe("idle");
    expect(media.recorder()).toBeUndefined();
    expect(media.track.stop).toHaveBeenCalled();
    expect(onClip).not.toHaveBeenCalled();
  });

  it("stops itself at the cap and still delivers the clip", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    media = installMedia();
    const { result, onClip, onCap } = setup(5);
    await act(async () => {
      await result.current.start();
    });
    media.advance(5100);
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(onCap).toHaveBeenCalledTimes(1);
    expect(onClip).toHaveBeenCalledTimes(1);
    expect(result.current.phase).toBe("idle");
  });

  it("a clip shorter than 0.4 s is 'no speech'", async () => {
    media = installMedia();
    const { result, onClip, onError } = setup();
    await act(async () => {
      await result.current.start();
    });
    media.advance(100);
    act(() => result.current.stop());
    expect(onClip).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledWith({ code: "empty" });
    expect(result.current.phase).toBe("error");
  });

  it("the user's Block is permission_denied; the site policy is policy_blocked", async () => {
    media = installMedia({ reject: "NotAllowedError" });
    const a = setup();
    await act(async () => {
      await a.result.current.start();
    });
    expect(a.result.current.error).toEqual({ code: "permission_denied" });
    a.unmount();
    media.restore();

    media = installMedia({ policy: false });
    const b = setup();
    await act(async () => {
      await b.result.current.start();
    });
    expect(b.result.current.error).toEqual({ code: "policy_blocked" });
    expect(media.getUserMedia).not.toHaveBeenCalled(); // the policy is known before asking
  });

  it("no microphone is no_device", async () => {
    media = installMedia({ reject: "NotFoundError" });
    const { result } = setup();
    await act(async () => {
      await result.current.start();
    });
    expect(result.current.phase).toBe("error");
    expect(result.current.error).toEqual({ code: "no_device" });
  });
});
