import { ShopShell } from "@/components/shop/ShopShell";

export default function ShopLayout({ children }: { children: React.ReactNode }) {
  return <ShopShell>{children}</ShopShell>;
}
