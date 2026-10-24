import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn, Spinner, useAuth } from "@sgjio/ui";
import { Check, ChevronDown, LogOut, UsersRound, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useMatch, useNavigate } from "react-router-dom";

import { Avatar } from "./admins/Avatar";

/**
 * The signed-in administrator's menu, top right (SCRUM-81): who you are, Administrators,
 * and Sign out. Managing administrators is occasional, so it lives here rather than taking
 * a tab beside Content and Reports, which are for everyday work. On a phone the button is
 * just your initials.
 */
export function AccountMenu() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const onAdmins = useMatch("/administrators") !== null;
  const [signingOut, setSigningOut] = useState(false);

  if (!user) return null;

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
      navigate("/sign-in", { replace: true });
    } finally {
      setSigningOut(false);
    }
  }

  return (
    // Not modal, like the rows' menus: the page keeps scrolling behind it.
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label={`Account menu for ${user.name}`}
          className={cn(
            "group flex items-center gap-2 rounded-full py-1 pr-1 pl-1 sm:pr-2.5",
            "hover:bg-surface data-[state=open]:bg-surface",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
        >
          <Avatar name={user.name} seed={user.email} size="sm" />
          <span className="hidden max-w-40 truncate text-sm font-semibold text-ink sm:inline">
            {user.name}
          </span>
          <ChevronDown
            className="hidden size-4 text-muted transition-transform group-data-[state=open]:rotate-180 sm:block"
            aria-hidden
          />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={6}
          collisionPadding={8}
          className="z-50 w-64 max-w-[calc(100vw-1rem)] rounded-md border border-line bg-white p-1 shadow-lg"
        >
          <div className="flex items-center gap-3 px-2.5 pt-2 pb-3">
            <Avatar name={user.name} seed={user.email} />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{user.name}</p>
              <p className="truncate text-xs text-muted">{user.email}</p>
            </div>
          </div>
          <DropdownMenu.Separator className="-mx-1 mb-1 h-px bg-line" />
          <MenuLink
            icon={UsersRound}
            current={onAdmins}
            onSelect={() => navigate("/administrators")}
          >
            Administrators
          </MenuLink>
          <DropdownMenu.Separator className="-mx-1 my-1 h-px bg-line" />
          <MenuLink
            icon={LogOut}
            onSelect={(event) => {
              // Stay open, showing the spinner, until signed out.
              event.preventDefault();
              void handleSignOut();
            }}
          >
            <span className="flex-1">Sign out</span>
            {signingOut && <Spinner className="size-3.5" label="Signing out" />}
          </MenuLink>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

function MenuLink({
  icon: Icon,
  current = false,
  onSelect,
  children,
}: {
  icon: LucideIcon;
  current?: boolean;
  onSelect: (event: Event) => void;
  children: ReactNode;
}) {
  return (
    <DropdownMenu.Item
      onSelect={onSelect}
      aria-current={current ? "page" : undefined}
      className={cn(
        "flex cursor-pointer items-center gap-2.5 rounded-sm px-2.5 py-2 text-sm text-ink outline-none select-none",
        // The page you are on is filled in, so it reads as selected, not just hovered.
        current
          ? "bg-brand-soft font-semibold data-highlighted:bg-brand-soft"
          : "data-highlighted:bg-surface",
      )}
    >
      <Icon className={cn("size-4 shrink-0", current ? "text-brand" : "text-muted")} aria-hidden />
      {children}
      {current && <Check className="ml-auto size-4 shrink-0 text-brand" aria-hidden />}
    </DropdownMenu.Item>
  );
}
