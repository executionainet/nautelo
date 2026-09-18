// Unauthenticated, server-side reads of the combined-directory API.
// Deliberately separate from src/lib/api/client.ts, which is the browser
// client (access token, credentials, refresh retry) and throws on every
// non-2xx. Here a 404 is a meaningful answer, not an error.
import { forwardedClientIp } from "./internal-headers";

export const DIRECTORY_API_BASE_URL =
  // 127.0.0.1, not localhost: this runs in Node during SSR and this machine
  // resolves localhost to IPv6 ::1 (Phase 0/1 retrospective).
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8020";

// Server-only: never NEXT_PUBLIC_-prefixed, so Next.js never inlines this
// into a client bundle. Proves a services_directory request genuinely came
// from this project's own Next.js server - see
// common.throttling.HashedIPScopedRateThrottle.
const INTERNAL_SERVICE_SECRET = process.env.INTERNAL_SERVICE_SECRET ?? "";

// The single source of truth for the locale union in the whole frontend: it is
// the API contract's ?locale= parameter. lib/i18n/directory.ts imports and
// re-exports this type rather than declaring a second, drifting copy.
//
// A second, unrelated locale union lives at lib/auth/types.ts's LocaleCode
// ("EN" | "IT" | "ES", uppercase) — that one is the session/user-preference
// value from the auth API and is intentionally not merged with this one (see
// the note there). resolveLocale() in lib/i18n/directory.ts is case-insensitive
// and accepts either casing, so it doubles as the conversion from LocaleCode to
// Locale until something needs more than that.
export type Locale = "en" | "it" | "es";

export interface ServiceCategory {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon_key: string;
  display_order: number;
  has_seo_page: boolean;
  url: string | null;
}

export interface ServiceCategoryDetail extends ServiceCategory {
  seo_title: string;
  seo_description: string;
}

export interface CategoryRef {
  slug: string;
  name: string;
}

export interface ProfessionalCard {
  id: string;
  slug: string;
  display_name: string;
  short_description: string;
  city: string;
  region: string;
  country_code: string;
  service_area: string[];
  categories: CategoryRef[];
  active_service_count: number;
  url: string;
}

export interface ProfessionalService {
  id: string;
  title: string;
  description: string;
  service_area: string[];
  category: CategoryRef;
}

export interface RelatedProfessional {
  slug: string;
  display_name: string;
  city: string;
  url: string;
}

export interface ProfessionalDetail extends ProfessionalCard {
  description: string;
  services: ProfessionalService[];
  related: RelatedProfessional[];
}

/** The one "City, Region" display string for a professional.
 *
 * Either half may legitimately be blank (both are blank-allowed on Phase 3's
 * `ProfessionalProfile`), so the empty parts are dropped rather than leaving a
 * dangling comma. The result card and the detail page's status line both use
 * this: they showed the same expression twice and must not drift apart.
 */
export function formatProfessionalLocation(professional: {
  city: string;
  region: string;
}): string {
  return [professional.city, professional.region].filter(Boolean).join(", ");
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export async function directoryFetch<T>(path: string): Promise<T | null> {
  const clientIp = await forwardedClientIp();
  const response = await fetch(`${DIRECTORY_API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      "X-Internal-Service-Secret": INTERNAL_SERVICE_SECRET,
      ...(clientIp ? { "X-Internal-Client-IP": clientIp } : {}),
    },
    // Directory content is staff-edited and provider-edited; never serve a
    // stale grid from the build cache.
    cache: "no-store",
  });

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Directory API ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, value);
    }
  }
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

// null means "the API answered 404", which for a collection endpoint can only
// mean the combined_services_professionals rollout flag is off (Task 6's
// CombinedDirectoryEnabled). It is NOT the same as an empty list, and the two
// must not be collapsed here: an empty list is a real directory with nothing
// in it and gets the spec 31 empty-state copy, while null means the feature
// does not exist publicly and the page must notFound(). Callers decide.
export async function fetchServiceCategories(
  locale: Locale,
): Promise<ServiceCategory[] | null> {
  return directoryFetch<ServiceCategory[]>(
    `/api/v1/service-categories/${query({ locale })}`,
  );
}

export async function fetchServiceCategory(
  slug: string,
  locale: Locale,
): Promise<ServiceCategoryDetail | null> {
  return directoryFetch<ServiceCategoryDetail>(
    `/api/v1/service-categories/${encodeURIComponent(slug)}/${query({ locale })}`,
  );
}

export interface ProfessionalSearch {
  q?: string;
  category?: string;
  location?: string;
  sort?: string;
  page?: string;
  page_size?: string;
}

// Same contract as fetchServiceCategories: null = flag off, an empty `results`
// array = no matching professionals.
export async function fetchProfessionals(
  search: ProfessionalSearch,
  locale: Locale,
): Promise<Paginated<ProfessionalCard> | null> {
  return directoryFetch<Paginated<ProfessionalCard>>(
    `/api/v1/professionals/${query({ ...search, locale })}`,
  );
}

/** The shape a caller substitutes when it has already decided a 404 is not fatal. */
export const EMPTY_PROFESSIONAL_PAGE: Paginated<ProfessionalCard> = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

export async function fetchProfessional(
  slug: string,
  locale: Locale,
): Promise<ProfessionalDetail | null> {
  return directoryFetch<ProfessionalDetail>(
    `/api/v1/professionals/${encodeURIComponent(slug)}/${query({ locale })}`,
  );
}

export async function resolveLegacyProfessional(legacyId: string): Promise<string | null> {
  const resolved = await directoryFetch<{ url: string }>(
    `/api/v1/legacy/professional-redirect/${query({ id: legacyId })}`,
  );
  return resolved?.url ?? null;
}
