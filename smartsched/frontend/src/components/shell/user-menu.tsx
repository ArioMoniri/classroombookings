"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Keyboard, LogOut, Settings } from "lucide-react";
import { useRouter } from "next/navigation";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api/endpoints";
import { useMe } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
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
  const me = useMe();
  const { t } = useI18n();
  const router = useRouter();
  const qc = useQueryClient();
  const setShortcutsOpen = useUiStore((s) => s.setShortcutsOpen);
  const user = me.data;
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
            className={cn("flex items-center gap-2 rounded-md text-left text-sm hover:bg-accent", compact ? "size-8 justify-center" : collapsed ? "size-9 justify-center" : "w-full px-2 py-1.5")}
          >
            <Avatar className="size-7">
              <AvatarFallback className="text-[11px]">{user ? initials(user.full_name, user.email) : "…"}</AvatarFallback>
            </Avatar>
            {!collapsed && !compact ? (
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{user?.full_name ?? user?.email ?? "…"}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{user?.role ?? ""}</span>
              </span>
            ) : null}
          </button>
        }
      />
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>
          <span className="block truncate">{user?.full_name ?? ""}</span>
          <span className="block truncate text-xs font-normal text-muted-foreground">{user?.email ?? ""}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
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
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
