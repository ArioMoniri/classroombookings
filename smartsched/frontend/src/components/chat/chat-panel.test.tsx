import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { ChatPanel } from "./chat-panel";
import type { StreamEvent } from "./chat-stream";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));
const sendChat = vi.fn(async () => ({ messages: [] }));
vi.mock("@/lib/api/hooks", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/hooks")>()),
  useChat: () => ({ data: { messages: [] } }),
  useSettings: () => ({ data: { anthropic_api_key_masked: "sk-…", anthropic_model: "claude" } }),
  useSendChat: () => ({ mutateAsync: sendChat, isPending: false }),
  useUndoProposal: () => ({ mutateAsync: vi.fn() }),
}));
vi.mock("@/lib/api/shell-extra", async (orig) => ({ ...(await orig<typeof import("@/lib/api/shell-extra")>()), usePermissions: () => ({ can: () => true }) }));
let release: () => void = () => undefined;
const stream = vi.fn();
vi.mock("./chat-stream", async (orig) => ({ ...(await orig<typeof import("./chat-stream")>()), streamChat: (...a: unknown[]) => stream(...a) }));

function renderPanel() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="en">
        <ChatPanel runId={5} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // jsdom has no element scrolling
  Element.prototype.scrollTo ??= vi.fn() as unknown as typeof Element.prototype.scrollTo;
  stream.mockReset();
  sendChat.mockClear();
});

describe("ChatPanel streaming (ai-engineer follow-up)", () => {
  it("renders streamed text as it arrives and each tool call as pending, then its result", async () => {
    stream.mockImplementation(async (_run: number, _msg: string, _lang: string, on: (e: StreamEvent) => void) => {
      on({ event: "tool_start", data: { name: "find_rooms" } });
      on({ event: "text", data: { text: "Looking at A 204" } });
      await new Promise<void>((r) => (release = r));
      on({ event: "tool", data: { name: "find_rooms", ok: true } });
      on({ event: "done", data: { message_id: 1 } });
    });
    renderPanel();
    await userEvent.type(screen.getByRole("textbox"), "Move BME 419 to A 204");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Looking at A 204")).toBeInTheDocument();
    expect(screen.getByTestId("chat-tools").querySelector("li")).toHaveAttribute("data-state", "pending");
    expect(screen.getByTestId("chat-panel").querySelector("[aria-live]")).toHaveAttribute("aria-busy", "true");
    release();
    expect(sendChat).not.toHaveBeenCalled();
  });

  it("falls back to the non-streaming call when the stream cannot start", async () => {
    stream.mockRejectedValue(new Error("405"));
    renderPanel();
    await userEvent.type(screen.getByRole("textbox"), "Hello");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(sendChat).toHaveBeenCalledWith("Hello"));
  });
});
