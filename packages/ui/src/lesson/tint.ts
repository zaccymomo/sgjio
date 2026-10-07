/** A soft background made from an image's main colour, for the panel it sits on. */
export function tint(color: string | null | undefined, amount = 16): string {
  return color ? `color-mix(in srgb, ${color} ${amount}%, white)` : "var(--color-surface)";
}
