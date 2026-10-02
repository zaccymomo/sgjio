import { useCallback, useEffect, useRef } from "react";
import { useBlocker, type BlockerFunction } from "react-router-dom";

/**
 * Warn before leaving a page with unsaved changes (SCRUM-64 AC6).
 *
 * - Closing or reloading the tab, or typing another address: the browser's own prompt,
 *   through `beforeunload`. Browsers do not let a page choose its wording.
 * - Anything inside the portal, including the browser's back button: `blocker` is
 *   "blocked" and the page shows its own dialog, calling `blocker.proceed()` or
 *   `blocker.reset()`. This is why the admin portal uses a data router (App.tsx).
 *
 * Call `allowNavigation()` just before a navigation the page itself makes after saving or
 * deleting, so that one is let through even though the render that clears `dirty` has not
 * happened yet.
 */
export function useUnsavedChanges(dirty: boolean) {
  const dirtyRef = useRef(dirty);
  const allowNext = useRef(false);

  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);

  const shouldBlock = useCallback<BlockerFunction>(({ currentLocation, nextLocation }) => {
    if (allowNext.current) {
      allowNext.current = false;
      return false;
    }
    const moving =
      currentLocation.pathname !== nextLocation.pathname ||
      currentLocation.search !== nextLocation.search;
    return dirtyRef.current && moving;
  }, []);
  const blocker = useBlocker(shouldBlock);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Older browsers show the prompt only when this is set.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const allowNavigation = useCallback(() => {
    allowNext.current = true;
  }, []);

  return { blocker, allowNavigation };
}
