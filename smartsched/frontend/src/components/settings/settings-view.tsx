"use client";

import { Check, Eye, EyeOff, Loader2, Plus } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/common/status-badge";
import { ACCENTS, useAccentPreference, type Accent } from "@/components/shell/appearance";
import { AppearancePreferencesControl } from "@/components/ui/appearance-preferences";
import { SegmentedGlass } from "@/components/ui/segmented-glass";
import { HttpError } from "@/lib/api/client";
import { aiFailureKind, testAiKey, useMeFull, usePermissions } from "@/lib/api/shell-extra";
import { useHydrated } from "@/lib/use-hydrated";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { initials } from "@/components/shell/user-menu";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { api } from "@/lib/api/endpoints";
import { useSettings, useUpdateSettings, useUsers } from "@/lib/api/hooks";
import { useQueryClient } from "@tanstack/react-query";
import type { Role, Settings } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

const WEIGHT_KINDS = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;

type KeyTest = { state: "untested" } | { state: "testing" } | { state: "ok"; model: string | null; which: "typed" | "stored" } | { state: "failed"; kind: ReturnType<typeof aiFailureKind>; which: "typed" | "stored" };

/** The status pill reflects the last backend test only: never "connected" unless the backend confirmed it. */
function KeyStatus({ test, hasKey }: { test: KeyTest; hasKey: boolean }) {
  const { t } = useI18n();
  if (test.state === "testing")
    return (
      <span role="status" className="inline-flex items-center gap-1.5 text-[12.5px] text-label-2">
        <Loader2 className="size-3.5 animate-spin" aria-hidden /> {t("settings.testing")}
      </span>
    );
  if (test.state === "ok") return <span role="status" data-testid="test-result"><StatusBadge kind="feasible" label={test.model ? t("glass.settings.keyOkModel", { model: test.model }) : t("glass.settings.keyOk")} /></span>;
  if (test.state === "failed") return <span role="status" data-testid="test-result"><StatusBadge kind="infeasible" label={t(`glass.settings.keyFail.${test.kind}`)} /></span>;
  return <span className="text-[12.5px] text-label-3">{hasKey ? t("glass.settings.keyUntested") : t("settings.noKey")}</span>;
}

