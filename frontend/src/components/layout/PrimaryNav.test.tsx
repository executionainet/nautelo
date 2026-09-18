import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PrimaryNav from "@/components/layout/PrimaryNav";
import type { PermissionMap, SessionPayload } from "@/lib/auth/types";

const { useSessionMock } = vi.hoisted(() => ({ useSessionMock: vi.fn() }));

vi.mock("@/lib/auth/session", () => ({
  useSession: () => useSessionMock(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

const ALL_FALSE: PermissionMap = {
  browse_public_content: true,
  submit_inquiry: false,
  reveal_contact_after_inquiry: false,
  reveal_any_contact: false,
  create_private_listing: false,
  create_broker_listing: false,
  create_listing_on_behalf: false,
  enable_listing_finance_flag: false,
  approve_listings_and_revisions: false,
  configure_broker_auto_approval: false,
  configure_products_and_settings: false,
  manage_taxonomy: false,
};

function mockSession(
  permissions: PermissionMap,
  authenticated = true,
  brokerMemberships: SessionPayload["broker_memberships"] = [],
  localeCode: SessionPayload["locale"] = "EN",
) {
  const value: SessionPayload = {
    authenticated,
    user: authenticated
      ? {
          id: "1",
          email: "nav@example.com",
          full_name: "Nav User",
          primary_role: "BUYER",
          locale: localeCode,
          email_verified: true,
          is_active: true,
        }
      : null,
    locale: localeCode,
    permissions,
    broker_memberships: brokerMemberships,
    professional_profile: null,
    staff: { is_staff_moderator: false, is_staff_admin: false },
  };
  useSessionMock.mockReturnValue({
    session: value,
    loading: false,
    error: null,
    can: (key: keyof PermissionMap) => permissions[key] === true,
    login: vi.fn(),
    logout: vi.fn(),
    reload: vi.fn(),
  });
}

const BROKER_MEMBERSHIP = {
  broker_id: "b-1",
  broker_name: "Phase19 Alpha Brokers",
  broker_slug: "phase19-alpha-brokers",
  broker_status: "ACTIVE" as const,
  broker_auto_approve_listings: false,
  role: "AGENT" as const,
  can_edit_listings: false,
  can_manage_team: false,
  can_read_messages: false,
};

afterEach(() => useSessionMock.mockReset());

describe("PrimaryNav", () => {
  it("shows only public links to a guest", () => {
    mockSession(ALL_FALSE, false);
    render(<PrimaryNav />);
    expect(screen.getByRole("link", { name: "Boats" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Moderation" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
  });

  it("links to no page that does not exist yet", () => {
    // Every permission granted: the nav must STILL not offer /sell/ or /fleet/,
    // because Phase 11/16 have not built those pages. See the note in Step 6.
    mockSession(
      Object.fromEntries(
        Object.keys(ALL_FALSE).map((key) => [key, true]),
      ) as PermissionMap,
    );
    render(<PrimaryNav />);
    expect(screen.queryByRole("link", { name: "Sell" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Fleet" })).not.toBeInTheDocument();
  });

  it("shows the moderation link only to approvers", () => {
    mockSession({ ...ALL_FALSE, approve_listings_and_revisions: true });
    render(<PrimaryNav />);
    expect(screen.getByRole("link", { name: "Moderation" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
  });

  it("shows the settings link only to staff admins", () => {
    mockSession({ ...ALL_FALSE, configure_products_and_settings: true });
    render(<PrimaryNav />);
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("shows the broker dashboard link only to a member of a broker organization", () => {
    mockSession(ALL_FALSE);
    render(<PrimaryNav />);
    expect(
      screen.queryByRole("link", { name: "Broker dashboard" }),
    ).not.toBeInTheDocument();
  });

  it("shows the broker dashboard link to a broker member with no permissions at all", () => {
    // Membership, not a permission: spec 5's capability table has no "broker
    // dashboard" row, and an AGENT with every flag false is still a member.
    mockSession(ALL_FALSE, true, [BROKER_MEMBERSHIP]);
    render(<PrimaryNav />);
    expect(
      screen.getByRole("link", { name: "Broker dashboard" }),
    ).toHaveAttribute("href", "/dashboard/broker/");
  });

  it.each([
    ["EN", "Broker dashboard"],
    ["IT", "Pannello broker"],
    ["ES", "Panel del bróker"],
  ])("renders the broker dashboard label in %s", (localeCode, label) => {
    // Spec 37: this phase's new nav text is a dictionary key, not a literal.
    // The six entries merged in Phase 3 remain hard-coded English — see this
    // task's note and Known Limitation 18.
    mockSession(
      ALL_FALSE,
      true,
      [BROKER_MEMBERSHIP],
      localeCode as SessionPayload["locale"],
    );
    render(<PrimaryNav />);
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  });

  it("renders the services/professionals label from the locale dictionary", () => {
    mockSession(ALL_FALSE, false, [], "IT");
    render(<PrimaryNav />);
    expect(
      screen.getByRole("link", { name: "Servizi / Professionisti" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Services / Professionals" }),
    ).not.toBeInTheDocument();
  });
});
