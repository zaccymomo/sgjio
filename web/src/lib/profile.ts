import { ApiError, apiFetch } from "@sgjio/ui";
import { useCallback, useEffect, useState } from "react";

/** The signed-in user's matching preferences (SCRUM-14). Empty until profile setup. */
export type Profile = {
  interests: string[];
  languages: string[];
  neighbourhood: string | null;
};

/** The choices the form offers, owned by services/identity/app/profile_options.py. */
export type ProfileOptions = {
  interests: string[];
  languages: string[];
  neighbourhoods: string[];
};

type State =
  | { status: "loading" }
  | { status: "ready"; profile: Profile; options: ProfileOptions }
  | { status: "error"; message: string };

export function isProfileComplete(profile: Profile): boolean {
  return profile.interests.length > 0 && profile.languages.length > 0 && !!profile.neighbourhood;
}

export function saveProfile(profile: Profile): Promise<Profile> {
  return apiFetch<Profile>("/api/profile", { method: "PUT", body: profile });
}

/** Loads the profile and the choices together, with a `reload` for the error state's retry. */
export function useProfile() {
  const [state, setState] = useState<State>({ status: "loading" });

  const load = useCallback(async (signal?: AbortSignal): Promise<State | null> => {
    try {
      const [profile, options] = await Promise.all([
        apiFetch<Profile>("/api/profile", { signal }),
        apiFetch<ProfileOptions>("/api/profile/options", { signal }),
      ]);
      return { status: "ready", profile, options };
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return null;
      return {
        status: "error",
        message:
          error instanceof ApiError
            ? error.message
            : "We couldn't load your profile. Please try again.",
      };
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal).then((next) => {
      if (next) setState(next);
    });
    return () => controller.abort();
  }, [load]);

  const reload = useCallback(async () => {
    setState({ status: "loading" });
    const next = await load();
    if (next) setState(next);
  }, [load]);

  return { state, reload };
}