function SettingsRow({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6 [&:not(:last-child)]:hairline-b">
      <div className="min-w-0">
        <Label htmlFor={htmlFor} className="text-[13px] font-medium text-label-1">{label}</Label>
        {hint ? <p className="text-[12px] leading-4 text-label-2">{hint}</p> : null}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function AiCard() {
  const { t } = useI18n();
  const settings = useSettings();
  const update = useUpdateSettings();
  const keyRef = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState(false);
  const [show, setShow] = useState(false);
  const [test, setTest] = useState<KeyTest>({ state: "untested" });
  const [modelState, setModel] = useState<string | null>(null);
  const s = settings.data;
  const model = modelState ?? s?.anthropic_model ?? "";
  const masked = s?.anthropic_api_key_masked ?? null;
  const typing = !masked || replacing;
  const runTest = async (which: "typed" | "stored") => {
    const typed = keyRef.current?.value.trim() ?? "";
    if (which === "typed" && !typed) return;
    setTest({ state: "testing" });
    try {
      const res = await testAiKey(which === "typed" ? { api_key: typed, model } : { model });
      setTest(res.ok ? { state: "ok", model: res.model ?? model, which } : { state: "failed", kind: aiFailureKind(res.detail), which });
    } catch (e) {
      setTest({ state: "failed", kind: e instanceof HttpError && e.status === 0 ? "network" : "other", which });
    }
  };
  const saveKey = async () => {
    const value = keyRef.current?.value.trim() ?? "";
    if (!value) return;
    await update.mutateAsync({ anthropic_api_key: value });
    if (keyRef.current) keyRef.current.value = "";
    setReplacing(false);
    // a saved key is not a working key: keep a typed-key test result, otherwise ask for a test
    setTest((prev) => (prev.state === "ok" || prev.state === "failed" ? { ...prev, which: "stored" } : { state: "untested" }));
    toast.success(t("settings.saved"));
  };
  const saveModel = async () => {
    await update.mutateAsync({ anthropic_model: model });
    setTest({ state: "untested" });
    toast.success(t("settings.saved"));
  };
  const hint = (m: string) => (m.includes("opus") ? t("glass.settings.modelOpus") : m.includes("haiku") ? t("glass.settings.modelHaiku") : t("glass.settings.modelSonnet"));
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.apiKey")}</CardTitle>
          <CardDescription>{t("settings.apiKeyHint")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!typing ? (
            <div className="flex flex-wrap items-center gap-2">
              <span aria-label={t("settings.apiKeyMasked", { tail: masked?.slice(-4) ?? "" })} className="rounded-lg bg-fill-3 px-3 py-1.5 font-mono text-[13px] shadow-[inset_0_0_0_1px_var(--hairline)]" data-testid="api-key-masked">sk-ant-•••••••{masked?.slice(-4)}</span>
              <Button size="sm" variant="outline" onClick={() => void runTest("stored")} disabled={test.state === "testing"} data-testid="test-key">
                {t("settings.test")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setReplacing(true)}>{t("settings.replaceKey")}</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <div className="grid w-full flex-1 basis-full gap-1 sm:max-w-md sm:basis-auto">
                <Label htmlFor="api-key">{t("settings.apiKey")}</Label>
                <div className="relative">
                  <Input id="api-key" ref={keyRef} type={show ? "text" : "password"} placeholder="sk-ant-…" autoComplete="off" spellCheck={false} className="pr-10 font-mono" onChange={() => test.state !== "untested" && setTest({ state: "untested" })} />
                  <button type="button" aria-pressed={show} aria-label={show ? t("glass.auth.hidePassword") : t("glass.auth.showPassword")} onClick={() => setShow((v) => !v)} className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-label-3 hover:text-label-1">{show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={() => void runTest("typed")} disabled={test.state === "testing"} data-testid="test-key-typed">{t("glass.settings.testFirst")}</Button>
              <Button size="sm" onClick={() => void saveKey()} disabled={update.isPending}>{t("common.save")}</Button>
              {masked ? <Button size="sm" variant="ghost" onClick={() => setReplacing(false)}>{t("settings.cancelReplace")}</Button> : null}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2" aria-live="polite">
            <KeyStatus test={test} hasKey={Boolean(masked)} />
            {test.state === "failed" ? <span className="text-[12px] text-label-2">{t(`glass.settings.keyFixHint.${test.kind}`)}</span> : null}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.model")}</CardTitle>
          <CardDescription>{t("glass.settings.modelHint")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div role="radiogroup" aria-label={t("settings.model")}>
            {(s?.available_models ?? []).map((m) => (
              <label key={m} className="flex cursor-pointer items-center gap-3 py-2.5 text-[13px] [&:not(:last-child)]:hairline-b">
                <input type="radio" name="model" value={m} checked={model === m} onChange={() => setModel(m)} className="accent-(--accent)" />
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-label-1">{m}</span>
                  <span className="block text-[12px] text-label-3">{hint(m)}</span>
                </span>
              </label>
            ))}
          </div>
          <Button size="sm" className="mt-3" onClick={() => void saveModel()} disabled={!s || model === s.anthropic_model || update.isPending} data-testid="save-model">{t("common.save")}</Button>
        </CardContent>
      </Card>
    </div>
  );
}

const ACCENT_SWATCH: Record<Accent, string> = { blue: "#0a63d1", indigo: "#4f46e5", teal: "#0b7268", graphite: "#3d3d44", orange: "#b9470b" };

function AppearanceCard() {
  const { t } = useI18n();
  const me = useMeFull();
  const { theme, setTheme } = useTheme();
  const { accent, set } = useAccentPreference(me.data?.id);
  const density = useUiStore((st) => st.density);
  const setDensity = useUiStore((st) => st.setDensity);
  const mounted = useHydrated();
  const mode = mounted && (theme === "light" || theme === "dark") ? theme : "system";
  return (
    <div className="space-y-5" data-testid="appearance">
      <Card>
        <CardHeader>
          <CardTitle>{t("glass.settings.appearance")}</CardTitle>
          <CardDescription>{t("glass.settings.appearanceHint")}</CardDescription>
        </CardHeader>
        <CardContent>
          <SettingsRow label={t("settings.theme")} hint={t("glass.settings.themeHint")}>
            <SegmentedGlass size="sm" aria-label={t("settings.theme")} value={mode} onValueChange={(v) => setTheme(v)} options={[{ value: "system", label: t("theme.system") }, { value: "light", label: t("theme.light") }, { value: "dark", label: t("theme.dark") }]} />
          </SettingsRow>
          <SettingsRow label={t("glass.settings.accent")} hint={t("glass.settings.accentHint")}>
            <div role="radiogroup" aria-label={t("glass.settings.accent")} className="flex items-center gap-2">
              {ACCENTS.map((a) => (
                <button key={a} type="button" role="radio" aria-checked={accent === a} aria-label={t(`glass.settings.accents.${a}`)} title={t(`glass.settings.accents.${a}`)} onClick={() => set(a)} data-testid={`accent-${a}`} className="relative flex size-7 items-center justify-center rounded-full outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)" style={{ background: ACCENT_SWATCH[a] }}>
                  {accent === a ? <Check className="size-4 text-white" aria-hidden /> : null}
                </button>
              ))}
            </div>
          </SettingsRow>
          <SettingsRow label={t("glass.settings.density")} hint={t("glass.settings.densityHint")}>
            <SegmentedGlass size="sm" aria-label={t("glass.settings.density")} value={density} onValueChange={(v) => setDensity(v === "compact" ? "compact" : "comfortable")} options={[{ value: "comfortable", label: t("glass.settings.comfortable") }, { value: "compact", label: t("glass.settings.compact") }]} />
          </SettingsRow>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("glass.settings.accessibility")}</CardTitle>
          <CardDescription>{t("glass.settings.accessibilityHint")}</CardDescription>
        </CardHeader>
        <CardContent>
          <AppearancePreferencesControl userId={me.data?.id} labels={{ motion: t("glass.settings.reduceMotion"), motionHint: t("glass.settings.reduceMotionHint"), transparency: t("glass.settings.reduceTransparency"), transparencyHint: t("glass.settings.reduceTransparencyHint") }} />
        </CardContent>
      </Card>
    </div>
  );
}

function SolverCard() {
  const settings = useSettings();
  if (!settings.data) return null;
  return <SolverForm key={settings.dataUpdatedAt} initial={settings.data} />;
}

function SolverForm({ initial }: { initial: Settings }) {
  const { t } = useI18n();
  const update = useUpdateSettings();
  const [form, setForm] = useState({ time: initial.solver_default_time_limit, workers: initial.solver_default_workers, seed: initial.solver_default_seed, weights: { ...initial.default_weights } });
  const save = async () => {
    await update.mutateAsync({ solver_default_time_limit: form.time, solver_default_workers: form.workers, solver_default_seed: form.seed, default_weights: form.weights });
    toast.success(t("settings.saved"));
  };
  return (
    <Card>
      <CardHeader><CardTitle>{t("settings.solver")}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1"><Label htmlFor="s-time">{t("settings.timeLimit")}</Label><Input id="s-time" type="number" min={10} max={900} value={form.time} onChange={(e) => setForm({ ...form, time: Number(e.target.value) })} /></div>
          <div className="grid gap-1"><Label htmlFor="s-workers">{t("settings.workers")}</Label><Input id="s-workers" type="number" min={1} max={16} value={form.workers} onChange={(e) => setForm({ ...form, workers: Number(e.target.value) })} /></div>
          <div className="grid gap-1"><Label htmlFor="s-seed">{t("settings.seed")}</Label><Input id="s-seed" type="number" value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })} /></div>
        </div>
        <div>
          <p className="mb-2 text-sm font-medium">{t("settings.weights")}</p>
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground"><tr><th scope="col" className="text-left font-medium">{t("runs.constraints")}</th><th scope="col" className="w-48 text-left font-medium">w</th></tr></thead>
            <tbody>
              {WEIGHT_KINDS.map((k) => (
                <tr key={k}>
                  <th scope="row" className="py-1.5 text-left font-normal">{t(`generate.weight.${k}`)}</th>
                  <td className="flex items-center gap-2 py-1.5"><Slider min={0} max={10} step={1} value={[form.weights[k] ?? 0]} onValueChange={(v) => setForm({ ...form, weights: { ...form.weights, [k]: Array.isArray(v) ? v[0] : v } })} aria-label={t(`generate.weight.${k}`)} className="w-32" /><span className="w-5 font-mono text-xs tabular-nums">{form.weights[k] ?? 0}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button size="sm" onClick={() => void save()} disabled={update.isPending} data-testid="save-solver">{t("common.save")}</Button>
      </CardContent>
    </Card>
  );
}

function UsersCard() {
  const { t } = useI18n();
  const users = useUsers();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", full_name: "", role: "PLANNER" as Role, password: "" });
  const [saving, setSaving] = useState(false);
  const submit = async () => {
    setSaving(true);
    try {
      await api.settings.createUser(form);
      await qc.invalidateQueries({ queryKey: ["users"] });
      setOpen(false);
      setForm({ email: "", full_name: "", role: "PLANNER", password: "" });
      toast.success(t("settings.saved"));
    } finally {
      setSaving(false);
    }
  };
  if (users.isError) return null; // GET /users is ADMIN-only (403 for planners/viewers)
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>{t("settings.users")}</CardTitle>
        <Button size="sm" onClick={() => setOpen(true)} data-testid="add-user"><Plus /> {t("settings.addUser")}</Button>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader><TableRow><TableHead>{t("settings.name")}</TableHead><TableHead>{t("settings.email")}</TableHead><TableHead>{t("settings.role")}</TableHead><TableHead>{t("common.status")}</TableHead></TableRow></TableHeader>
          <TableBody>
            {(users.data ?? []).map((u) => (
              <TableRow key={u.id}>
                <TableCell className="flex items-center gap-2"><Avatar className="size-6"><AvatarFallback className="text-[10px]">{initials(u.full_name, u.email ?? "")}</AvatarFallback></Avatar>{u.full_name ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{u.email ?? "—"}</TableCell>
                <TableCell className="text-label-2">{t(`glass.role.${u.role}`)}</TableCell>
                <TableCell><span className={cn("inline-flex items-center gap-1 text-xs", u.is_active ? "text-status-feasible-fg" : "text-muted-foreground")}><span className={cn("size-1.5 rounded-full", u.is_active ? "bg-status-feasible-solid" : "bg-border-strong")} aria-hidden />{u.is_active ? t("settings.active") : t("settings.inactive")}</span></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>{t("settings.addUser")}</DialogTitle><DialogDescription className="sr-only">{t("settings.users")}</DialogDescription></DialogHeader>
          <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <div className="grid gap-1"><Label htmlFor="u-name">{t("settings.name")}</Label><Input id="u-name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></div>
            <div className="grid gap-1"><Label htmlFor="u-email">{t("settings.email")}</Label><Input id="u-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
            <div className="grid gap-1"><Label htmlFor="u-role">{t("settings.role")}</Label><NativeSelect id="u-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>{(["ADMIN", "PLANNER", "VIEWER"] as const).map((r) => <option key={r} value={r}>{t(`glass.role.${r}`)}</option>)}</NativeSelect></div>
            <div className="grid gap-1"><Label htmlFor="u-pass">{t("auth.password")}</Label><Input id="u-pass" type="password" required autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
            <DialogFooter><Button type="submit" disabled={saving}>{t("common.save")}</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function GeneralCard() {
  const { t } = useI18n();
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader><CardTitle>{t("settings.general")}</CardTitle></CardHeader>
        <CardContent>
          <SettingsRow label={t("settings.language")} hint={t("glass.settings.languageHint")}>
            <LocaleToggle />
          </SettingsRow>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t("common.periods")}</CardTitle>
          <CardDescription>{t("glass.settings.periodsHint")}</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] tabular-nums sm:grid-cols-3">
            {PERIODS.map((p) => (
              <li key={p.index} className="flex gap-2">
                <span className="w-6 text-label-3">{p.index}.</span>
                <span className="text-label-1">{p.start}–{p.end}</span>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

export function SettingsView() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const { can } = usePermissions();
  const admin = can(["planning.admin", "setup.settings"]);
  const tabs = [
    { value: "general", label: t("settings.general"), show: true },
    { value: "appearance", label: t("glass.settings.appearance"), show: true },
    { value: "ai", label: t("settings.ai"), show: admin },
    { value: "solver", label: t("settings.solver"), show: admin },
    { value: "users", label: t("settings.users"), show: can("setup.users") },
  ].filter((x) => x.show);
  const requested = params.get("tab") ?? (admin ? "ai" : "appearance");
  const tab = tabs.some((x) => x.value === requested) ? requested : "appearance";
  return (
    <div className="mx-auto max-w-[880px]" data-testid="settings">
      <PageHeader title={t("settings.title")} subtitle={admin ? t("settings.subtitle") : t("glass.settings.subtitleUser")} />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/settings?tab=${String(v)}`)}>
        <TabsList className="mb-5 max-w-full overflow-x-auto">
          {tabs.map((x) => (
            <TabsTrigger key={x.value} value={x.value} data-testid={`tab-${x.value}`}>{x.label}</TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="general"><GeneralCard /></TabsContent>
        <TabsContent value="appearance"><AppearanceCard /></TabsContent>
        {admin ? <TabsContent value="ai"><AiCard /></TabsContent> : null}
        {admin ? <TabsContent value="solver"><SolverCard /></TabsContent> : null}
        <TabsContent value="users"><UsersCard /></TabsContent>
      </Tabs>
    </div>
  );
}
