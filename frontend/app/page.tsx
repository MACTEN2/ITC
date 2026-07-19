import { redirect } from "next/navigation";

// The root route has no content of its own -- it just hands off to the
// login gateway, which itself forwards already-authenticated visitors on to
// /dashboard (see app/login/page.tsx).
export default function RootPage() {
  redirect("/login");
}
