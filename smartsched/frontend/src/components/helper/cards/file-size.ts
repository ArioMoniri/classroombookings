/** "1,2 MB" / "640 KB" in the reader's language (helper file chips and the handed-over file row). */
export function formatSize(bytes: number, locale: string): string {
  const tag = locale === "tr" ? "tr-TR" : "en-GB";
  if (bytes >= 1024 * 1024) return `${new Intl.NumberFormat(tag, { maximumFractionDigits: 1 }).format(bytes / (1024 * 1024))} MB`;
  return `${new Intl.NumberFormat(tag).format(Math.max(1, Math.ceil(bytes / 1024)))} KB`;
}
