/** "3:45 pm" in the viewer's local time, for messages such as "Try again after 3:45 pm". */
export function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-SG", { hour: "numeric", minute: "2-digit" });
}
