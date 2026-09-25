import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

import { TextField, type TextFieldProps } from "./TextField";

/**
 * Password input, hidden by default with a button to show it
 * (SCRUM-61 AC7, SCRUM-62 AC4, SCRUM-68 AC4).
 */
export function PasswordField(props: Omit<TextFieldProps, "type" | "endAdornment">) {
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;

  return (
    <TextField
      {...props}
      type={visible ? "text" : "password"}
      endAdornment={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="flex size-9 items-center justify-center rounded-sm text-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
        >
          <Icon className="size-4" aria-hidden />
        </button>
      }
    />
  );
}
