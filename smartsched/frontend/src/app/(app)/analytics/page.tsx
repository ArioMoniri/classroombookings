import { redirect } from "next/navigation";

/** /analytics (the breadcrumb parent of the heatmap) opens the heatmap. */
export default function AnalyticsIndex() {
  redirect("/analytics/heatmap");
}
