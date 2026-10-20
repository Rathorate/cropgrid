import AccountClient from "./account-client";
import "./account.css";
import type { Metadata } from "next";

export const metadata: Metadata = { referrer: "no-referrer", robots: { index: false, follow: false } };

export const dynamic = "force-dynamic";

export default function AccountPage() {
  return <AccountClient />;
}
