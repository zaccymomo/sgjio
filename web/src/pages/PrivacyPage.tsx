import { Link } from "react-router-dom";

/** Public notice; update the version in this file, RegisterPage and services/identity/app/privacy.py together. */
export function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl space-y-6 px-5 py-8 text-sm leading-6 text-ink">
      <div>
        <Link to="/register" className="text-brand underline">
          Back to registration
        </Link>
        <h1 className="mt-4 text-2xl font-bold">SGJio privacy notice</h1>
        <p className="text-muted">Version 2026-10-22</p>
      </div>
      <section>
        <h2 className="text-lg font-semibold">What we collect and why</h2>
        <p>
          We collect your name, email, account type and password (stored as a secure hash) to run
          your account. If you fill in a profile, we also store your interests, languages and
          neighbourhood to personalise SGJio. We store lesson progress and quiz answers so you can
          continue learning and see your results. We use sign-in and reset records to protect your
          account.
        </p>
      </section>
      <section>
        <h2 className="text-lg font-semibold">What other users can see</h2>
        <p>
          SGJio’s buddy feature is not available yet. When it is introduced, the buddy card is
          intended to show your display name, account type, interests, languages and neighbourhood
          to other people using that feature. Your email, password, quiz answers and lesson progress
          are not intended to appear on a buddy card. We will update this notice before enabling
          buddy matching.
        </p>
      </section>
      <section>
        <h2 className="text-lg font-semibold">Deleting your account</h2>
        <p>
          Open Settings and choose Delete account. After you confirm with your password, SGJio
          removes your account, profile, lesson progress and quiz attempts, and signs you out. This
          cannot be undone. You can then register again with the same email address.
        </p>
      </section>
    </main>
  );
}
