import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { I18nProvider } from "@/lib/i18n/provider";
import { UploadPanel } from "./upload-panel";
import { WriteIt } from "./write-it";

let text = "Akşam dersleri B blokta olsun";
const state = { nlText: text, setNlText: (v: string) => (text = v), addTray: vi.fn() };
vi.mock("./studio-context", () => ({
  useStudio: () => ({ termId: 3, store: { getState: () => state }, goStep: vi.fn(), meta: { templates: [] }, kind: "COURSE", sentence: { programs: [] } }),
  useStudioStore: (sel: (s: typeof state) => unknown) => sel({ ...state, nlText: text }),
}));
vi.mock("./studio-data", () => ({ useStudioData: () => ({ rooms: [] }) }));
let usage: Record<string, unknown> | undefined;
vi.mock("@/lib/api/ai-admin", async (orig) => ({ ...(await orig<typeof import("@/lib/api/ai-admin")>()), useMyAiUsage: () => ({ data: usage }) }));
const elicit = vi.fn();
const uploadPreferences = vi.fn();
vi.mock("@/lib/api/endpoints", async (orig) => {
  const real = await orig<typeof import("@/lib/api/endpoints")>();
  return { ...real, api: { ...real.api, studio: { ...real.api.studio, elicit: (...a: unknown[]) => elicit(...a), uploadPreferences: (...a: unknown[]) => uploadPreferences(...a) } } };
});

function renderIt() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <WriteIt noKey={false} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  usage = undefined;
  elicit.mockReset();
  text = "Akşam dersleri B blokta olsun";
});

describe("WriteIt AI usage (wave 3 integration)", () => {
  it("shows the AI notice and the near-limit banner", () => {
    usage = { state: "soft", org_state: "ok", pct: 85, daily_pct: 85, monthly_pct: 10 };
    renderIt();
    expect(screen.getByTestId("write-it").querySelector("[data-testid=ai-notice]")).not.toBeNull();
    expect(screen.getByTestId("ai-banner-near")).toBeInTheDocument();
  });

  it("a guardrail / limit refusal is told in Turkish, not as an HTTP status line", async () => {
    elicit.mockRejectedValue(
      new HttpError(429, "429 Too Many Requests", { detail: { code: "ai_limit_reached", message_en: "You reached your AI limit.", message_tr: "Yapay zekâ sınırınıza ulaştınız." } }),
    );
    renderIt();
    await userEvent.click(screen.getByTestId("nl-analyse"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Yapay zekâ sınırınıza ulaştınız.");
    expect(alert).not.toHaveTextContent("429");
  });
});

describe("UploadPanel AI usage (wave 3 integration)", () => {
  it("shows the AI notice, the at-limit banner and a refused upload in Turkish", async () => {
    usage = { state: "hard", org_state: "ok", pct: 100, daily_pct: 100, monthly_pct: 30 };
    uploadPreferences.mockRejectedValue(
      new HttpError(422, "422 Unprocessable Entity", { detail: { code: "prompt_injection_override", message_en: "This text tries to change the assistant's instructions.", message_tr: "Bu metin asistanın talimatlarını değiştirmeye çalışıyor." } }),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <UploadPanel onClose={() => undefined} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const panel = screen.getByTestId("upload-panel");
    expect(panel.querySelector("[data-testid=ai-notice]")).not.toBeNull();
    expect(screen.getByTestId("ai-banner-at")).toBeInTheDocument();
    await userEvent.upload(screen.getByTestId("upload-input"), new File(["x"], "tercihler.docx"));
    expect(await screen.findByText("Bu metin asistanın talimatlarını değiştirmeye çalışıyor.")).toBeInTheDocument();
  });
});
