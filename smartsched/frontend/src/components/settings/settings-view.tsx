"use client";

import { Check, Eye, EyeOff, Loader2, Plus, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { NativeSelect } from "@/components/common/native-select";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { initials } from "@/components/shell/user-menu";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { api } from "@/lib/api/endpoints";
import { useSettings, useUpdateSettings, useUsers } from "@/lib/api/hooks";
import { useQueryClient } from "@tanstack/react-query";
import type { Role, Settings, TestAiResponse } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS } from "@/lib/time";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

const WEIGHT_KINDS = ["room_preference", "building_preference", "min_capacity_waste", "same_room_across_weeks", "stability", "exam_gap"] as const;

function AiCard() {
  const { t } = useI18n();
  const settings = useSettings();
  const update = useUpdateSettings();
  const keyRef = useRef<HTMLInputElement>(null);
  const [replacing, setReplacing] = useState(false);
  const [show, setShow] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestAiResponse | null>(null);
  const [modelState, setModel] = useState<string | null>(null);
  const s = settings.data;
  const model = modelState ?? s?.anthropic_model ?? "";
  const masked = s?.anthropic_api_key_masked ?? null;
  const test = async () => {
    setTesting(true);
    try {
      const res = await api.settings.testAi();
      setResult(res);
      if (res.ok) toast.success(t("settings.testOk", { model: res.model ?? "", ms: res.latency_ms ?? 0 }));
      else toast.error(t("settings.testFailed", { reason: res.error ?? "" }));
    } finally {
      setTesting(false);
    }
  };
  const saveKey = async () => {
    const value = keyRef.current?.value.trim() ?? "";
    if (!value) return;
    await update.mutateAsync({ anthropic_api_key: value });
    if (keyRef.current) keyRef.current.value = "";
    setReplacing(false);
    toast.success(t("settings.saved"));
  };
  const saveModel = async () => {
    await update.mutateAsync({ anthropic_model: model });
    toast.success(t("settings.saved"));
  };
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>{t("settings.apiKey")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("settings.apiKeyHint")}</p>
          {masked && !replacing ? (
            <div className="flex flex-wrap items-center gap-2">
              <span aria-label={t("settings.apiKeyMasked", { tail: masked.slice(-4) })} className="rounded-md border bg-muted px-3 py-1.5 font-mono text-sm" data-testid="api-key-masked">sk-ant-•••••••••••••••••••{masked.slice(-4)}</span>
              <Badge variant="outline" className="border-status-feasible-border text-status-feasible-fg">connected</Badge>
              <Button size="sm" variant="outline" onClick={() => void test()} disabled={testing} data-testid="test-key">{testing ? <><Loader2 className="animate-spin" /> {t("settings.testing")}</> : t("settings.test")}</Button>
              <Button size="sm" variant="ghost" onClick={() => setReplacing(true)}>{t("settings.replaceKey")}</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-end gap-2">
              <div className="grid flex-1 gap-1 sm:max-w-md">
                <Label htmlFor="api-key">{t("settings.apiKey")}</Label>
                <div className="relative">
                  <Input id="api-key" ref={keyRef} type={show ? "text" : "password"} placeholder="sk-ant-…" autoComplete="off" spellCheck={false} className="pr-9 font-mono" />
                  <button type="button" aria-pressed={show} aria-label={show ? "Hide" : "Show"} onClick={() => setShow((v) => !v)} className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-muted-foreground">{show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
                </div>
              </div>
              <Button size="sm" onClick={() => void saveKey()} disabled={update.isPending}>{t("common.save")}</Button>
              {masked ? <Button size="sm" variant="ghost" onClick={() => setReplacing(false)}>{t("settings.cancelReplace")}</Button> : null}
            </div>
          )}
          {result ? (
            <p role="status" className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs", result.ok ? "border-status-feasible-border bg-status-feasible text-status-feasible-fg" : "border-status-infeasible-border bg-status-infeasible text-status-infeasible-fg")} data-testid="test-result">
              {result.ok ? <Check className="size-3.5" /> : <X className="size-3.5" />} {result.ok ? t("settings.testOk", { model: result.model ?? "", ms: result.latency_ms ?? 0 }) : t("settings.testFailed", { reason: result.error ?? "" })}
            </p>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>{t("settings.model")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div role="radiogroup" aria-label={t("settings.model")} className="space-y-1.5">
            {(s?.available_models ?? []).map((m) => (
              <label key={m} className={cn("flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm", model === m && "border-primary bg-primary-tint")}>
                <input type="radio" name="model" value={m} checked={model === m} onChange={() => setModel(m)} className="accent-primary" />
                <span className="font-mono">{m}</span>
                <span className="ml-auto text-xs text-muted-foreground">{m.includes("opus") ? "$$$ · strongest reasoning" : m.includes("haiku") ? "$ · fastest" : "$$ · default"}</span>
              </label>
            ))}
          </div>
          <Button size="sm" onClick={() => void saveModel()} disabled={!s || model === s.anthropic_model || update.isPending} data-testid="save-model">{t("common.save")}</Button>
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
                <TableCell className="flex items-center gap-2"><Avatar className="size-6"><AvatarFallback className="text-[10px]">{initials(u.full_name, u.email)}</AvatarFallback></Avatar>{u.full_name ?? "—"}</TableCell>
                <TableCell className="text-muted-foreground">{u.email}</TableCell>
                <TableCell><Badge variant={u.role === "ADMIN" ? "default" : u.role === "PLANNER" ? "secondary" : "outline"}>{u.role}</Badge></TableCell>
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
            <div className="grid gap-1"><Label htmlFor="u-role">{t("settings.role")}</Label><NativeSelect id="u-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>{(["ADMIN", "PLANNER", "VIEWER"] as const).map((r) => <option key={r} value={r}>{r}</option>)}</NativeSelect></div>
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
  const density = useUiStore((s) => s.density);
  const setDensity = useUiStore((s) => s.setDensity);
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>{t("settings.general")}</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="grid gap-1"><Label>{t("settings.language")}</Label><LocaleToggle className="w-fit" /></div>
          <div className="grid gap-1"><Label>{t("settings.theme")}</Label><ThemeToggle className="w-fit" /></div>
          <div className="grid gap-1"><Label htmlFor="density">Density</Label><NativeSelect id="density" value={density} onChange={(e) => setDensity(e.target.value === "compact" ? "compact" : "comfortable")}><option value="comfortable">Comfortable</option><option value="compact">Compact</option></NativeSelect></div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>{t("common.periods")}</CardTitle></CardHeader>
        <CardContent>
          <ol className="grid grid-cols-2 gap-x-6 gap-y-0.5 font-mono text-xs sm:grid-cols-3">{PERIODS.map((p) => <li key={p.index}>P{p.index} {p.start}–{p.end}{p.index === 12 ? " · 30 dk" : ""}</li>)}</ol>
        </CardContent>
      </Card>
    </div>
  );
}

export function SettingsView() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") ?? "ai";
  return (
    <div className="mx-auto max-w-[880px]" data-testid="settings">
      <PageHeader title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/settings?tab=${String(v)}`)}>
        <TabsList className="mb-4">
          <TabsTrigger value="general">{t("settings.general")}</TabsTrigger>
          <TabsTrigger value="ai" data-testid="tab-ai">{t("settings.ai")}</TabsTrigger>
          <TabsTrigger value="solver" data-testid="tab-solver">{t("settings.solver")}</TabsTrigger>
          <TabsTrigger value="users" data-testid="tab-users">{t("settings.users")}</TabsTrigger>
        </TabsList>
        <TabsContent value="general"><GeneralCard /></TabsContent>
        <TabsContent value="ai"><AiCard /></TabsContent>
        <TabsContent value="solver"><SolverCard /></TabsContent>
        <TabsContent value="users"><UsersCard /></TabsContent>
      </Tabs>
    </div>
  );
}
