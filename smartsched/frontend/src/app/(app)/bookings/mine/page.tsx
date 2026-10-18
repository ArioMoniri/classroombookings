import { redirect } from "next/navigation";
import { myBookingsHref } from "@/components/bookings/deep-link";

/**
 * RF-11: the backend's e-mails and notices link "My bookings" as `/bookings/mine?…` (request, series, booking);
 * this frontend's page is /my-bookings, so the link lands there with the same deep link.
 */
export default async function BookingsMineRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  redirect(myBookingsHref(await searchParams));
}
