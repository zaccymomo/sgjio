import { ApiError } from "@sgjio/ui";
import type { Asset } from "@sgjio/ui/lesson";
import { useState } from "react";

import { uploadMedia } from "./lessons";

/** What the editor's file pickers offer: what the API accepts (app/media.py). */
export const IMAGE_TYPES = "image/jpeg,image/png,image/webp";
export const AUDIO_TYPES =
  "audio/mpeg,audio/mp4,audio/x-m4a,audio/wav,audio/x-wav,audio/ogg,.mp3,.m4a,.wav,.ogg";

export function isImageFile(file: File) {
  return /^image\/(jpeg|png|webp)$/.test(file.type);
}

function uploadError(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "The file couldn't be uploaded. Check your connection and try again.";
}

/** Upload a file, tracking whether it is running and what went wrong. */
export function useUpload(onUploaded: (asset: Asset) => void) {
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function upload(file: File) {
    setUploading(file.name);
    setError(null);
    try {
      onUploaded(await uploadMedia(file));
    } catch (failure) {
      setError(uploadError(failure));
    } finally {
      setUploading(null);
    }
  }
  return { upload, uploading, error };
}
