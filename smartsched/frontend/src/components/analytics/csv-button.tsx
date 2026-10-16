"use client";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";

/** a CSV download (same-origin proxy; the backend names the file in Content-Disposition, UTF-8 with a BOM) */
export function CsvButton({ href, label, testId }: { href: string; label: string; testId?: string }) {
  return (
    <Button variant="outline" size="sm" nativeButton={false} render={<a href={href} download />} data-testid={testId}>
      <Download aria-hidden />
      {label}
    </Button>
  );
}
