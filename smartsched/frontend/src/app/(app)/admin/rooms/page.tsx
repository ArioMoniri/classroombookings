import type { Metadata } from "next";
import { RoomsAdmin } from "@/components/admin/rooms-admin";

export const metadata: Metadata = { title: "Rooms" };

export default function Page() {
  return <RoomsAdmin />;
}
