import type { DashboardData, Period } from "@/types/dashboard";

/** The API answered, but with an error. Network failures stay plain `TypeError`s. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "error" in body && typeof body.error === "string") {
      return body.error;
    }
  } catch {
    // not JSON: fall through to the generic message
  }
  return `Request failed (${response.status})`;
}

export async function fetchDashboard(period: Period = "today"): Promise<DashboardData> {
  const response = await fetch(`/api/dashboard?period=${period}`, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }
  return (await response.json()) as DashboardData;
}
