// Source: https://beui.dev (lib/utils.ts) via shadcn registry @beui/shared lib — https://github.com/starc007/ui-components
// Licence: MIT, Copyright (c) 2026 Saurabh Chauhan (full text: src/components/ui/LICENSES/beui-MIT.txt)
// Modified: no
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
