import type { ReactNode } from "react";

import { Card, CardAction, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SectionCardProps {
  title: string;
  /** Anchor id, so the sidebar can link to the section. */
  id?: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** The glass card every dashboard section sits in, with a real heading for accessibility. */
export function SectionCard({ title, id, description, action, className, children }: SectionCardProps) {
  return (
    <section id={id} className="scroll-mt-20 lg:scroll-mt-6">
      <Card className={cn("h-full bg-white/[0.04] ring-white/10 backdrop-blur-xl", className)}>
        <CardHeader>
          <h2 className="text-sm font-medium tracking-wide text-zinc-300">{title}</h2>
          {description ? <CardDescription>{description}</CardDescription> : null}
          {action ? <CardAction>{action}</CardAction> : null}
        </CardHeader>
        <CardContent className="flex-1">{children}</CardContent>
      </Card>
    </section>
  );
}
