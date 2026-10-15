import { ProfileView } from "@/components/admin/profile-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.profile");

export default function ProfilePage() {
  return <ProfileView />;
}
