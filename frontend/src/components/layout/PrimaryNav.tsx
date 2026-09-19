"use client";

import Link from "next/link";

import NotificationBell from "@/components/layout/NotificationBell";
import { useSession } from "@/lib/auth/session";
import type { PermissionKey } from "@/lib/auth/types";
import { tConversations } from "@/lib/i18n/conversations";
import { resolveLocale, t } from "@/lib/i18n/directory";

interface NavLink {
  href: string;
  /** Hard-coded English, as the six entries merged in Phase 3 all are. */
  label?: string;
  /** A key in CONVERSATION_MESSAGES, resolved per the viewer's locale.
   *
   * New UI text must be an EN/IT/ES key (spec 37), so this phase's entry uses
   * this rather than `label`. The existing entries are NOT converted here:
   * retro-fitting six labels into a dictionary is a change to Phase 3's
   * component with its own copy decisions (what is "Boats" in Italian on a
   * marketplace that has not shipped a boats page?), and this plan's charter is
   * spec 28. Recorded as Known Limitation 18, beside the related observation
   * that the same six links point at pages that do not exist. */
  messageKey?: string;
  /** Spec 37: a key in the directory message dictionary (DIRECTORY_MESSAGES),
   * resolved per the viewer's locale. Used by the Services entry, whose copy
   * already ships EN/IT/ES there. */
  directoryKey?: string;
  permission?: PermissionKey;
  /** Some entries are gated on membership rather than on a spec 5 capability:
   * spec 5's table has no "broker dashboard" row, and an AGENT with every flag
   * false is still a member of the organization. */
  requiresBrokerMembership?: boolean;
}

// Public routes come from spec 4.1; the gated ones from spec 5's capability table.
const LINKS: NavLink[] = [
  { href: "/boats/", label: "Boats" },
  { href: "/brokers/", label: "Brokers" },
  {
    href: "/services/professionals/",
    label: "Services / Professionals",
    directoryKey: "nav.services_professionals",
  },
  { href: "/financing/", label: "Financing" },
  // NOTE: /sell/ (create_private_listing) and /fleet/ (create_broker_listing)
  // are deliberately ABSENT until Phase 11/16 build those pages. See the note below.
  {
    href: "/dashboard/broker/",
    // Spec 37: new UI text is a key, never a literal. `broker.dashboard.title`
    // already carries EN/IT/ES and is the same string the broker home page's
    // own nav landmark uses, so the two can never drift.
    messageKey: "broker.dashboard.title",
    requiresBrokerMembership: true,
  },
  {
    href: "/dashboard/staff/",
    label: "Moderation",
    permission: "approve_listings_and_revisions",
  },
  {
    href: "/settings/",
    label: "Settings",
    permission: "configure_products_and_settings",
  },
];

export default function PrimaryNav() {
  const { session, loading, can, logout } = useSession();
  const authenticated = session?.authenticated === true;

  const isBrokerMember = (session?.broker_memberships?.length ?? 0) > 0;
  // PrimaryNav is already a client component holding the session, so the
  // viewer's own locale is available here. resolveLocale is the shared helper
  // (lib/i18n/directory.ts:15) — the session's LocaleCode is "EN"/"IT"/"ES"
  // and the dictionary's Locale is "en"/"it"/"es", and that lowercasing lives
  // in exactly one place.
  const locale = resolveLocale(session?.user?.locale);

  const visible = LINKS.filter((link) => {
    if (link.permission !== undefined && !can(link.permission)) return false;
    if (link.requiresBrokerMembership && !isBrokerMember) return false;
    return true;
  });

  return (
    <nav
      aria-label="Primary"
      className="flex flex-wrap items-center gap-space-md border-b border-outline-variant bg-surface px-margin-mobile py-space-sm md:px-margin"
    >
      <Link href="/" className="font-title-lg text-title-lg text-primary">
        NAUTA
      </Link>
      <ul className="flex flex-wrap items-center gap-space-md">
        {visible.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="font-body-md text-on-surface-variant hover:text-primary"
            >
              {link.messageKey
                ? tConversations(locale, link.messageKey)
                : link.directoryKey
                  ? t(locale, link.directoryKey)
                  : link.label}
            </Link>
          </li>
        ))}
      </ul>
      <div className="ml-auto flex items-center gap-space-sm">
        {loading ? null : authenticated ? (
          <>
            <NotificationBell locale={locale} />
            <Link
              href="/account/"
              className="font-body-sm text-on-surface-variant hover:text-primary"
            >
              {session?.user?.full_name || session?.user?.email}
            </Link>
            <button
              type="button"
              onClick={() => void logout()}
              className="font-label-md text-label-md text-primary"
            >
              Sign out
            </button>
          </>
        ) : (
          <Link
            href="/login"
            className="font-label-md text-label-md text-primary"
          >
            Sign in
          </Link>
        )}
      </div>
    </nav>
  );
}
