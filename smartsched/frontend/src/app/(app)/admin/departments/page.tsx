import type { Metadata } from "next";
import { DepartmentsAdmin } from "@/components/admin/departments-admin";

export const metadata: Metadata = { title: "Departments" };

export default function Page() {
  return <DepartmentsAdmin />;
}
