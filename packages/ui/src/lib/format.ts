/** "3:45 pm" in the viewer's local time, for messages such as "Try again after 3:45 pm". */
export function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-SG", { hour: "numeric", minute: "2-digit" });
}

/** "30 September 2026", for dates such as when an account was created. */
export function formatDate(date: Date): string {
  return date.toLocaleDateString("en-SG", { day: "numeric", month: "long", year: "numeric" });
}
