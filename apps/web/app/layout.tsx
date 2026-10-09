import type { Metadata } from "next";
import "./styles.css";
import "./ai.css";

export const metadata: Metadata = {
  title: "CropGrid — Trade better, grow together",
  description: "A clearer marketplace for West African agricultural trade.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
