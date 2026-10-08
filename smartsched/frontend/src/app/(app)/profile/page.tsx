import type { Metadata } from "next";
import { ProfileView } from "@/components/admin/profile-view";

export const metadata: Metadata = { title: "Profile" };

export default function ProfilePage() {
  return <ProfileView />;
}
