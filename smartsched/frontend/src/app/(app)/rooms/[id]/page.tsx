import { Suspense } from "react";
import { RoomDetail } from "@/components/rooms/room-detail";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.room");

export default async function RoomPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <RoomDetail id={Number(id)} />
    </Suspense>
  );
}
