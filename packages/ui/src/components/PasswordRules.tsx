import { Check, Circle, X } from "lucide-react";

import { cn } from "../lib/cn";
import { PASSWORD_RULES } from "../lib/validation";

/**
 * The password rules as a live checklist under a new-password field. Each rule ticks as
 * soon as it is met; after a failed submit (`showUnmet`), the ones still missing turn red.
 */
export function PasswordRules({
  password,
  showUnmet = false,
  id,
}: {
  password: string;
  showUnmet?: boolean;
  /** So the password field can point at the list with aria-describedby. */
  id?: string;
}) {
  return (
    <ul id={id} className="flex flex-wrap gap-x-4 gap-y-1" aria-label="Password rules">
      {PASSWORD_RULES.map((rule) => {
        const met = rule.met(password);
        const failed = !met && showUnmet;
        const Icon = met ? Check : failed ? X : Circle;
        return (
          <li
            key={rule.label}
            className={cn(
              "flex items-center gap-1.5 text-xs transition-colors",
              met ? "text-success" : failed ? "text-danger" : "text-muted",
            )}
          >
            <Icon className={cn("shrink-0", met || failed ? "size-3.5" : "size-2.5")} aria-hidden />
            {rule.label}
            <span className="sr-only">{met ? " (done)" : " (not yet)"}</span>
          </li>
        );
      })}
    </ul>
  );
}
