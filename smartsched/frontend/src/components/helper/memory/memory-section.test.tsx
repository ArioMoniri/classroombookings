/** HX-08 (helper.md §5.1): Profil › Yardımcı — switch, notes (add / delete / refused name), history delete. */
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "@/lib/api/client";
import { helperApi, helperCaps, type HelperMemory } from "@/lib/api/helper";
import { renderHelper } from "../test-helpers";
import { HelperMemorySection } from "./memory-section";

vi.mock("sonner", async (orig) => ({ ...(await orig<typeof import("sonner")>()), toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }) }));

const mem = (over: Partial<HelperMemory> = {}): HelperMemory => ({ institution_enabled: true, enabled: true, notes: 1, max_notes: 20, max_chars: 200, retention_days: 180, history_days: 30, ...over });
let notes = [{ id: 7, text: "Tercih edilen bina: B blok", source: "user_confirmed", created_at: null, last_used_at: null, expires_at: null }];

beforeEach(() => {
  vi.restoreAllMocks();
  notes = [{ id: 7, text: "Tercih edilen bina: B blok", source: "user_confirmed", created_at: null, last_used_at: null, expires_at: null }];
  vi.spyOn(helperApi, "memory").mockImplementation(async () => mem({ notes: notes.length }));
  vi.spyOn(helperApi, "notes").mockImplementation(async () => notes);
});

