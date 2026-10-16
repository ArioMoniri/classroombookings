import { redirect } from "next/navigation";

/** /exams (the breadcrumb parent of Gözetmen ataması) opens Gözetmen ataması. */
export default function ExamsIndex() {
  redirect("/exams/invigilation");
}
