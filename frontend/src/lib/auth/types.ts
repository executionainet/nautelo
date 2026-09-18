export type PermissionKey =
  | "browse_public_content"
  | "submit_inquiry"
  | "reveal_contact_after_inquiry"
  | "reveal_any_contact"
  | "create_private_listing"
  | "create_broker_listing"
  | "create_listing_on_behalf"
  | "enable_listing_finance_flag"
  | "approve_listings_and_revisions"
  | "configure_broker_auto_approval"
  | "configure_products_and_settings"
  | "manage_taxonomy";

export type PermissionMap = Record<PermissionKey, boolean>;

export type UserRole =
  | "BUYER"
  | "PRIVATE_SELLER"
  | "BROKER"
  | "SERVICE_PROVIDER"
  | "STAFF";

// The session/user-preference locale (uppercase, as the auth API returns it).
// A second, unrelated locale union lives at lib/api/directory.ts's Locale
// ("en" | "it" | "es", lowercase) — that one is the single source of truth
// for the directory API's ?locale= contract and is intentionally not merged
// with this one: they serve different APIs that happen to share a value set.
// resolveLocale() in lib/i18n/directory.ts is case-insensitive and accepts
// either casing, so it doubles as the conversion from LocaleCode to Locale
// until something needs more than that.
export type LocaleCode = "EN" | "IT" | "ES";

export type EntityStatus = "DRAFT" | "PENDING" | "ACTIVE" | "SUSPENDED";

export type BrokerMembershipRole = "ADMIN" | "MANAGER" | "AGENT" | "VIEWER";

export interface SessionUser {
  id: string;
  email: string;
  full_name: string;
  primary_role: UserRole;
  locale: LocaleCode;
  email_verified: boolean;
  is_active: boolean;
}

export interface BrokerMembershipSummary {
  broker_id: string;
  broker_name: string;
  broker_slug: string;
  broker_status: EntityStatus;
  /** Spec §11.1: visible to broker members, changeable only by staff admin. */
  broker_auto_approve_listings: boolean;
  role: BrokerMembershipRole;
  can_edit_listings: boolean;
  can_manage_team: boolean;
  can_read_messages: boolean;
}

export interface ProfessionalProfileSummary {
  id: string;
  slug: string;
  display_name: string;
  status: EntityStatus;
}

export interface SessionPayload {
  authenticated: boolean;
  user: SessionUser | null;
  locale: LocaleCode;
  permissions: PermissionMap;
  broker_memberships: BrokerMembershipSummary[];
  professional_profile: ProfessionalProfileSummary | null;
  staff: { is_staff_moderator: boolean; is_staff_admin: boolean };
}

export interface LoginResponse {
  access: string;
  user: SessionUser;
}
