import { Alert } from "./Alert";
import { Button } from "./Button";

/** "Couldn't load, try again" block, for the retry criteria in SCRUM-43, 58 and 66. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-3 px-4 py-16 text-center">
      <Alert tone="error" className="w-full text-left">
        {message}
      </Alert>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
