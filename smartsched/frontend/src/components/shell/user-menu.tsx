"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Keyboard, LogOut, Settings, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useAppVersion } from "@/lib/api/crbs";
import { api } from "@/lib/api/endpoints";
import { useMeFull } from "@/lib/api/shell-extra";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

export function initials(name: string | null | undefined, email: string): string {
  const src = name?.trim() || email;
  return src
    .split(/[\s@._]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toLocaleUpperCase("tr-TR") ?? "")
    .join("");
}

export function UserMenu({ collapsed, compact }: { collapsed?: boolean; compact?: boolean }) {
  const me = useMeFull();
  const { t } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const setShortcutsOpen = useUiStore((s) => s.setShortcutsOpen);
  const hydrated = useHydrated();
  const user = hydrated ? me.data : undefined;
  // CRBS layout footer: the running version (backend GET /health), so a bug report can name it
  const version = useAppVersion();
  const logout = async () => {
    await api.auth.logout();
    qc.clear();
    router.push("/login");
    router.refresh();
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            aria-label={t("nav.account")}
            data-testid="user-menu"
            className={cn("flex items-center gap-2 rounded-xl text-left text-sm outline-none transition-colors duration-(--dur-fast) hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)", compact ? "size-9 justify-center rounded-full" : collapsed ? "size-9 justify-center" : "w-full px-2 py-1.5")}
          >
            <Avatar className="size-7">
              <AvatarFallback className="text-[11px]">{user ? initials(user.full_name, user.email ?? user.username ?? "?") : "…"}</AvatarFallback>
            </Avatar>
            {!collapsed && !compact ? (
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium text-label-1">{user?.full_name ?? user?.email ?? user?.username ?? "…"}</span>
                <span className="block truncate text-[11px] text-label-3">{user ? t(`glass.role.${user.role}` as MessageKey) : ""}</span>
              </span>
            ) : null}
          </button>
        }
      />
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>
          <span className="block truncate">{user?.full_name ?? ""}</span>
          <span className="block truncate text-xs font-normal text-label-3">{user?.email ?? ""}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {/* CRBS header "Display name" -> profile/edit: names, e-mail, language, password (UI gap audit #1) */}
        <DropdownMenuItem onClick={() => router.push("/profile")} data-testid="user-menu-profile">
          <UserRound /> {t("crbs.nav.profile")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => router.push("/settings")}>
          <Settings /> {t("nav.settings")}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setShortcutsOpen(true)}>
          <Keyboard /> {t("shortcuts.title")}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={() => void logout()} data-testid="logout">
          <LogOut /> {t("nav.logout")}
        </DropdownMenuItem>
        {version.data ? (
          <p className="px-2 pt-1.5 pb-1 type-caption text-label-3 tabular-nums" data-testid="app-version">
            {t("admingaps.shell.version", { version: version.data })}
          </p>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
