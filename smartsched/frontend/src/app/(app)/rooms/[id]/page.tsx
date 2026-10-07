import type { Metadata } from "next";
import { RoomDetail } from "@/components/rooms/room-detail";

export const metadata: Metadata = { title: "Room" };

export default async function RoomPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <RoomDetail id={Number(id)} />;
}
