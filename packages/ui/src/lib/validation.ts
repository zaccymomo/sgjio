/**
 * Form rules the register and reset-password pages check before calling the API, so the
 * reader is told what is wrong without waiting for a round trip.
 *
 * The API is still the authority: every rule here is also enforced in
 * `api/app/security.py` and `api/app/schemas.py`. Keep the two in step — if they ever
 * disagree, the server's answer is the one shown (see how ApiError.field is used).
 */

/** Mirrors PASSWORD_MIN_LENGTH in api/app/security.py. */
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

/** Shown under the password field, so the rules are known before typing. */
export const PASSWORD_HINT = `At least ${PASSWORD_MIN_LENGTH} characters, including a letter and a number.`;

/**
 * The rules as a checklist, for showing which are met while typing. Same rules as
 * passwordRuleFailures() below; the length ceiling is left out because almost nobody
 * reaches it, and passwordRuleFailures() still reports it.
 */
export const PASSWORD_RULES: Array<{ label: string; met: (password: string) => boolean }> = [
  {
    label: `At least ${PASSWORD_MIN_LENGTH} characters`,
    met: (password) => password.length >= PASSWORD_MIN_LENGTH,
  },
  { label: "A letter", met: (password) => /[A-Za-z]/.test(password) },
  { label: "A number", met: (password) => /\d/.test(password) },
];

/**
 * One message per password rule the password breaks; empty means it is acceptable.
 * Mirrors password_rule_failures() in api/app/security.py (SCRUM-61 AC4).
 */
export function passwordRuleFailures(password: string): string[] {
  const failures: string[] = [];
  if (password.length < PASSWORD_MIN_LENGTH) {
    failures.push(`Use at least ${PASSWORD_MIN_LENGTH} characters.`);
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    failures.push(`Use no more than ${PASSWORD_MAX_LENGTH} characters.`);
  }
  if (!/[A-Za-z]/.test(password)) failures.push("Include at least one letter.");
  if (!/\d/.test(password)) failures.push("Include at least one number.");
  return failures;
}

/**
 * A deliberately loose check for an obviously malformed address (SCRUM-61 AC3): one "@"
 * with something either side and a dot in the domain. Addresses that pass here are still
 * checked properly by the API, which uses a full email parser.
 */
export function looksLikeEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}
