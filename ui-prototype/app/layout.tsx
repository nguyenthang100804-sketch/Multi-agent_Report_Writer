import type { Metadata } from "next";
import { Suspense } from "react";
import { Providers } from "./providers";
import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "Report Writer · Báo cáo tài chính",
  description: "Lập, kiểm chứng và trao đổi về báo cáo tài chính",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi">
      <body className="min-h-full flex flex-col"><Suspense fallback={null}><Providers>{children}</Providers></Suspense></body>
    </html>
  );
}
