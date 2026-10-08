"use client";
/**
 * The shell bell (wave 1, docs/product/wave1-api.md §4): in-app notifications from GET /me/notifications with
 * an unread count, mark one / all read, and deep links (approval requests for approvers, decisions for the
 * requester). Planners keep the recent solver runs under the list (what the bell showed before wave 1).
 *
 * Motion: the count bumps (bouncy-subtle, a ≤ 32 px badge) only when it goes up, so a new request is noticed;
 * the popover itself uses the primitive's glass-morph reveal. Reduced motion: no bump. The count is also in the
 * button's accessible name, and new arrivals are announced politely.
 */
import { Bell, CheckCheck, Inbox } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { StatusBadge } from "@/components/common/status-badge";
import { runStatusBadge } from "@/components/runs/runs-list";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useRuns } from "@/lib/api/hooks";
import { usePermissions } from "@/lib/api/shell-extra";
import { useNotifications, wave1, w1Keys, type Notification } from "@/lib/api/wave1";
import { intlLocale } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { springs, useReduce } from "@/lib/motion";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { parseTimestamp } from "@/components/bookings/date-format";
import { notificationHref, relativeTime, unreadLabel } from "./notification-model";

const UNREAD_KEY = ["w1", "notifications", "unread"] as const;

export function NotificationBell({ className }: { className?: string }) {
  const { t, locale } = useI18n();
  const hydrated = useHydrated();
  const router = useRouter();
  const qc = useQueryClient();
  const reduce = useReduce();
  const { can } = usePermissions();
  const planner = can("planning.view");
  const [open, setOpen] = useState(false);
  const list = useNotifications(hydrated);
  const unread = useQuery({
    queryKey: UNREAD_KEY,
    queryFn: () => wave1.notifications.list({ unread: true, limit: 200 }),
    enabled: hydrated,
    retry: false,
    refetchInterval: 60_000,
    staleTime: 20_000,
  });
  const runs = useRuns();
  const count = hydrated ? (unread.data?.length ?? 0) : 0;
  const label = unreadLabel(count);

  // bump only when the count grows (a new notification), never on first paint or when it drops
  const prev = useRef<number | null>(null);
  const [bump, setBump] = useState(0);
  const [announce, setAnnounce] = useState("");
  useEffect(() => {
    if (!unread.isSuccess) return;
    if (prev.current !== null && count > prev.current) {
      setBump((b) => b + 1);
      setAnnounce(t("wave1.bell.newArrived", { count: count - prev.current }));
    }
    prev.current = count;
  }, [count, unread.isSuccess, t]);

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: w1Keys.notifications }), qc.invalidateQueries({ queryKey: UNREAD_KEY })]);
  const markRead = async (body: { ids: number[] } | { all: true }) => {
    try {
      await wave1.notifications.read(body);
    } finally {
      await refresh();
    }
  };
  const openItem = (n: Notification) => {
    const href = notificationHref(n.link, n.request_id);
    if (!n.read_at) void markRead({ ids: [n.id] });
    setOpen(false);
    if (href) router.push(href);
  };

  const items = hydrated ? (list.data ?? []) : [];
  const recentRuns = hydrated && planner ? (runs.data?.slice(0, 5) ?? []) : [];
  const now = new Date();
  const tag = intlLocale(locale);
  const accessible = label ? `${t("nav.notifications")}, ${t("wave1.bell.unread", { count })}` : t("nav.notifications");

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="icon" aria-label={accessible} className={cn("relative", className)} data-testid="notification-bell">
            <Bell />
            <AnimatePresence initial={false}>
              {label ? (
                <motion.span
                  key={`b-${bump}`}
                  aria-hidden
                  data-testid="notification-count"
                  initial={reduce || bump === 0 ? false : { scale: 0.6 }}
                  animate={{ scale: 1 }}
                  exit={{ opacity: 0, transition: { duration: 0.1 } }}
                  transition={reduce ? { duration: 0 } : springs.bouncySubtle}
                  className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-tint px-1 text-center text-[10px] leading-4 font-semibold text-tint-foreground tabular-nums"
                >
                  {label}
                </motion.span>
              ) : null}
            </AnimatePresence>
          </Button>
        }
      />
      <span className="sr-only" role="status" aria-live="polite">
        {announce}
      </span>
      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-1rem))] p-1.5" data-testid="notification-panel">
        <div className="flex items-center justify-between gap-2 px-2.5 pt-1 pb-1.5">
          <p className="type-headline text-label-1">{t("nav.notifications")}</p>
          {count > 0 ? (
            <Button variant="ghost" size="sm" onClick={() => void markRead({ all: true })} data-testid="notifications-read-all">
              <CheckCheck aria-hidden />
              {t("wave1.bell.readAll")}
            </Button>
          ) : null}
        </div>
        {items.length === 0 ? (
          <p className="flex items-center gap-2 px-2.5 py-3 type-callout text-label-2">
            <Inbox className="size-4 text-label-3" aria-hidden />
            {list.isLoading ? t("crbs.common.loading") : t("wave1.bell.empty")}
          </p>
        ) : (
          <ul className="max-h-[min(60vh,420px)] overflow-y-auto" aria-label={t("nav.notifications")}>
            {items.map((n) => {
              const when = n.created_at ? parseTimestamp(n.created_at) : null;
              return (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => openItem(n)}
                    data-testid={`notification-${n.id}`}
                    data-unread={!n.read_at}
                    className="flex w-full items-start gap-2.5 rounded-[10px] px-2.5 py-2 text-left outline-none hover:bg-fill-2 focus-visible:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)"
                  >
                    <span aria-hidden className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-(--accent)")} />
                    <span className="min-w-0 flex-1">
                      <span className={cn("block type-callout text-label-1", !n.read_at && "font-semibold")}>{n.title}</span>
                      {n.body ? <span className="line-clamp-2 block type-footnote text-label-2">{n.body}</span> : null}
                      <span className="block type-caption text-label-3">
                        {when ? relativeTime(when, now, tag) : null}
                        {!n.read_at ? <span className="sr-only">, {t("wave1.bell.unreadOne")}</span> : null}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {recentRuns.length ? (
          <div className="mt-1 pt-1 hairline-t">
            <p className="px-2.5 pt-1 pb-1 text-[11px] font-semibold text-label-3">{t("glass.shell.recentRuns")}</p>
            <ul>
              {recentRuns.map((r) => (
                <li key={r.id}>
                  <Link href={`/runs/${r.id}`} onClick={() => setOpen(false)} className="flex items-center gap-3 rounded-[10px] px-2.5 py-2 outline-none hover:bg-fill-2 focus-visible:bg-fill-2">
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] font-medium text-label-1">{t("glass.shell.runTitle", { id: r.id, term: r.term_code })}</span>
                      <span className="block text-[12px] text-label-3">{new Intl.DateTimeFormat(tag, { dateStyle: "medium", timeStyle: "short" }).format(new Date(r.created_at))}</span>
                    </span>
                    <StatusBadge {...runStatusBadge(r, t)} />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
