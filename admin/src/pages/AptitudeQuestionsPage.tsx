import { Alert, ApiError, Button, ErrorState, Spinner, TextField } from "@sgjio/ui";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { aptitudeApi, type AptitudeBank, type AptitudeQuestion } from "../lib/aptitude";
import { topicApi, type Topic } from "../lib/content";

type Form = {
  topic_id: string;
  level: number;
  prompt: string;
  options: string[];
  correct: number;
  is_active: boolean;
};
const empty = (): Form => ({
  topic_id: "",
  level: 1,
  prompt: "",
  options: ["", "", ""],
  correct: 0,
  is_active: true,
});

export function AptitudeQuestionsPage() {
  const [bank, setBank] = useState<AptitudeBank | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AptitudeQuestion | "new" | null>(null);
  const [form, setForm] = useState<Form>(empty);
  const [saving, setSaving] = useState(false);

  const load = () =>
    Promise.all([aptitudeApi.bank(), topicApi.list()])
      .then(([next, allTopics]) => {
        setBank(next);
        setTopics(allTopics.filter((topic) => !topic.archived_at));
        setError(null);
      })
      .catch((cause: unknown) =>
        setError(cause instanceof ApiError ? cause.message : "We couldn't load the question bank."),
      );
  useEffect(() => {
    void load();
  }, []);

  const open = (question?: AptitudeQuestion) => {
    setEditing(question ?? "new");
    setForm(
      question
        ? {
            topic_id: question.topic_id,
            level: question.level,
            prompt: question.prompt,
            options: question.options.map((option) => option.text),
            correct: question.options.findIndex(
              (option) => option.id === question.correct_option_id,
            ),
            is_active: question.is_active,
          }
        : empty(),
    );
    setError(null);
  };
  const save = async () => {
    if (!form.topic_id || !form.prompt.trim() || form.options.some((option) => !option.trim())) {
      setError("Choose a topic and complete the question and every answer option.");
      return;
    }
    setSaving(true);
    const fields = {
      topic_id: form.topic_id,
      prompt: form.prompt,
      is_active: form.is_active,
      options: form.options.map((text, index) => ({
        id: `option-${index + 1}`,
        text,
        correct: index === form.correct,
      })),
    };
    try {
      if (editing === "new") await aptitudeApi.create({ ...fields, level: form.level });
      else if (editing) await aptitudeApi.update(editing.id, fields);
      setEditing(null);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The question could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  if (!bank && !error)
    return (
      <div className="flex justify-center py-16 text-brand">
        <Spinner className="size-6" label="Loading question bank" />
      </div>
    );
  if (!bank) return <ErrorState message={error ?? "Could not load"} onRetry={() => void load()} />;
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink">Aptitude question bank</h1>
          <p className="mt-1 text-sm text-muted">
            One random active question from each level is used in onboarding.
          </p>
        </div>
        <Button onClick={() => open()}>
          <Plus className="size-4" /> New question
        </Button>
      </div>
      <Alert tone={bank.ready ? "success" : "error"}>
        {bank.ready
          ? "Quiz ready — every level has active questions."
          : "Quiz not ready — add an active question to every level."}
      </Alert>
      <div className="grid grid-cols-5 gap-2">
        {[1, 2, 3, 4, 5].map((level) => (
          <div key={level} className="rounded-lg border border-line bg-white p-3 text-center">
            <p className="text-xs text-muted">Level {level}</p>
            <p className="text-2xl font-bold text-ink">{bank.counts_by_level[level] ?? 0}</p>
            <p className="text-xs text-muted">active</p>
          </div>
        ))}
      </div>
      <div className="rounded-lg border border-line bg-white p-4">
        <h2 className="font-semibold text-ink">Active questions by topic</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(bank.counts_by_topic).map(([topic, count]) => (
            <span key={topic} className="rounded-full bg-surface px-3 py-1 text-xs text-muted">
              {topic}: {count}
            </span>
          ))}
        </div>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      {editing && (
        <section className="rounded-lg border border-brand/30 bg-white p-4">
          <h2 className="font-semibold text-ink">
            {editing === "new" ? "New question" : "Edit question"}
          </h2>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <label className="text-xs font-semibold">
              Topic
              <select
                className="mt-1 h-11 w-full rounded-sm border border-line px-3 text-sm"
                value={form.topic_id}
                onChange={(event) => setForm({ ...form, topic_id: event.target.value })}
              >
                <option value="">Choose topic</option>
                {topics.map((topic) => (
                  <option key={topic.id} value={topic.id}>
                    {topic.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-semibold">
              Level
              <select
                disabled={editing !== "new"}
                className="mt-1 h-11 w-full rounded-sm border border-line px-3 text-sm disabled:bg-surface"
                value={form.level}
                onChange={(event) => setForm({ ...form, level: Number(event.target.value) })}
              >
                {[1, 2, 3, 4, 5].map((level) => (
                  <option key={level}>{level}</option>
                ))}
              </select>
            </label>
          </div>
          <TextField
            className="mt-3"
            label="Question"
            value={form.prompt}
            onChange={(event) => setForm({ ...form, prompt: event.target.value })}
          />
          {form.options.map((option, index) => (
            <div key={index} className="mt-3 flex items-center gap-2">
              <input
                type="radio"
                name="correct"
                checked={form.correct === index}
                onChange={() => setForm({ ...form, correct: index })}
                aria-label={`Mark option ${index + 1} correct`}
              />
              <TextField
                className="flex-1"
                label={`Option ${index + 1}${form.correct === index ? " (correct)" : ""}`}
                value={option}
                onChange={(event) =>
                  setForm({
                    ...form,
                    options: form.options.map((value, i) =>
                      i === index ? event.target.value : value,
                    ),
                  })
                }
              />
            </div>
          ))}
          <label className="mt-3 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) => setForm({ ...form, is_active: event.target.checked })}
            />{" "}
            Active
          </label>
          <div className="mt-4 flex gap-2">
            <Button loading={saving} onClick={() => void save()}>
              Save question
            </Button>
            <Button variant="secondary" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </section>
      )}
      <div className="overflow-hidden rounded-lg border border-line bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs text-muted">
            <tr>
              <th className="p-3">Question</th>
              <th className="p-3">Topic</th>
              <th className="p-3">Level</th>
              <th className="p-3">Status</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {bank.questions.map((question) => (
              <tr key={question.id} className="border-t border-line">
                <td className="p-3 font-medium text-ink">{question.prompt}</td>
                <td className="p-3 text-muted">{question.topic_name}</td>
                <td className="p-3">Level {question.level}</td>
                <td className="p-3">{question.is_active ? "Active" : "Inactive"}</td>
                <td className="p-3">
                  <Button variant="ghost" onClick={() => open(question)}>
                    Edit
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
