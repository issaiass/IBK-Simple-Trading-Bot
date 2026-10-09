import { Skeleton } from "@/components/ui/skeleton";

const BLOCK = "rounded-xl bg-white/[0.06]";

/**
 * Placeholder with the same grid, and roughly the same card heights, as the loaded dashboard,
 * so the page does not jump when the data arrives.
 */
export function DashboardSkeleton() {
  return (
    <div
      data-testid="dashboard-skeleton"
      role="status"
      aria-busy="true"
      aria-label="Loading dashboard"
      className="flex flex-col gap-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <Skeleton className="h-10 w-48 bg-white/[0.06]" />
        <Skeleton className="h-11 w-full rounded-full bg-white/[0.06] sm:w-[52rem] sm:max-w-full" />
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Skeleton className={`h-[25.5rem] ${BLOCK}`} />
        <Skeleton className={`h-[25.5rem] ${BLOCK} xl:col-span-2`} />
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Skeleton className={`h-[19.5rem] ${BLOCK}`} />
        <Skeleton className={`h-[19.5rem] ${BLOCK} xl:col-span-2`} />
      </div>
      <Skeleton className={`h-[11.75rem] ${BLOCK}`} />
      <Skeleton className={`h-[25rem] ${BLOCK}`} />
    </div>
  );
}
