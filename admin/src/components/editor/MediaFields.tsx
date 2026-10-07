import { cn, Spinner, TextField } from "@sgjio/ui";
import { AudioPlayer, CardImage, type Asset } from "@sgjio/ui/lesson";
import { ImagePlus, Mic, RefreshCw, Trash2, Upload, type LucideIcon } from "lucide-react";
import { useId, useRef, useState, type DragEvent, type ReactNode } from "react";

import { AUDIO_TYPES, IMAGE_TYPES, useUpload } from "../../lib/media";

/** An empty slot for a file: drop it here, or choose one. */
function DropZone({
  icon: Icon,
  title,
  hint,
  accept,
  onFile,
  uploading,
}: {
  icon: LucideIcon;
  title: string;
  hint: string;
  accept: string;
  onFile: (file: File) => void;
  uploading: string | null;
}) {
  const inputId = useId();
  const [over, setOver] = useState(false);

  function drop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  }

  return (
    <label
      htmlFor={inputId}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={cn(
        "flex min-h-32 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 text-center transition-colors",
        over ? "border-brand bg-brand-soft" : "border-line bg-surface hover:border-ink/30",
      )}
    >
      {uploading ? (
        <>
          <Spinner className="size-5 text-brand" label="Uploading" />
          <span className="max-w-full truncate text-xs text-muted">Uploading {uploading}…</span>
        </>
      ) : (
        <>
          <Icon className="size-6 text-subtle" aria-hidden />
          <span className="text-sm font-semibold text-ink">{title}</span>
          <span className="text-xs text-muted">{hint}</span>
        </>
      )}
      <input
        id={inputId}
        type="file"
        accept={accept}
        className="sr-only"
        disabled={uploading !== null}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
    </label>
  );
}

function FileButtons({
  accept,
  onFile,
  onRemove,
  uploading,
  kind,
}: {
  accept: string;
  onFile: (file: File) => void;
  onRemove: () => void;
  uploading: string | null;
  kind: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const button =
    "inline-flex h-8 items-center gap-1.5 rounded-sm px-2.5 text-xs font-semibold text-muted hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-brand disabled:opacity-50";
  return (
    <div className="flex gap-1">
      <button
        type="button"
        className={button}
        onClick={() => inputRef.current?.click()}
        disabled={uploading !== null}
      >
        {uploading ? (
          <Spinner className="size-3.5" />
        ) : (
          <RefreshCw className="size-3.5" aria-hidden />
        )}
        Replace
      </button>
      <button type="button" className={button} onClick={onRemove} aria-label={`Remove ${kind}`}>
        <Trash2 className="size-3.5" aria-hidden />
        Remove
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="sr-only"
        tabIndex={-1}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
    </div>
  );
}

function Problem({ children }: { children: ReactNode }) {
  return children ? <p className="text-xs text-danger">{children}</p> : null;
}

function Warning({ children }: { children: ReactNode }) {
  return children ? <p className="text-xs text-amber-700">{children}</p> : null;
}

/** A card's image: drop, paste (anywhere on the card) or choose one; then its description. */
export function ImageField({
  image,
  asset,
  onChange,
  issue,
}: {
  image: { asset_id: string; alt: string } | null;
  asset: Asset | undefined;
  onChange: (image: { asset_id: string; alt: string } | null, asset?: Asset) => void;
  issue?: { message: string; severity: "blocker" | "warning" };
}) {
  const { upload, uploading, error } = useUpload((uploaded) => {
    if (uploaded.kind !== "image") return;
    onChange({ asset_id: uploaded.id, alt: image?.alt ?? "" }, uploaded);
  });

  if (!image) {
    return (
      <div className="flex flex-col gap-1.5">
        <DropZone
          icon={ImagePlus}
          title="Add an image"
          hint="Drop, paste or choose · JPEG, PNG or WebP · 4:3 looks best"
          accept={IMAGE_TYPES}
          onFile={(file) => void upload(file)}
          uploading={uploading}
        />
        <Problem>{error}</Problem>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-line p-3">
      <div className="flex items-start gap-3">
        <div className="w-36 shrink-0 overflow-hidden rounded-md">
          <CardImage asset={asset} alt={image.alt} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="truncate text-xs font-semibold text-ink">{asset?.filename || "Image"}</p>
          {asset?.width && (
            <p className="text-xs text-muted">
              {asset.width} × {asset.height}
            </p>
          )}
          <FileButtons
            kind="image"
            accept={IMAGE_TYPES}
            uploading={uploading}
            onFile={(file) => void upload(file)}
            onRemove={() => onChange(null)}
          />
        </div>
      </div>
      <TextField
        label="Describe the image"
        value={image.alt}
        onChange={(event) => onChange({ ...image, alt: event.target.value })}
        maxLength={300}
        hint="For people who can't see it, e.g. “Two cups of kopi on a marble table”."
      />
      <Problem>{error}</Problem>
      {issue &&
        (issue.severity === "blocker" ? (
          <Problem>{issue.message}</Problem>
        ) : (
          <Warning>{issue.message}</Warning>
        ))}
    </div>
  );
}

/** A card's audio: drop or choose a file; then its transcript. */
export function AudioField({
  audio,
  asset,
  onChange,
  issue,
}: {
  audio: { asset_id: string; transcript: string } | null;
  asset: Asset | undefined;
  onChange: (audio: { asset_id: string; transcript: string } | null, asset?: Asset) => void;
  issue?: { message: string; severity: "blocker" | "warning" };
}) {
  const { upload, uploading, error } = useUpload((uploaded) => {
    if (uploaded.kind !== "audio") return;
    onChange({ asset_id: uploaded.id, transcript: audio?.transcript ?? "" }, uploaded);
  });

  if (!audio) {
    return (
      <div className="flex flex-col gap-1.5">
        <DropZone
          icon={Mic}
          title="Add audio"
          hint="Drop or choose · MP3, M4A, WAV or Ogg · under 20 seconds"
          accept={AUDIO_TYPES}
          onFile={(file) => void upload(file)}
          uploading={uploading}
        />
        <Problem>{error}</Problem>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <AudioPlayer asset={asset} transcript="" autoplay={false} size="pill" />
        </div>
        <FileButtons
          kind="audio"
          accept={AUDIO_TYPES}
          uploading={uploading}
          onFile={(file) => void upload(file)}
          onRemove={() => onChange(null)}
        />
      </div>
      <p className="truncate text-xs text-muted">
        <Upload className="mr-1 inline size-3" aria-hidden />
        {asset?.filename || "Audio"}
      </p>
      <TextField
        label="Transcript"
        value={audio.transcript}
        onChange={(event) => onChange({ ...audio, transcript: event.target.value })}
        maxLength={1000}
        hint="Exactly what is said, for people who can't listen."
      />
      <Problem>{error}</Problem>
      {issue &&
        (issue.severity === "blocker" ? (
          <Problem>{issue.message}</Problem>
        ) : (
          <Warning>{issue.message}</Warning>
        ))}
    </div>
  );
}