describe("Profil › Yardımcı", () => {
  it("lists the notes, the history line and the notice", async () => {
    renderHelper(<HelperMemorySection />);
    expect(await screen.findByTestId("helper-note-7")).toHaveTextContent("Tercih edilen bina: B blok");
    expect(screen.getByTestId("helper-memory")).toHaveTextContent("Son 30 günün konuşmaları saklanır.");
    expect(screen.getByTestId("helper-memory")).toHaveTextContent("Hepsini silebilirsiniz.");
    expect(screen.getByTestId("helper-memory")).toHaveAttribute("data-tour", "profile-helper-memory");
  });

  it("the switch turns the person's memory off", async () => {
    const set = vi.spyOn(helperApi, "setMemory").mockResolvedValue(mem({ enabled: false }));
    renderHelper(<HelperMemorySection />);
    const sw = await screen.findByTestId("helper-memory-switch");
    fireEvent.click(sw);
    await waitFor(() => expect(set).toHaveBeenCalledWith(false));
  });

  it("adds a note only from Not ekle (source user_confirmed)", async () => {
    const add = vi.spyOn(helperApi, "addNote").mockImplementation(async (text) => {
      const n = { id: 8, text, source: "user_confirmed", created_at: null, last_used_at: null, expires_at: null };
      notes = [...notes, n];
      return n;
    });
    renderHelper(<HelperMemorySection />);
    const input = await screen.findByTestId("helper-note-input");
    fireEvent.change(input, { target: { value: "Varsayılan süre: 2 ders saati" } });
    fireEvent.click(screen.getByTestId("helper-note-add"));
    await waitFor(() => expect(add).toHaveBeenCalledWith("Varsayılan süre: 2 ders saati", "user_confirmed"));
    expect(await screen.findByTestId("helper-note-8")).toBeInTheDocument();
    expect(document.activeElement).toBe(input);
  });

  it("shows the server's refusal when a note names a person", async () => {
    vi.spyOn(helperApi, "addNote").mockRejectedValue(new HttpError(422, "names_a_person", { code: "names_a_person", message_tr: "Notlarda başka bir kişinin adı olamaz.", message_en: "A note cannot name another person." }));
    renderHelper(<HelperMemorySection />);
    fireEvent.change(await screen.findByTestId("helper-note-input"), { target: { value: "Ayşe Hoca ile" } });
    fireEvent.click(screen.getByTestId("helper-note-add"));
    expect(await screen.findByTestId("helper-note-error")).toHaveTextContent("Notlarda başka bir kişinin adı olamaz.");
  });

  it("deletes one note and keeps the focus on the page", async () => {
    const del = vi.spyOn(helperApi, "deleteNote").mockImplementation(async (id) => {
      notes = notes.filter((n) => n.id !== id);
    });
    renderHelper(<HelperMemorySection />);
    fireEvent.click(await screen.findByTestId("helper-note-delete-7"));
    await waitFor(() => expect(del).toHaveBeenCalledWith(7));
    expect(await screen.findByTestId("helper-notes-empty")).toHaveTextContent("Henüz hatırlanan bir şey yok.");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("helper-note-input")));
  });

  it("HX-18 M7: Sohbet geçmişini sil keeps the notes (threads-only DELETE /helper/threads)", async () => {
    helperCaps.threadsDelete = true;
    const threads = vi.spyOn(helperApi, "deleteThreads").mockResolvedValue({ notes: 0, threads: 3 });
    const all = vi.spyOn(helperApi, "deleteAll");
    renderHelper(<HelperMemorySection />);
    const btn = await screen.findByTestId("helper-history-delete");
    expect(btn).toHaveTextContent("Sohbet geçmişini sil");
    fireEvent.click(btn);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Sohbet geçmişiniz silinsin mi?");
    expect(screen.getByRole("dialog")).toHaveTextContent("Notlarınız silinmez.");
    fireEvent.click(screen.getByTestId("helper-history-confirm"));
    await waitFor(() => expect(threads).toHaveBeenCalled());
    expect(all).not.toHaveBeenCalled();
  });

  it("HX-18 M7: without the threads-only route the button and the dialog say the notes go too", async () => {
    helperCaps.threadsDelete = false;
    const all = vi.spyOn(helperApi, "deleteAll").mockResolvedValue({ notes: 1, threads: 3 });
    renderHelper(<HelperMemorySection />);
    const btn = await screen.findByTestId("helper-history-delete");
    expect(btn).toHaveTextContent("Notları ve geçmişi sil");
    fireEvent.click(btn);
    expect(all).not.toHaveBeenCalled();
    expect(await screen.findByRole("dialog")).toHaveTextContent("Notlarınız ve konuşma geçmişiniz silinsin mi?");
    fireEvent.click(screen.getByTestId("helper-history-confirm"));
    await waitFor(() => expect(all).toHaveBeenCalledWith(true));
  });

  it("HX-18 M7: Tüm notları sil (notes list) asks first, deletes only the notes and keeps the focus on the page", async () => {
    const all = vi.spyOn(helperApi, "deleteAll").mockImplementation(async () => {
      notes = [];
      return { notes: 1, threads: 0 };
    });
    renderHelper(<HelperMemorySection />);
    fireEvent.click(await screen.findByTestId("helper-notes-delete-all"));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Tüm notlarınız silinsin mi?");
    fireEvent.click(screen.getByTestId("helper-notes-delete-all-confirm"));
    await waitFor(() => expect(all).toHaveBeenCalledWith(false));
    await waitFor(() => expect(document.activeElement).not.toBe(document.body));
  });

  it("HX-18 m3: the note field stays 16 px on a touch tablet", async () => {
    renderHelper(<HelperMemorySection />);
    const input = await screen.findByTestId("helper-note-input");
    expect(input.className).toMatch(/pointer-fine:sm:type-callout/);
    expect(input.className).not.toMatch(/(^| )sm:type-callout/);
  });

  it("with the institution's memory off the switch is disabled and says why", async () => {
    vi.spyOn(helperApi, "memory").mockResolvedValue(mem({ institution_enabled: false, enabled: false }));
    renderHelper(<HelperMemorySection />);
    expect(await screen.findByText("Kurumunuz yardımcı notlarını kapattı.")).toBeInTheDocument();
    expect(screen.getByTestId("helper-memory-switch")).toHaveAttribute("data-disabled");
    expect(screen.queryByTestId("helper-note-input")).toBeNull();
  });
});
