/** VO-06 mic: visibility, consent first, transcript into the box (never sent), hold / lock / cancel, error copy. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PromptComposer } from "@/components/ui/beautifului/prompt-composer";
import { I18nProvider } from "@/lib/i18n/provider";
import { installMedia } from "@/test/voice-media";

const state = vi.hoisted(() => ({
  status: {} as Record<string, unknown> | Error,
  transcribe: null as null | ((body: Blob) => { status?: number; json: unknown }),
  calls: [] as { path: string; method?: string; body?: unknown }[],
  coarse: false,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; formData?: FormData } = {}) => {
      state.calls.push({ path, method: opts.method });
      if (path === "/ai/voice/status") {
        if (state.status instanceof Error) throw state.status;
        return (await import("@/lib/api/voice")).VoiceStatus.parse(state.status);
      }
      if (path === "/me/consents/voice") return { ok: true };
      if (path === "/ai/me/usage") return {};
      throw new Error(`unexpected ${path}`);
    },
  };
});

import { HttpError } from "@/lib/api/client";
import { MicButton } from "./mic-button";

const ok = { available: true, reason: null, consent: true, provider_label: "OpenAI", region: "EU", max_seconds: 120, live_captions: "off" };
let media: ReturnType<typeof installMedia>;
const realMatch = window.matchMedia;

beforeEach(() => {
  state.calls = [];
  state.coarse = false;
  state.status = { ...ok };
  state.transcribe = () => ({ json: { text: "B-204 numaralı salonda", duration_s: 3, language: "tr", warnings: [] } });
  // the clip goes as the raw body through fetch (VO-B API.md §2), not through request()
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    state.calls.push({ path: url, method: init.method, body: init.body });
    const r = state.transcribe!(init.body as Blob);
    return new Response(JSON.stringify(r.json), { status: r.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  window.matchMedia = ((q: string) => ({ matches: q.includes("coarse") ? state.coarse : false, media: q, onchange: null, addListener: () => undefined, removeListener: () => undefined, addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false })) as typeof window.matchMedia;
  media = installMedia();
});
afterEach(() => {
  vi.unstubAllGlobals();
  media.restore();
  window.matchMedia = realMatch;
  delete document.documentElement.dataset.motion;
});

function renderIt(ui: React.ReactNode, locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

function Box({ target = "rules" as const }: { target?: "rules" | "chat" | "guard" }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  return (
    <div>
      <textarea aria-label="kutu" ref={ref} defaultValue="" data-testid="box" />
      <MicButton target={target} fieldRef={ref} />
    </div>
  );
}

async function record(btn: HTMLElement) {
  await act(async () => {
    fireEvent.click(btn);
  });
  await waitFor(() => expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording"));
}

describe("MicButton visibility", () => {
  it.each([
    ["voice off", { available: false, reason: "disabled" }],
    ["no model", { available: false, reason: "not_configured" }],
    ["no permission", { available: false, reason: "no_permission" }],
  ])("is hidden when %s", async (_n, st) => {
    state.status = { ...ok, ...st };
    renderIt(<Box />);
    await waitFor(() => expect(state.calls.some((c) => c.path === "/ai/voice/status")).toBe(true));
    await act(async () => undefined);
    expect(screen.queryByTestId("voice-mic")).toBeNull();
  });
  it("is hidden without a voice backend (status 404)", async () => {
    state.status = new HttpError(404, "404");
    renderIt(<Box />);
    await act(async () => undefined);
    await waitFor(() => expect(state.calls.length).toBeGreaterThan(0));
    expect(screen.queryByTestId("voice-mic")).toBeNull();
  });
});

describe("MicButton status", () => {
  it("is hidden on a surface outside `targets`", async () => {
    state.status = { ...ok, targets: ["guard"] };
    renderIt(<Box target="rules" />);
    await waitFor(() => expect(state.calls.some((c) => c.path === "/ai/voice/status")).toBe(true));
    await act(async () => undefined);
    expect(screen.queryByTestId("voice-mic")).toBeNull();
  });
  it("limit reached: the mic stays, marked disabled, and says the minutes without recording", async () => {
    state.status = { ...ok, available: false, reason: "limit_reached", usage: { day_s: 600, day_limit_s: 600, month_s: 600, month_limit_s: 6000 } };
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    expect(btn).toHaveAttribute("aria-disabled", "true");
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(await screen.findByTestId("voice-error")).toHaveTextContent("Bugünkü sesli giriş sınırınıza ulaştınız (10/10 dk).");
    expect(media.getUserMedia).not.toHaveBeenCalled();
  });
});

describe("MicButton desktop", () => {
  it("click to start, click to stop: the transcript lands in the box, selected, focused, with the chip — nothing is sent", async () => {
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    expect(btn).toHaveAccessibleName("Sesle yaz");
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await record(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(btn).toHaveAccessibleName("Kaydı durdur");
    media.advance(2500);
    await act(async () => {
      fireEvent.click(btn);
    });
    const box = screen.getByTestId("box") as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toBe("B-204 numaralı salonda"));
    expect(document.activeElement).toBe(box);
    expect([box.selectionStart, box.selectionEnd]).toEqual([0, 22]);
    expect(screen.getByTestId("voice-chip")).toHaveTextContent("Sesle girildi");
    const up = state.calls.find((c) => c.path.startsWith("/api/v1/ai/voice/transcribe"))!;
    expect(up.path).toBe("/api/v1/ai/voice/transcribe?feature=rules&lang=tr");
    expect(up.method).toBe("POST");
    expect((up.body as Blob).type).toBe("audio/webm;codecs=opus");
    // F-VO-3: an input event that leaves the text as the voice put it (a re-dispatch, a framework's own event) keeps
    // the chip; this cleared it before (2 of 4 e2e runs lost the chip within the 10 s window)
    fireEvent.input(box);
    await act(async () => new Promise((r) => setTimeout(r, 900)));
    expect(screen.getByTestId("voice-chip")).toHaveTextContent("Sesle girildi");
    // the user's own edit removes the chip
    fireEvent.input(box, { target: { value: "B-204 numaralı salonda pazartesi" } });
    expect(screen.queryByTestId("voice-chip")).toBeNull();
  });

  it("inside a PromptComposer the text goes into its box and onSend is never called", async () => {
    const onSend = vi.fn();
    renderIt(<PromptComposer onSend={onSend} label="Sohbet" leading={<MicButton target="chat" />} />);
    const btn = await screen.findByTestId("voice-mic");
    await act(async () => {
      fireEvent.click(btn);
    });
    await waitFor(() => expect(screen.getByTestId("voice-mic-chat")).toHaveAttribute("data-phase", "recording"));
    media.advance(1500);
    await act(async () => {
      fireEvent.click(btn);
    });
    const box = screen.getByLabelText("Sohbet") as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toBe("B-204 numaralı salonda"));
    expect(onSend).not.toHaveBeenCalled();
    // the composer's own state followed the insertion: its send button is live
    expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled();
  });

  it("Ctrl+Shift+M in the box toggles; Esc cancels and focus returns to the mic", async () => {
    renderIt(<Box />);
    await screen.findByTestId("voice-mic");
    const box = screen.getByTestId("box");
    await act(async () => {
      fireEvent.keyDown(box, { key: "M", ctrlKey: true, shiftKey: true });
    });
    await waitFor(() => expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording"));
    media.advance(1000);
    await act(async () => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "idle");
    expect(document.activeElement).toBe(screen.getByTestId("voice-mic"));
    expect(state.calls.some((c) => c.path.startsWith("/api/v1/ai/voice/transcribe"))).toBe(false);
  });
});

describe("MicButton consent", () => {
  it("first use opens the sheet with the provider and region; agreeing records the consent and starts; focus starts on the action", async () => {
    state.status = { ...ok, consent: false };
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await act(async () => {
      fireEvent.click(btn);
    });
    const sheet = await screen.findByTestId("voice-consent");
    expect(sheet).toHaveTextContent("OpenAI hizmetine (EU)");
    expect(sheet).toHaveTextContent("ses kaydı saklanmaz");
    expect(media.getUserMedia).not.toHaveBeenCalled();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("voice-consent-accept")));
    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-consent-accept"));
    });
    await waitFor(() => expect(state.calls.some((c) => c.path === "/me/consents/voice" && c.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording"));
  });

  it("'Şimdi değil' closes the sheet and returns focus to the mic", async () => {
    state.status = { ...ok, consent: false };
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await act(async () => {
      fireEvent.click(btn);
    });
    await act(async () => {
      fireEvent.click(await screen.findByTestId("voice-consent-later"));
    });
    await waitFor(() => expect(screen.queryByTestId("voice-consent")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(btn));
    expect(media.getUserMedia).not.toHaveBeenCalled();
  });
});

describe("MicButton errors", () => {
  it("the site policy shows the policy sentence (TR and EN)", async () => {
    media.restore();
    media = installMedia({ policy: false });
    const { unmount } = renderIt(<Box />);
    await act(async () => {
      fireEvent.click(await screen.findByTestId("voice-mic"));
    });
    expect(await screen.findByTestId("voice-error")).toHaveTextContent("Bu sitede mikrofon kullanımı kapalı. Yöneticinize bildirin.");
    unmount();
    renderIt(<Box />, "en");
    await act(async () => {
      fireEvent.click(await screen.findByTestId("voice-mic"));
    });
    expect(await screen.findByTestId("voice-error")).toHaveTextContent("Microphone use is turned off for this site. Tell your administrator.");
  });

  it("permission denied shows the sentence and the browser steps", async () => {
    media.restore();
    media = installMedia({ reject: "NotAllowedError" });
    renderIt(<Box />);
    await act(async () => {
      fireEvent.click(await screen.findByTestId("voice-mic"));
    });
    const e = await screen.findByTestId("voice-error");
    expect(e).toHaveAttribute("data-code", "permission_denied");
    expect(e).toHaveTextContent("Mikrofon izni verilmedi.");
    expect(e).toHaveTextContent("Mikrofon › İzin ver");
  });

  it.each([
    [429, { code: "ai_voice_limit_reached", scope: "user_daily", used_min: 10, limit_min: 10 }, "Bugünkü sesli giriş sınırınıza ulaştınız (10/10 dk)."],
    [409, { code: "voice_not_configured", reason: "disabled" }, "Ses için bir model seçilmedi."],
    [409, { code: "ai_transfer_basis_missing" }, "KVKK aktarım kaydı yok"],
    [502, { code: "provider_error" }, "Ses yazıya dökülemedi. Tekrar deneyin ya da yazarak devam edin."],
    [413, { code: "too_long" }, "Kayıt en fazla 120 saniye olabilir"],
  ])("server %s → its sentence, the box untouched", async (status, detail, text) => {
    state.transcribe = () => ({ status, json: { detail: { ...detail, message_tr: "x", message_en: "x" } } });
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await record(btn);
    media.advance(2000);
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(await screen.findByTestId("voice-error")).toHaveTextContent(text);
    expect((screen.getByTestId("box") as HTMLTextAreaElement).value).toBe("");
  });

  it("an empty transcript is 'no speech'", async () => {
    state.transcribe = () => ({ json: { text: "", warnings: ["empty"] } });
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await record(btn);
    media.advance(2000);
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(await screen.findByTestId("voice-error")).toHaveTextContent("Ses algılanmadı.");
  });
});

describe("MicButton phone (coarse pointer)", () => {
  const down = (el: HTMLElement, x = 100, y = 100) => fireEvent.pointerDown(el, { pointerId: 7, pointerType: "touch", clientX: x, clientY: y });
  const move = (el: HTMLElement, x: number, y: number) => fireEvent.pointerMove(el, { pointerId: 7, pointerType: "touch", clientX: x, clientY: y });
  const up = (el: HTMLElement) => fireEvent.pointerUp(el, { pointerId: 7, pointerType: "touch" });

  beforeEach(() => {
    state.coarse = true;
  });

  it("press and hold records; release stops and transcribes", async () => {
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await act(async () => {
      down(btn);
    });
    await waitFor(() => expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording"));
    expect(screen.getByTestId("voice-hold-hint")).toHaveTextContent("Kilitle");
    media.advance(1800);
    await act(async () => {
      up(btn);
      fireEvent.click(btn); // the click that follows a touch is swallowed
    });
    await waitFor(() => expect((screen.getByTestId("box") as HTMLTextAreaElement).value).toBe("B-204 numaralı salonda"));
  });

  it("slide left cancels: nothing is uploaded", async () => {
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await act(async () => {
      down(btn);
    });
    await waitFor(() => expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording"));
    media.advance(1000);
    await act(async () => {
      move(btn, 10, 100);
    });
    await act(async () => {
      up(btn);
    });
    expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "idle");
    expect(state.calls.some((c) => c.path.startsWith("/api/v1/ai/voice/transcribe"))).toBe(false);
  });

  it("slide up locks: release keeps recording until Bitti", async () => {
    renderIt(<Box />);
    const btn = await screen.findByTestId("voice-mic");
    await act(async () => {
      down(btn);
    });
    await waitFor(() => expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording"));
    media.advance(1000);
    await act(async () => {
      move(btn, 100, 30);
      up(btn);
      fireEvent.click(btn);
    });
    expect(screen.getByTestId("voice-mic-rules")).toHaveAttribute("data-phase", "recording");
    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-done"));
    });
    await waitFor(() => expect((screen.getByTestId("box") as HTMLTextAreaElement).value).toBe("B-204 numaralı salonda"));
  });
});

describe("reduced motion", () => {
  it("the level bar is static", async () => {
    document.documentElement.dataset.motion = "reduced";
    renderIt(<Box />);
    await record(await screen.findByTestId("voice-mic"));
    expect(screen.getByTestId("voice-level")).toHaveAttribute("data-static", "1");
  });
});
