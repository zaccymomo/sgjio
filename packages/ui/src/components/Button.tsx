import type { ComponentProps } from "react";

import { cn } from "../lib/cn";
import { Spinner } from "./Spinner";

type Variant = "primary" | "accent" | "secondary" | "ghost";
type Size = "md" | "sm";

const variants: Record<Variant, string> = {
  // Dark button, as on the Figma lesson card's action
  primary: "bg-ink text-white hover:bg-ink/90",
  // Brand red, for the one action you most want people to take
  accent: "bg-brand text-white hover:bg-brand/90",
  secondary: "border border-line bg-white text-ink hover:bg-surface",
  ghost: "text-muted hover:bg-surface hover:text-ink",
};

const sizes: Record<Size, string> = {
  md: "h-11 px-4 text-sm",
  sm: "h-8 px-3 text-xs",
};

export type ButtonProps = ComponentProps<"button"> & {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  /** Shows a spinner and disables the button, e.g. while a form submits. */
  loading?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  fullWidth,
  loading,
  disabled,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-sm font-semibold transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        "disabled:cursor-not-allowed disabled:opacity-60",
        variants[variant],
        sizes[size],
        fullWidth && "w-full",
        className,
      )}
      {...props}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}
